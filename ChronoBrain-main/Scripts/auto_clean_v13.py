# by chatgpt SemanticSplitterNodeParser 
# ==========================================
# 1. IMPORTS
# ==========================================
import os
import re
import json
import requests
import numpy as np
import faiss
import pandas as pd
import time
from datetime import datetime
from typing import List, Dict, Optional
from llama_index.core import Document
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# ✅ NEW: Semantic chunking
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding


# ==========================================
# 2. CONFIG
# ==========================================
load_dotenv()

class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_KEY_HERE")
    CLEANING_MODEL = "llama-3.1-8b-instant"
    EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    
    INDEX_PATH = "../data/metadata_v13/vector_v13.index"
    METADATA_PATH = "../data/metadata_v13/metadata_v13.json"
    LOG_EXCEL_PATH = "../data/logs/performance_logs.xlsx"


# ==========================================
# 3. DATA CLEANING
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
        except:
            return None

    @classmethod
    def llm_clean_and_structure(cls, text: str) -> List[Dict]:
        prompt = f"""
        You are an expert French Editor. Rewrite this transcript into professional, clean French.
        Return ONLY a JSON array.
        Format: [ {{"clean_text": "...", "topic": "...", "keywords": ["..."] }} ]
        Transcript: {text}
        """

        headers = {
            "Authorization": f"Bearer {Config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": Config.CLEANING_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }

        try:
            res = requests.post(Config.GROQ_URL, headers=headers, json=payload, timeout=30)
            content = res.json()["choices"][0]["message"]["content"]
            parsed = cls.extract_json_safely(content)

            return parsed if parsed else [{
                "clean_text": text,
                "topic": "General",
                "keywords": []
            }]

        except:
            return [{
                "clean_text": text,
                "topic": "Error",
                "keywords": []
            }]


# ==========================================
# 4. CORE ENGINE
# ==========================================
class ChronoBrain:

    def __init__(self):
        print("🔄 Loading embedding model...")
        self.embedder = SentenceTransformer(Config.EMBEDDING_MODEL_NAME)

        self.index = None
        self.chunks_metadata = []

        if os.path.exists(Config.INDEX_PATH) and os.path.exists(Config.METADATA_PATH):
            print("⚡ Loading existing vector DB...")
            self.index = faiss.read_index(Config.INDEX_PATH)

            with open(Config.METADATA_PATH, "r", encoding="utf-8") as f:
                self.chunks_metadata = json.load(f)

            print(f"✅ Loaded {len(self.chunks_metadata)} chunks.")

    # ======================================
    # ✅ NEW: Semantic Chunking
    # # ======================================
    # def semantic_chunk_text(self, text: str) -> List[str]:

    #     embed_model = HuggingFaceEmbedding(
    #         model_name=Config.EMBEDDING_MODEL_NAME
    #     )

    #     splitter = SemanticSplitterNodeParser(
    #         embed_model=embed_model,
    #         breakpoint_percentile_threshold=90
    #     )

    #     #documents = [{"text": text}]
    #     documents = [Document(text=text)]
    #     nodes = splitter.get_nodes_from_documents(documents)

    #     chunks = [node.text for node in nodes]

    #     # safety split (avoid very long chunks)
    #     final_chunks = []
    #     for chunk in chunks:
    #         words = chunk.split()
    #         if len(words) > 500:
    #             for i in range(0, len(words), 400):
    #                 final_chunks.append(" ".join(words[i:i+400]))
    #         else:
    #             final_chunks.append(chunk)

    #     return final_chunks
    def semantic_chunk_text(self, text: str) -> List[str]:

        embed_model = HuggingFaceEmbedding(
            model_name=Config.EMBEDDING_MODEL_NAME
        )

        splitter = SemanticSplitterNodeParser(
            embed_model=embed_model,
            breakpoint_percentile_threshold=90
        )

        # ✅ FIX HERE
        documents = [Document(text=text)]

        nodes = splitter.get_nodes_from_documents(documents)

        chunks = [node.text for node in nodes]

        return chunks

    # ======================================
    def save_to_local(self):
        if self.index is not None:
            print("💾 Saving index...")
            faiss.write_index(self.index, Config.INDEX_PATH)

            with open(Config.METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(self.chunks_metadata, f, ensure_ascii=False, indent=2)

    # ======================================
    def log_performance(self, question, answer, response_time):
        data = {
            "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            "Model": [Config.CLEANING_MODEL],
            "Question": [question],
            "Answer": [answer],
            "Response Time (s)": [round(response_time, 3)]
        }

        df_new = pd.DataFrame(data)

        if os.path.exists(Config.LOG_EXCEL_PATH):
            df_old = pd.read_excel(Config.LOG_EXCEL_PATH)
            df_final = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_final = df_new

        df_final.to_excel(Config.LOG_EXCEL_PATH, index=False)

    # ======================================
    def process_transcript_file(self, file_path: str):

        print(f"\n📂 Processing: {file_path}")

        if file_path.endswith(".txt"):
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()

        elif file_path.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file_path)
            raw_text = df.to_string(index=False)

        else:
            return

        # cleaning
        text = DataCleaner.regex_pre_clean(raw_text)
        structured = DataCleaner.llm_clean_and_structure(text)

        final_text = structured[0]["clean_text"]
        topic = structured[0]["topic"]
        filename = os.path.basename(file_path)

        # ✅ SEMANTIC CHUNKING HERE
        chunks = self.semantic_chunk_text(final_text)

        metadata = []
        for chunk in chunks:
            metadata.append({
                "text": chunk,
                "topic": topic,
                "source": filename,
                "keywords": structured[0]["keywords"]
            })

        self.chunks_metadata.extend(metadata)

        # embedding
        print(f"🧠 Embedding {len(chunks)} chunks...")
        embeddings = self.embedder.encode([c["text"] for c in metadata])

        if self.index is None:
            self.index = faiss.IndexFlatL2(embeddings.shape[1])

        self.index.add(np.array(embeddings).astype("float32"))

    # ======================================
    def query(self, question: str):

        if self.index is None:
            return "No data indexed."

        start = time.time()

        query_vec = self.embedder.encode([question]).astype("float32")
        distances, indices = self.index.search(query_vec, k=3)

        context = "\n---\n".join([
            self.chunks_metadata[i]["text"] for i in indices[0]
        ])

        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nRéponds en français."

        res = requests.post(
            Config.GROQ_URL,
            headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}"},
            json={
                "model": Config.CLEANING_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            }
        )

        answer = res.json()["choices"][0]["message"]["content"]

        duration = time.time() - start
        self.log_performance(question, answer, duration)

        return answer


# ==========================================
# 5. MAIN
# ==========================================
if __name__ == "__main__":

    brain = ChronoBrain()

    if brain.index is None:
        print("📂 Building database...")

        folder = "../data/transcripts"

        files = [f for f in os.listdir(folder) if f.endswith((".txt", ".xlsx", ".xls"))]

        for file in files:
            brain.process_transcript_file(os.path.join(folder, file))

        brain.save_to_local()

    print("\n💬 Ask your question:")
    #q = "comment creer un profile utilisateur?"
    q = "hjbsxyusgxnshl"
    print(brain.query(q))