import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Models
CLEANING_MODEL = "llama-3.1-8b-instant"
STRUCTURING_MODEL = "mixtral-8x7b-32768"

# Chunking
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

# Paths
RAW_DATA_PATH = "../data/1_file"
CLEAN_DATA_PATH = "data/cleaned_groq/"
CHUNK_PATH = "data/chunks/"