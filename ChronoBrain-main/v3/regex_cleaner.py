import re

def clean_noise(text: str) -> str:
    text = re.sub(r"\[.*?\]", "", text)  # timestamps
    text = re.sub(r"\b(euh|uh|um|bon|voilà)\b", "", text, flags=re.I)
    text = re.sub(r"\b(\w+)( \1\b)+", r"\1", text)  # repeated words
    text = re.sub(r"\s+", " ", text)
    return text.strip()