# this code of script is dedicated the 'all videoss'
# is considered for semntic splitting
import os
import re
import json
import requests
import numpy as np
import faiss
import pandas as pd
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import time
from datetime import datetime 

# ==========================================
# 1. CONFIGURATION
# ==========================================
load_dotenv()

class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_KEY_HERE")
    CLEANING_MODEL = "llama-3.1-8b-instant"
    EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"
    # Note: Semantic chunking handles size dynamically, but we set a max limit
    MAX_CHUNK_WORDS = 600 
    BREAKPOINT_PERCENTILE = 85 # Higher = fewer chunks (more meaning grouped together)
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    INDEX_PATH = "../data/metadata_v10/vector_v10.index"
    METADATA_PATH = "../data/metadata_v10/metadata_v10.json"
    LOG_EXCEL_PATH = "../data/logs/performance_logs.xlsx"

# ==========================================
# 2. DATA CLEANING MODULE
# ==========================================
# (DataCleaner class remains the same...)
class DataCleaner:
    @staticmethod
    def regex_pre_clean(text: str) -> str:
        text = re.sub(r"\[?\d{1,2}:\d{2}(:\d{2})?\]?", "", text)
        fillers = r"\b(euh|uh|um|bon|voilà|donc|alors|tu sais|je veux dire)\b"
        text = re.sub(fillers, "", text, flags=re.I)
        text = re.sub(r"\b(\w+)( \1\b)+", r"\1", text, flags=re.I)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def extract_json_safely(text: str) -> Optional[List[Dict]]:
        try:
            match = re.search(r"\[\s*{.*}\s*\]", text, re.DOTALL)
            if match: return json.loads(match.group(0))
            return None
        except Exception: return None

    @classmethod
    def llm_clean_and_structure(cls, text: str) -> List[Dict]:
        prompt = f"Rewrite this transcript into professional, clean French. Return ONLY JSON array. Format: [{{'clean_text': '...', 'topic': '...', 'keywords': []}}] \nTranscript: {text}"
        headers = {"Authorization": f"Bearer {Config.GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": Config.CLEANING_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        try:
            res = requests.post(Config.GROQ_URL, headers=headers, json=payload, timeout=30)
            content = res.json()["choices"][0]["message"]["content"]
            return cls.extract_json_safely(content) or [{"clean_text": text, "topic": "General", "keywords": []}]
        except Exception: return [{"clean_text": text, "topic": "Error", "keywords": []}]

# ==========================================
# 3. PROCESSING & VECTOR STORE
# ==========================================

class ChronoBrain:
    def __init__(self):
        print("Loading Embedding Model...")
        self.embedder = SentenceTransformer(Config.EMBEDDING_MODEL_NAME)
        self.index = None
        self.chunks_metadata = []
        if os.path.exists(Config.INDEX_PATH) and os.path.exists(Config.METADATA_PATH):
            self.index = faiss.read_index(Config.INDEX_PATH)
            with open(Config.METADATA_PATH, "r", encoding="utf-8") as f:
                self.chunks_metadata = json.load(f)

    def save_to_local(self):
        if self.index is not None:
            faiss.write_index(self.index, Config.INDEX_PATH)
            with open(Config.METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(self.chunks_metadata, f, ensure_ascii=False, indent=2)

    # --- UPDATED: SEMANTIC CHUNKING ---
    def chunk_text(self, text: str) -> List[str]:
        """Splits text based on semantic meaning changes."""
        # 1. Split into sentences
        sentences = re.split(r'(?<=[.!?]) +', text)
        if len(sentences) < 3: return [text]

        # 2. Embed sentences to understand their meaning
        embeddings = self.embedder.encode(sentences)

        # 3. Calculate cosine distance between consecutive sentences
        distances = []
        for i in range(len(embeddings) - 1):
            # Calculate how 'different' sentence i is from sentence i+1
            similarity = np.dot(embeddings[i], embeddings[i+1]) / (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[i+1]))
            distances.append(1 - similarity) # Distance is 1 - similarity

        # 4. Identify breakpoints (where distance is higher than the 85th percentile)
        if not distances: return [text]
        threshold = np.percentile(distances, Config.BREAKPOINT_PERCENTILE)
        
        chunks = []
        current_chunk = [sentences[0]]
        
        for i, dist in enumerate(distances):
            # If the meaning changes a lot OR the chunk is getting too big
            word_count = len(" ".join(current_chunk).split())
            
            if dist > threshold or word_count > Config.MAX_CHUNK_WORDS:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentences[i + 1]]
            else:
                current_chunk.append(sentences[i + 1])
        
        chunks.append(" ".join(current_chunk))
        print(f"✂️ Semantic Splitting: Created {len(chunks)} chunks from sentences.")
        return chunks

    def log_performance(self, question: str, response_time: float):
        new_data = {"Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")], "Model": [Config.CLEANING_MODEL], "Question": [question], "Response Time (s)": [round(response_time, 3)]}
        df_new = pd.DataFrame(new_data)
        if os.path.exists(Config.LOG_EXCEL_PATH):
            df_old = pd.read_excel(Config.LOG_EXCEL_PATH)
            df_final = pd.concat([df_old, df_new], ignore_index=True)
        else: df_final = df_new
        df_final.to_excel(Config.LOG_EXCEL_PATH, index=False)

    def process_transcript_file(self, file_path: str):
        if not os.path.exists(file_path): return
        print(f"\n📂 Reading: {file_path}")
        
        if file_path.endswith(".txt"):
            with open(file_path, 'r', encoding='utf-8') as f: raw_text = f.read()
        elif file_path.endswith((".xlsx", ".xls")):
            raw_text = pd.read_excel(file_path).to_string(index=False)
        else: return

        # Step 1 & 2: Clean and LLM logic
        pre_cleaned = DataCleaner.regex_pre_clean(raw_text)
        structured_data = DataCleaner.llm_clean_and_structure(pre_cleaned)
        
        final_text = structured_data[0]["clean_text"]
        main_topic = structured_data[0]["topic"]
        source_filename = os.path.basename(file_path)

        # Step 3: Semantic Chunking
        text_chunks = self.chunk_text(final_text)
        
        current_metadata = []
        for chunk in text_chunks:
            current_metadata.append({
                "text": chunk,
                "topic": main_topic,
                "source": source_filename,
                "keywords": structured_data[0]["keywords"]
            })
        
        self.chunks_metadata.extend(current_metadata)

        # Step 4: Embedding
        print(f"🧠 Embedding {len(text_chunks)} semantic chunks...")
        embeddings = self.embedder.encode([c["text"] for c in current_metadata])
        
        if self.index is None:
            self.index = faiss.IndexFlatL2(embeddings.shape[1])
        
        self.index.add(np.array(embeddings).astype("float32"))

    def query(self, question: str):
        if self.index is None: return "No data."
        start_time = time.time()
        query_vec = self.embedder.encode([question]).astype("float32")
        distances, indices = self.index.search(query_vec, k=3)
        context = "\n---\n".join([self.chunks_metadata[i]["text"] for i in indices[0]])
        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nRéponds en français."
        res = requests.post(Config.GROQ_URL, headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}"},
                            json={"model": Config.CLEANING_MODEL, "messages": [{"role": "user", "content": prompt}]})
        
        self.log_performance(question, time.time() - start_time)
        return res.json()["choices"][0]["message"]["content"]

# ==========================================
# 4. EXECUTION
# ==========================================
if __name__ == "__main__":
    brain = ChronoBrain()
    if brain.index is None:
        folder_path = "../data/transcripts" 
        if os.listdir(folder_path):
            for filename in os.listdir(folder_path):
                if filename.endswith((".txt", ".xlsx")):
                    brain.process_transcript_file(os.path.join(folder_path, filename))
            brain.save_to_local()
    
    
    #q = "À quoi sert le matricule alpha et dans quels cas est-il utilisé ?"
    #q = "Quelle est la différence entre un programme hebdomadaire et un cycle ?"
    #q = "Que se passe-t-il lorsqu’un collaborateur badge en dehors de sa plage horaire ?"
    #q = "Comment les heures supplémentaires sont‑elles calculées ?"
    #q = "Comment créer client principal ?"
    #q = "c'est quoi la difference entre astreinte et heures supplémentaire?"
    #q = "eeeeeeeeeeeeeeeee"
    #q = "comment fonctionnent asreinte realisees et astreinte prevue ?"
    q = "comment creer un profile utilisateur?"
    print(f"\nQuestion: {q}\nRéponse: {brain.query(q)}")