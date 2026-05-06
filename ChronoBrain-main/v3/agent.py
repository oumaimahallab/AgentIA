from __future__ import annotations

from typing import Any, Dict

from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent

from config import HRConfig, default_config
from ..chronobrain_hr.indexing import get_or_build_index
from ..chronobrain_hr.tools.leave import calculate_leave_balance, working_days_between
from ..chronobrain_hr.validation import is_valid_query


def _tool_calculate_leave_balance(
    start_date: str,
    as_of: str,
    entitlement_per_year: float,
    taken_days: float = 0.0,
    carryover_days: float = 0.0,
    accrual: str = "monthly",
) -> Dict[str, Any]:
    res = calculate_leave_balance(
        start_date=start_date,
        as_of=as_of,
        entitlement_per_year=entitlement_per_year,
        taken_days=taken_days,
        carryover_days=carryover_days,
        accrual=accrual,
    )
    return {
        "start_date": res.start_date.isoformat(),
        "as_of": res.as_of.isoformat(),
        "entitlement_per_year": res.entitlement_per_year,
        "accrued_days": res.accrued_days,
        "taken_days": res.taken_days,
        "carryover_days": res.carryover_days,
        "balance_days": res.balance_days,
        "notes": "Valeur générique (à ajuster selon la politique interne si elle est précisée dans les transcriptions).",
    }


def _tool_working_days_between(start_date: str, end_date: str) -> Dict[str, Any]:
    # ISO YYYY-MM-DD, inclusive
    from datetime import datetime

    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
    ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    days = working_days_between(sd, ed)
    return {"start_date": sd.isoformat(), "end_date": ed.isoformat(), "working_days_inclusive": days}


def build_hr_agent(cfg: HRConfig | None = None) -> ReActAgent:
    """
    Builds a retrieval-augmented agent over transcripts, with HR tools:
    - leave balance calculator
    - working days calculator (for vacation requests)
    """
    cfg = cfg or default_config()

    Settings.llm = Ollama(model=cfg.llm_model, request_timeout=360.0)
    Settings.embed_model = HuggingFaceEmbedding(model_name=cfg.embed_model)

    index = get_or_build_index(cfg)
    retriever = index.as_retriever(similarity_top_k=cfg.top_k)

    tools = [
        FunctionTool.from_defaults(
            fn=_tool_calculate_leave_balance,
            name="calculate_leave_balance",
            description=(
                "Calcule un solde de congés/vacances (générique) avec une méthode d'acquisition "
                "mensuelle ou journalière. Paramètres: start_date (YYYY-MM-DD), as_of (YYYY-MM-DD), "
                "entitlement_per_year, taken_days, carryover_days, accrual."
            ),
        ),
        FunctionTool.from_defaults(
            fn=_tool_working_days_between,
            name="working_days_between",
            description="Compte le nombre de jours ouvrés entre deux dates incluses (YYYY-MM-DD), hors week-end.",
        ),
    ]

    system_prompt = (
        "Vous êtes ChronoBrain HR, l'assistant interne pour les employés.\n"
        "Règles:\n"
        "- Utilisez les transcriptions comme source principale pour les règles internes (process, politiques, paramétrage).\n"
        "- Si une information n'existe pas dans les transcriptions, dites-le clairement et proposez la do ée manquante.\n"
        "- Pour les calculs (congés/vacances, jours ouvrés), utilisez les outils disponibles et présentez le résultat clairement.\n"
        "- Vous pouvez produire du code (scripts, requêtes, pseudo-code) quand on vous le demande.\n"
        "- Répondez en français.\n"
    )

    return ReActAgent.from_tools(
        tools=tools,
        retriever=retriever,
        system_prompt=system_prompt,
        verbose=False,
    )


class ChronoBrainHR:
    """
    Thin wrapper to apply the same input validation behavior as your older CLI.
    """

    def __init__(self, agent: ReActAgent):
        self._agent = agent

    def chat(self, text: str) -> str:
        t = (text or "").strip()
        if not is_valid_query(t):
            return "Veuillez poser une question complète."
        return str(self._agent.chat(t))


def build_hr_chatbot(cfg: HRConfig | None = None) -> ChronoBrainHR:
    return ChronoBrainHR(build_hr_agent(cfg))

