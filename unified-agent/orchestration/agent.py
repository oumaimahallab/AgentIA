import sys
import os
import time
import logging
import json
import re
from typing import Dict, List, Optional, Any, Tuple


class ConversationBuffer:
    """Petit tampon mémoire pour garder un historique de conversation simple."""

    def __init__(self, max_turns: int = 6):
        self.max_turns = max_turns
        self.messages: List[Dict[str, str]] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def get_messages(self) -> List[Dict[str, str]]:
        return list(self.messages)

    def _trim(self) -> None:
        if len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-(self.max_turns * 2):]

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class UnifiedAgent:
    """Agent Principal Unifié - Combine tous les modules"""
    
    def __init__(
        self,
        config=None,
    ):
        """
        Initialize Unified Agent
        
        Args:
            config: Configuration (UnifiedAgentConfig ou None for defaults)
        """
        if config is None:
            from config import get_config
            config = get_config()
        
        self.config = config
        
        # Initialize components
        self._init_embeddings()
        self._init_indices()
        self._init_retrievers()
        self._init_llm()
        self._init_evaluators()
        self.conversation_buffer = ConversationBuffer(max_turns=6)
        
        logger.info("Unified Agent initialized")
    
    def _init_evaluators(self):
        """Initialize evaluators and trackers"""
        from core.evaluator import ResponseEvaluator
        from core.performance_tracker import PerformanceTracker
        
        self.evaluator = ResponseEvaluator(self.config)
        self.tracker = PerformanceTracker(self.config)
        logger.info("Evaluators and trackers initialized")
    
    def _init_embeddings(self):
        """Initialize embeddings manager"""
        from retrieval.embeddings import EmbeddingsManager
        
        self.embeddings = EmbeddingsManager(
            model_name=self.config.embeddings.MODEL_NAME,
            device=self.config.embeddings.DEVICE,
        )
        logger.info("Embeddings initialized")
    
    def _init_indices(self):
        """Initialize vector indices"""
        from retrieval.faiss_manager import FAISSManager
        from retrieval.bm25_manager import BM25Manager
        
        self.faiss = FAISSManager(
            self.config.paths.FAISS_INDEX_DIR,
        )
        self.bm25 = BM25Manager(
            self.config.paths.BM25_INDEX_DIR,
        )
        logger.info("Indices initialized")
    
    def _init_retrievers(self):
        """Initialize retrieval components"""
        from retrieval.hybrid_retriever import HybridRetriever
        from retrieval.source_merger import SourceMerger
        from retrieval.reranker import Reranker
        
        self.retriever = HybridRetriever(
            self.faiss,
            self.bm25,
            alpha=self.config.retrieval.ALPHA,
        )
        
        self.merger = SourceMerger(
            dedup_threshold=self.config.deduplication.SIMILARITY_THRESHOLD,
        )
        
        self.reranker = Reranker()
        
        logger.info("Retrievers initialized")
    
    def _init_llm(self):
        """Initialize LLM orchestrator"""
        from llm.llm_orchestrator import LLMOrchestrator
        
        self.llm = LLMOrchestrator()
        
        logger.info("LLM orchestrator initialized")
    
    def _format_conversation_history(self, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Formate l'historique de conversation pour le prompt."""
        messages = history or self.conversation_buffer.get_messages()
        if not messages:
            return ""

        formatted = []
        for message in messages:
            role = message.get("role", "user")
            content = (message.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                formatted.append(f"Utilisateur: {content}")
            else:
                formatted.append(f"Assistant: {content}")
        return "\n".join(formatted)

    def _build_follow_up_context(self, question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Résout les références implicites d'une question de suivi à partir de l'historique récent."""
        messages = history or self.conversation_buffer.get_messages()
        if not messages:
            return ""

        lowered_question = question.lower()
        if not any(token in lowered_question for token in ["ça", "celle", "celui", "elle", "il", "sa", "son", "cette", "cet", "celle-ci", "celui-ci"]):
            return ""

        recent_context = []
        for message in messages[-4:]:
            content = (message.get("content") or "").strip()
            if content:
                recent_context.append(content)

        if not recent_context:
            return ""

        return (
            f"Contexte de suivi implicite pour la question '{question}': "
            + " | ".join(recent_context[-2:])
        )

    def _strip_html(self, text: str) -> str:
        """Retire le balisage HTML d'un message d'historique."""
        if not text:
            return ""
        cleaned = re.sub(r'<[^>]+>', ' ', text)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def _get_previous_exchange(self) -> Optional[Tuple[str, str]]:
        """
        Récupère le dernier échange (question utilisateur, réponse assistant)
        en gérant le doublon éventuel du message courant.
        """
        messages = self.conversation_buffer.get_messages()
        if len(messages) < 3:
            return None

        current = messages[-1]
        if current.get("role") != "user":
            return None

        assistant_idx = -2
        if (
            messages[assistant_idx].get("role") == "user"
            and messages[assistant_idx].get("content", "").strip() == current.get("content", "").strip()
        ):
            assistant_idx = -3

        if abs(assistant_idx) > len(messages) or messages[assistant_idx].get("role") != "assistant":
            return None

        user_idx = assistant_idx - 1
        if abs(user_idx) > len(messages) or messages[user_idx].get("role") != "user":
            return None

        previous_user = self._strip_html(messages[user_idx].get("content", ""))
        previous_assistant = self._strip_html(messages[assistant_idx].get("content", ""))
        if not previous_user or not previous_assistant:
            return None

        return previous_user, previous_assistant

    def _looks_like_correction(self, question: str) -> bool:
        """Heuristique rapide pour repérer un message de correction."""
        lowered = question.lower().strip()
        correction_markers = [
            "non ", "non,", "non.", "non la", "non le", "non c'est", "non ce n'est",
            "ce n'est pas", "c'est pas", "c'est faux", "c'est incorrect", "c'est une erreur",
            "tu te trompes", "tu as tort", "faux", "incorrect", "erreur", "correction",
            "en fait", "plutôt", "au contraire", "pas correct", "pas bon", "pas ça",
            "la premiere etape", "la première étape", "le premier", "la première",
            "ce n'est pas ça", "ce nest pas", "mal ordre", "mauvais ordre",
        ]
        return any(marker in lowered for marker in correction_markers)

    def _parse_llm_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extrait et parse un objet JSON depuis une réponse LLM."""
        content = (text or "").strip()
        if "{" not in content:
            return None
        try:
            json_blob = content[content.find("{"):content.rfind("}") + 1]
            return json.loads(json_blob)
        except json.JSONDecodeError:
            return None

    def _verify_correction_applied(self, corrected_info: str, topic: str) -> bool:
        """Vérifie que la correction est bien retrouvable dans les index."""
        if not corrected_info:
            return False

        search_query = f"{topic} {corrected_info}".strip()
        query_embedding = self.embeddings.embed(search_query, is_query=True)
        retrieval_results = self.retriever.search(query_embedding, search_query, top_k=5)

        corrected_lower = corrected_info.lower()
        corrected_tokens = [token for token in re.findall(r"\w+", corrected_lower) if len(token) > 3]
        if not corrected_tokens:
            corrected_tokens = corrected_lower.split()

        for result in retrieval_results:
            result_text = (result.text or "").lower()
            if corrected_lower in result_text:
                return True
            matched_tokens = sum(1 for token in corrected_tokens if token in result_text)
            if matched_tokens >= max(2, len(corrected_tokens) // 2):
                return True

        return False

    def _detect_and_handle_correction(self, question: str) -> Optional[Dict[str, Any]]:
        """
        Détecte si le message de l'utilisateur est une correction de la réponse précédente.
        Si oui, met à jour PostgreSQL, FAISS et BM25.
        """
        exchange = self._get_previous_exchange()
        if not exchange:
            return None

        previous_user, previous_assistant = exchange

        if not self._looks_like_correction(question):
            return None

        # 1. Utiliser le LLM pour détecter si c'est une correction factuelle
        detect_prompt = f"""Tu es un assistant de gestion de connaissances. Analyse la conversation suivante pour déterminer si le dernier message de l'utilisateur est une correction ou une mise à jour d'un fait erroné présent dans la réponse précédente de l'assistant (par exemple, contredire l'ordre d'une étape, signaler une erreur de procédure, corriger un chiffre, dire que c'est faux/incorrect).

IMPORTANT: L'utilisateur doit proposer une correction (par exemple: "la première étape est X", "non, c'est Y", "tu te trompes, Z"). Les simples questions de suivi ou demandes de précisions ne sont PAS des corrections.

Réponds UNIQUEMENT sous la forme d'un objet JSON avec ce format exact:
{{
  "is_correction": true ou false,
  "incorrect_info": "l'information erronée ou obsolète identifiée dans la réponse précédente de l'assistant",
  "corrected_info": "la nouvelle information correcte apportée par l'utilisateur",
  "topic": "le sujet principal de la correction (ex: processus de gestion du travail posté, astreintes, etc.)"
}}

CONVERSATION:
Utilisateur: {previous_user}
Assistant: {previous_assistant}
Dernier message de l'utilisateur: {question}

JSON:"""

        try:
            llm_res = self.llm.generate(detect_prompt, system_prompt="Tu es un classificateur d'intentions précis.")
            res_json = self._parse_llm_json(llm_res.get("text", ""))
            if not res_json or not res_json.get("is_correction"):
                return None

            corrected_info = (res_json.get("corrected_info") or "").strip()
            incorrect_info = (res_json.get("incorrect_info") or "").strip()
            topic = (res_json.get("topic") or previous_user).strip()

            if not corrected_info:
                return None

            logger.info(
                "Correction détectée! Incorrect: %s | Correct: %s",
                incorrect_info,
                corrected_info,
            )

            # 2. Chercher dans la base sémantique pour trouver le chunk correspondant à corriger
            search_query = f"{topic} {incorrect_info or corrected_info}"
            query_embedding = self.embeddings.embed(search_query, is_query=True)

            retrieval_results = self.retriever.search(
                query_embedding,
                search_query,
                top_k=5,
            )

            if not retrieval_results:
                logger.warning("Aucun chunk trouvé pour la recherche de correction.")
                return self._build_correction_fallback_response(
                    question, corrected_info, topic, reason="Aucun document source identifié."
                )

            chunks_context = ""
            for idx, r in enumerate(retrieval_results):
                chunk_dict = r.to_dict()
                chunk_id = chunk_dict.get("chunk_id") or chunk_dict.get("id") or f"chunk_{idx}"
                source_name = r.source_files[0] if r.source_files else "Inconnu"
                chunks_context += f"--- CHUNK {idx} (Source: {source_name}, ID: {chunk_id}) ---\n{r.text}\n\n"

            rewrite_prompt = f"""Voici des extraits (chunks) de notre base de connaissances RAG.
L'un d'eux contient une information incorrecte: "{incorrect_info}".
L'utilisateur a fourni la correction suivante: "{corrected_info}".

Identifie le CHUNK qui contient l'erreur, et réécris-le ENTIÈREMENT pour corriger l'erreur d'après l'information correcte de l'utilisateur, tout en conservant le style et le reste des informations inchangés (ne perds aucune autre information).

Réponds UNIQUEMENT avec un objet JSON au format exact :
{{
  "chunk_found": true ou false,
  "chunk_id": "l'identifiant exact du chunk à corriger (ex: doc_0, x.pdf_5, etc.)",
  "corrected_text": "le texte du chunk entièrement corrigé et réécrit"
}}

EXTRAITS DISPONIBLES:
{chunks_context}

JSON:"""

            rewrite_res = self.llm.generate(rewrite_prompt, system_prompt="Tu es un éditeur de texte RAG factuel.")
            rewrite_json = self._parse_llm_json(rewrite_res.get("text", ""))
            if not rewrite_json or not rewrite_json.get("chunk_found") or not rewrite_json.get("chunk_id"):
                logger.warning("Le LLM n'a pas pu identifier le chunk à modifier.")
                return self._build_correction_fallback_response(
                    question, corrected_info, topic, reason="Le segment source n'a pas pu être identifié."
                )

            target_chunk_id = rewrite_json.get("chunk_id")
            corrected_text = rewrite_json.get("corrected_text")
            logger.info("Chunk cible identifié pour correction: %s", target_chunk_id)

            db_updated = False
            faiss_updated = False
            bm25_updated = False
            source_file = ""
            chunk_num = -1

            match = re.search(r"^(.*?)(?:_(\d+))$", target_chunk_id)
            if match:
                source_file = match.group(1)
                chunk_num = int(match.group(2))
            else:
                for meta in self.faiss.metadata:
                    if meta.get("chunk_id") == target_chunk_id:
                        source_file = meta.get("source") or ""
                        idx_match = re.search(r"(\d+)$", target_chunk_id)
                        if idx_match:
                            chunk_num = int(idx_match.group(1))
                        break

            if source_file and chunk_num >= 0:
                logger.info("Mise à jour en cours pour %s, index %s...", source_file, chunk_num)

                import psycopg2
                try:
                    conn = psycopg2.connect(
                        host=os.getenv("DB_HOST", "localhost"),
                        port=os.getenv("DB_PORT", "5432"),
                        dbname=os.getenv("DB_NAME", "postgres"),
                        user=os.getenv("DB_USER", "postgres"),
                        password=os.getenv("DB_PASSWORD", "root"),
                    )
                    c = conn.cursor()
                    try:
                        c.execute("""
                            SELECT dc.id
                            FROM document_chunks dc
                            JOIN documents d ON dc.document_id = d.id
                            WHERE d.filename = %s AND dc.chunk_number = %s
                        """, (source_file, chunk_num + 1))
                        row = c.fetchone()
                        if row:
                            db_chunk_id = row[0]
                            from ingestion.chunk_manager import ChunkManager
                            cm = ChunkManager()
                            db_updated = cm.update_chunk(db_chunk_id, corrected_text)
                            logger.info("✓ Chunk DB mis à jour (row id: %s)", db_chunk_id)
                    except Exception as e:
                        logger.error("Erreur SQL lors de la correction: %s", e)
                    finally:
                        conn.close()
                except Exception as e:
                    logger.error("Connexion PostgreSQL impossible pour la correction: %s", e)

                new_embedding = self.embeddings.embed(corrected_text)
                faiss_updated = self.faiss.update_chunk(source_file, chunk_num, corrected_text, new_embedding)
                bm25_updated = self.bm25.update_chunk(source_file, chunk_num, corrected_text)

            if db_updated or faiss_updated or bm25_updated:
                verified = self._verify_correction_applied(corrected_info, topic)
                verification_line = (
                    "La vérification automatique confirme que la correction est bien indexée."
                    if verified
                    else "La vérification automatique n'a pas pu confirmer l'indexation, mais la mise à jour a été appliquée."
                )

                confirm_message = f"""J'ai bien pris en compte votre correction.

**Mise à jour de la base de connaissances effectuée :**
* **Information corrigée** : "{corrected_info}"
* **Source modifiée** : {source_file} (Segment #{chunk_num})
* **Synchronisation** : PostgreSQL + FAISS + BM25
* **Vérification** : {verification_line}

Désormais, le système utilisera cette version mise à jour pour les prochaines questions sur ce sujet."""

                self.conversation_buffer.add_assistant_message(confirm_message)

                return {
                    "answer": confirm_message,
                    "intent": "correction",
                    "confidence": 1.0,
                    "sources": [{"source": source_file, "location": ""}],
                    "duration": 0.0,
                    "metrics": {"faithfulness": 1.0, "relevance": 1.0, "verified": verified},
                    "model": "system_correction"
                }

            return self._build_correction_fallback_response(
                question, corrected_info, topic, reason="La mise à jour des index a échoué."
            )

        except Exception as e:
            logger.error("Erreur lors du traitement de la correction: %s", e, exc_info=True)

        return None

    def _build_correction_fallback_response(
        self,
        question: str,
        corrected_info: str,
        topic: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Réponse quand la correction est comprise mais la mise à jour KB a échoué."""
        fallback_message = f"""J'ai bien compris votre correction : "{corrected_info}".

Je n'ai pas pu mettre à jour automatiquement la base de connaissances ({reason}).
Je tiendrai compte de votre correction pour la suite de cette conversation.

**Correction retenue pour cette session :**
* **Sujet** : {topic}
* **Information correcte** : {corrected_info}"""

        self.conversation_buffer.add_assistant_message(fallback_message)
        return {
            "answer": fallback_message,
            "intent": "correction_partial",
            "confidence": 0.8,
            "sources": [],
            "duration": 0.0,
            "metrics": {"faithfulness": 0.8, "relevance": 1.0, "verified": False},
            "model": "system_correction_fallback",
            "correction_context": corrected_info,
        }

    def answer(self, question: str) -> Dict[str, Any]:
        """
        Répond à une question avec évaluation et tracking
        
        Args:
            question: La question de l'utilisateur
            
        Returns:
            Dict avec réponse + métadonnées + scores
        """
        start_time = time.time()
        self.conversation_buffer.add_user_message(question)
        
        # Détection de correction utilisateur
        correction_result = self._detect_and_handle_correction(question)
        if correction_result:
            return correction_result
            
        # 1. DETECT INTENT
        from core.intent_detector import IntentDetector, QueryIntent
        
        intent_detector = IntentDetector()
        intent_result = intent_detector.detect(question)
        
        logger.info(f"Intent: {intent_result.intent.value} ({intent_result.confidence:.0%})")
        
        # 2. EMBED QUERY
        query_embedding = self.embeddings.embed(question, is_query=True)
        
        # 3. HYBRID RETRIEVAL
        retrieval_results = self.retriever.search(
            query_embedding,
            question,
            top_k=self.config.retrieval.SEMANTIC_TOP_K,
        )
        
        logger.info(f"Retrieved: {len(retrieval_results)} results")
        
        # 4. MERGE & DEDUPLICATE
        merged_sources = self.merger.merge(retrieval_results)
        
        logger.info(f"Merged: {len(merged_sources)} unique sources")
        
        # 5. BUILD CONTEXT
        context_info = self.merger.build_context(
            merged_sources,
            max_tokens=self.config.retrieval.MAX_CONTEXT_TOKENS,
        )
        
        context = context_info["context"]
        
        # 6. SELECT SYSTEM PROMPT
        system_prompt = IntentDetector.get_system_prompt(intent_result.intent)
        
        # 7. BUILD FINAL PROMPT
        history_text = self._format_conversation_history()
        follow_up_context = self._build_follow_up_context(question)
        conversation_context = f"""
HISTORIQUE DE CONVERSATION:
{history_text}

""" if history_text else ""

        follow_up_context_block = f"""
CONTEXTE DE SUIVI IMPLICITE:
{follow_up_context}

""" if follow_up_context else ""

        correction_context_block = ""
        if self._looks_like_correction(question):
            exchange = self._get_previous_exchange()
            if exchange:
                _, previous_assistant = exchange
                correction_context_block = f"""
CORRECTION UTILISATEUR EN COURS:
L'utilisateur signale que la réponse précédente était incorrecte.
Réponse précédente à ne PAS répéter: {previous_assistant[:800]}
Message de correction: {question}
Tu dois intégrer explicitement la correction de l'utilisateur dans ta nouvelle réponse.

"""

        final_prompt = f"""CONTEXT:
{context}

---

{conversation_context}{follow_up_context_block}{correction_context_block}QUESTION: {question}

RAPPEL IMPORTANT: Ne mentionne JAMAIS "Selon le document", "D'après le guide" ou le nom des fichiers (ex: .pptx, .pdf). Donne la réponse directement et naturellement. Si la question suit une précédente conversation, utilise le contexte précédent pour répondre de façon fluide et continue.

RESPONSE:"""
        
        # 8. GENERATE RESPONSE
        llm_result = self.llm.generate(final_prompt, system_prompt)
        answer = llm_result["text"]
        self.conversation_buffer.add_assistant_message(answer)
        
        # 9. EVALUATE (LLM-as-a-Judge)
        logger.info("Evaluation de la reponse...")
        scores = self.evaluator.evaluate(context, question, answer)
        
        # 10. TRACK PERFORMANCE
        duration = time.time() - start_time
        log_data = {
            "Question": question,
            "Answer": answer,
            "Sources_Count": len(merged_sources),
            "Duration_Sec": duration,
            "Faithfulness_Score": scores.get("faithfulness", 0.0),
            "Relevance_Score": scores.get("relevance", 0.0),
            "Intent": intent_result.intent.value
        }
        self.tracker.log_interaction(log_data)
        
        return {
            "answer": answer,
            "intent": intent_result.intent.value,
            "confidence": intent_result.confidence,
            "sources": [s.to_dict() for s in merged_sources],
            "duration": duration,
            "metrics": scores,
            "model": llm_result.get("source", "unknown")
        }
    
    def batch_answer(self, questions: List[str]) -> List[Dict[str, Any]]:
        """
        Répond à un batch de questions
        
        Args:
            questions: Liste de questions
        Returns:
            Liste de réponses
        """
        
        answers = []
        for question in questions:
            try:
                answer = self.answer(question)
                answers.append(answer)
            except Exception as e:
                logger.error(f"Error answering question: {e}")
                answers.append({
                    "question": question,
                    "answer": f"Error: {str(e)}",
                    "error": True,
                })
        
        return answers
    
    def get_system_status(self) -> Dict[str, Any]:
        """Retourne le statut du système"""
        
        return {
            "embeddings": self.embeddings.get_cache_stats(),
            "indices": {
                "faiss": self.faiss.get_stats(),
                "bm25": self.bm25.get_stats(),
            },
            "llm": self.llm.get_status(),
            "retriever": self.retriever.get_stats(),
        }


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*50)
    print("UNIFIED AGENT - MODE CONSOLE")
    print("="*50)
    
    try:
        agent = UnifiedAgent()
        print("\nSysteme pret ! (Tapez 'exit' pour quitter)")
        
        while True:
            question = input("\nVotre question : ")
            if question.lower() in ['exit', 'quit', 'q']:
                break
            
            if not question.strip():
                continue
                
            print("\nL'agent reflechit...")
            result = agent.answer(question)
            
            print(f"\nREPONSE ({result.get('model', 'unknown')}):")
            print("-" * 30)
            print(result['answer'])
            print("-" * 30)
            
            if result.get("sources"):
                print("\nSOURCES :")
                for s in result["sources"][:3]:
                    fname = os.path.basename(s.source_files[0] if s.source_files else 'Inconnu')
                    print(f"  - {fname}")
                    
    except Exception as e:
        print(f"Erreur critique : {e}")
