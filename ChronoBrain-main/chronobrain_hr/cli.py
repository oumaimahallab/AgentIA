from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .agent import build_hr_chatbot
from .config import default_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chronobrain-hr", description="ChronoBrain HR assistant (RAG + leave tools).")
    parser.add_argument(
        "--transcripts-dir",
        default=None,
        help="Override transcripts directory (default: data/transcribe if exists else data/transcripts).",
    )
    parser.add_argument(
        "--chroma-dir",
        default=None,
        help="Override Chroma persistence directory (default: data/chroma_hr).",
    )
    args = parser.parse_args(argv)

    cfg = default_config()
    if args.transcripts_dir:
        cfg = replace(cfg, transcripts_dir=Path(args.transcripts_dir))
    if args.chroma_dir:
        cfg = replace(cfg, chroma_db_dir=Path(args.chroma_dir))

    bot = build_hr_chatbot(cfg)

    print("ChronoBrain HR prêt. Tapez 'quit' pour sortir.\n")
    while True:
        try:
            q = input("[Employé] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            return 0
        if not q:
            continue
        if q.lower() in {"quit", "exit"}:
            return 0

        try:
            resp = bot.chat(q)
            print(f"\n[ChronoBrain HR]\n{resp}\n")
        except Exception as e:
            print(f"\n[Erreur] {e}\n")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

