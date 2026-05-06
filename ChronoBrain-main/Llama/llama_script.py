import time
import csv
import os
from llama_cpp import Llama

# 1. Initialize the Model
print("Loading model... please wait.")
# llm = Llama.from_pretrained(
#     repo_id="bartowski/Llama-3.2-3B-Instruct-GGUF",
#     filename="Llama-3.2-3B-Instruct-Q4_K_M.gguf"
# )
# Initialize the model with a larger n_ctx (context window)
# 1. Initialize the Model
print("Loading 8B model... please wait.")

llm = Llama.from_pretrained(
    repo_id="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF", # Added "Meta-"
    filename="Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",    # Added "Meta-"
    n_ctx=8192,
    n_batch=512,
    n_gpu_layers=-1 # If you have an NVIDIA GPU, this will make it fast!
)
# 2. Load your Knowledge Base
file_path = "../data/file_all_enriched.txt"
with open(file_path, "r", encoding="utf-8") as f:
    knowledge_base = f.read()

def ask_chronotime(question):
    # Construct the prompt using the knowledge base
    prompt = f"""
    You are an expert assistant for the Chrono-Time module.
    Use the provided 'Base de Connaissances' to answer the user's question accurately.
    If the answer is not in the text, say you don't know.

    Base de Connaissances:
    {knowledge_base}

    User Question:
    {question}
    """

    # Start timer
    start_time = time.time()
    
    # Generate response
    response = llm(prompt, max_tokens=500, stop=["User Question:"])
    answer = response['choices'][0]['text'].strip()
    
    # End timer
    end_time = time.time()
    duration = end_time - start_time
    
    return answer, duration

# --- Main execution ---
user_query = "Comment puis-je créer un nouveau profil utilisateur dans Chronotime ?"
answer, duration = ask_chronotime(user_query)

print(f"\n--- Réponse ---\n{answer}")
print(f"\n--- Temps de réponse: {duration:.2f} secondes ---")

# --- Log to CSV ---
csv_file = "model_performance.csv"
file_exists = os.path.isfile(csv_file)

with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    if not file_exists:
        writer.writerow(["Model", "Question", "Time_Seconds", "Answer"])  ])
    writer.writerow(["Llama-3.1-8B", user_query, f"{duration:.2f}", answer])