# unified_chatbot.py — Routes questions to the right RAG pipeline
# - Agent 1 (documents/PDF): ask_agent()  → data/processed/documents.json
# - Agent 2 (transcripts):   brain.query() → ../data/metadata_v13/

import os
import sys
import importlib.util

# ==========================================
# LAZY LOADER — import a file by path
# ==========================================

def load_module(name: str, path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"[ERROR] File not found: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# ==========================================
# CONFIG — adjust paths if needed
# ==========================================

AGENT_DOCS_PATH        = "docs.py"        # file 1 (PDF/documents)
AGENT_TRANSCRIPTS_PATH = "auto_clean_v13.py"       # file 2 (transcripts)

# Keywords that strongly indicate a transcript/video question
TRANSCRIPT_KEYWORDS = [
    "formation", "vidéo", "tutoriel", "transcript", "enregistrement",
    "séquence", "module", "cours", "session", "demo", "démonstration",
    "explication orale", "formateur", "présentateur",
]

# Keywords that strongly indicate a document/PDF question
DOCUMENT_KEYWORDS = [
    "procédure", "guide", "manuel", "document", "pdf", "référence",
    "documentation", "fiche", "notice", "règle", "politique", "processus",
    "tableau", "liste", "type", "définition", "glossaire",
]

# ==========================================
# ROUTER
# ==========================================

def detect_source(question: str) -> str:
    """
    Returns 'transcripts', 'documents', or 'both'.
    Scores keyword matches; ties → 'both'.
    """
    q = question.lower()
    t_score = sum(1 for kw in TRANSCRIPT_KEYWORDS if kw in q)
    d_score = sum(1 for kw in DOCUMENT_KEYWORDS   if kw in q)

    if t_score > d_score:
        return "transcripts"
    if d_score > t_score:
        return "documents"
    return "both"   # no clear signal → query both and merge


# ==========================================
# AGENTS — loaded once at startup
# ==========================================

class UnifiedBot:

    def __init__(self):
        print("=" * 55)
        print("  Loading Agent 1 — Documents / PDF index...")
        print("=" * 55)
        self._docs_mod = load_module("chatbot_docs", AGENT_DOCS_PATH)

        print("\n" + "=" * 55)
        print("  Loading Agent 2 — Transcripts index...")
        print("=" * 55)
        self._trans_mod = load_module("chatbot_transcripts", AGENT_TRANSCRIPTS_PATH)

        # Agent 2 exposes a ChronoBrain instance created at module level
        # If the module creates `brain` at __main__ guard only, instantiate here
        if not hasattr(self._trans_mod, "brain"):
            brain = self._trans_mod.ChronoBrain()
            self._trans_mod.brain = brain

        self._brain = self._trans_mod.brain
        print("\n✅ Both agents ready.\n")

    # ── Agent wrappers ──────────────────────────────────────

    def _ask_docs(self, question: str):
        """Returns (answer, sources)"""
        try:
            return self._docs_mod.ask_agent(question)
        except Exception as e:
            return f"[Agent Documents ERROR] {e}", []

    def _ask_transcripts(self, question: str):
        """Returns answer string"""
        try:
            return self._brain.query(question), []
        except Exception as e:
            return f"[Agent Transcripts ERROR] {e}", []

    # ── Main entry point ────────────────────────────────────

    def ask(self, question: str):
        source = detect_source(question)

        if source == "documents":
            print(f"  🗂️  Routing → Documents index")
            answer, sources = self._ask_docs(question)
            return answer, sources, "documents"

        if source == "transcripts":
            print(f"  🎬  Routing → Transcripts index")
            answer, sources = self._ask_transcripts(question)
            return answer, sources, "transcripts"

        # "both" — query each, pick the longer / more informative answer
        print(f"  🔀  No clear signal — querying both indexes...")

        ans_d, src_d = self._ask_docs(question)
        ans_t, src_t = self._ask_transcripts(question)

        # Merge: present both if they differ meaningfully
        if ans_d and ans_t:
            combined = (
                f"📄 D'après les documents :\n{ans_d}"
                f"\n\n{'─'*50}\n\n"
                f"🎬 D'après les transcriptions :\n{ans_t}"
            )
            return combined, src_d + src_t, "both"

        # Fallback: whichever returned something
        if ans_d:
            return ans_d, src_d, "documents"
        return ans_t, src_t, "transcripts"


# ==========================================
# INTERACTIVE LOOP
# ==========================================

if __name__ == "__main__":
    bot = UnifiedBot()

    print("=" * 55)
    print("  CHRONOBRAIN UNIFIED — Posez vos questions")
    print("  Commandes: 'exit' | 'sources' (toggle)")
    print("=" * 55)

    show_sources = False

    while True:
        try:
            question = input("\n👤 Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Au revoir.")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("👋 Au revoir.")
            break
        if question.lower() == "sources":
            show_sources = not show_sources
            print(f"  ℹ️  Sources: {'ON' if show_sources else 'OFF'}")
            continue

        answer, sources, used = bot.ask(question)

        print(f"\n🤖 Réponse [{used}]:\n{answer}")

        if show_sources and sources:
            print("\n📚 Sources:")
            for s in sources:
                print(f"  - {s}")