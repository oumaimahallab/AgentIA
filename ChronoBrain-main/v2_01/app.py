"""
 py — Streamlit UI for ChronoBrain (bonus)

Usage:
    streamlit run  py
    streamlit run  py -- --debug
"""

import sys
import time
import argparse
import streamlit as st

from validator import is_valid_query
from hybrid_retriever import HybridRetriever
from llm import build_prompt, safe_complete, ConversationHistory
from postprocess import strip_hallucinations, faithfulness_check
from cache import ResponseCache

FALLBACK_MSG = "Je n'ai pas trouvé cette information dans les données de formation."
TIMEOUT_MSG  = "Le modèle met trop de temps à répondre. Veuillez réessayer."


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ChronoBrain",
    page_icon="🧠",
    layout="centered",
)

st.title("🧠 ChronoBrain")
st.caption("Assistant expert basé sur les formations Inetum · Réponses grondées uniquement")


# ── Session state initialisation ──────────────────────────────────────────────
if "retriever" not in st.session_state:
    with st.spinner("Chargement des index…"):
        try:
            st.session_state.retriever = HybridRetriever.load()
        except FileNotFoundError as e:
            st.error(f"Index non trouvé. Lancez `python ingest.py` d'abord.\n\n{e}")
            st.stop()

if "history_obj" not in st.session_state:
    st.session_state.history_obj = ConversationHistory()

if "cache_obj" not in st.session_state:
    st.session_state.cache_obj = ResponseCache()

if "messages" not in st.session_state:
    st.session_state.messages = []    # list of {role, content}

if "debug" not in st.session_state:
    st.session_state.debug = False


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Options")
    st.session_state.debug = st.toggle("Mode debug (scores de retrieval)", value=st.session_state.debug)

    if st.button("Réinitialiser la conversation"):
        st.session_state.messages = []
        st.session_state.history_obj.clear()
        st.session_state.cache_obj.clear()
        st.success("Conversation réinitialisée.")

    st.divider()
    cache_len = len(st.session_state.cache_obj)
    st.caption(f"Cache: {cache_len} réponses mémorisées")


# ── Chat history display ──────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ── User input ────────────────────────────────────────────────────────────────
user_input = st.chat_input("Posez votre question…")

if user_input:
    # Display user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        # Input validation
        valid, reason = is_valid_query(user_input)
        if not valid:
            st.warning(reason)
            st.session_state.messages.append({"role": "assistant", "content": reason})
            st.stop()

        # Cache check
        cache_obj = st.session_state.cache_obj
        cached = cache_obj.get(user_input)
        if cached:
            st.markdown(cached)
            st.caption("_(réponse depuis le cache)_")
            st.session_state.messages.append({"role": "assistant", "content": cached})
            st.stop()

        # Retrieval
        retriever = st.session_state.retriever
        with st.spinner("Recherche en cours…"):
            chunks, used_fallback = retriever.retrieve(user_input, debug=False)

        if not chunks:
            st.markdown(FALLBACK_MSG)
            st.session_state.messages.append({"role": "assistant", "content": FALLBACK_MSG})
            st.stop()

        # Debug: show retrieved sources
        if st.session_state.debug:
            with st.expander(f"Sources récupérées ({len(chunks)} extraits)", expanded=False):
                for c in chunks:
                    asr = " ⚠" if c.has_asr_warning else ""
                    st.markdown(
                        f"**{c.source}** [{c.start_time} → {c.end_time}] "
                        f"score={c.score:.3f}{asr}\n\n> {c.text[:200]}…"
                    )

        # LLM call
        context = "\n\n".join(c.text for c in chunks)
        prompt  = build_prompt(
            context        = context,
            chunks         = chunks,
            history        = st.session_state.history_obj.get(),
            question       = user_input,
            low_confidence = used_fallback,
        )

        with st.spinner("Réflexion…"):
            t0     = time.time()
            raw    = safe_complete(prompt)
            latency = time.time() - t0

        if raw is None:
            st.error(TIMEOUT_MSG)
            st.session_state.messages.append({"role": "assistant", "content": TIMEOUT_MSG})
            st.stop()

        # Post-processing
        answer = strip_hallucinations(raw)
        faith  = faithfulness_check(user_input, context, answer)

        st.markdown(answer)
        st.caption(f"_{latency:.1f}s · overlap={faith['overlap']:.2f}_")

        if used_fallback:
            st.warning("Confiance faible — vérifiez la réponse.")

        # Update history + cache
        st.session_state.history_obj.add(user_input, answer)
        FALLBACK_PHRASES = ["je n'ai pas trouvé", "je ne sais pas"]
        if not any(p in answer.lower() for p in FALLBACK_PHRASES) and faith["faithful"]:
            cache_obj.set(user_input, answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})
