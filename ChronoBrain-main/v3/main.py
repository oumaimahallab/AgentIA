from  regex_cleaner import clean_noise
from  llm_cleaner import clean_with_llm
from  chunker import chunk_text
from  metadata_builder import build_metadata
from  embedder import embed_chunks
from faiss_store import FAISSStore

def run_pipeline(text):
    # Step 1: rule cleaning
    cleaned = clean_noise(text)

    # Step 2: LLM cleaning
    structured = clean_with_llm(cleaned)

    if isinstance(structured, list):
        text = structured[0]["clean_text"]
        topic = structured[0]["topic"]
    else:
        text = cleaned
        topic = "unknown"

    # Step 3: chunking
    chunks = chunk_text(text)

    # Step 4: metadata
    chunks_meta = [build_metadata(c, i, topic) for i, c in enumerate(chunks)]

    # Step 5: embedding
    vectors = embed_chunks(chunks_meta)

    # Step 6: store
    store = FAISSStore(len(vectors[0]))
    store.add(vectors)

    return chunks_meta, store