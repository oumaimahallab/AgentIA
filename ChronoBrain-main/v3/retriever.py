def retrieve(query_embedding, store, chunks, k=5):
    indices = store.search(query_embedding, k)
    return [chunks[i] for i in indices[0]]