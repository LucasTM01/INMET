"""Download e parsing do Oceanic Niño Index (ONI) do NOAA/CPC.

Gera a tabela ``oni_monthly`` no mesmo ``inmet.db``:
  year, month (mês central da janela de 3 meses), season, oni_anom, enso_phase.

Fases (thresholds do usuário):
  oni_anom >  1.5  → "Strong El Niño"
  oni_anom >  0.5  → "El Niño"
  oni_anom < -1.5  → "Strong La Niña"
  oni_anom < -0.5  → "La Niña"
  caso contrário   → "Neutro"
"""
from __future__ import annotations

import warnings

import pandas as pd
import requests

from . import config, db

# Mês central de cada janela de 3 meses do ONI
_SEASON_TO_MONTH: dict[str, int] = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4,
    "AMJ": 5, "MJJ": 6, "JJA": 7, "JAS": 8,
    "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}

_MISSING = 99.9  # valor sentinela do NOAA para dados faltantes


def _classify(anom: float | None) -> str:
    if anom is None or pd.isna(anom):
        return "Neutro"
    if anom > 1.5:
        return "Strong El Niño"
    if anom > 0.5:
        return "El Niño"
    if anom < -1.5:
        return "Strong La Niña"
    if anom < -0.5:
        return "La Niña"
    return "Neutro"


def download_oni(url: str = config.ONI_URL) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        resp = requests.get(url, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_oni(text: str) -> pd.DataFrame:
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        seas, yr, anom_str = parts[0], parts[1], parts[2]
        if seas not in _SEASON_TO_MONTH:
            continue
        # format: SEAS YR TOTAL ANOM  (4 cols) — take last column as anomaly
        anom_str = parts[-1]
        try:
            year = int(yr)
            anom = float(anom_str)
        except ValueError:
            continue
        if abs(anom - _MISSING) < 0.01:
            anom = None
        rows.append({
            "year": year,
            "month": _SEASON_TO_MONTH[seas],
            "season": seas,
            "oni_anom": anom,
            "enso_phase": _classify(anom),
        })
    df = pd.DataFrame(rows)
    return df.sort_values(["year", "month"]).reset_index(drop=True)


def run(csv_path=None) -> None:
    print(f"Baixando ONI de {config.ONI_URL} ...")
    text = download_oni()
    df = parse_oni(text)
    print(f"Parsed: {len(df)} linhas, anos {df['year'].min()}–{df['year'].max()}")

    conn = db.get_conn()
    try:
        db.init_db(conn)
        n = db.upsert_oni(conn, df)
        conn.commit()
        print(f"oni_monthly: {n} linhas gravadas.")
    finally:
        conn.close()

    if csv_path:
        csv_path = config.OUTPUT_DIR / "oni_monthly.csv" if csv_path is True else csv_path
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"CSV: {csv_path}")

    phases = df["enso_phase"].value_counts().to_dict()
    print("Distribuição de fases:", phases)
