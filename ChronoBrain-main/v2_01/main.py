"""
main.py — ChronoBrain CLI chatbot

Usage:
    python main.py
    python main.py --debug        # show retrieval scores
    python main.py --no-eval      # skip faithfulness check

Commands during chat:
    quit / exit    — exit
    reset          — clear history + cache
    stats          — show session metrics
    debug on/off   — toggle retrieval score display
"""

import sys
import time
import logging
import argparse

from config import LOG_LEVEL
from validator import is_valid_query
from hybrid_retriever import HybridRetriever
from llm import build_prompt, safe_complete, ConversationHistory
from postprocess import strip_hallucinations, faithfulness_check
from cache import ResponseCache

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, LOG_LEVEL, logging.WARNING),
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("chronobrain.main")

FALLBACK_MSG = (
    "Je n'ai pas trouvé cette information dans les données de formation."
)
TIMEOUT_MSG = (
    "Le modèle met trop de temps à répondre. "
    "Veuillez réessayer ou simplifier votre question."
)


# ── Metrics tracker ───────────────────────────────────────────────────────────

class Metrics:
    def __init__(self):
        self.queries      = 0
        self.total_lat    = 0.0
        self.fallbacks    = 0
        self.cache_hits   = 0
        self.stripped     = 0
        self.unfaithful   = 0

    def record(self, latency: float, is_fallback: bool,
               was_stripped: bool, is_unfaithful: bool) -> None:
        self.queries   += 1
        self.total_lat += latency
        if is_fallback:   self.fallbacks  += 1
        if was_stripped:  self.stripped   += 1
        if is_unfaithful: self.unfaithful += 1

    def print_inline(self, latency: float, is_fallback: bool,
                     was_stripped: bool, is_unfaithful: bool) -> None:
        self.record(latency, is_fallback, was_stripped, is_unfaithful)
        avg  = self.total_lat / self.queries
        flags = ""
        if is_fallback:   flags += " [fallback]"
        if was_stripped:  flags += " [stripped]"
        if is_unfaithful: flags += " [⚠ unfaithful]"
        print(f"[Metrics] #{self.queries} | {latency:.1f}s | moy {avg:.1f}s{flags}")

    def print_stats(self) -> None:
        if self.queries == 0:
            print("Aucune requête enregistrée.\n")
            return
        avg = self.total_lat / self.queries
        print(
            f"\n[Stats]\n"
            f"  Requêtes LLM  : {self.queries}\n"
            f"  Cache hits    : {self.cache_hits}\n"
            f"  Latence moy   : {avg:.1f}s\n"
            f"  Fallbacks     : {self.fallbacks}\n"
            f"  Réponses épurées : {self.stripped}\n"
            f"  Non-fidèles   : {self.unfaithful}\n"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main(debug: bool = False, no_eval: bool = False) -> None:
    print("Initialisation de ChronoBrain…")

    try:
        retriever = HybridRetriever.load()
    except FileNotFoundError as e:
        print(f"\nErreur: {e}")
        sys.exit(1)

    history = ConversationHistory()
    cache   = ResponseCache()
    metrics = Metrics()

    print("\nChronoBrain prêt.")
    print("Commandes: 'quit' · 'reset' · 'stats' · 'debug on/off'\n")

    while True:
        try:
            user_input = input("[ChronoBrain] Votre question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if not user_input:
            continue

        # ── Built-in commands ─────────────────────────────────────────────────
        cmd = user_input.lower()
        if cmd in ("quit", "exit"):
            break
        if cmd == "reset":
            history.clear(); cache.clear()
            print("Historique et cache effacés.\n")
            continue
        if cmd == "stats":
            metrics.print_stats()
            continue
        if cmd == "debug on":
            debug = True;  print("Debug activé.\n");  continue
        if cmd == "debug off":
            debug = False; print("Debug désactivé.\n"); continue

        # ── Input validation ──────────────────────────────────────────────────
        valid, reason = is_valid_query(user_input)
        if not valid:
            print(f"{reason}\n")
            continue

        # ── Cache hit ─────────────────────────────────────────────────────────
        cached = cache.get(user_input)
        if cached:
            metrics.cache_hits += 1
            print(f"\n[cache] {cached}\n")
            continue

        # ── Hybrid retrieval ──────────────────────────────────────────────────
        print("Recherche en cours…")
        chunks, used_fallback = retriever.retrieve(user_input, debug=debug)

        if not chunks:
            print(f"\nRéponse: {FALLBACK_MSG}\n")
            history.add(user_input, FALLBACK_MSG)
            continue

        # ── Build context string ──────────────────────────────────────────────
        context = "\n\n".join(c.text for c in chunks)

        # ── Build prompt + call LLM ───────────────────────────────────────────
        prompt = build_prompt(
            context       = context,
            chunks        = chunks,
            history       = history.get(),
            question      = user_input,
            low_confidence= used_fallback,
        )

        print("Réflexion…")
        t0      = time.time()
        raw     = safe_complete(prompt)
        latency = time.time() - t0

        if raw is None:
            print(f"\nRéponse: {TIMEOUT_MSG}\n")
            continue

        # ── Post-processing ───────────────────────────────────────────────────
        answer_before = raw
        answer        = strip_hallucinations(raw)
        was_stripped  = answer != answer_before

        # ── Faithfulness check ────────────────────────────────────────────────
        is_unfaithful = False
        if not no_eval:
            faith = faithfulness_check(user_input, context, answer)
            is_unfaithful = not faith["faithful"]
            if is_unfaithful:
                log.warning("Low faithfulness: %s", faith)

        metrics.print_inline(latency, used_fallback, was_stripped, is_unfaithful)

        # ── Display ───────────────────────────────────────────────────────────
        print(f"\nRéponse:\n{answer}\n")

        if debug:
            print("[Sources utilisées]")
            for c in chunks:
                asr = " ⚠ASR" if c.has_asr_warning else ""
                print(f"  score={c.score:.3f} | {c.source} [{c.start_time}→{c.end_time}]{asr}")
            print()

        # ── Update history + cache ────────────────────────────────────────────
        FALLBACK_PHRASES = [
            "je n'ai pas trouvé",
            "je ne sais pas",
            "je n'ai pas cette information",
        ]
        is_explicit_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)

        history.add(user_input, answer)
        if not is_explicit_fallback and not is_unfaithful:
            cache.set(user_input, answer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChronoBrain chatbot")
    parser.add_argument("--debug",   action="store_true", help="Show retrieval scores")
    parser.add_argument("--no-eval", action="store_true", help="Skip faithfulness check")
    args = parser.parse_args()
    main(debug=args.debug, no_eval=args.no_eval)
