import os
import json
import faiss
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from groq import Groq

# ===============================
# CONFIGURATION
# ===============================

DOCUMENTS_JSON = "data/processed/documents.json"
VECTOR_DIR = "../data/vectorstore/faiss_index"  # fallback si documents.json absent
TOP_K = 15  # Augmenté pour meilleur contexte et plus de robustesse
MODEL_NAME = "llama-3.1-8b-instant"

api_key = os.getenv("GROQ_API_KEY",  "YOUR_KEY_HERE")
if not api_key:
    raise RuntimeError("[ERROR] GROQ_API_KEY non défini")
client = Groq(api_key=api_key)

# ===============================
# CHARGEMENT FAISS
# ===============================

print("[*] Chargement FAISS et embeddings...")

embed_model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# ===============================
# CHARGEMENT DIRECT documents.json (PRIORITÉ)
# ===============================

def _load_from_documents_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        docs = json.load(f)
    texts_local = []
    metas_local = []
    for d in docs:
        t = (d.get("text") or "").strip()
        if not t:
            continue
        texts_local.append(t)
        metas_local.append({
            "source": d.get("source", "Document"),
            "location": d.get("location", ""),
            "type": d.get("type", ""),
        })
    return texts_local, metas_local


loaded = _load_from_documents_json(DOCUMENTS_JSON)
if loaded is not None:
    texts, metadatas = loaded
    print(f"[*] Source: {DOCUMENTS_JSON} ({len(texts)} documents)")
    # Build in-memory FAISS index on documents.json (rapide: ~232 docs)
    doc_embs = embed_model.encode(texts, convert_to_numpy=True).astype(np.float32)
    dim = int(doc_embs.shape[1])
    index = faiss.IndexFlatL2(dim)
    index.add(doc_embs)
else:
    # Fallback: utilise l'ancien store FAISS sur disque si documents.json absent
    index = faiss.read_index(os.path.join(VECTOR_DIR, "index.faiss"))
    with open(os.path.join(VECTOR_DIR, "metadata.json"), "r", encoding="utf-8") as f:
        store = json.load(f)
    texts = store["texts"]
    metadatas = store["metadatas"]
    print(f"[*] Source: {VECTOR_DIR} (fallback) ({len(texts)} chunks)")

# ===============================
# TYPE DE CHUNK (STRUCTUREL)
# ===============================

def infer_chunk_type(text: str) -> str:
    t = text.lower()
    lines = text.split("\n")

    # PROCESSUS STRUCTURÉ (Étapes) — extraction PPTX améliorée
    # ex: "Étapes\n\nÉtape 1: ...\n\nÉtape 2: ..."
    if re.search(r"\bÉtapes\b", text) and re.search(r"(?m)^\s*Étape\s*1\s*:", text):
        if re.search(r"(?m)^\s*Étape\s*2\s*:", text):
            return "structured_steps"

    # GLOSSAIRE / TABLEAU NORMATIF (très haut priorité pour les listes de types)
    # Cherche des motifs: "Terme | Définition", "Code | Description", etc.
    if re.search(r"(?m)^\s*(Terme|Code|Type|Absences?|Modalit|Catégor|Heures?|Nom)\s*\|\s*(Définition|Description|Traitement)", t):
        return "normative_list"
    
    # Glossaire avec format "Terme : Définition" répété plusieurs fois
    if re.search(r"(?m)^Termes?\s+clés", t):
        return "normative_list"
    if re.search(r"(?m)^Glossaire", t):
        return "normative_list"
    
    # SOMMAIRES/TABLES contenant des listes d'énumérations (types, catégories)
    if re.search(r"(?m)^Sommaire|^Table des matières", t):
        # Cherche des énumérations (plusieurs lignes avec des mots-clés de types)
        if re.search(r"(Demande d'absence|Arrêt maladie|Absences|types|catégorie)", t):
            return "normative_list"

    # LISTE / TABLEAU NORMATIF — motifs élargis (exports PPTX/PDF souvent sans espace après "1.")
    list_line = re.compile(
        r"(?m)^\s*(?:"
        r"\d+[\.\)][ \t]*\S|"  # 1.xxx ou 1) xxx
        r"[-*•\u2022\u2023\u25cf\u25cb\u25e6·][ \t]*\S"  # puces courantes
        r")"
    )
    if list_line.search(text) and len([ln for ln in lines if ln.strip()]) >= 2:
        return "normative_list"

    if re.search(r"^\s*(\d+\.|[-•*])\s", text, re.MULTILINE):
        if len(lines) >= 2:
            return "normative_list"

    # TABLEAU FORMATÉ (avec colonnes, tirets, etc.)
    if "|" in text or "---" in text or re.search(r"[A-Z][A-Z ]{2,}", text):
        if len(lines) >= 2:
            return "normative_list"

    # Plusieurs lignes courtes + vocabulaire « types / HS » → liste sémantique (pas procédure UI)
    trimmed = [ln.strip() for ln in lines if ln.strip()]
    if len(trimmed) >= 2 and re.search(
        r"\b(type|types|heures?\s+supplément|supplémentaires?|modalit|catégor|vari|classique|structur|absences?|demande|arrêt|congés?)\b",
        t,
    ):
        avg = sum(len(ln) for ln in trimmed) / len(trimmed)
        if avg < 160:
            return "normative_list"

    # PROCÉDURE UI (étapes, actions, clics)
    if re.search(r"\b(cliquez|sélectionnez|validez|confirmez|appuyez|entrez|saisir|tape)\b", t):
        return "procedure"
    if re.search(r"(?m)(?:\bétape\b|\bstep\b|^\s*\d+\.\s+(?:cliquez|sélectionnez|ouvrez|allez))", t):
        return "procedure"
    if t.count("\n") >= 2:
        return "procedure"

    # DÉFINITION (courte explication)
    if re.search(r"\b(est |désigne|correspond à|définition|signifie|veut dire)\b", t):
        if len(t.split()) < 300:  # Augmenté de 200 à 300 pour accepter plus de contexte
            return "definition"

    return "explanation"

# ===============================
# INTENTION QUESTION
# ===============================

def detect_intent(question: str) -> str:
    q = question.lower().strip()
    
    # PROCÉDURE: "Comment...", "Explique...", "Étapes...", "Faire..."
    # PRIORITÉ HAUTE: Si la question contient explicitement "étapes" ou "processus"
    # ⚠️ Support accents ET pas d'accents: "étape" et "etape"
    if "étape" in q or "etape" in q or "processus" in q or "démarche" in q:
        return "procedure"
    
    procedure_keywords = [
        "comment", "comment faire", "explique", "comment procéder",
        "faire", "réaliser",
        "ajouter", "créer", "modifier", "supprimer", "approuver",
        "valider", "soumettre", "envoyer", "configurer", "cliquer",
        "sélectionner", "entrer", "saisir", "saisie", "accéder", "ouvrir",
        "afficher", "générer", "importer", "exporter", "charger"
    ]
    if any(kw in q for kw in procedure_keywords):
        return "procedure"
    
    # DÉFINITION: "C'est quoi", "Qu'est-ce", "Signifie", "Définition"
    definition_keywords = [
        "c est quoi", "c'est quoi", "qu'est-ce", "qu est ce",
        "définition", "signifie", "veut dire", "c'est", "est ce que",
        "qu est ce que", "qu'est-ce que", "désigne", "correspond",
        "signification", "sens", "contexte", "qu'est", "cest",
        "comprise", "entendre par", "appelle", "nom", "terme"
    ]
    if any(kw in q for kw in definition_keywords):
        return "definition"
    
    # ÉNUMÉRATION: "Types", "Quels", "Liste", "Lesquels", "Énumère"
    list_keywords = [
        "types", "quels", "lesquels", "liste", "énumère", "énumérez",
        "énumération", "combien", "nombre", "combien de", "quoi", "quoi d'autre",
        "tous les", "toutes les", "listes", "répertoire", "catégories",
        "catégorie", "exemples", "exemple", "cas", "variantes"
    ]
    if any(kw in q for kw in list_keywords):
        return "list_types"
    
    # Par défaut: explication/discussion
    return "explanation"

# ===============================
# RETRIEVAL FAISS
# ===============================

def retrieve_chunks(question: str, intent: str | None = None):
    """FAISS top-k ; pour les questions « types / liste », 2e requête élargie pour ramener les bons paragraphes."""
    if intent is None:
        intent = detect_intent(question)

    def _search(q: str, k: int):
        q_emb = embed_model.encode([q], convert_to_numpy=True)
        return index.search(q_emb, k)

    # PRE-SCAN AGRESSIF pour les procédures avec étapes structurées
    # (avant la recherche FAISS habituelle)
    best: dict[int, float] = {}
    
    if intent == "procedure":
        ql = question.lower()
        
        # Cherche TOUS les documents avec Étapes structurées
        best_procedure_idx = None
        best_procedure_steps = 0
        
        for idx, txt in enumerate(texts):
            tl = txt.lower()
            step_count = len(re.findall(r"(?m)^\s*Étape\s+\d+\s*:", txt))
            
            # Si question sur astreintes ET document a 6 étapes structurées
            if "astreint" in ql and step_count >= 6 and "astreint" in tl and "intervention" in tl:
                best[idx] = -1000.0  # Distance EXTRÊMEMENT BASSE
                best_procedure_idx = idx
                best_procedure_steps = step_count
                break  # On l'a trouvé, on peut arrêter
        
        # Si pas trouvé avec 6 étapes, chercher les documents avec 4+ étapes
        if best_procedure_idx is None:
            for idx, txt in enumerate(texts):
                tl = txt.lower()
                step_count = len(re.findall(r"(?m)^\s*Étape\s+\d+\s*:", txt))
                
                if step_count >= 4 and "processus général" in tl:
                    if "astreint" in ql and "astreint" in tl:
                        best[idx] = -500.0
                        best_procedure_idx = idx

    # Recherche FAISS standard
    dists, indices = _search(question, TOP_K)
    for rank, idx in enumerate(indices[0]):
        if 0 <= idx < len(texts):
            d = float(dists[0][rank])
            # Ne pas overwrite les documents trouvés en pre-scan (distance très basse)
            if idx not in best or d < best[idx]:
                best[idx] = d

    if intent == "list_types":
        # Recherche 1: Ajout de mots-clés pour les énumérations
        alt_q = question + " liste des types catégories modalités variante énumération"
        d2, i2 = _search(alt_q, TOP_K)
        for rank, idx in enumerate(i2[0]):
            if 0 <= idx < len(texts):
                d = float(d2[0][rank])
                if idx not in best or d < best[idx]:
                    best[idx] = d
        
        # Recherche 2: Ciblage spécifique des GLOSSAIRES et TABLEAUX
        alt_q2 = question + " glossaire définition tableau termes clés"
        d3, i3 = _search(alt_q2, TOP_K)
        for rank, idx in enumerate(i3[0]):
            if 0 <= idx < len(texts):
                d = float(d3[0][rank])
                # Boost la priorité des glossaires (distance * 0.7)
                if idx not in best or d * 0.7 < best[idx]:
                    best[idx] = d * 0.7

    # Pour les procédures: recherche alternative
    if intent == "procedure" and len([k for k in best if best[k] < -100]) == 0:
        alt_q = question + " Étapes Étape 1: Étape 2: Processus général"
        d2, i2 = _search(alt_q, TOP_K)
        for rank, idx in enumerate(i2[0]):
            if 0 <= idx < len(texts):
                d = float(d2[0][rank])
                if idx not in best or d < best[idx]:
                    best[idx] = d

    ordered_idx = sorted(best.keys(), key=lambda i: best[i])[:TOP_K]

    chunks = []
    for idx in ordered_idx:
        chunks.append({
            "text": texts[idx],
            "meta": metadatas[idx],
            "chunk_type": infer_chunk_type(texts[idx]),
        })

    if not chunks:
        q_emb = embed_model.encode([question], convert_to_numpy=True)
        _, indices = index.search(q_emb, min(30, len(texts)))
        for idx in indices[0]:
            if 0 <= idx < len(texts):
                chunks.append({
                    "text": texts[idx],
                    "meta": metadatas[idx],
                    "chunk_type": infer_chunk_type(texts[idx]),
                })

    return chunks

# ===============================
# PRIORISATION
# ===============================

def _keyword_overlap_score(question: str, chunk_text: str) -> float:
    """Petit bonus lexical pour rapprocher la question des bons paragraphes."""
    q = re.findall(r"[a-zàâäéèêëïîôùûüç]{4,}", question.lower())
    t = chunk_text.lower()
    if not q:
        return 0.0
    hits = sum(1 for w in q if w in t)
    return min(hits / max(len(q), 1), 1.0) * 0.5


def rerank_chunks(chunks: list, intent: str, question: str = "") -> list:
    """Réordonne les chunks par pertinence (types de questions + chevauchement lexical)."""

    def score_chunk(c, intent):
        type_match = 0
        text_lower = c["text"].lower()
        chunk_text = c["text"]
        
        # Pour les questions de PROCÉDURES
        if intent == "procedure":
            chunk_type = c["chunk_type"]
            
            # Compter le nombre d'étapes structurées (Étape 1:, Étape 2:, etc.)
            step_count = len(re.findall(r"(?m)^\s*Étape\s+\d+\s*:", chunk_text))
            
            # Priorité 1: Étapes bien structurées (4+ étapes)
            if chunk_type == "structured_steps" and step_count >= 4:
                type_match = 5
            # Priorité 2: Étapes structurées (2-3 étapes)
            elif chunk_type == "structured_steps":
                type_match = 4
            # Priorité 3: Autres procédures
            elif chunk_type == "procedure":
                type_match = 2
            
            # PÉNALITÉ: Si c'est "Principe et application" sans structure claire
            if "principe et application" in text_lower and step_count < 4:
                type_match = max(type_match - 2, 0)
        
        # Pour les questions de LISTES
        elif intent == "list_types":
            chunk_type = c["chunk_type"]
            
            # Priorité 1: Glossaires explicites
            if "glossaire" in text_lower or "termes clés" in text_lower:
                type_match = 4
            # Priorité 2: Tableaux/listes normatives
            elif chunk_type == "normative_list":
                type_match = 3
            # Priorité 3: Sommaires/Tables contenant des énumérations de types
            elif "sommaire" in text_lower or "table des matières" in text_lower:
                if re.search(r"^\s*\w+[\s\n]+\w+[\s\n]+\w+", c["text"]):  # Énumération
                    type_match = 2
            # Priorité 4: Explications contenant des types
            elif chunk_type in ("procedure", "explanation"):
                if re.search(
                    r"\b(type|types|catégor|modalit|vari|classique|structur|heures?\s+supplément|supplémentaires?|demande|arrêt|congés?)\b",
                    text_lower,
                ):
                    type_match = 1
        
        # Pour les PROCÉDURES
        elif intent == "procedure":
            if c["chunk_type"] == "structured_steps":
                type_match = 3
            elif c["chunk_type"] == "procedure":
                type_match = 2
        
        # Pour les DÉFINITIONS
        elif intent == "definition":
            if c["chunk_type"] == "definition":
                type_match = 2

        length_score = min(len(c["text"]) / 500, 1)
        keyword_score = _keyword_overlap_score(question, c["text"])
        
        return type_match + length_score + keyword_score

    return sorted(
        chunks,
        key=lambda c: score_chunk(c, intent),
        reverse=True,
    )

# ===============================
# RESTITUTION FIDÈLE (LISTES / TABLEAUX / STRUCTURES)
# ===============================

def direct_restitution(chunks: list, intent: str = "explanation"):
    """Retourne le contenu exact sans traitement LLM UNIQUEMENT pour structures très claires"""
    
    # Priorité 0: Processus "Étapes" (procédures)
    if intent == "procedure":
        for c in chunks:
            if c.get("chunk_type") == "structured_steps":
                text = c["text"].strip()
                # Retourne uniquement la section "Étapes" (plus fidèle, moins de bruit)
                m = re.search(r"(?s)\bÉtapes\b\s*(.*)$", text)
                if m:
                    steps_part = ("Étapes\n\n" + m.group(1).strip()).strip()
                    return (
                        "Voici l'information EXACTE telle que définie dans les documents :\n\n"
                        + steps_part
                    )
                return (
                    "Voici l'information EXACTE telle que définie dans les documents :\n\n"
                    + text
                )

    # Priorité 1: Listes / tableaux (uniquement pour les questions de type liste)
    if intent == "list_types":
        for c in chunks:
            text = c["text"].strip()
            
            # Cas 1: Tableau formaté avec |
            if "|" in text:
                if c["chunk_type"] == "normative_list" or ":" in text:
                    return (
                        "Voici l'information EXACTE telle que définie dans les documents :\n\n"
                        + text
                    )
            
            # Cas 2: Listes avec puces/tirets
            if text.count("•") >= 2 or text.count("-") >= 3 or "\n- " in text or "\n• " in text:
                return (
                    "Voici l'information EXACTE telle que définie dans les documents :\n\n"
                    + text
                )
            
            # Cas 3: Énumération simple avec des lignes numérotées ou titres + définitions
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            if len(lines) >= 3:
                tl = text.lower()
                # Cherche les motifs de listes (Code:, Type:, Nom:, Terme:)
                if re.search(r"(?m)^\s*\w+\s*[:|]\s*", text):
                    if re.search(
                        r"\b(type|types|code|terme|absences?|heures?\s+|modalit|catégor)\b",
                        tl,
                    ):
                        return (
                            "Voici l'information EXACTE telle que définie dans les documents :\n\n"
                            + text
                        )
    
    # Priorité 2: Définitions courtes et précises UNIQUEMENT
    if intent == "definition":
        for c in chunks:
            if c["chunk_type"] == "definition":
                text = c["text"].strip()
                # Définition bien dimensionnée et claire
                if 50 < len(text) < 500:
                    return text
    
    return None

# ===============================
# BUILD PROMPT - ADAPTÉ AU TYPE DE QUESTION
# ===============================

def build_prompt(question: str, chunks: list, intent: str):
    context = "\n\n---\n\n".join(c["text"] for c in chunks)
    
    # Prompt adapté selon le type de question
    if intent == "procedure":
        instructions = """Fournis une réponse ÉTAPE PAR ÉTAPE, NUMÉROTÉE et STRUCTURÉE.
Utilise le format:
1. [première action]
2. [deuxième action]
etc.

Sois clair, précis et complet."""
    elif intent == "definition":
        instructions = """Donne une définition PRÉCISE et CONCISE. Inclus des détails essentiels."""
    elif intent == "list_types":
        instructions = """Énumère TOUS les éléments/types/catégories trouvés dans le contexte. Sois complet.
Si le contexte décrit plusieurs sortes (ex. types d'heures, modalités), liste-les clairement même sans mot exact « type » dans le passage."""
    else:  # explanation
        instructions = """Explique le concept en détail avec le contexte fourni."""

    return f"""Tu es un assistant expert qui répond uniquement à partir des documents fournis.

STYLE: {instructions}

RÈGLES STRICTES:
✅ RÉPONDS basé UNIQUEMENT sur le contexte fourni
✅ Sois précis, factuel et complet
✅ Cite des exemples du contexte si disponibles
[NO] N'AJOUTE JAMAIS d'informations externes
[NO] Si aucun passage du contexte ne permet de répondre, dis: "Je n'ai pas trouvé cette information"
[OK] Si le contexte répond partiellement (ex. liste de catégories sans le mot « type »), synthétise quand même à partir du texte fourni
[NO] Ne fais JAMAIS de suppositions ou d'extrapolations

CONTEXTE DES DOCUMENTS:
{context}

QUESTION DE L'UTILISATEUR:
{question}

RÉPONSE COMPLÈTE (basée uniquement sur le contexte):"""

# ===============================
# APPEL GROQ
# ===============================

def call_groq(prompt: str) -> str:
    """Appelle Groq avec gestion d'erreurs stricte"""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un assistant expert qui répond précisément basé sur les documents fournis. Ne fabrique jamais d'informations. Si l'info n'existe pas, dis-le."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Modéré pour équilibre créativité/factualité
            max_tokens=1000
        )
        if not completion.choices or not completion.choices[0].message:
            raise ValueError("Réponse vide de Groq")
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] Erreur Groq: {str(e)}")
        raise

# ===============================
# AGENT PRINCIPAL - ROBUSTE POUR TOUS LES CAS
# ===============================

def ask_agent(question: str):
    """
    Agent RAG universel - répond à TOUS les types de questions
    Gère: procédures, définitions, listes, explications, questions diverses
    """
    try:
        # Validation entrée
        if not question or not isinstance(question, str):
            return "Veuillez poser une question valide.", []
        
        question = question.strip()
        
        # Détection du type de question
        intent = detect_intent(question)
        
        chunks = retrieve_chunks(question, intent)
        
        if not chunks:
            return "Je n'ai pas trouvé d'informations pertinentes dans les documents pour cette question.", []
        
        chunks = rerank_chunks(chunks, intent, question)
        
        # ===== STRATÉGIE 1: Restitution directe UNIQUEMENT pour listes/définitions claires =====
        if intent in ["procedure", "list_types", "definition"]:
            direct = direct_restitution(chunks, intent)
            if direct:
                if intent == "procedure":
                    # Pour éviter du bruit, ne cite que la première source "Étapes" pertinente
                    for c in chunks:
                        if c.get("chunk_type") == "structured_steps":
                            src = f"{c['meta'].get('source', 'Document')} — {c['meta'].get('location', 'section')}"
                            return direct, [src]
                    return direct, []

                sources = {
                    f"{c['meta'].get('source', 'Document')} — {c['meta'].get('location', 'section')}"
                    for c in chunks if c["chunk_type"] in ["normative_list", "definition"]
                }
                return direct, list(sources) if sources else []
        
        # ===== STRATÉGIE 2: LLM pour procédures et explications =====
        num_chunks = min(7, len(chunks))  # Plus de contexte pour les procédures
        prompt = build_prompt(question, chunks[:num_chunks], intent)
        
        try:
            answer = call_groq(prompt)
        except Exception as e:
            # Fallback: retourner un contexte plus complet si LLM échoue
            if len(chunks) > 0 and len(chunks[0]["text"]) > 100:
                # Retourner le contenu complet du meilleur chunk
                answer = f"Voici l'information pertinente trouvée:\n\n{chunks[0]['text']}"
            else:
                answer = "\n\n---\n\n".join([
                    f"[Contexte {i+1}] {c['text']}"
                    for i, c in enumerate(chunks[:3])
                ])
        
        # Extraction des sources
        sources = {
            f"{c['meta'].get('source', 'Document')} — {c['meta'].get('location', 'section')}"
            for c in chunks[:num_chunks]
        }
        
        return answer, list(sources) if sources else []
        
    except Exception as e:
        error_msg = f"Erreur lors du traitement de votre question: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return "Je n'ai pas pu traiter votre question. Veuillez réessayer.", []

# ===============================
# MODE INTERACTIF
# ===============================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent RAG Groq (Chronotime)")
    parser.add_argument("--question", "-q", help="Poser une question en mode non-interactif")
    args = parser.parse_args()

    if args.question:
        q = args.question.strip()
        answer, sources = ask_agent(q)
        print("\n[REPONSE] :")
        print(answer)
        if sources:
            print("\n[SOURCES] :")
            for s in sources:
                print(f"  - {s}")
        raise SystemExit(0)

    print("\n[OK] Agent RAG GROQ OPTIMISE - pret. Tape 'exit' pour quitter.\n")

    while True:
        try:
            q = input("[?] Question : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(Au revoir - lance ce script depuis un terminal interactif)")
            break

        if not q:
            continue
        if q.lower() in ["exit", "quit", "q"]:
            break

        answer, sources = ask_agent(q)

        print("\n[REPONSE] :")
        print(answer)

        if sources:
            print("\n[SOURCES] :")
            for s in sources:
                print(f"  - {s}")

        print("\n" + "-" * 70)