import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from openai import OpenAI  # You can use OpenAI, Ollama, or Groq
import sys
from dotenv import load_dotenv
# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
if os.path.exists(".env"):
    load_dotenv()
elif os.path.exists("../.env"):
    load_dotenv("../.env")
class ChatConfig:
    CHUNKS_PATH = "../data/chunks/chunks.json"
    EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    # LLM Settings (Using OpenAI as an example, but adaptable)
    #OPENAI_API_KEY = "your-api-key-here" 
    LLM_MODEL = "gpt-4o" 

# ══════════════════════════════════════════════════════════════════════════════
# CHRONOBRAIN CHAT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class ChronoBot:
    def __init__(self):
        print(f"[*] Loading {ChatConfig.EMBEDDING_MODEL}...")
        self.embedder = SentenceTransformer(ChatConfig.EMBEDDING_MODEL)
        
        print(f"[*] Loading chunks from {ChatConfig.CHUNKS_PATH}...")
        with open(ChatConfig.CHUNKS_PATH, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
            
        self.index = None
        self._build_index()
        
        # Initialize LLM Client
        self.client = OpenAI(api_key=ChatConfig.OPENAI_API_KEY)

    def _build_index(self):
        """Create a FAISS vector index for fast retrieval."""
        print(f"[*] Building vector index for {len(self.chunks)} chunks...")
        
        # Multilingual-E5 requires "passage: " prefix for indexing
        texts = [f"passage: {c['text']}" for c in self.chunks]
        embeddings = self.embedder.encode(texts, normalize_embeddings=True, show_progress_bar=True)
        
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)  # Inner Product (Cosine similarity)
        self.index.add(np.array(embeddings).astype('float32'))
        print("[+] Index ready.")

    def retrieve(self, query: str, top_k: int = 3):
        """Find the most relevant chunks for a query."""
        # Multilingual-E5 requires "query: " prefix for retrieval
        query_emb = self.embedder.encode([f"query: {query}"], normalize_embeddings=True)
        distances, indices = self.index.search(np.array(query_emb).astype('float32'), top_k)
        
        results = []
        for idx in indices[0]:
            if idx != -1:
                results.append(self.chunks[idx])
        return results

    def answer(self, question: str):
        """Full RAG Pipeline: Retrieve -> Augment -> Generate."""
        # 1. Retrieve
        context_chunks = self.retrieve(question)
        context_text = "\n\n---\n\n".join([c['text'] for c in context_chunks])
        sources = list(set([c['source_file'] for c in context_chunks]))

        # 2. Construct Prompt
        prompt = f"""Tu es ChronoBrain, un expert technique sur le logiciel Chronotime. 
Utilise les extraits de transcriptions suivants pour répondre à la question de l'utilisateur. 
Si tu ne trouves pas la réponse dans le contexte, dis-le poliment, n'invente rien.

CONTEXTE:
{context_text}

QUESTION:
{question}

RÉPONSE (en français):"""

        # 3. Generate with LLM
        response = self.client.chat.completions.create(
            model=ChatConfig.LLM_MODEL,
            messages=[
                {"role": "system", "content": "Tu es un assistant technique expert en gestion des temps."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        answer_text = response.choices[0].message.content
        return answer_text, sources

# ══════════════════════════════════════════════════════════════════════════════
# INTERACTIVE LOOP
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Check for API Key
    #if ChatConfig.OPENAI_API_KEY == "your-api-key-here":
    if not  ChatConfig.OPENAI_API_KEY:
        print("!! ERREUR: Configurez votre OPENAI_API_KEY dans le code.")
        exit()

    bot = ChronoBot()
    
    print("\n" + "="*50)
    print("CHRONOBRAIN CHAT - Posez vos questions sur Chronotime")
    print("(Tapez 'exit' pour quitter)")
    print("="*50 + "\n")

    while True:
        query = input("\n👤 Question: ")
        if query.lower() in ['exit', 'quit']:
            break
            
        print("🤖 Réflexion...")
        answer, docs = bot.answer(query)
        
        print(f"\n✨ RÉPONSE:\n{answer}")
        print(f"\n📚 SOURCES: {', '.join(docs)}")

    #q = "À quoi sert le matricule alpha et dans quels cas est-il utilisé ?"
    #q = "Quelle est la différence entre un programme hebdomadaire et un cycle ?"
    #q = "Que se passe-t-il lorsqu’un collaborateur badge en dehors de sa plage horaire ?"
    #q = "Comment les heures supplémentaires sont‑elles calculées ?"
    #q = "Comment créer client principal ?"
    #q = "c'est quoi la difference entre astreinte et heures supplémentaire?"
    #q = "eeeeeeeeeeeeeeeee"
    #q = "comment fonctionnent asreinte realisees et astreinte prevue ?"
    #q = "comment creer un profile utilisateur?"