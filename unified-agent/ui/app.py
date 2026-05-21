import os
import sys
import logging
import psycopg2
from psycopg2 import extras
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import threading
from datetime import datetime
import time
import hashlib

# Charger les variables d'environnement (recherche dans les dossiers parents si nécessaire)
load_dotenv()

# Configurer le logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'root'),
            connect_timeout=5
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Impossible de se connecter à PostgreSQL pour l'initialisation. Vérifiez si le serveur est lancé.")
        return
    
    try:
        c = conn.cursor()
        # Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id SERIAL PRIMARY KEY, email TEXT UNIQUE, name TEXT, password TEXT)''')
        
        # Create sessions table
        c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                     (session_id TEXT PRIMARY KEY, user_email TEXT, title TEXT, messages TEXT, timestamp TEXT, is_pinned INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0)''')
                     
        try:
            c.execute("ALTER TABLE sessions ADD COLUMN is_deleted INTEGER DEFAULT 0")
        except Exception:
            pass # Column might already exist

                     
        # Create documents table for admin ingestion tracking
        c.execute('''CREATE TABLE IF NOT EXISTS documents 
                     (id SERIAL PRIMARY KEY, filename TEXT UNIQUE, status TEXT, error_msg TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Ajouter des utilisateurs de test par défaut
        users = [
            ('admin@inetum.com', 'Oumaima Hallab', 'admin123'),
            ('demo@inetum.com', 'Imane Benzegunine', 'demo123')
        ]
        for email, name, pwd in users:
            c.execute("""
                INSERT INTO users (email, name, password) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, password = EXCLUDED.password
            """, (email, name, pwd))
        
        conn.commit()
        logger.info("✅ Base de données PostgreSQL initialisée avec succès.")
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'initialisation de la DB: {e}")
    finally:
        conn.close()

# Initialiser la base de données au démarrage
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
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Erreur de connexion à la base de données"}), 500
        
    try:
        c = conn.cursor()
        c.execute("SELECT name, email FROM users WHERE email=%s AND password=%s", (email, password))
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
    
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500
        
    try:
        c = conn.cursor()
        c.execute("SELECT session_id, title, messages, timestamp, is_pinned, is_archived FROM sessions WHERE user_email=%s AND is_deleted = 0 ORDER BY is_pinned DESC, timestamp DESC", (email,))
        rows = c.fetchall()
        conn.close()
        
        sessions = []
        for row in rows:
            sessions.append({
                "id": row[0],
                "title": row[1],
                "messages": json.loads(row[2]) if isinstance(row[2], str) else row[2],
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
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO sessions (session_id, user_email, title, messages, timestamp, is_pinned, is_archived) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET 
                user_email = EXCLUDED.user_email,
                title = EXCLUDED.title,
                messages = EXCLUDED.messages,
                timestamp = EXCLUDED.timestamp,
                is_pinned = EXCLUDED.is_pinned,
                is_archived = EXCLUDED.is_archived
        """, (
            session['id'], 
            email, 
            session['title'], 
            json.dumps(session['messages']), 
            session['timestamp'], 
            1 if session.get('isPinned') else 0, 
            1 if session.get('isArchived') else 0
        ))
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
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        c = conn.cursor()
        c.execute("UPDATE sessions SET is_deleted = 1 WHERE session_id=%s AND user_email=%s", (session_id, email))
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
    from ingestion.unified_ingester import UnifiedIngester
    from pathlib import Path
except ImportError as e:
    logger.error(f"Erreur d'importation: {e}")
    sys.exit(1)

# Initialiser l'agent dès le démarrage (Eager Loading)
logger.info("🚀 Chargement de l'Agent Unifié en cours au démarrage... (Patientez)")
config = get_config()
agent = UnifiedAgent(config)
logger.info("✅ Agent prêt !")

def get_agent():
    return agent

# Dossier pour les uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def background_ingest(filepath, filename, db_doc_id):
    current_agent = get_agent()
    try:
        # Update status to processing
        conn = get_db_connection()
        if conn:
            c = conn.cursor()
            c.execute("UPDATE documents SET status='En cours' WHERE id=%s", (db_doc_id,))
            conn.commit()
            conn.close()

        ingester = UnifiedIngester()
        result = ingester.ingest(Path(filepath))
        
        if result:
            chunks_text, metadata = result
            # Prepare metadata dicts
            metadatas = [
                {"chunk_id": f"{filename}_{i}", "fingerprint": hashlib.sha256(text.encode('utf-8')).hexdigest(), "content": text, "source": filename, "type": "document", "location": "admin_upload"}
                for i, text in enumerate(chunks_text)
            ]
            
            # FAISS
            embs = current_agent.embeddings.embed_batch(chunks_text, batch_size=32)
            current_agent.faiss.add_embeddings(embs, metadatas)
            current_agent.faiss.save()
            
            # BM25
            current_agent.bm25.add_documents(chunks_text, metadatas)
            current_agent.bm25.save()
            
            # Success
            conn = get_db_connection()
            if conn:
                c = conn.cursor()
                c.execute("UPDATE documents SET status='Ingéré' WHERE id=%s", (db_doc_id,))
                conn.commit()
                conn.close()
            logger.info(f"✅ Ingestion de {filename} terminée et sauvegardée dans l'index.")
        else:
            raise Exception("Format non supporté ou erreur d'ingestion")
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        conn = get_db_connection()
        if conn:
            c = conn.cursor()
            c.execute("UPDATE documents SET status='Erreur', error_msg=%s WHERE id=%s", (str(e), db_doc_id))
            conn.commit()
            conn.close()

@app.route('/api/admin/upload_and_ingest', methods=['POST'])
def admin_upload_and_ingest():
    email = request.form.get('email', '')
    if email != 'admin@inetum.com':
        return jsonify({"error": "Unauthorized"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nom de fichier vide"}), 400

    conn = get_db_connection()
    if conn:
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM documents WHERE filename=%s", (file.filename,))
            res = c.fetchone()
            if res:
                conn.close()
                return jsonify({"error": f"Le fichier '{file.filename}' est déjà uploadé. L'ingestion est annulée."}), 409
        except Exception as e:
            logger.error(f"Erreur vérification doublon: {e}")

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)
    
    # Save to DB
    db_doc_id = None
    if conn:
        try:
            c = conn.cursor()
            c.execute("INSERT INTO documents (filename, status) VALUES (%s, 'En attente') RETURNING id", (file.filename,))
            db_doc_id = c.fetchone()[0]
            conn.commit()
        except Exception as e:
            conn.rollback()
        finally:
            conn.close()

    # Start async thread
    if db_doc_id:
        thread = threading.Thread(target=background_ingest, args=(filepath, file.filename, db_doc_id))
        thread.daemon = True
        thread.start()
        
    return jsonify({"success": True, "message": "Fichier uploadé et ingestion démarrée en arrière-plan."})

@app.route('/api/admin/documents', methods=['GET'])
def get_admin_documents():
    email = request.args.get('email', '')
    if email != 'admin@inetum.com':
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    try:
        c = conn.cursor()
        c.execute("SELECT id, filename, status, error_msg, created_at FROM documents ORDER BY created_at DESC")
        rows = c.fetchall()
        docs = [{"id": r[0], "filename": r[1], "status": r[2], "error_msg": r[3], "created_at": r[4]} for r in rows]
        return jsonify(docs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/transactions', methods=['GET'])
def get_admin_transactions():
    email = request.args.get('email', '')
    if email != 'admin@inetum.com':
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    try:
        c = conn.cursor()
        c.execute("SELECT session_id, user_email, title, timestamp, is_archived, is_deleted FROM sessions ORDER BY timestamp DESC LIMIT 50")
        rows = c.fetchall()
        trans = [{"id": r[0], "user_email": r[1], "title": r[2], "timestamp": r[3], "is_archived": r[4], "is_deleted": r[5]} for r in rows]
        return jsonify(trans)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/transactions/<session_id>', methods=['GET'])
def get_admin_transaction_details(session_id):
    email = request.args.get('email', '')
    if email != 'admin@inetum.com':
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = get_db_connection()
    if not conn: return jsonify({"error": "Database error"}), 500
    try:
        c = conn.cursor()
        c.execute("SELECT user_email, title, messages, timestamp FROM sessions WHERE session_id = %s", (session_id,))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Transaction not found"}), 404
            
        return jsonify({
            "id": session_id,
            "user_email": row[0],
            "title": row[1],
            "messages": json.loads(row[2]) if isinstance(row[2], str) else row[2],
            "timestamp": row[3]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/transactions/delete', methods=['POST'])
def admin_delete_transactions():
    email = request.args.get('email', '')
    if email != 'admin@inetum.com':
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    if not data or not data.get('session_ids'):
        return jsonify({"error": "No session_ids provided"}), 400
        
    session_ids = data['session_ids']
    
    conn = get_db_connection()
    if not conn: return jsonify({"error": "Database error"}), 500
    try:
        c = conn.cursor()
        format_strings = ','.join(['%s'] * len(session_ids))
        c.execute(f"DELETE FROM sessions WHERE session_id IN ({format_strings})", tuple(session_ids))
        conn.commit()
        return jsonify({"success": True, "deleted": c.rowcount})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

import psutil

@app.route('/api/admin/metrics', methods=['GET'])
def get_admin_metrics():
    email = request.args.get('email', '')
    if email != 'admin@inetum.com':
        return jsonify({"error": "Unauthorized"}), 403
        
    current_agent = get_agent()
    sys_status = current_agent.get_system_status()
    
    conn = get_db_connection()
    total_users = 0
    total_sessions = 0
    if conn:
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM sessions")
            total_sessions = c.fetchone()[0]
        except Exception:
            pass
        finally:
            conn.close()
            
    # Récupération des métriques système réelles
    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    hardware_metrics = {
        "cpu": cpu_percent,
        "ram": {
            "percent": ram.percent,
            "used": round(ram.used / (1024 ** 3), 2),
            "total": round(ram.total / (1024 ** 3), 2)
        },
        "disk": {
            "percent": disk.percent,
            "used": round(disk.used / (1024 ** 3), 2),
            "total": round(disk.total / (1024 ** 3), 2)
        }
    }
            
    return jsonify({
        "system": sys_status,
        "hardware": hardware_metrics,
        "database": {
            "total_users": total_users,
            "total_sessions": total_sessions
        }
    })

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
    current_agent = get_agent()
    
    data = request.json
    question = data.get('question')
    
    if not question:
        return jsonify({"error": "Question vide"}), 400
    
    logger.info(f"❓ Question reçue: {question}")
    
    try:
        # Demander à l'agent
        result = current_agent.answer(question)
        answer_text = result["answer"]
        
        # Nettoyage automatique des listes de sources/références en fin de texte
        for pattern in ["**Sources", "**Référence", "Sources :", "Références :", "Source :"]:
            if pattern in answer_text:
                answer_text = answer_text.split(pattern)[0].strip()

        # Préparer les sources
        seen_files = set()
        formatted_sources = []
        
        for merged_s in result.get("sources", []):
            files = merged_s.get('source_files', [])
            if not files and merged_s.get('primary_sources'):
                p = merged_s.get('primary_sources')[0]
                files = [p.get('source') or p.get('doc_name') or "Document"]

            for raw_file in files:
                if not raw_file: continue
                filename = os.path.basename(str(raw_file))
                
                # Nettoyage pour détection doublons plus stricte
                base_name = filename.split('.')[0].lower()
                
                if base_name not in seen_files and filename not in ["Document", "unknown", "None"]:
                    formatted_sources.append({"source": filename, "location": ""})
                    seen_files.add(base_name)
            
            if len(formatted_sources) >= 4: # Limiter à 4 sources max
                break

        return jsonify({
            "answer": answer_text,
            "sources": formatted_sources,
            "intent": result.get("intent", "unknown"),
            "metrics": result.get("metrics", {})
        })
    except Exception as e:
        logger.error(f"❌ Erreur lors de la génération: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def status():
    current_agent = get_agent()
    return jsonify(current_agent.get_system_status())

if __name__ == '__main__':
    # L'agent est maintenant initialisé au démarrage pour éviter le retard sur la première question
    print("\n" + "="*50)
    print("SERVEUR API LANCE SUR http://localhost:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5005, debug=False, threaded=True)
