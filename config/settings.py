import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_SOURCE_URL = os.getenv(
    "DATA_SOURCE_URL",
    "https://data.source.coop/krishnaglodha/ksrsac-gis/main/Taluk.parquet",
)
DATA_DIR = ROOT / os.getenv("DATA_DIR", "data")
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE_PATH = ROOT / os.getenv("WAREHOUSE_PATH", "data/warehouse.duckdb")
MAX_DOWNLOAD_MB = int(os.getenv("MAX_DOWNLOAD_MB", "250"))
