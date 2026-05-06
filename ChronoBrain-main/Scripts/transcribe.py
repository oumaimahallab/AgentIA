import os
import time
from faster_whisper import WhisperModel

VIDEO_DIR = "/opt/airflow/data/raw_videos"
OUTPUT_DIR = "/opt/airflow/data/transcripts"

def format_time(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

def transcribe_one_video(video_filename):
    input_path = os.path.join(VIDEO_DIR, video_filename)
    output_filename = video_filename.rsplit('.', 1)[0] + ".txt"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    tmp_path = os.path.join(OUTPUT_DIR, output_filename + ".tmp")

    # If the final .txt exists and has data, skip it!
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return f"✅ (Already Exists) {video_filename}"

    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(input_path, beam_size=5, language="fr")

        # Write to a temporary file first
        with open(tmp_path, "w", encoding="utf-8") as f:
            for segment in segments:
                line = f"[{format_time(segment.start)} -> {format_time(segment.end)}] {segment.text.strip()}\n"
                f.write(line)

        # If transcription finishes successfully, rename .tmp to .txt
        os.replace(tmp_path, output_path)
        
        return f"✅ (New) {video_filename}"

    except Exception as e:
        # If it crashes, the .txt is never created. We remove the temp file to keep it clean.
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return f"❌ (Error) {video_filename}: {str(e)}"