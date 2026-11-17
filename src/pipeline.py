import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

from config.settings import DATA_SOURCE_URL, RAW_DIR, WAREHOUSE_PATH, MAX_DOWNLOAD_MB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kdi")

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def download_snapshot(url: str = DATA_SOURCE_URL) -> tuple[Path, str]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=(20, 180), stream=True, headers={"User-Agent": "KarnatakaDataIntelligencePortfolio/1.0"})
    response.raise_for_status()
    content_length = int(response.headers.get("Content-Length", "0"))
    if content_length and content_length > MAX_DOWNLOAD_MB * 1024 * 1024:
        raise ValueError(f"Source is larger than configured limit ({MAX_DOWNLOAD_MB} MB).")
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=1024 * 1024):
        if chunk:
            total += len(chunk)
            if total > MAX_DOWNLOAD_MB * 1024 * 1024:
                raise ValueError(f"Download exceeded configured limit ({MAX_DOWNLOAD_MB} MB).")
            chunks.append(chunk)
    payload = b"".join(chunks)
    if not payload:
        raise ValueError("Downloaded source is empty.")
    digest = sha256(payload)
    snapshot = RAW_DIR / f"taluk_{digest}.parquet"
    if not snapshot.exists():
        snapshot.write_bytes(payload)
    return snapshot, digest

def json_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value

def initialize_warehouse(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id VARCHAR PRIMARY KEY,
            source_url VARCHAR,
            snapshot_hash VARCHAR,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            row_count BIGINT,
            status VARCHAR,
            error_message VARCHAR
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_hash VARCHAR PRIMARY KEY,
            source_url VARCHAR,
            raw_path VARCHAR,
            downloaded_at TIMESTAMP,
            row_count BIGINT
        );
        CREATE TABLE IF NOT EXISTS current_features (
            feature_key VARCHAR PRIMARY KEY,
            record_hash VARCHAR NOT NULL,
            attributes JSON NOT NULL,
            snapshot_hash VARCHAR NOT NULL,
            first_seen_at TIMESTAMP NOT NULL,
            last_seen_at TIMESTAMP NOT NULL
        );
        CREATE TABLE IF NOT EXISTS feature_observations (
            feature_key VARCHAR,
            snapshot_hash VARCHAR,
            record_hash VARCHAR,
            observed_at TIMESTAMP,
            PRIMARY KEY(feature_key, snapshot_hash)
        );
        CREATE TABLE IF NOT EXISTS quarantine_records (
            quarantine_id VARCHAR PRIMARY KEY,
            snapshot_hash VARCHAR,
            payload JSON,
            reason VARCHAR,
            quarantined_at TIMESTAMP
        );
    """)

def run_pipeline(source_url: str = DATA_SOURCE_URL):
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    run_id = hashlib.sha256(f"{source_url}|{started.isoformat()}".encode()).hexdigest()[:20]
    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE_PATH))
    initialize_warehouse(con)
    try:
        raw_path, digest = download_snapshot(source_url)
        frame = con.execute("SELECT * FROM read_parquet(?)", [str(raw_path)]).fetchdf()
        if frame.empty:
            raise ValueError("Source Parquet contains no rows.")
        columns = list(frame.columns)
        log.info("Read %s rows and %s columns: %s", len(frame), len(columns), columns)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        con.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [digest, source_url, str(raw_path), now, len(frame)],
        )
        con.execute(
            """INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, NULL, ?, 'running', NULL)
               ON CONFLICT(run_id) DO NOTHING""",
            [run_id, source_url, digest, started, len(frame)],
        )

        for row in frame.to_dict(orient="records"):
            safe = {str(k): json_value(v) for k, v in row.items()}
            canonical = json.dumps(safe, sort_keys=True, separators=(",", ":"), default=str)
            record_hash = sha256(canonical.encode())
            # Snapshot records have no assumed business key; stable content hash is used as a safe key.
            feature_key = record_hash
            payload = json.dumps(safe, default=str)
            con.execute(
                """INSERT INTO current_features VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(feature_key) DO UPDATE SET
                     record_hash=excluded.record_hash,
                     attributes=excluded.attributes,
                     snapshot_hash=excluded.snapshot_hash,
                     last_seen_at=excluded.last_seen_at""",
                [feature_key, record_hash, payload, digest, now, now],
            )
            con.execute(
                """INSERT INTO feature_observations VALUES (?, ?, ?, ?)
                   ON CONFLICT(feature_key, snapshot_hash) DO NOTHING""",
                [feature_key, digest, record_hash, now],
            )

        con.execute(
            "UPDATE pipeline_runs SET completed_at=?, status='success' WHERE run_id=?",
            [now, run_id],
        )
        log.info("Pipeline succeeded. Snapshot=%s rows=%s raw=%s", digest, len(frame), raw_path)
        return {"snapshot_hash": digest, "rows": len(frame), "columns": columns, "raw_path": str(raw_path)}
    except Exception as exc:
        con.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, NULL, ?, ?, 0, 'failed', ?) ON CONFLICT(run_id) DO NOTHING",
            [run_id, source_url, started, datetime.now(timezone.utc).replace(tzinfo=None), str(exc)[:2000]],
        )
        raise
    finally:
        con.close()

if __name__ == "__main__":
    print(run_pipeline())
