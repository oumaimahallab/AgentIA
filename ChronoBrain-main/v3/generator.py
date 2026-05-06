import requests
from  config import GROQ_API_KEY

URL = "https://api.groq.com/openai/v1/chat/completions"

def generate_answer(context, question):
    prompt = f"""
Context:
{context}

Question:
{question}

Answer only using context.
"""

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}]
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    res = requests.post(URL, headers=headers, json=payload)
    return res.json()["choices"][0]["message"]["content"]