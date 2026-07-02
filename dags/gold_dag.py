"""DAG Airflow — recalcul annuel couche Gold (incrémental)."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

DAGS_DIR = "/opt/airflow/dags"


def _run_build_gold(**_):
    env = os.environ.copy()
    env["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://mongo:27017")
    env["MONGO_DB"] = os.getenv("MONGO_DB", "belgique")
    env["HDFS_URL"] = os.getenv("HDFS_URL", "http://namenode:9870")
    env["HDFS_USER"] = os.getenv("HDFS_USER", "airflow")
    subprocess.run(
        [sys.executable, f"{DAGS_DIR}/build_gold.py"],
        check=True,
        env=env,
        cwd=DAGS_DIR,
    )


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="gold_recalculation",
    default_args=default_args,
    description="Recalcul incrémental couche Gold hotel_gold",
    schedule_interval="@yearly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["gold", "hotel"],
) as dag:

    build_gold_task = PythonOperator(
        task_id="build_gold",
        python_callable=_run_build_gold,
    )

    build_gold_task
