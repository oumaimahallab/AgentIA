import os
import sys
import logging
import sqlite3
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Configurer le logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE = 'users.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, name TEXT, password TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, user_email TEXT, title TEXT, messages TEXT, timestamp TEXT, is_pinned INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0)''')
    
    # Vérifier si les colonnes existent, sinon les ajouter (pour les bases existantes)
    try:
        c.execute("ALTER TABLE sessions ADD COLUMN is_pinned INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE sessions ADD COLUMN is_archived INTEGER DEFAULT 0")
    except: pass
    
    # Ajouter des utilisateurs de test par défaut
    users = [
        ('admin@inetum.com', 'Oumaima Hallab', 'admin123'),
        ('demo@inetum.com', 'Imane Benzegunine', 'demo123')
    ]
    for email, name, pwd in users:
        c.execute("INSERT OR REPLACE INTO users (email, name, password) VALUES (?, ?, ?)", (email, name, pwd))
    
    conn.commit()
    conn.close()

init_db()

# Initialiser Flask
app = Flask(__name__)
CORS(app)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT name, email FROM users WHERE email=? AND password=?", (email, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            return jsonify({"success": True, "name": user[0], "email": user[1]})
        else:
            return jsonify({"success": False, "message": "Email ou mot de passe incorrect"}), 401
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"success": False, "message": "Erreur serveur"}), 500

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    email = request.args.get('email')
    if not email: return jsonify([]), 400
    
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT session_id, title, messages, timestamp, is_pinned, is_archived FROM sessions WHERE user_email=? ORDER BY is_pinned DESC, timestamp DESC", (email,))
        rows = c.fetchall()
        conn.close()
        
        sessions = []
        for row in rows:
            sessions.append({
                "id": row[0],
                "title": row[1],
                "messages": json.loads(row[2]),
                "timestamp": row[3],
                "isPinned": bool(row[4]),
                "isArchived": bool(row[5])
            })
        return jsonify(sessions)
    except Exception as e:
        logger.error(f"Get sessions error: {e}")
        return jsonify([]), 500

@app.route('/api/sessions', methods=['POST'])
def save_session_route():
    data = request.json
    email = data.get('email')
    session = data.get('session')
    if not email or not session: return jsonify({"error": "Missing data"}), 400
    
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO sessions (session_id, user_email, title, messages, timestamp, is_pinned, is_archived) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (session['id'], email, session['title'], json.dumps(session['messages']), session['timestamp'], 1 if session.get('isPinned') else 0, 1 if session.get('isArchived') else 0))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Save session error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session_route(session_id):
    email = request.args.get('email')
    if not email: return jsonify({"error": "Missing email"}), 400
    
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE session_id=? AND user_email=?", (session_id, email))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        return jsonify({"error": str(e)}), 500

# Ajouter le chemin racine pour importer l'agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from orchestration.agent import UnifiedAgent
    from config import get_config
except ImportError as e:
    logger.error(f"Erreur d'importation: {e}")
    sys.exit(1)

# Initialiser l'agent globalement
agent = None

def init_agent():
    global agent
    if agent is None:
        logger.info("🚀 Chargement de l'Agent Unifié...")
        config = get_config()
        agent = UnifiedAgent(config)
        logger.info("✅ Agent prêt !")

# Dossier pour les uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'files' not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
    
    files = request.files.getlist('files')
    saved_files = []
    
    for file in files:
        if file.filename:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            saved_files.append(file.filename)
            logger.info(f"📁 Fichier sauvegardé : {file.filename}")
            
    return jsonify({
        "message": f"{len(saved_files)} fichiers téléchargés avec succès",
        "files": saved_files
    })

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
        for pattern in ["**Sources", "**Référence", "Sources :", "Références :", "Source :"]:
            if pattern in answer_text:
                answer_text = answer_text.split(pattern)[0].strip()

        # Préparer les sources
        seen_files = set()
        formatted_sources = []
        
        for merged_s in result.get("sources", []):
            files = merged_s.get("source_files", [])
            if not files and merged_s.get("primary_sources"):
                p = merged_s["primary_sources"][0]
                files = [p.get("source") or p.get("doc_name") or "Document"]

            for raw_file in files:
                if not raw_file: continue
                filename = os.path.basename(str(raw_file))
                if filename not in seen_files and filename not in ["Document", "unknown", "None"]:
                    formatted_sources.append({"source": filename, "location": ""})
                    seen_files.add(filename)
            
            if len(formatted_sources) >= 5:
                break

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
