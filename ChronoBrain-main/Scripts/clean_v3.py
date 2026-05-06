import re
import os
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

# ── CONFIG ────────────────────────────────────────────────────────────────────
INPUT_DIR  = "../data/transcripts"
OUTPUT_DIR = "../data/cleaned_txt_v3"
# We use this to detect if a sentence is actually meaningful or just noise/filler
MODEL_NAME = 'all-MiniLM-L6-v2' 

# Initialize embedding model to filter low-information text
model = SentenceTransformer(MODEL_NAME)

def is_meaningless(text: str) -> bool:
    """Uses semantic embedding to check if text is just noise/filler."""
    if len(text.split()) < 3: return True
    # If the embedding vector has a very low norm or is close to 'filler' phrases, drop it
    embedding = model.encode(text)
    norm = np.linalg.norm(embedding)
    return norm < 0.2  # Threshold: very low signal text is ignored

def clean_transcript(text: str) -> str:
    # 1. Remove [everything inside brackets]
    text = re.sub(r'\[.*?\]', '', text)
    
    # 2. Remove repetitive filler phrases (e.g., "euh", "ok", "donc")
    fillers = r'\b(euh+|ah+|hm+|ok|donc|alors|voilà|ben|bah|ouais|tout à fait)\b'
    text = re.sub(fillers, '', text, flags=re.IGNORECASE)
    
    # 3. Remove repeated words (e.g., "la la la" -> "la")
    text = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', text, flags=re.IGNORECASE)
    
    # 4. Final normalization
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def process_files():
    input_path = Path(INPUT_DIR)
    output_path = Path(OUTPUT_DIR)
    output_path.mkdir(parents=True, exist_ok=True)

    for file_path in input_path.glob("*.txt"):
        print(f"Cleaning: {file_path.name}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        cleaned_lines = []
        for line in lines:
            txt = clean_transcript(line)
            # Use the AI model to verify if the line is meaningful
            if txt and not is_meaningless(txt):
                cleaned_lines.append(txt)
        
        # Save the result
        with open(output_path / file_path.name, 'w', encoding='utf-8') as f:
            f.write("\n".join(cleaned_lines))

if __name__ == "__main__":
    process_files()
    print("Done! Data is ready for RAG ingestion.")