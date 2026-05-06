from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import os

sys.path.append('/opt/airflow/scripts')
from transcribe import transcribe_one_video
from notifications import send_summary_notification

def get_videos_as_dict():
    video_dir = "/opt/airflow/data/raw_videos"
    videos = [f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.mkv', '.mov'))]
    return [{"video_filename": v} for v in videos]

with DAG(
    dag_id="video_to_text_parallel",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
    max_active_tasks=2 # Protect your 16GB RAM
) as dag:

    # 1. Get List
    get_list_task = PythonOperator(
        task_id="get_video_list",
        python_callable=get_videos_as_dict
    )

    # 2. Transcribe (Mapped)
    transcribe_task = PythonOperator.partial(
        task_id="transcribe_video",
        python_callable=transcribe_one_video,
    ).expand(
        op_kwargs=get_list_task.output
    )

    # 3. Summary Report
    # 'all_done' ensures this runs even if some workers fail
    report_task = PythonOperator(
        task_id="send_final_report",
        python_callable=send_summary_notification,
        op_args=[transcribe_task.output], 
        trigger_rule="all_done" 
    )

    get_list_task >> transcribe_task >> report_task