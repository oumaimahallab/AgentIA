from  config import CHUNK_SIZE, CHUNK_OVERLAP

def chunk_text(text):
    words = text.split()
    chunks = []

    i = 0
    while i < len(words):
        chunk = words[i:i + CHUNK_SIZE]
        chunks.append(" ".join(chunk))
        i += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks