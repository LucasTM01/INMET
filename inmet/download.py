"""Download dos zips anuais do INMET, com cache em disco."""
from pathlib import Path

import requests
import urllib3

from . import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def cache_path(year: int) -> Path:
    return config.CACHE_DIR / f"{year}.zip"


def download_year(year: int, force: bool = False, retries: int = 2) -> Path:
    """Baixa o zip do ano para o cache e retorna o caminho.

    Reusa o arquivo em cache se já existir, a menos que ``force=True`` (usado no
    modo update, que sempre re-baixa o ano corrente). O portal do INMET tem
    problemas de certificado SSL, então usamos ``verify=False``.
    """
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = cache_path(year)

    if dest.exists() and not force:
        print(f"[{year}] usando cache: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest

    url = config.URL_TEMPLATE.format(year=year)
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"[{year}] baixando {url} (tentativa {attempt}/{retries})...")
            resp = requests.get(url, verify=False, timeout=600)
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                print(f"[{year}] salvo: {dest.name} ({len(resp.content) / 1e6:.1f} MB)")
                return dest
            last_err = RuntimeError(f"HTTP {resp.status_code}")
            print(f"[{year}] falha HTTP {resp.status_code}")
        except Exception as e:  # rede, timeout, etc.
            last_err = e
            print(f"[{year}] erro no download: {e}")

    raise RuntimeError(f"Não foi possível baixar {year}: {last_err}")
