import os
import re
import numpy as np
from rank_bm25 import BM25Okapi
#from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from transformers import pipeline
import torch
import pickle
from pathlib import Path
import faiss
from time import time

class VideoTranscriptChatbot:
    def __init__(self):
        self.TRANSCRIPT_FOLDER = "../data/transcripts/"
        self.CACHE_FOLDER = "../data/cache/"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        Path(self.TRANSCRIPT_FOLDER).mkdir(exist_ok=True)
        Path(self.CACHE_FOLDER).mkdir(exist_ok=True)
        
        print(f"--- Initializing on {self.device.upper()} ---")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2', device=self.device)
        self.llm = pipeline(
            #"text-generation",
            "text2text-generation",
            model="google/flan-t5-large",
            device=self.device,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        self.corpus = []
        self.chunk_metadata = []
        self.load_or_process_documents()

    def merge_transcript_blocks(self, file_path):
        merged = []
        current_ts = None
        current_text = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(r'\[(\d{2}:\d{2} -> \d{2}:\d{2})\]', line)
                if match:
                    if current_ts and current_ts != match.group(1):
                        merged.append({"ts": current_ts, "text": " ".join(current_text)})
                        current_text = []
                    current_ts = match.group(1)
                    clean_text = re.sub(r'\[.*?\]', '', line).strip()
                    current_text.append(clean_text)
        
        if current_ts:
            merged.append({"ts": current_ts, "text": " ".join(current_text)})
        return merged

    def load_or_process_documents(self):
        cache_file = os.path.join(self.CACHE_FOLDER, "transcript_cache.pkl")
        faiss_file = os.path.join(self.CACHE_FOLDER, "faiss_index.faiss")
        
        if os.path.exists(cache_file) and os.path.exists(faiss_file):
            print("Loading from cache...")
            with open(cache_file, "rb") as f:
                self.corpus, self.chunk_metadata = pickle.load(f)
            self.faiss_index = faiss.read_index(faiss_file)
            self.bm25 = BM25Okapi([doc.split() for doc in self.corpus])
        else:
            print("Processing new transcripts...")
            self.process_transcripts_and_create_embeddings()

    def process_transcripts_and_create_embeddings(self):
        txt_files = [f for f in os.listdir(self.TRANSCRIPT_FOLDER) if f.endswith(".txt")]
        for filename in txt_files:
            blocks = self.merge_transcript_blocks(os.path.join(self.TRANSCRIPT_FOLDER, filename))
            for block in blocks:
                chunks = self.text_splitter.split_text(block['text'])
                for chunk in chunks:
                    self.corpus.append(chunk)
                    self.chunk_metadata.append({"source": filename, "timestamp": block['ts']})

        self.bm25 = BM25Okapi([doc.split() for doc in self.corpus])
        embeddings = self.embedder.encode(self.corpus, show_progress_bar=True)
        self.faiss_index = faiss.IndexFlatL2(384)
        self.faiss_index.add(embeddings.astype('float32'))
        
        with open(os.path.join(self.CACHE_FOLDER, "transcript_cache.pkl"), "wb") as f:
            pickle.dump((self.corpus, self.chunk_metadata), f)
        faiss.write_index(self.faiss_index, os.path.join(self.CACHE_FOLDER, "faiss_index.faiss"))

    def ask_question(self, question: str):
        query_embedding = self.embedder.encode(question).astype('float32').reshape(1, -1)
        _, indices = self.faiss_index.search(query_embedding, 3)
        
        # Build context string
        context_text = ""
        sources = []
        for idx in indices[0]:
            chunk = self.corpus[idx]
            meta = self.chunk_metadata[idx]
            context_text += f"[{meta['timestamp']}] {chunk} "
            sources.append(f"{meta['source']} at {meta['timestamp']}")
            
        # Refined prompt for T5
        prompt = f"""You are a helpful assistant. Use the following context to answer the question. If the answer is not in the context, say you don't know.
        
        Context:
        {context_text}
        
        Question: {question}
        
        Answer:"""
        
        # Generate
        response = self.llm(
            prompt, 
            max_new_tokens=256, 
            do_sample=True, 
            temperature=0.5
        )
        
        return response[0]["generated_text"], list(set(sources))

if __name__ == "__main__":
    bot = VideoTranscriptChatbot()
    print("\n--- Assistant Ready! Type 'quit' to exit. ---")
    while True:
        user_input = input("\nUser Query: ")
        if user_input.lower() == 'quit':
            break
        answer, sources = bot.ask_question(user_input)
        print(f"\nAI Answer: {answer}")
        print(f"Sources: {', '.join(sources)}")