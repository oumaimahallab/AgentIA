import os
import sys
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

# Configurer le logging pour voir ce qui se passe
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ajouter le chemin racine pour importer l'agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from orchestration.agent import UnifiedAgent
    from config import get_config
except ImportError as e:
    logger.error(f"Erreur d'importation: {e}")
    sys.exit(1)

app = Flask(__name__)
CORS(app)

# Initialiser l'agent globalement
agent = None

def init_agent():
    global agent
    if agent is None:
        logger.info("🚀 Chargement de l'Agent Unifié...")
        config = get_config()
        agent = UnifiedAgent(config)
        logger.info("✅ Agent prêt !")

@app.route('/api/ask', methods=['POST'])
def ask():
    init_agent() # S'assurer qu'il est prêt
    
    data = request.json
    question = data.get('question')
    
    if not question:
        return jsonify({"error": "Question vide"}), 400
    
    logger.info(f"❓ Question reçue: {question}")
    
    try:
        # Demander à l'agent
        result = agent.answer(question)
        answer_text = result["answer"]
        
        # Nettoyage automatique des listes de sources/références en fin de texte
        # (Pour éviter le doublon avec les badges de l'UI)
        for pattern in ["**Sources", "**Référence", "Sources :", "Références :", "Source :"]:
            if pattern in answer_text:
                answer_text = answer_text.split(pattern)[0].strip()

        # Préparer les sources pour le Web (Adapté à la structure MergedSource)
        seen_files = set()
        formatted_sources = []
        
        for merged_s in result.get("sources", []):
            # Dans MergedSource, les fichiers sont dans 'source_files'
            files = merged_s.get("source_files", [])
            
            # Si vide, on regarde dans la source primaire
            if not files and merged_s.get("primary_sources"):
                p = merged_s["primary_sources"][0]
                files = [p.get("source") or p.get("doc_name") or "Document"]

            for raw_file in files:
                if not raw_file: continue
                
                filename = os.path.basename(str(raw_file))
                
                # Éviter les doublons et les noms génériques
                if filename not in seen_files and filename not in ["Document", "unknown", "None"]:
                    formatted_sources.append({
                        "source": filename,
                        "location": "" # On pourrait extraire la page ici si besoin
                    })
                    seen_files.add(filename)
            
            if len(formatted_sources) >= 5:
                break

        logger.info(f"✅ Réponse prête avec {len(formatted_sources)} sources réelles.")
        
        return jsonify({
            "answer": answer_text,
            "sources": formatted_sources,
            "intent": result.get("intent", "unknown")
        })
    except Exception as e:
        logger.error(f"❌ Erreur lors de la génération: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def status():
    init_agent()
    return jsonify(agent.get_system_status())

if __name__ == '__main__':
    init_agent()
    print("\n" + "="*50)
    print("🌍 SERVEUR API LANCÉ SUR http://localhost:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
