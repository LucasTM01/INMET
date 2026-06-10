"""Tracking por mina: casa cada mina às estações INMET mais próximas (por ano)
e gera uma série diária de temperatura e chuva via IDW (inverse-distance weighting).

Saídas no mesmo ``inmet.db``:
  - ``mine_station_map``: mina × ano × estação (rank 1..k) com distância, peso e cobertura.
  - ``mine_daily``: série diária por mina (chuva e temperatura combinadas) — fato p/ Power BI.
E um CSV achatado em ``output/mine_daily.csv``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, db

EARTH_RADIUS_KM = 6371.0


def parse_coordinates(value: str) -> tuple[float | None, float | None]:
    """`"-5.80..., -50.53..."` → (lat, lon). Retorna (None, None) se inválido."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    parts = str(value).split(",")
    if len(parts) < 2:
        return None, None
    try:
        return float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return None, None


def load_mines(xlsx_path=config.MINES_XLSX, sheet: str = config.MINES_SHEET) -> pd.DataFrame:
    """Lê a aba de minas e normaliza colunas + coordenadas."""
    raw = pd.read_excel(xlsx_path, sheet_name=sheet)
    df = pd.DataFrame({
        "company": raw.get("Company"),
        "asset_name": raw["Asset name (English)"],
        "ore": raw.get("Ore"),
        "subnational_unit": raw.get("Subnational unit"),
    })
    coords = raw["Coordinates"].map(parse_coordinates)
    df["mine_lat"] = [c[0] for c in coords]
    df["mine_lon"] = [c[1] for c in coords]
    df = df.dropna(subset=["mine_lat", "mine_lon"]).reset_index(drop=True)
    return df


def haversine(lat1, lon1, lat2, lon2):
    """Distância em km entre pontos (vetorizado). lat2/lon2 podem ser arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def station_year_index(conn) -> pd.DataFrame:
    """[year, station, lat, lon, state, city, n_days] — estações com dados por ano."""
    counts = pd.read_sql_query(
        "SELECT year, station, COUNT(*) AS n_days "
        "FROM weather_daily GROUP BY year, station",
        conn,
    )
    stations = pd.read_sql_query(
        "SELECT station, state, city, latitude AS lat, longitude AS lon FROM stations",
        conn,
    )
    idx = counts.merge(stations, on="station", how="inner")
    return idx.dropna(subset=["lat", "lon"])


def select_proxies(mines: pd.DataFrame, station_idx: pd.DataFrame,
                   k: int = config.K_NEAREST,
                   min_days: int = config.MIN_DAYS_PER_YEAR) -> pd.DataFrame:
    """Para cada (mina, ano), escolhe as k estações mais próximas com cobertura e calcula pesos IDW.

    Filtra estações com ``n_days >= min_days``; se menos de k qualificarem naquele ano,
    cai de volta para as k mais próximas independentemente da cobertura (fallback).
    """
    years = sorted(station_idx["year"].unique())
    rows = []
    for _, mine in mines.iterrows():
        for year in years:
            pool = station_idx[station_idx["year"] == year]
            if pool.empty:
                continue
            qualified = pool[pool["n_days"] >= min_days]
            chosen = qualified if len(qualified) >= k else pool
            dist = haversine(mine["mine_lat"], mine["mine_lon"],
                             chosen["lat"].to_numpy(), chosen["lon"].to_numpy())
            chosen = chosen.assign(dist_km=dist).nsmallest(k, "dist_km")

            inv = 1.0 / chosen["dist_km"].clip(lower=1e-6)
            weights = inv / inv.sum()
            for rank, ((_, st), w) in enumerate(zip(chosen.iterrows(), weights), start=1):
                rows.append({
                    "company": mine["company"], "asset_name": mine["asset_name"],
                    "ore": mine["ore"], "subnational_unit": mine["subnational_unit"],
                    "mine_lat": mine["mine_lat"], "mine_lon": mine["mine_lon"],
                    "year": int(year), "rank": rank,
                    "station": st["station"], "station_city": st["city"],
                    "station_state": st["state"], "station_lat": st["lat"],
                    "station_lon": st["lon"], "dist_km": round(float(st["dist_km"]), 2),
                    "weight": round(float(w), 6), "n_days": int(st["n_days"]),
                })
    return pd.DataFrame(rows)


def build_mine_daily(conn, map_df: pd.DataFrame) -> pd.DataFrame:
    """Combina as estações-proxy de cada mina por IDW diário (renormalizado por dia)."""
    # Puxa de uma vez só o weather_daily das estações efetivamente usadas.
    used = sorted(map_df["station"].unique())
    placeholders = ",".join("?" * len(used))
    daily = pd.read_sql_query(
        f"SELECT year, station, date, rainfall_mm, temperature_c "
        f"FROM weather_daily WHERE station IN ({placeholders})",
        conn, params=used,
    )

    results = []
    keys = ["company", "asset_name", "ore", "subnational_unit", "mine_lat", "mine_lon"]
    for mine_id, grp in map_df.groupby("asset_name"):
        meta = grp.iloc[0]
        # junta o map (station, year, weight) com as séries diárias
        merged = grp[["year", "station", "weight"]].merge(
            daily, on=["year", "station"], how="inner"
        )
        if merged.empty:
            continue
        merged["w_temp"] = merged["weight"] * merged["temperature_c"]
        merged["w_rain"] = merged["weight"] * merged["rainfall_mm"]
        # pesos válidos só onde há valor naquele dia (renormalização por dia)
        merged["w_t_valid"] = merged["weight"].where(merged["temperature_c"].notna())
        merged["w_r_valid"] = merged["weight"].where(merged["rainfall_mm"].notna())

        agg = merged.groupby("date").agg(
            wt=("w_temp", "sum"), wr=("w_rain", "sum"),
            sw_t=("w_t_valid", "sum"), sw_r=("w_r_valid", "sum"),
            n_stations_used=("station", "nunique"),
        ).reset_index()

        agg["temperature_c"] = np.where(agg["sw_t"] > 0, agg["wt"] / agg["sw_t"], np.nan)
        agg["rainfall_mm"] = np.where(agg["sw_r"] > 0, agg["wr"] / agg["sw_r"], np.nan)
        agg = agg[(agg["sw_t"] > 0) | (agg["sw_r"] > 0)]

        out = pd.DataFrame({"date": agg["date"]})
        for kcol in keys:
            out[kcol] = meta[kcol]
        dt = pd.to_datetime(agg["date"])
        out["year"] = dt.dt.year.to_numpy()
        out["month"] = dt.dt.month.to_numpy()
        out["day"] = dt.dt.day.to_numpy()
        out["rainfall_mm"] = agg["rainfall_mm"].round(2).to_numpy()
        out["temperature_c"] = agg["temperature_c"].round(2).to_numpy()
        out["n_stations_used"] = agg["n_stations_used"].to_numpy()
        results.append(out)

    daily_df = pd.concat(results, ignore_index=True)
    return daily_df.sort_values(["asset_name", "date"]).reset_index(drop=True)


def write_outputs(conn, map_df: pd.DataFrame, daily_df: pd.DataFrame,
                  csv_path=config.MINE_CSV) -> None:
    map_df.to_sql("mine_station_map", conn, if_exists="replace", index=False)
    daily_df.to_sql("mine_daily", conn, if_exists="replace", index=False)
    conn.commit()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    daily_df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def run(xlsx_path=config.MINES_XLSX, sheet: str = config.MINES_SHEET,
        k: int = config.K_NEAREST) -> None:
    conn = db.get_conn()
    try:
        mines = load_mines(xlsx_path, sheet)
        print(f"Minas carregadas: {len(mines)}")
        idx = station_year_index(conn)
        print(f"Índice estação-ano: {len(idx)} linhas, "
              f"{idx['station'].nunique()} estações, anos {idx['year'].min()}–{idx['year'].max()}")
        map_df = select_proxies(mines, idx, k=k)
        daily_df = build_mine_daily(conn, map_df)
        write_outputs(conn, map_df, daily_df)
        print(f"OK — mine_station_map: {len(map_df)} linhas | "
              f"mine_daily: {len(daily_df)} linhas | CSV: {config.MINE_CSV}")
    finally:
        conn.close()
