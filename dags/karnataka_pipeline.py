from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

def execute_pipeline():
    from src.pipeline import run_pipeline
    return run_pipeline()

with DAG(
    dag_id="karnataka_data_intelligence",
    start_date=datetime(2025, 1, 1),
    schedule="@weekly",
    catchup=False,
    default_args={"owner": "portfolio", "retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["karnataka", "open-data", "data-engineering"],
) as dag:
    ingest = PythonOperator(task_id="download_validate_and_load_snapshot", python_callable=execute_pipeline)
