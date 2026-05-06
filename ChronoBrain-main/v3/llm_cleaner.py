import requests
from  config import GROQ_API_KEY, CLEANING_MODEL
from  json_utils import extract_json

URL = "https://api.groq.com/openai/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

PROMPT = """
You are a data cleaning engine.

Return ONLY valid JSON:
[
  {
    "clean_text": "...",
    "topic": "...",
    "keywords": ["..."]
  }
]

Rules:
- Remove noise
- Keep meaning
- French only
- NO explanation
"""

def clean_with_llm(text):
    payload = {
        "model": CLEANING_MODEL,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": text}
        ],
        "temperature": 0.2
    }

    response = requests.post(URL, headers=HEADERS, json=payload)
    data = response.json()

    content = data["choices"][0]["message"]["content"]

    parsed = extract_json(content)
    return parsed if parsed else content