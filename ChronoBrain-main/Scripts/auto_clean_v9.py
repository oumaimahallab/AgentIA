# this code of script is dedicated the 'all videoss'
import os
import re
import json
import requests
import numpy as np
import faiss
import pandas as pd  # <--- Added for Excel support
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import time  # <--- Added to measure time
from datetime import datetime 
# ==========================================
# 1. CONFIGURATION
# ==========================================
load_dotenv()

class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_KEY_HERE")
    CLEANING_MODEL = "llama-3.1-8b-instant"
    EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"
    CHUNK_SIZE = 400
    CHUNK_OVERLAP = 50
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    INDEX_PATH = "../data/metadata_v9/vector_v9.index"
    METADATA_PATH = "../data/metadata_v9/metadata_v9.json"
    LOG_EXCEL_PATH = "../data/logs/performance_logs.xlsx"

# ==========================================
# 2. DATA CLEANING MODULE
# ==========================================

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
            if match:
                return json.loads(match.group(0))
            return None
        except Exception:
            return None

    @classmethod
    def llm_clean_and_structure(cls, text: str) -> List[Dict]:
        prompt = f"""
        You are an expert French Editor. Rewrite this transcript into professional, clean French.
        Return ONLY a JSON array.
        Format: [ {{"clean_text": "...", "topic": "...", "keywords": ["..."] }} ]
        Transcript: {text}
        """
        headers = {"Authorization": f"Bearer {Config.GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": Config.CLEANING_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        try:
            res = requests.post(Config.GROQ_URL, headers=headers, json=payload, timeout=30)
            content = res.json()["choices"][0]["message"]["content"]
            parsed = cls.extract_json_safely(content)
            return parsed if parsed else [{"clean_text": text, "topic": "General", "keywords": []}]
        except Exception as e:
            return [{"clean_text": text, "topic": "Error", "keywords": []}]

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
            print("⚡ Loading existing vector DB from local storage...")
            self.index = faiss.read_index(Config.INDEX_PATH)
            with open(Config.METADATA_PATH, "r", encoding="utf-8") as f:
                self.chunks_metadata = json.load(f)
            print(f"✅ Loaded {len(self.chunks_metadata)} chunks.")

    def save_to_local(self):
        if self.index is not None:
            print("💾 Saving FAISS index and metadata...")
            faiss.write_index(self.index, Config.INDEX_PATH)
            with open(Config.METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(self.chunks_metadata, f, ensure_ascii=False, indent=2)
            print("✅ Save complete.")

    # --- NEW: Method to log performance to Excel ---
    def log_performance(self, question: str, answer:str ,response_time: float):
        new_data = {
            "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            "Model": [Config.CLEANING_MODEL],
            "Question": [question],
            "Answer": [answer],
            "Response Time (s)": [round(response_time, 3)]
        }
        df_new = pd.DataFrame(new_data)

        if os.path.exists(Config.LOG_EXCEL_PATH):
            df_old = pd.read_excel(Config.LOG_EXCEL_PATH)
            df_final = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_final = df_new
        
        df_final.to_excel(Config.LOG_EXCEL_PATH, index=False)
        print(f"📊 Performance logged to {Config.LOG_EXCEL_PATH}")
    def chunk_text(self, text: str) -> List[str]:
        words = text.split()
        return [" ".join(words[i : i + Config.CHUNK_SIZE]) 
                for i in range(0, len(words), Config.CHUNK_SIZE - Config.CHUNK_OVERLAP)]

    def process_transcript_file(self, file_path: str):
        if not os.path.exists(file_path):
            print(f"❌ Error: File {file_path} not found.")
            return

        print(f"\n📂 Reading file: {file_path}")
        
        # --- MODIFIED: Added logic to handle Excel files ---
        if file_path.endswith(".txt"):
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
        elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
            try:
                df = pd.read_excel(file_path)
                # Convert the entire Excel table to a readable text string
                raw_text = df.to_string(index=False)
            except Exception as e:
                print(f"❌ Could not read Excel file: {e}")
                return
        else:
            print(f"⚠️ Unsupported format: {file_path}")
            return

        # Step 1: Regex
        pre_cleaned = DataCleaner.regex_pre_clean(raw_text)

        # Step 2: LLM
        print("✨ Cleaning data with LLM...")
        structured_data = DataCleaner.llm_clean_and_structure(pre_cleaned)
        
        final_text = structured_data[0]["clean_text"]
        main_topic = structured_data[0]["topic"]
        source_filename = os.path.basename(file_path)

        # Step 3: Chunking
        text_chunks = self.chunk_text(final_text)
        
        current_metadata = []
        for i, chunk in enumerate(text_chunks):
            current_metadata.append({
                "text": chunk,
                "topic": main_topic,
                "source": source_filename,
                "keywords": structured_data[0]["keywords"]
            })
        
        self.chunks_metadata.extend(current_metadata)

        # Step 4: Embedding
        print(f"🧠 Embedding {len(text_chunks)} chunks...")
        embeddings = self.embedder.encode([c["text"] for c in current_metadata])
        
        if self.index is None:
            self.index = faiss.IndexFlatL2(embeddings.shape[1])
        
        self.index.add(np.array(embeddings).astype("float32"))
        print(f"✅ Successfully indexed: {source_filename}")

    def query(self, question: str):
        if self.index is None: return "No data indexed."
        start_time = time.time()
        query_vec = self.embedder.encode([question]).astype("float32")
        distances, indices = self.index.search(query_vec, k=3)
        context = "\n---\n".join([self.chunks_metadata[i]["text"] for i in indices[0]])
        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nRéponds en français."
        res = requests.post(
            Config.GROQ_URL, 
            headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}"},
            json={"model": Config.CLEANING_MODEL, "messages": [{"role": "user", "content": prompt}]}
        )
        # 1. Extract the answer text first
        answer = res.json()["choices"][0]["message"]["content"]
        # --- END TIMING ---
        end_time = time.time()
        duration = end_time - start_time
        
        # Log to Excel
        self.log_performance(question, answer,duration)
        
        return res.json()["choices"][0]["message"]["content"]

# ==========================================
# 4. EXECUTION
# ==========================================

if __name__ == "__main__":
    brain = ChronoBrain()

    if brain.index is None:
        print("📂 No local DB found. Starting processing...")
        folder_path = "../data/transcripts" 
        
        if os.path.exists(folder_path):
            # --- MODIFIED: Added .xlsx to the allowed extensions ---
            files_to_process = [f for f in os.listdir(folder_path) if f.endswith((".txt", ".xlsx", ".xls"))]
            
            if files_to_process:
                for filename in files_to_process:
                    brain.process_transcript_file(os.path.join(folder_path, filename))
                
                brain.save_to_local()
            else:
                print("No supported files found to process.")
        else:
            print(f"Please create the folder '{folder_path}'")
    else:
        print("⏩ Skipping processing: Database loaded from local files.")

    # Test RAG
    if brain.index:
        print("\n--- Ask a question about your files ---")
        #q = "À quoi sert le matricule alpha et dans quels cas est-il utilisé ?"
        #q = "Quelle est la différence entre un programme hebdomadaire et un cycle ?"
        #q = "Que se passe-t-il lorsqu’un collaborateur badge en dehors de sa plage horaire ?"
        #q = "Comment les heures supplémentaires sont‑elles calculées ?"
        #q = "Comment créer client principal ?"
        #q = "c'est quoi la difference entre astreinte et heures supplémentaire?"
        #q = "eeeeeeeeeeeeeeeee"
        #q = "comment fonctionnent asreinte realisees et astreinte prevue ?"
        q = "comment creer un profile utilisateur?"
        print(f"Question: {q}\nRéponse: {brain.query(q)}")