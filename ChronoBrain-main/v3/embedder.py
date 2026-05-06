from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/multilingual-e5-base")

def embed_chunks(chunks):
    texts = [c["text"] for c in chunks]
    return model.encode(texts, normalize_embeddings=True)