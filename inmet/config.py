"""Constantes e caminhos do pipeline INMET."""
from pathlib import Path

# Diretórios (relativos à raiz do projeto INMEET)
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "cache"
DB_PATH = BASE_DIR / "inmet.db"

# Fonte de dados
URL_TEMPLATE = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{year}.zip"
START_YEAR = 2000

# Valor sentinela de dado faltante no INMET
MISSING = -9999

# Cidade excluída (estação na Antártica, sem relevância regional)
EXCLUDE_CITIES = {"CRIOSFERA"}

# Layout do CSV de estação: as 8 primeiras linhas são metadados da estação;
# a 9ª linha (skiprows=8) é o cabeçalho das colunas horárias.
CSV_SKIPROWS = 8
CSV_SEP = ";"
CSV_ENCODING = "latin1"
CSV_DECIMAL = ","

# Padrões (substring, maiúsculas) para localizar colunas mesmo quando o INMET
# muda os nomes/acentos entre os anos. Mais robusto que uma drop-list fixa.
COL_RAINFALL = "PRECIPITA"          # ex.: "PRECIPITAÇÃO TOTAL, HORÁRIO (mm)"
COL_AIR_TEMP = "TEMPERATURA DO AR"  # ex.: "TEMPERATURA DO AR - BULBO SECO, HORARIA (°C)"
COL_DATE = "DATA"                   # ex.: "DATA (YYYY-MM-DD)" ou "Data"

# Rótulos dos metadados no cabeçalho (sem acento, em maiúsculas, para casar tolerante)
META_LABELS = {
    "region": "REGIAO",
    "state": "UF",
    "station": "CODIGO",
    "city": "ESTACAO",
    "latitude": "LATITUDE",
    "longitude": "LONGITUDE",
    "altitude": "ALTITUDE",
}
