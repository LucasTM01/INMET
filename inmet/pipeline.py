"""Orquestração: processa anos (batches) e grava no SQLite."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from . import config, db, download, parse


def process_year(conn, year: int, force_download: bool = False) -> int:
    """Baixa, agrega e grava um ano. Idempotente: apaga o ano e re-insere.

    Agrega cada CSV de estação para mensal individualmente e só então concatena
    (memória baixa). Toda a escrita do ano ocorre numa única transação.
    """
    zip_path = download.download_year(year, force=force_download)

    daily_frames: list[pd.DataFrame] = []
    station_records: list[dict] = []
    n_files = 0
    for filename, raw in parse.iter_station_csvs(zip_path):
        n_files += 1
        meta = parse.parse_station_metadata(raw, filename)
        if meta:
            station_records.append(meta)
        frame = parse.parse_station_daily(filename, raw)
        if frame is not None and not frame.empty:
            daily_frames.append(frame)

    if not daily_frames:
        print(f"[{year}] nenhum dado utilizável em {n_files} arquivos — pulando.")
        return 0

    daily_df = pd.concat(daily_frames, ignore_index=True)
    monthly_df = parse.daily_to_monthly(daily_df)

    try:
        conn.execute("BEGIN;")
        del_m, del_d = db.delete_year(conn, year)
        ins_d = db.upsert_daily(conn, daily_df)
        ins_m = db.upsert_monthly(conn, monthly_df)
        db.upsert_stations(conn, station_records)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print(f"[{year}] OK — {n_files} arquivos | diário: {ins_d} ins ({del_d} del) | "
          f"mensal: {ins_m} ins ({del_m} del) | {len(station_records)} estações.")
    return ins_m


def run_full(start: int = config.START_YEAR, force: bool = False,
             skip_existing: bool = False) -> None:
    """Roda todo o histórico de ``start`` até o ano atual."""
    current = datetime.today().year
    conn = db.get_conn()
    db.init_db(conn)
    try:
        for year in range(start, current + 1):
            if skip_existing and not force and db.year_exists(conn, year):
                print(f"[{year}] já existe na DB — pulando (--skip-existing).")
                continue
            try:
                process_year(conn, year, force_download=force)
            except Exception as e:
                print(f"[{year}] ERRO: {e} — seguindo para o próximo ano.")
    finally:
        conn.close()
    print("### FULL concluído ###")


def run_current_year() -> None:
    """Modo mensal: re-baixa o ano corrente, apaga e re-insere seus dados."""
    current = datetime.today().year
    conn = db.get_conn()
    db.init_db(conn)
    try:
        process_year(conn, current, force_download=True)
    finally:
        conn.close()
    print(f"### UPDATE {current} concluído ###")
