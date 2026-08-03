import sys
import os
import logging
from pathlib import Path
import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.append(str(PROJECT_ROOT))

# Force output to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_correction")

def test_dynamic_correction():
    from orchestration.agent import UnifiedAgent
    
    logger.info("Initializing agent...")
    agent = UnifiedAgent()
    
    # 1. Simulate previous conversation history with the incorrect steps order
    agent.conversation_buffer.messages = []
    
    previous_user = "donne moi les etapes du processus de gestion du travail posté"
    previous_assistant = """Le processus de gestion du travail posté est composé de 6 étapes :
1. Saisie des activités : Le travailleur posté saisit ses heures normales, ses heures d'astreintes, ses interventions et son badgeage.
2. Validation par le responsable : Le CPDP valide les heures d'astreintes et les interventions.
3. Traitement des anomalies : En cas d'anomalie, celle-ci doit être corrigée impérativement par le collaborateur.
4. Mise à jour des compteurs : Les compteurs de récupération et de paiement sont mis à jour.
5. Intégration en paye : Les compteurs de paiement sont envoyés pour intégration en paye.
6. Planification et attribution des horaires : Le Manager ou Team Leader gère le planning."""

    agent.conversation_buffer.add_user_message(previous_user)
    agent.conversation_buffer.add_assistant_message(previous_assistant)
    
    # 2. Correct the agent
    correction_query = "non la premiere etape est Planification et attribution des horaires"
    logger.info(f"Sending correction: '{correction_query}'")
    
    result = agent.answer(correction_query)
    
    logger.info("\n" + "="*50)
    logger.info("Correction Result:")
    logger.info(result.get("answer"))
    logger.info("="*50 + "\n")
    
    # Verify indexes and database were updated
    conn = psycopg2.connect('host=localhost port=5432 dbname=postgres user=postgres password=root')
    c = conn.cursor()
    c.execute("""
        SELECT dc.chunk_number, dc.text 
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE d.filename = 'x.pdf' AND dc.chunk_number = 6
    """)
    row = c.fetchone()
    if row:
        logger.info(f"PostgreSQL Chunk #{row[0]} Content now:")
        logger.info(repr(row[1])[:500] + "...")
    conn.close()
    
    # 3. Try to ask the original question again in a fresh buffer
    logger.info("Resetting conversation buffer and asking original question...")
    agent.conversation_buffer.messages = []
    
    result_fresh = agent.answer("donne moi les etapes du processus de gestion du travail posté en bon ordre")
    
    logger.info("\n" + "="*50)
    logger.info("Fresh Question Result:")
    logger.info(result_fresh.get("answer"))
    logger.info("="*50 + "\n")

if __name__ == '__main__':
    test_dynamic_correction()
