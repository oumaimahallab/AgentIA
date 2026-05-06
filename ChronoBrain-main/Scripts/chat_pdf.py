# chatbot.py — Ask questions against your indexed documents
# Loads: ../data/stage2/vector.index + metadata.json

import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import requests
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CONFIG
# ==========================================
class Config:
    INDEX_PATH       = "../data/stage2/vector.index"
    METADATA_PATH    = "../data/stage2/metadata.json"
    EMBEDDING_MODEL  = "intfloat/multilingual-e5-base"
    GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL       = "llama-3.1-8b-instant"
    GROQ_URL         = "https://api.groq.com/openai/v1/chat/completions"
    TOP_K            = 5


# ==========================================
# CHATBOT
# ==========================================
class ChronoBot:

    def __init__(self):
        print("🔄 Loading embedding model...")
        self.embedder = SentenceTransformer(Config.EMBEDDING_MODEL)

        print("⚡ Loading FAISS index...")
        self.index = faiss.read_index(Config.INDEX_PATH)

        with open(Config.METADATA_PATH, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        print(f"✅ Ready — {self.index.ntotal} vectors loaded.\n")

    def retrieve(self, question: str):
        query_vec = self.embedder.encode(
            [f"query: {question}"],
            normalize_embeddings=True
        ).astype("float32")

        distances, indices = self.index.search(query_vec, Config.TOP_K)

        chunks = []
        for score, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            chunk = self.metadata[idx].copy()
            chunk["score"] = round(float(score), 4)
            chunks.append(chunk)
        return chunks

    def answer(self, question: str) -> str:
        chunks = self.retrieve(question)

        if not chunks:
            return "Aucun contexte trouvé pour cette question."

        context = "\n\n---\n\n".join([
            f"[{c['source_file']} | p.{c['page_or_slide']}]\n{c['text']}"
            for c in chunks
        ])

        prompt = f"""Tu es ChronoBrain, un assistant expert sur les documents Chronotime.
Réponds à la question en français en te basant UNIQUEMENT sur le contexte fourni.
Si la réponse n'est pas dans le contexte, dis-le clairement. N'invente rien.

CONTEXTE:
{context}

QUESTION:
{question}

RÉPONSE:"""

        try:
            res = requests.post(
                Config.GROQ_URL,
                headers={
                    "Authorization": f"Bearer {Config.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": Config.GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                },
                timeout=30
            )
            return res.json()["choices"][0]["message"]["content"].strip()

        except Exception as e:
            return f"[ERREUR LLM] {e}"

    def show_sources(self, chunks):
        print("\n📚 Sources utilisées:")
        for i, c in enumerate(chunks, 1):
            print(f"  {i}. {c['source_file']} | page/slide {c['page_or_slide']} | score {c['score']}")


# ==========================================
# MAIN
# ==========================================
if __name__ == "__main__":
    if not Config.GROQ_API_KEY:
        print("❌ GROQ_API_KEY manquant dans .env")
        exit(1)

    bot = ChronoBot()

    print("=" * 55)
    print("  CHRONOBRAIN — Posez vos questions sur vos documents")
    print("  (tapez 'exit' pour quitter, 'sources' pour les refs)")
    print("=" * 55)

    show_sources = False

    while True:
        question = input("\n👤 Question: ").strip()

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("👋 Au revoir.")
            break
        if question.lower() == "sources":
            show_sources = not show_sources
            print(f"  ℹ️  Affichage des sources: {'ON' if show_sources else 'OFF'}")
            continue

        chunks = bot.retrieve(question)
        answer = bot.answer(question)

        print(f"\n🤖 Réponse:\n{answer}")

        if show_sources:
            bot.show_sources(chunks)