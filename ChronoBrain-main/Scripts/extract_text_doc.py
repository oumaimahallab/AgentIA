# stage1_extract.py — Extract text from PDF & PPTX → raw_extracts.json
# Run this FIRST before stage2_chunk_embed.py

import os
import re
import io
import json
import hashlib
import time
from datetime import datetime
from typing import List, Dict

import fitz  # PyMuPDF
from pptx import Presentation
from PIL import Image
import pytesseract
import pandas as pd

# ==========================================
# CONFIG
# ==========================================
class Config:
    INPUT_FOLDER    = "../data/documents"       # folder with your PDF/PPTX files
    OUTPUT_JSON     = "../data/stage1/raw_extracts.json"
    LOG_PATH        = "../data/logs/stage1_log.xlsx"
    OCR_LANG        = "fra+eng"
    MIN_TEXT_LEN    = 20                          # chars; shorter = skip


# ==========================================
# TEXT UTILS
# ==========================================
def basic_clean(text: str) -> str:
    text = re.sub(r"\[?\d{1,2}:\d{2}(:\d{2})?\]?", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fingerprint(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


# ==========================================
# PDF EXTRACTOR
# ==========================================
def extract_pdf(file_path: str) -> List[Dict]:
    results = []
    seen = set()
    filename = os.path.basename(file_path)

    try:
        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            ocr_used = False

            if len(text) < Config.MIN_TEXT_LEN:
                # OCR fallback
                try:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    text = pytesseract.image_to_string(img, lang=Config.OCR_LANG)
                    ocr_used = True
                except Exception as e:
                    print(f"  [OCR ERROR] page {page_num}: {e}")
                    continue

            text = basic_clean(text)
            if len(text) < Config.MIN_TEXT_LEN:
                continue

            fp = fingerprint(text)
            if fp in seen:
                continue
            seen.add(fp)

            results.append({
                "source_file": filename,
                "type": "pdf",
                "page_or_slide": page_num,
                "extraction_method": "ocr" if ocr_used else "text",
                "raw_text": text
            })

    except Exception as e:
        print(f"  [PDF ERROR] {filename}: {e}")
        raise

    return results


# ==========================================
# PPTX EXTRACTOR
# ==========================================
def extract_pptx(file_path: str) -> List[Dict]:
    results = []
    seen = set()
    filename = os.path.basename(file_path)

    try:
        prs = Presentation(file_path)
        for slide_num, slide in enumerate(prs.slides, start=1):
            parts = []
            ocr_used = False

            for shape in slide.shapes:
                # Normal text
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        line = " ".join(r.text for r in para.runs).strip()
                        if line:
                            parts.append(line)

                # Image → OCR
                if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
                    try:
                        img = Image.open(io.BytesIO(shape.image.blob)).convert("RGB")
                        ocr_text = pytesseract.image_to_string(img, lang=Config.OCR_LANG).strip()
                        if len(ocr_text) >= Config.MIN_TEXT_LEN:
                            parts.append(ocr_text)
                            ocr_used = True
                    except Exception as e:
                        print(f"  [OCR ERROR] slide {slide_num}: {e}")

            text = basic_clean(" ".join(parts))
            if len(text) < Config.MIN_TEXT_LEN:
                continue

            fp = fingerprint(text)
            if fp in seen:
                continue
            seen.add(fp)

            results.append({
                "source_file": filename,
                "type": "pptx",
                "page_or_slide": slide_num,
                "extraction_method": "ocr" if ocr_used else "text",
                "raw_text": text
            })

    except Exception as e:
        print(f"  [PPTX ERROR] {filename}: {e}")
        raise

    return results


# ==========================================
# LOGGER
# ==========================================
def log_result(filename: str, duration: float, num_pages: int,
               ocr_used: bool, error: str = ""):
    row = {
        "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "File": [filename],
        "Processing Time (s)": [round(duration, 3)],
        "Pages/Slides Extracted": [num_pages],
        "OCR Used": ["yes" if ocr_used else "no"],
        "Error": [error]
    }
    df_new = pd.DataFrame(row)
    os.makedirs(os.path.dirname(Config.LOG_PATH), exist_ok=True)

    if os.path.exists(Config.LOG_PATH):
        df_old = pd.read_excel(Config.LOG_PATH)
        pd.concat([df_old, df_new], ignore_index=True).to_excel(Config.LOG_PATH, index=False)
    else:
        df_new.to_excel(Config.LOG_PATH, index=False)


# ==========================================
# MAIN
# ==========================================
SUPPORTED = {".pdf": extract_pdf, ".pptx": extract_pptx}

if __name__ == "__main__":
    os.makedirs(os.path.dirname(Config.OUTPUT_JSON), exist_ok=True)

    folder = Config.INPUT_FOLDER
    files = [f for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in SUPPORTED]

    if not files:
        print(f"No PDF/PPTX files found in {folder}")
        exit(1)

    all_extracts = []

    for filename in sorted(files):
        path = os.path.join(folder, filename)
        ext = os.path.splitext(filename)[1].lower()
        extractor = SUPPORTED[ext]

        print(f"\n📄 Extracting: {filename}")
        start = time.time()
        error_msg = ""
        extracts = []

        try:
            extracts = extractor(path)
            ocr_flag = any(e["extraction_method"] == "ocr" for e in extracts)
            print(f"  ✅ {len(extracts)} pages/slides | OCR: {'yes' if ocr_flag else 'no'}")
        except Exception as e:
            error_msg = str(e)
            ocr_flag = False

        duration = time.time() - start
        log_result(filename, duration, len(extracts), ocr_flag, error_msg)
        all_extracts.extend(extracts)

    # Save all extracts to JSON
    with open(Config.OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_extracts, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done. {len(all_extracts)} total pages/slides saved to:")
    print(f"   {Config.OUTPUT_JSON}")
    print(f"\n▶️  Now run: python stage2_chunk_embed.py")