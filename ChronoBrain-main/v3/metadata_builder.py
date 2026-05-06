def build_metadata(chunk, idx, topic="general"):
    return {
        "chunk_id": f"chunk_{idx}",
        "topic": topic,
        "language": "fr",
        "text": chunk
    }