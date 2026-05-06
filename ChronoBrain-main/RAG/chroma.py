import os
import logging
import sys
from llama_index.core import (
    VectorStoreIndex, 
    SimpleDirectoryReader, 
    StorageContext,
    Settings,
    PromptTemplate
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

# --- 1. CONFIGURATION ---
DATA_DIR = "../data/transcripts"
DB_PATH = "../data/chroma_db2"
LLM_MODEL = "phi3" 
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# --- 2. SETUP INFRASTRUCTURE ---
def setup_engine():
    Settings.llm = Ollama(model=LLM_MODEL, request_timeout=300.0)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)

    db = chromadb.PersistentClient(path=DB_PATH)
    chroma_collection = db.get_or_create_collection("chronobrain_docs")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    documents = SimpleDirectoryReader(DATA_DIR, recursive=True).load_data()

    index = VectorStoreIndex.from_documents(
        documents, 
        storage_context=storage_context,
        show_progress=True
    )
    return index

# --- 3. CUSTOM PROMPTING (MODIFIED) ---
def get_query_engine(index):
    # Enforced French, direct answer, no citations requested
    qa_prompt_tmpl = (
        "Vous êtes ChronoBrain, l'assistant officiel de l'entreprise. "
        "Utilisez les informations contextuelles fournies ci-dessous pour répondre à la question.\n"
        "---------------------\n"
        "{context_str}\n"
        "---------------------\n"
        "Instructions:\n"
        "1. Répondez exclusivement en français.\n"
        "2. Fournissez une réponse directe, complète et concise.\n"
        "3. Ne citez pas les sources ou les horodatages dans votre réponse.\n"
        "4. Si vous ne trouvez pas la réponse dans le contexte, dites simplement que vous ne savez pas.\n"
        "Question: {query_str}\n"
        "Réponse directe: "
    )
    qa_prompt = PromptTemplate(qa_prompt_tmpl)
    
    return index.as_query_engine(
        similarity_top_k=4,
        text_qa_template=qa_prompt
    )

# --- 4. EXECUTION ---
# --- 4. EXECUTION (SIMPLIFIED TO AVOID TIMEOUTS) ---
if __name__ == "__main__":
    if not os.path.exists(DATA_DIR):
        print(f"Error: Directory {DATA_DIR} not found.")
        sys.exit(1)

    print("Initialisation de ChronoBrain...")
    index = setup_engine()
    
    # Use a retriever instead of a query engine
    retriever = index.as_retriever(similarity_top_k=3)
    llm = Settings.llm # The Ollama instance we configured

    while True:
        user_input = input("\n[ChronoBrain] Posez votre question (ou 'quit'): ")
        if user_input.lower() == 'quit':
            break
            
        # 1. Retrieve raw chunks
        nodes = retriever.retrieve(user_input)
        context_str = "\n\n".join([n.get_content() for n in nodes])
        
        # 2. Build a simple string prompt
        prompt = (
            f"Vous êtes l'assistant de l'entreprise. Répondez en français de manière directe et concise.\n"
            f"Contexte: {context_str}\n\n"
            f"Question: {user_input}\n"
            f"Réponse: "
        )
        
        # 3. Call the LLM directly (avoiding LlamaIndex synthesis engine entirely)
        print("Réflexion en cours...")
        response = llm.complete(prompt)
        print(f"\nRéponse: {response}")