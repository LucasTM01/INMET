"""Leitura dos CSVs de estação (direto do zip) e agregação para painel mensal."""
from __future__ import annotations

import io
import unicodedata
import zipfile
from typing import Iterator

import pandas as pd

from . import config


def _norm(text: str) -> str:
    """Maiúsculas + remoção de acentos, para casar nomes de coluna/rótulos."""
    nfkd = unicodedata.normalize("NFKD", str(text))
    no_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accent.upper().strip()


def _find_col(columns, pattern: str) -> str | None:
    """Primeira coluna cujo nome normalizado contém o padrão (já normalizado)."""
    pat = _norm(pattern)
    for col in columns:
        if pat in _norm(col):
            return col
    return None


def iter_station_csvs(zip_path) -> Iterator[tuple[str, bytes]]:
    """Itera os membros .csv do zip lendo em memória (sem extrair para disco).

    Funciona para os dois layouts do INMET: CSVs na raiz (anos < 2020) ou dentro
    de subpasta do ano (>= 2020), pois apenas filtra membros terminados em .csv.
    """
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if info.filename.lower().endswith(".csv"):
                yield info.filename, z.read(info.filename)


def _parse_float(raw: str) -> float | None:
    if raw is None:
        return None
    txt = str(raw).strip().replace(config.CSV_DECIMAL, ".")
    if not txt:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def parse_station_metadata(raw_bytes: bytes, filename: str) -> dict | None:
    """Lê as 8 linhas de cabeçalho → dict de metadados da estação."""
    head = raw_bytes[:4096].decode(config.CSV_ENCODING, errors="replace")
    lines = head.splitlines()[: config.CSV_SKIPROWS]
    fields: dict[str, str] = {}
    for line in lines:
        if config.CSV_SEP not in line:
            continue
        label, _, value = line.partition(config.CSV_SEP)
        fields[_norm(label)] = value.strip()

    def grab(target: str) -> str | None:
        tgt = _norm(target)
        for label, value in fields.items():
            if tgt in label:
                return value
        return None

    station = grab(config.META_LABELS["station"])
    if not station:
        # fallback: código vem do nome do arquivo
        parts = filename.split("/")[-1].split("_")
        station = parts[3] if len(parts) > 3 else None
    if not station:
        return None

    return {
        "station": station,
        "region": grab(config.META_LABELS["region"]),
        "state": grab(config.META_LABELS["state"]),
        "city": grab(config.META_LABELS["city"]),
        "latitude": _parse_float(grab(config.META_LABELS["latitude"])),
        "longitude": _parse_float(grab(config.META_LABELS["longitude"])),
        "altitude": _parse_float(grab(config.META_LABELS["altitude"])),
    }


def _names_from_filename(filename: str) -> tuple[str, str, str, str]:
    """Region/State/Station/City a partir do nome do arquivo INMET_<R>_<UF>_<COD>_<CIDADE>_..."""
    base = filename.split("/")[-1]
    parts = base.split("_")
    region = parts[1] if len(parts) > 1 else ""
    state = parts[2] if len(parts) > 2 else ""
    station = parts[3] if len(parts) > 3 else ""
    city = parts[4] if len(parts) > 4 else ""
    return region, state, station, city


def parse_station_daily(filename: str, raw_bytes: bytes) -> pd.DataFrame | None:
    """Lê um CSV de estação e devolve já agregado em diário.

    Colunas de saída: region, state, station, city, year, month, day, date,
    rainfall_mm (soma do dia), temperature_c (média do dia). Retorna None se
    inutilizável. O mensal é derivado deste diário (ver ``daily_to_monthly``),
    garantindo que as duas tabelas batam exatamente.
    """
    try:
        df = pd.read_csv(
            io.BytesIO(raw_bytes),
            skiprows=config.CSV_SKIPROWS,
            sep=config.CSV_SEP,
            encoding=config.CSV_ENCODING,
            decimal=config.CSV_DECIMAL,
        )
    except Exception as e:
        print(f"  ! erro lendo {filename}: {e}")
        return None

    if df.empty:
        return None

    rain_col = _find_col(df.columns, config.COL_RAINFALL)
    temp_col = _find_col(df.columns, config.COL_AIR_TEMP)
    date_col = _find_col(df.columns, config.COL_DATE)
    if date_col is None or (rain_col is None and temp_col is None):
        return None

    region, state, station, city = _names_from_filename(filename)
    if _norm(city) in {_norm(c) for c in config.EXCLUDE_CITIES}:
        return None

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce")
    out["rainfall_mm"] = (
        pd.to_numeric(df[rain_col], errors="coerce") if rain_col else pd.NA
    )
    out["temperature_c"] = (
        pd.to_numeric(df[temp_col], errors="coerce") if temp_col else pd.NA
    )

    # Sentinela de faltante -> NaN
    out = out.replace(config.MISSING, pd.NA)
    out = out.dropna(subset=["date"])
    if out.empty:
        return None

    out["day_ts"] = out["date"].dt.normalize()
    grouped = (
        out.groupby("day_ts", as_index=False)
        .agg(rainfall_mm=("rainfall_mm", "sum"), temperature_c=("temperature_c", "mean"))
    )
    if grouped.empty:
        return None

    ts = grouped.pop("day_ts").dt
    grouped["year"] = ts.year
    grouped["month"] = ts.month
    grouped["day"] = ts.day
    grouped["date"] = ts.strftime("%Y-%m-%d")

    grouped.insert(0, "city", city)
    grouped.insert(0, "station", station)
    grouped.insert(0, "state", state)
    grouped.insert(0, "region", region)
    return grouped


def daily_to_monthly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Deriva o painel mensal a partir do diário (chuva=soma, temperatura=média).

    Mantém a equivalência exata com ``weather_daily``: agregar o diário no Power
    BI (SUM/AVERAGE) reproduz estas mesmas linhas.
    """
    return (
        daily_df.groupby(
            ["region", "state", "station", "city", "year", "month"], as_index=False
        )
        .agg(rainfall_mm=("rainfall_mm", "sum"), temperature_c=("temperature_c", "mean"))
    )
