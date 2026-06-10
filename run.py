"""CLI do ETL INMET.

Exemplos:
    uv run python run.py full                     # histórico completo (2000 -> atual)
    uv run python run.py full --start 2023        # subconjunto recente
    uv run python run.py full --skip-existing     # retoma, pula anos já gravados
    uv run python run.py update                   # só o ano corrente (mensal)
    uv run python run.py mines                     # tracking por mina (proxy INMET via IDW)
    uv run python run.py oni                       # baixa índice ENSO/ONI do NOAA
    uv run python run.py oni --csv                 # idem + exporta oni_monthly.csv
"""
import argparse

from inmet import config, mining, oni, pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL histórico INMET -> SQLite")
    sub = parser.add_subparsers(dest="command", required=True)

    p_full = sub.add_parser("full", help="roda todo o histórico")
    p_full.add_argument("--start", type=int, default=config.START_YEAR,
                        help=f"ano inicial (padrão {config.START_YEAR})")
    p_full.add_argument("--force", action="store_true",
                        help="re-baixa os zips mesmo se já estiverem em cache")
    p_full.add_argument("--skip-existing", action="store_true",
                        help="pula anos que já existem na DB")

    sub.add_parser("update", help="atualiza apenas o ano corrente")

    p_mines = sub.add_parser("mines", help="tracking por mina (proxy INMET via IDW)")
    p_mines.add_argument("--xlsx", default=str(config.MINES_XLSX),
                         help="planilha com a aba de minas")
    p_mines.add_argument("--sheet", default=config.MINES_SHEET, help="aba das minas")
    p_mines.add_argument("--k", type=int, default=config.K_NEAREST,
                         help=f"estações combinadas por IDW (padrão {config.K_NEAREST})")

    p_oni = sub.add_parser("oni", help="baixa índice ENSO/ONI do NOAA e grava em oni_monthly")
    p_oni.add_argument("--csv", action="store_true",
                       help=f"exporta também {config.ONI_CSV}")

    args = parser.parse_args()
    if args.command == "full":
        pipeline.run_full(start=args.start, force=args.force,
                          skip_existing=args.skip_existing)
    elif args.command == "update":
        pipeline.run_current_year()
    elif args.command == "mines":
        mining.run(xlsx_path=args.xlsx, sheet=args.sheet, k=args.k)
    elif args.command == "oni":
        oni.run(csv_path=args.csv)


if __name__ == "__main__":
    main()
