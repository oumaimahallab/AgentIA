FROM apache/airflow:2.7.1-python3.10

USER root
# Install system dependencies needed for faster-whisper and tokenizers
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    gcc \
    && apt-get clean

USER airflow

# Upgrade pip and setuptools
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .

# Install requirements
RUN pip install --no-cache-dir -r requirements.txt

# Install unified-agent ingestion dependencies
RUN pip install --no-cache-dir python-dotenv PyPDF2 python-pptx Pillow