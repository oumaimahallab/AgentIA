from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

with DAG(
    dag_id="unified_agent_ingestion",
    start_date=datetime(2026, 1, 1),
    schedule_interval=None,
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["unified-agent", "ingestion"],
) as dag:

    stage_documents = BashOperator(
        task_id="stage_documents",
        bash_command=(
            "python /opt/airflow/scripts/unified_ingest.py "
            "--stage --input-dir /opt/airflow/data/documents "
            "--stage-dir /opt/airflow/data/unified_stage"
        ),
    )

    verify_stage_file = BashOperator(
        task_id="verify_stage_file",
        bash_command=(
            "test -s /opt/airflow/data/unified_stage/staged_chunks.json"
        ),
    )

    index_documents = BashOperator(
        task_id="index_documents",
        bash_command=(
            "python /opt/airflow/scripts/unified_ingest.py "
            "--index --stage-dir /opt/airflow/data/unified_stage"
        ),
    )

    stage_documents >> verify_stage_file >> index_documents
