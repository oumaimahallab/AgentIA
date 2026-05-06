import faiss
import numpy as np

class FAISSStore:
    def __init__(self, dim):
        self.index = faiss.IndexFlatL2(dim)

    def add(self, vectors):
        self.index.add(np.array(vectors))

    def search(self, query_vector, k=5):
        D, I = self.index.search(query_vector, k)
        return I