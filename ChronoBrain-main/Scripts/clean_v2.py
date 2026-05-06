import re
import argparse
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Matches the timestamp block at the start of the line: [06:32 -> 06:34]
TIMESTAMP_RE = re.compile(r"\[\d{1,2}:\d{2}\s*->\s*\d{1,2}:\d{2}\]\s*")

FILLER_PATTERN = re.compile(
    r"^(oui|non|d'accord|ok|euh+|hm+|ah+|oh+|voilà|donc|alors|ben|bah|ouais)[.!?,\s]*$",
    re.IGNORECASE,
)

def clean_text(text: str) -> str:
    """Standardizes text: fixes ASR errors and collapses spaces."""
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove repeated punctuation
    text = re.sub(r'([.!?,])\1+', r'\1', text)
    # Fix common French ASR artifacts
    text = re.sub(r'\bqu il\b', "qu'il", text, flags=re.IGNORECASE)
    text = re.sub(r'\bc est\b', "c'est", text, flags=re.IGNORECASE)
    return text

def process_transcript(input_file: Path, output_file: Path):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    clean_content = []
    
    for line in lines:
        line = line.strip()
        # 1. Remove the timestamp metadata using the regex
        text = TIMESTAMP_RE.sub("", line)
        
        # 2. Clean the resulting text
        text = clean_text(text)
        
        # 3. Skip noise lines (empty or filler)
        if not text or FILLER_PATTERN.match(text):
            continue
            
        clean_content.append(text)

    # Write as a single block of text (paragraph style)
    with open(output_file, 'w', encoding='utf-8') as f:
        # Join with space to make it look like a paragraph, 
        # or use "\n" if you want it line-by-line.
        f.write(" ".join(clean_content))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="../data/transcripts", help="Input directory")
    parser.add_argument("--output", default="../data/cleaned_txt", help="Output directory")
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    files = list(input_dir.glob("*.txt"))
    if not files:
        print(f"No .txt files found in {input_dir}")
        return

    print(f"Processing {len(files)} files...")
    
    for file_path in files:
        output_file = output_dir / f"{file_path.stem}_cleaned.txt"
        process_transcript(file_path, output_file)
        print(f"  → Cleaned: {file_path.name}")
    
    print(f"\nDone! All files saved to: {output_dir}")

if __name__ == "__main__":
    main()