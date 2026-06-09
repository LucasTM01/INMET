"""CLI do ETL INMET.

Exemplos:
    uv run python run.py full                     # histórico completo (2000 -> atual)
    uv run python run.py full --start 2023        # subconjunto recente
    uv run python run.py full --skip-existing     # retoma, pula anos já gravados
    uv run python run.py update                   # só o ano corrente (mensal)
"""
import argparse

from inmet import config, pipeline


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

    args = parser.parse_args()
    if args.command == "full":
        pipeline.run_full(start=args.start, force=args.force,
                          skip_existing=args.skip_existing)
    elif args.command == "update":
        pipeline.run_current_year()


if __name__ == "__main__":
    main()
