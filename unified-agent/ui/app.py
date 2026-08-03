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
import re

# Charger les variables d'environnement (recherche dans les dossiers parents si nécessaire)
load_dotenv()

# Configurer le logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _strip_html_from_text(text: str) -> str:
    """Retire le balisage HTML des messages d'historique pour le contexte LLM."""
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

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

ROLE_ADMIN = 'admin'
ROLE_USER = 'user'
INETUM_EMAIL_DOMAIN = '@inetum.com'


def normalize_email(email):
    return (email or '').strip()


def is_inetum_email(email):
    """Assistant interne : seuls les emails @inetum.com sont acceptés."""
    return normalize_email(email).lower().endswith(INETUM_EMAIL_DOMAIN)


def inetum_email_error(email, as_login=False):
    """Retourne une réponse Flask si l'email n'est pas @inetum.com, sinon None."""
    if not normalize_email(email):
        msg = "Email manquant"
        if as_login:
            return jsonify({"success": False, "message": msg}), 400
        return jsonify({"error": msg}), 400
    if not is_inetum_email(email):
        msg = (
            "Accès réservé aux comptes professionnels @inetum.com "
            "(assistant interne Inetum)."
        )
        if as_login:
            return jsonify({"success": False, "message": msg}), 403
        return jsonify({"error": msg, "message": msg}), 403
    return None


def get_user_role(email):
    """Retourne le rôle d'un utilisateur depuis la base (None si inconnu)."""
    if not email:
        return None
    conn = get_db_connection()
    if not conn:
        return None
    try:
        c = conn.cursor()
        c.execute("SELECT COALESCE(role, %s) FROM users WHERE email=%s", (ROLE_USER, email))
        row = c.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"get_user_role error: {e}")
        return None
    finally:
        conn.close()


def user_is_admin(email):
    return get_user_role(email) == ROLE_ADMIN


def admin_auth_error(email):
    """Retourne une réponse Flask (error, status) si non admin, sinon None."""
    domain_err = inetum_email_error(email)
    if domain_err:
        return domain_err
    if not user_is_admin(email):
        return jsonify({"error": "Unauthorized"}), 403
    return None


def get_user_id_by_email(email, cursor=None):
    """Retourne l'id utilisateur (table users) à partir de l'email."""
    email = normalize_email(email)
    if not email:
        return None
    own_conn = False
    conn = None
    try:
        if cursor is None:
            conn = get_db_connection()
            if not conn:
                return None
            cursor = conn.cursor()
            own_conn = True
        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"get_user_id_by_email error: {e}")
        return None
    finally:
        if own_conn and conn:
            conn.close()


def sync_serial_sequence(cursor, table, column="id"):
    """Réaligne la séquence SERIAL sur MAX(id) pour un id auto-incrémenté continu."""
    cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", (table, column))
    row = cursor.fetchone()
    if not row or not row[0]:
        return
    seq = row[0]
    cursor.execute(f"SELECT COALESCE(MAX({column}), 0) FROM {table}")
    max_id = cursor.fetchone()[0]
    cursor.execute("SELECT setval(%s, %s, %s)", (seq, max_id, max_id > 0))


def init_db():
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Impossible de se connecter à PostgreSQL pour l'initialisation. Vérifiez si le serveur est lancé.")
        return
    
    try:
        c = conn.cursor()
        # Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id SERIAL PRIMARY KEY, email TEXT UNIQUE, name TEXT, password TEXT,
                      role VARCHAR(20) DEFAULT 'user')''')
        conn.commit()

        try:
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'")
            c.execute("UPDATE users SET role = %s WHERE role IS NULL", (ROLE_USER,))
            c.execute("UPDATE users SET role = %s WHERE email = %s", (ROLE_ADMIN, 'admin@inetum.com'))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Role column migration: {e}")
        
        # Create sessions table
        c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                     (session_id TEXT PRIMARY KEY, user_email TEXT, title TEXT, messages TEXT, timestamp TEXT, is_pinned INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0)''')
        conn.commit()
                     
        # Create documents table for admin ingestion tracking
        c.execute('''CREATE TABLE IF NOT EXISTS documents 
                     (id SERIAL PRIMARY KEY, filename TEXT UNIQUE, status TEXT, error_msg TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        
        # Add progress columns + propriétaire du document
        try:
            c.execute('''ALTER TABLE documents 
                         ADD COLUMN IF NOT EXISTS progress_step VARCHAR(100) DEFAULT 'En attente',
                         ADD COLUMN IF NOT EXISTS progress_percentage INTEGER DEFAULT 0
            ''')
            c.execute('ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)')
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Progress columns may already exist: {e}")

        try:
            c.execute('ALTER TABLE user_documents ADD COLUMN IF NOT EXISTS document_id INTEGER REFERENCES documents(id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_user_documents_document_id ON user_documents(document_id)')
            c.execute("""
                UPDATE user_documents ud
                SET document_id = d.id
                FROM documents d
                WHERE ud.document_id IS NULL AND ud.filename = d.filename
            """)
            c.execute("""
                UPDATE documents d
                SET user_id = u.id
                FROM users u
                JOIN user_documents ud ON ud.user_email = u.email AND ud.filename = d.filename
                WHERE d.user_id IS NULL
            """)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"user_id / document_id migration: {e}")
        
        # Create user_documents table for user uploads with full metadata
        c.execute('''CREATE TABLE IF NOT EXISTS user_documents 
                     (id SERIAL PRIMARY KEY, 
                      user_email TEXT NOT NULL,
                      session_id TEXT,
                      filename TEXT NOT NULL,
                      file_type TEXT,
                      file_size INTEGER,
                      file_hash TEXT UNIQUE,
                      source_type TEXT,
                      status TEXT DEFAULT 'En attente',
                      error_msg TEXT,
                      total_chunks INTEGER DEFAULT 0,
                      processing_time FLOAT,
                      language TEXT DEFAULT 'fr',
                      keywords TEXT,
                      extracted_entities TEXT,
                      cleaning_stats TEXT,
                      ingestion_timestamp TIMESTAMP,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        # Add progress columns to user_documents table
        try:
            c.execute('''ALTER TABLE user_documents 
                         ADD COLUMN IF NOT EXISTS progress_step VARCHAR(100) DEFAULT 'En attente',
                         ADD COLUMN IF NOT EXISTS progress_percentage INTEGER DEFAULT 0
            ''')
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"User progress columns may already exist: {e}")
        
        # Index for faster queries
        try:
            c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_email ON user_documents(user_email)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_session ON user_documents(session_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_user_documents_status ON user_documents(status)")
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Indices may already exist: {e}")

        # Backfill: ensure each existing user_documents has a corresponding
        # documents row (so document_chunks FK will be satisfied).
        try:
            c.execute("SELECT filename FROM user_documents")
            user_files = [r[0] for r in c.fetchall()]
            for fname in user_files:
                try:
                    c.execute("""
                        INSERT INTO documents (filename, status, user_id)
                        SELECT ud.filename, 'En attente', u.id
                        FROM user_documents ud
                        JOIN users u ON u.email = ud.user_email
                        WHERE ud.filename = %s
                        ON CONFLICT (filename) DO NOTHING
                    """, (fname,))
                except Exception:
                    # Fallback: check existence then insert
                    c.execute("SELECT id FROM documents WHERE filename=%s", (fname,))
                    if not c.fetchone():
                        try:
                            c.execute("INSERT INTO documents (filename, status) VALUES (%s, 'En attente')", (fname,))
                        except Exception:
                            conn.rollback()
            conn.commit()
            logger.info("✅ Backfill documents from existing user_documents completed.")
        except Exception as e:
            conn.rollback()
            logger.warning(f"Backfill documents step failed: {e}")
        
        # Ajouter des utilisateurs de test par défaut
        try:
            users = [
                ('admin@inetum.com', 'Oumaima Hallab', 'admin123', ROLE_ADMIN),
                ('demo@inetum.com', 'Imane Benzegunine', 'demo123', ROLE_USER),
            ]
            for email, name, pwd, role in users:
                c.execute("""
                    INSERT INTO users (email, name, password, role) 
                    VALUES (%s, %s, %s, %s) 
                    ON CONFLICT (email) DO UPDATE SET
                        name = EXCLUDED.name,
                        password = EXCLUDED.password,
                        role = EXCLUDED.role
                """, (email, name, pwd, role))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"User insert error (may be duplicate): {e}")

        # Réaligner les séquences SERIAL (évite id 120 après max 7, etc.)
        try:
            for table in ("users", "documents", "user_documents"):
                sync_serial_sequence(c, table)
            conn.commit()
            logger.info("✅ Séquences id (SERIAL) synchronisées.")
        except Exception as e:
            conn.rollback()
            logger.warning(f"Sequence sync: {e}")
        
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
    data = request.json or {}
    email = normalize_email(data.get('email'))
    password = data.get('password')

    domain_err = inetum_email_error(email, as_login=True)
    if domain_err:
        return domain_err
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Erreur de connexion à la base de données"}), 500
        
    try:
        c = conn.cursor()
        c.execute(
            "SELECT name, email, COALESCE(role, %s) FROM users WHERE email=%s AND password=%s",
            (ROLE_USER, email, password),
        )
        user = c.fetchone()
        conn.close()
        
        if user:
            return jsonify({"success": True, "name": user[0], "email": user[1], "role": user[2]})
        else:
            return jsonify({"success": False, "message": "Email ou mot de passe incorrect"}), 401
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"success": False, "message": "Erreur serveur"}), 500

@app.route('/api/user/profile', methods=['GET'])
def user_profile():
    """Profil utilisateur (rôle) — utile pour rafraîchir la session sans re-login."""
    email = normalize_email(request.args.get('email', ''))
    domain_err = inetum_email_error(email)
    if domain_err:
        return domain_err
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database error"}), 500
    try:
        c = conn.cursor()
        c.execute(
            "SELECT name, email, COALESCE(role, %s) FROM users WHERE email=%s",
            (ROLE_USER, email),
        )
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Utilisateur inconnu"}), 404
        return jsonify({"name": row[0], "email": row[1], "role": row[2]})
    except Exception as e:
        logger.error(f"Profile error: {e}")
        return jsonify({"error": "Erreur serveur"}), 500
    finally:
        conn.close()


@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    email = normalize_email(request.args.get('email'))
    if not email:
        return jsonify([]), 400
    domain_err = inetum_email_error(email)
    if domain_err:
        return domain_err
    
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
    data = request.json or {}
    email = normalize_email(data.get('email'))
    session = data.get('session')
    if not email or not session:
        return jsonify({"error": "Missing data"}), 400
    domain_err = inetum_email_error(email)
    if domain_err:
        return domain_err
    
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
    email = normalize_email(request.args.get('email'))
    if not email:
        return jsonify({"error": "Missing email"}), 400
    domain_err = inetum_email_error(email)
    if domain_err:
        return domain_err
    
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

def update_progress(db_doc_id, step, percentage):
    """Mettre à jour la progression d'ingestion"""
    try:
        conn = get_db_connection()
        if conn:
            c = conn.cursor()
            c.execute(
                "UPDATE documents SET progress_step=%s, progress_percentage=%s WHERE id=%s",
                (step, percentage, db_doc_id)
            )
            conn.commit()
            conn.close()
            logger.info(f"📊 Progress: {step} ({percentage}%)")
    except Exception as e:
        logger.warning(f"Failed to update progress: {e}")


def update_progress_user(db_doc_id, step, percentage):
    """Mettre à jour la progression d'ingestion pour user_documents"""
    try:
        conn = get_db_connection()
        if conn:
            c = conn.cursor()
            c.execute(
                "UPDATE user_documents SET progress_step=%s, progress_percentage=%s WHERE id=%s",
                (step, percentage, db_doc_id)
            )
            conn.commit()
            conn.close()
            logger.info(f"📊 User Progress: {step} ({percentage}%)")
    except Exception as e:
        logger.warning(f"Failed to update user progress: {e}")


def start_progress_heartbeat(update_fn, db_doc_id, step, start_pct=35, end_pct=54, interval_sec=15):
    """Keep UI progress moving during long blocking steps like media transcription."""
    stop_event = threading.Event()

    def _run():
        current = max(0, min(100, int(start_pct)))
        target = max(current, min(100, int(end_pct)))
        while not stop_event.is_set() and current < target:
            try:
                update_fn(db_doc_id, step, current)
            except Exception:
                pass
            current += 1
            stop_event.wait(interval_sec)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return stop_event

def background_ingest(filepath, filename, db_doc_id):
    current_agent = get_agent()
    try:
        # Étape 1: Validation fichier
        update_progress(db_doc_id, "Validation fichier", 5)
        
        # Vérifier fichier
        if not os.path.exists(filepath):
            raise Exception("Fichier non trouvé")
        
        file_size = os.path.getsize(filepath)
        file_ext = os.path.splitext(filename)[1].lower()
        logger.info(f"📝 Format détecté: {file_ext}, Taille: {file_size} bytes")
        update_progress(db_doc_id, "Détection format fichier", 10)
        
        # Marquer comme En cours
        conn = get_db_connection()
        if conn:
            c = conn.cursor()
            c.execute("UPDATE documents SET status='En cours' WHERE id=%s", (db_doc_id,))
            conn.commit()
            conn.close()

        # Étape 2: Initialisation
        update_progress(db_doc_id, "Initialisation ingester", 15)
        ingester = UnifiedIngester()
        logger.info(f"✓ Ingester initialisé")
        
        # Étape 3: Prétraitement du document (parsing, extraction, nettoyage)
        update_progress(db_doc_id, "Parsing du fichier", 25)
        logger.info(f"📂 Parsing fichier: {filename}")
        
        update_progress(db_doc_id, "Extraction du texte", 35)
        logger.info(f"✂️ Extraction du contenu...")
        
        update_progress(db_doc_id, "Nettoyage du texte", 45)
        logger.info(f"🧹 Nettoyage et normalisation...")
        
        # Keep progress alive while the parser/transcriber is blocking.
        # PDFs/DOCX can also take a long time, not only media files.
        ext = os.path.splitext(filename)[1].lower()
        blocking_exts = {'.pdf', '.docx', '.pptx', '.txt', '.md', '.rtf', '.odt', '.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.mp4', '.avi', '.mov', '.mkv'}
        heartbeat = None
        if ext in blocking_exts:
            heartbeat = start_progress_heartbeat(
                update_progress,
                db_doc_id,
                "Nettoyage du texte",
                start_pct=46,
                end_pct=54,
                interval_sec=15,
            )

        def progress(step, pct):
            update_progress(db_doc_id, step, pct)

        try:
            result = ingester.ingest(Path(filepath), progress_callback=progress)
        finally:
            if heartbeat:
                heartbeat.set()
        
        if result:
            chunks_text, metadata = result
            logger.info(f"✓ Document traité: {len(chunks_text)} chunks")
            
            # Étape 4: Fragmentation
            update_progress(db_doc_id, "Fragmentation en chunks", 50)
            logger.info(f"🔀 {len(chunks_text)} segments créés")
            
            # Étape 4b: Sauvegarde des chunks en BD (associés à ce document)
            try:
                from ingestion.chunk_manager import ChunkManager
                chunk_manager = ChunkManager()
                chunk_manager.save_chunks(db_doc_id, chunks_text)
                logger.info(f"✓ {len(chunks_text)} chunks sauvegardés en BD pour user_documents id={db_doc_id}")
            except Exception as e:
                logger.warning(f"⚠️  Sauvegarde chunks BD échouée: {e}")
            
            # Étape 5: Génération embeddings
            update_progress(db_doc_id, "Génération embeddings (1/2)", 55)
            logger.info(f"🧠 Génération des vecteurs d'embedding...")
            
            metadatas = [
                {"chunk_id": f"{filename}_{i}", "fingerprint": hashlib.sha256(text.encode('utf-8')).hexdigest(), "content": text, "source": filename, "type": "document", "location": "admin_upload"}
                for i, text in enumerate(chunks_text)
            ]
            
            embs = current_agent.embeddings.embed_batch(chunks_text, batch_size=32)
            logger.info(f"✓ {len(embs)} embeddings générés")
            
            update_progress(db_doc_id, "Génération embeddings (2/2)", 62)
            
            # Étape 6: Indexation FAISS
            update_progress(db_doc_id, "Indexation FAISS (démarrage)", 68)
            logger.info(f"🔍 Ajout à l'index FAISS...")
            current_agent.faiss.add_embeddings(embs, metadatas)
            current_agent.faiss.save()
            logger.info(f"✓ Index FAISS mis à jour")
            
            update_progress(db_doc_id, "Indexation FAISS (sauvegarde)", 75)
            
            # Étape 7: Indexation BM25
            update_progress(db_doc_id, "Indexation BM25 (démarrage)", 80)
            logger.info(f"📚 Ajout à l'index BM25...")
            current_agent.bm25.add_documents(chunks_text, metadatas)
            current_agent.bm25.save()
            logger.info(f"✓ Index BM25 mis à jour")
            
            update_progress(db_doc_id, "Indexation BM25 (sauvegarde)", 88)
            
            # Étape 8: Finalisation
            update_progress(db_doc_id, "Finalisation et vérification", 95)
            logger.info(f"✓ Vérification des indices...")
            
            # Success
            update_progress(db_doc_id, "Ingéré avec succès", 100)
            conn = get_db_connection()
            if conn:
                c = conn.cursor()
                c.execute("UPDATE documents SET status='Ingéré' WHERE id=%s", (db_doc_id,))
                conn.commit()
                conn.close()
            logger.info(f"✅ Ingestion de {filename} terminée et sauvegardée dans l'index.")
        else:
            last_error = ingester.failed_files[-1][1] if getattr(ingester, "failed_files", None) else None
            raise Exception(last_error or f"Format non supporté: {file_ext} / erreur d'ingestion")
    except Exception as e:
        logger.error(f"❌ Ingestion error: {e}")
        update_progress(db_doc_id, f"Erreur: {str(e)[:50]}", 0)
        conn = get_db_connection()
        if conn:
            c = conn.cursor()
            c.execute("UPDATE documents SET status='Erreur', error_msg=%s WHERE id=%s", (str(e), db_doc_id))
            conn.commit()
            conn.close()


def background_ingest_user(filepath, filename, user_email, session_id, db_doc_id, doc_master_id=None):
    """Ingestion en arrière-plan pour utilisateurs normaux avec nettoyage complet"""
    import json as json_lib
    
    current_agent = get_agent()
    user_id = get_user_id_by_email(user_email)
    try:
        # Update status to processing (user_documents)
        conn = get_db_connection()
        if conn:
            try:
                c = conn.cursor()
                c.execute("UPDATE user_documents SET status='En cours' WHERE id=%s", (db_doc_id,))
                conn.commit()
            except Exception:
                conn.rollback()
            finally:
                conn.close()

        # Ligne documents (chunks FK) — créée à l'upload ou ici si absente
        if not doc_master_id:
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    try:
                        c.execute(
                            """INSERT INTO documents (filename, status, user_id)
                               VALUES (%s, 'En attente', %s)
                               ON CONFLICT (filename) DO UPDATE SET
                                   user_id = COALESCE(documents.user_id, EXCLUDED.user_id)
                               RETURNING id""",
                            (filename, user_id),
                        )
                        res = c.fetchone()
                        if res:
                            doc_master_id = res[0]
                    except Exception:
                        c.execute("SELECT id FROM documents WHERE filename=%s", (filename,))
                        res = c.fetchone()
                        if res:
                            doc_master_id = res[0]
                        else:
                            c.execute(
                                "INSERT INTO documents (filename, status, user_id) VALUES (%s, 'En attente', %s) RETURNING id",
                                (filename, user_id),
                            )
                            doc_master_id = c.fetchone()[0]
                    if doc_master_id and user_id:
                        c.execute(
                            "UPDATE documents SET user_id = COALESCE(user_id, %s) WHERE id = %s",
                            (user_id, doc_master_id),
                        )
                    c.execute(
                        "UPDATE user_documents SET document_id = %s WHERE id = %s AND document_id IS NULL",
                        (doc_master_id, db_doc_id),
                    )
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Unable to ensure master documents row: {e}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                finally:
                    conn.close()
        elif user_id:
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    c.execute(
                        "UPDATE documents SET user_id = COALESCE(user_id, %s) WHERE id = %s",
                        (user_id, doc_master_id),
                    )
                    c.execute(
                        "UPDATE user_documents SET document_id = %s WHERE id = %s AND document_id IS NULL",
                        (doc_master_id, db_doc_id),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                finally:
                    conn.close()

        # Progress helper that updates both `user_documents` and
        # `documents` (master) when available.
        def both_progress(step, pct):
            try:
                update_progress_user(db_doc_id, step, pct)
            except Exception:
                pass
            try:
                if doc_master_id:
                    update_progress(doc_master_id, step, pct)
            except Exception:
                pass

        # User progress: validation
        both_progress("Validation fichier", 5)
        both_progress("Détection format fichier", 10)

        # Initialize ingester with cleaning enabled
        both_progress("Initialisation ingester", 15)
        ingester = UnifiedIngester(language="fr", clean_text=True, extract_entities=True)

        both_progress("Extraction du texte", 35)

        # For long media transcription, advance progress gradually instead of
        # staying on one step for many minutes.
        ext = os.path.splitext(filename)[1].lower()
        media_exts = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.mp4', '.avi', '.mov', '.mkv'}
        heartbeat = None
        if ext in media_exts:
            # heartbeat should update both targets; we pass update_progress_user
            # to show live progress in the UI while `both_progress` keeps
            # documents in sync periodically below.
            heartbeat = start_progress_heartbeat(
                update_progress_user,
                db_doc_id,
                "Transcription en cours",
                start_pct=36,
                end_pct=54,
                interval_sec=15,
            )

        try:
            result = ingester.ingest(
                Path(filepath),
                user_email=user_email,
                session_id=session_id,
                progress_callback=both_progress,
            )
        finally:
            if heartbeat:
                heartbeat.set()
        
        if result:
            chunks_text, metadata = result
            
            if not chunks_text:
                raise Exception("Aucun contenu extrait du fichier")
            both_progress("Fragmentation en chunks", 50)
            
            # Prepare enriched metadata
            metadatas = [
                {
                    "chunk_id": f"{filename}_{i}",
                    "fingerprint": hashlib.sha256(text.encode('utf-8')).hexdigest(),
                    "content": text,
                    "source": filename,
                    "type": metadata.source_type.value,
                    "location": "user_upload",
                    "user_email": user_email,
                    "session_id": session_id,
                }
                for i, text in enumerate(chunks_text)
            ]
            
            # Save chunks to DB using the master documents id so that
            # document_chunks FK constraint is satisfied.
            try:
                from ingestion.chunk_manager import ChunkManager
                if doc_master_id:
                    cm = ChunkManager()
                    cm.save_chunks(doc_master_id, chunks_text)
                    logger.info(f"✓ {len(chunks_text)} chunks sauvegardés en BD pour documents id={doc_master_id}")
                else:
                    logger.warning("No master documents id available; skipping chunk save")
            except Exception as e:
                logger.warning(f"⚠ Erreur sauvegarde chunks BD: {e}")

            # Store in FAISS (vector search)
            try:
                both_progress("Génération embeddings (1/2)", 55)
                embs = current_agent.embeddings.embed_batch(chunks_text, batch_size=32)
                both_progress("Génération embeddings (2/2)", 62)
                both_progress("Indexation FAISS (démarrage)", 68)
                current_agent.faiss.add_embeddings(embs, metadatas)
                both_progress("Indexation FAISS (ajout)", 72)
                current_agent.faiss.save()
                both_progress("Indexation FAISS (sauvegarde)", 75)
                logger.info(f"✓ FAISS indexé: {len(chunks_text)} chunks")
            except Exception as e:
                logger.warning(f"⚠ Erreur FAISS: {e}")
            
            # Store in BM25 (full-text search)
            try:
                both_progress("Indexation BM25 (démarrage)", 80)
                current_agent.bm25.add_documents(chunks_text, metadatas)
                both_progress("Indexation BM25 (ajout)", 84)
                current_agent.bm25.save()
                both_progress("Indexation BM25 (sauvegarde)", 88)
                logger.info(f"✓ BM25 indexé: {len(chunks_text)} chunks")
            except Exception as e:
                logger.warning(f"⚠ Erreur BM25: {e}")

            try:
                both_progress("Finalisation et vérification", 95)
            except Exception:
                pass
            
            # Prepare metadata JSON
            keywords_json = json_lib.dumps(metadata.keywords) if metadata.keywords else None
            entities_json = json_lib.dumps(metadata.extracted_entities) if metadata.extracted_entities else None
            cleaning_json = json_lib.dumps(metadata.cleaning_stats) if metadata.cleaning_stats else None
            
            # Save to PostgreSQL
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    c.execute("""
                        UPDATE user_documents 
                        SET status='Ingéré',
                            total_chunks=%s,
                            processing_time=%s,
                            language=%s,
                            keywords=%s,
                            extracted_entities=%s,
                            cleaning_stats=%s,
                            ingestion_timestamp=%s,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s
                    """, (
                        len(chunks_text),
                        metadata.processing_time,
                        metadata.language,
                        keywords_json,
                        entities_json,
                        cleaning_json,
                        metadata.ingestion_timestamp,
                        db_doc_id
                    ))
                    conn.commit()
                    logger.info(f"✅ Ingestion utilisateur complète: {filename} ({len(chunks_text)} chunks) - User: {user_email}")
                    both_progress("Ingéré avec succès", 100)
                    # also mark master documents record as ingested
                    if doc_master_id:
                        conn2 = get_db_connection()
                        if conn2:
                            try:
                                c2 = conn2.cursor()
                                c2.execute("UPDATE documents SET status='Ingéré' WHERE id=%s", (doc_master_id,))
                                conn2.commit()
                            except Exception:
                                try:
                                    conn2.rollback()
                                except Exception:
                                    pass
                            finally:
                                conn2.close()
                except Exception as e:
                    logger.error(f"❌ Erreur mise à jour DB: {e}")
                    conn.rollback()
                finally:
                    conn.close()
        else:
            last_error = ingester.failed_files[-1][1] if getattr(ingester, "failed_files", None) else None
            raise Exception(last_error or "Format non supporté ou erreur d'ingestion")
            
    except Exception as e:
        logger.error(f"❌ Erreur ingestion utilisateur: {e}")
        conn = get_db_connection()
        if conn:
            try:
                c = conn.cursor()
                c.execute("""
                    UPDATE user_documents 
                    SET status='Erreur', error_msg=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (str(e), db_doc_id))
                conn.commit()
            except Exception as db_e:
                logger.error(f"Erreur mise à jour erreur DB: {db_e}")
                conn.rollback()
            finally:
                conn.close()

@app.route('/api/admin/upload_and_ingest', methods=['POST'])
def admin_upload_and_ingest():
    email = request.form.get('email', '')
    auth_err = admin_auth_error(email)
    if auth_err:
        return auth_err

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

    admin_email = normalize_email(email)
    user_id = get_user_id_by_email(admin_email)
    
    # Save to DB
    db_doc_id = None
    if conn:
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO documents (filename, status, user_id) VALUES (%s, 'En attente', %s) RETURNING id",
                (file.filename, user_id),
            )
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

@app.route('/api/admin/init-progress', methods=['POST'])
def init_progress_columns():
    """Initialize progress tracking columns in documents table"""
    email = request.json.get('email', '') if request.json else ''
    auth_err = admin_auth_error(email)
    if auth_err:
        return auth_err
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        c = conn.cursor()
        # Add progress columns if they don't exist
        c.execute('''
            ALTER TABLE documents 
            ADD COLUMN IF NOT EXISTS progress_step VARCHAR(100) DEFAULT 'En attente',
            ADD COLUMN IF NOT EXISTS progress_percentage INTEGER DEFAULT 0
        ''')
        conn.commit()
        logger.info("✅ Progress columns initialized")
        return jsonify({"success": True, "message": "Progress columns initialized"})
    except Exception as e:
        logger.error(f"❌ Error initializing progress columns: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/documents', methods=['GET'])
def get_admin_documents():
    email = request.args.get('email', '')
    auth_err = admin_auth_error(email)
    if auth_err:
        return auth_err
        
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    try:
        c = conn.cursor()
        c.execute("""
            SELECT d.id, d.filename, d.status, d.error_msg, d.created_at,
                   d.progress_step, d.progress_percentage, d.user_id,
                   u.email, u.name
            FROM documents d
            LEFT JOIN users u ON u.id = d.user_id
            ORDER BY d.created_at DESC
        """)
        rows = c.fetchall()
        docs = [{
            "id": r[0], "filename": r[1], "status": r[2], "error_msg": r[3],
            "created_at": r[4], "progress_step": r[5], "progress_percentage": r[6],
            "user_id": r[7], "user_email": r[8], "user_name": r[9],
        } for r in rows]
        return jsonify(docs)
    except Exception as e:
        # Fallback if columns don't exist yet
        try:
            c = conn.cursor()
            c.execute("SELECT id, filename, status, error_msg, created_at FROM documents ORDER BY created_at DESC")
            rows = c.fetchall()
            docs = [{"id": r[0], "filename": r[1], "status": r[2], "error_msg": r[3], "created_at": r[4], "progress_step": "En attente", "progress_percentage": 0, "user_id": None, "user_email": None, "user_name": None} for r in rows]
            return jsonify(docs)
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500
    finally:
        conn.close()


@app.route('/api/documents/<int:doc_id>/ingestion-status', methods=['GET'])
def get_document_ingestion_status(doc_id):
    """Statut d'ingestion d'un document (table documents) — sans droits admin."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database error"}), 500
    try:
        c = conn.cursor()
        c.execute(
            """SELECT id, filename, status, error_msg, progress_step, progress_percentage
               FROM documents WHERE id=%s""",
            (doc_id,),
        )
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Document not found"}), 404
        return jsonify({
            "id": row[0],
            "filename": row[1],
            "status": row[2],
            "error_msg": row[3],
            "progress_step": row[4] or "En attente",
            "progress_percentage": row[5] if row[5] is not None else 0,
        })
    except Exception as e:
        try:
            c = conn.cursor()
            c.execute(
                "SELECT id, filename, status, error_msg FROM documents WHERE id=%s",
                (doc_id,),
            )
            row = c.fetchone()
            if not row:
                return jsonify({"error": "Document not found"}), 404
            return jsonify({
                "id": row[0],
                "filename": row[1],
                "status": row[2],
                "error_msg": row[3],
                "progress_step": "En attente",
                "progress_percentage": 0,
            })
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500
    finally:
        conn.close()


@app.route('/api/admin/transactions', methods=['GET'])
def get_admin_transactions():
    email = request.args.get('email', '')
    auth_err = admin_auth_error(email)
    if auth_err:
        return auth_err
        
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
    auth_err = admin_auth_error(email)
    if auth_err:
        return auth_err
        
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
    auth_err = admin_auth_error(email)
    if auth_err:
        return auth_err
        
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
    auth_err = admin_auth_error(email)
    if auth_err:
        return auth_err
        
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
    """Upload chat : enregistre dans documents (user_id) + user_documents, puis ingestion."""
    if 'files' not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400

    user_email = normalize_email(request.form.get('email', ''))
    session_id = request.form.get('session_id', '') or None
    domain_err = inetum_email_error(user_email)
    if domain_err:
        return domain_err
    user_id = get_user_id_by_email(user_email)
    if not user_id:
        return jsonify({"success": False, "error": "Utilisateur inconnu. Reconnectez-vous."}), 403
    
    files = request.files.getlist('files')
    uploaded_docs = []
    
    for file in files:
        if not file.filename:
            continue
            
        try:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file_content = file.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
            with open(filepath, 'wb') as f:
                f.write(file_content)
            logger.info(f"📁 Fichier sauvegardé : {file.filename}")
            
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    c.execute("SELECT id FROM user_documents WHERE file_hash=%s", (file_hash,))
                    if c.fetchone():
                        conn.close()
                        uploaded_docs.append({
                            "id": None,
                            "filename": file.filename,
                            "status": "duplicate",
                            "error": "Ce fichier a déjà été traité",
                        })
                        continue

                    c.execute(
                        "INSERT INTO documents (filename, status, user_id) VALUES (%s, 'En attente', %s) RETURNING id",
                        (file.filename, user_id),
                    )
                    doc_id = c.fetchone()[0]
                    c.execute(
                        """
                        INSERT INTO user_documents
                        (user_email, session_id, filename, file_type, file_size, file_hash,
                         status, document_id)
                        VALUES (%s, %s, %s, %s, %s, %s, 'En attente', %s)
                        RETURNING id
                        """,
                        (
                            user_email,
                            session_id,
                            file.filename,
                            file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else '',
                            len(file_content),
                            file_hash,
                            doc_id,
                        ),
                    )
                    user_doc_id = c.fetchone()[0]
                    conn.commit()
                    logger.info(f"✓ Document #{doc_id} (user #{user_id}) — user_documents #{user_doc_id}")
                    
                    thread = threading.Thread(
                        target=background_ingest_user,
                        args=(filepath, file.filename, user_email, session_id, user_doc_id, doc_id),
                    )
                    thread.daemon = True
                    thread.start()
                    
                    uploaded_docs.append({
                        "id": doc_id,
                        "user_document_id": user_doc_id,
                        "filename": file.filename,
                        "status": "En attente",
                    })
                except Exception as e:
                    logger.error(f"❌ Erreur insertion BD : {e}")
                    conn.rollback()
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"❌ Erreur upload fichier {file.filename} : {e}")
    
    return jsonify({
        "message": f"{len(uploaded_docs)} fichier(s) uploadé(s) - Ingestion en cours...",
        "files": uploaded_docs,
        "success": len(uploaded_docs) > 0
    })

@app.route('/api/ask', methods=['POST'])
def ask():
    current_agent = get_agent()
    
    data = request.json or {}
    question = data.get('question')
    session_id = data.get('session_id') or request.args.get('session_id')
    history = data.get('history') or []
    
    if not question:
        return jsonify({"error": "Question vide"}), 400
    
    logger.info(f"❓ Question reçue: {question} | session={session_id}")
    
    try:
        if history:
            # Éviter le doublon du message courant (déjà ajouté côté client)
            trimmed_history = list(history[-10:])
            if trimmed_history:
                last_item = trimmed_history[-1]
                last_role = last_item.get('role') or ('assistant' if last_item.get('sender') == 'ai' else 'user')
                last_content = (last_item.get('content') or last_item.get('text') or '').strip()
                if last_role == 'user' and last_content == str(question).strip():
                    trimmed_history = trimmed_history[:-1]

            current_agent.conversation_buffer.messages = []
            for item in trimmed_history:
                role = item.get('role') or ('assistant' if item.get('sender') == 'ai' else 'user')
                content = item.get('content') or item.get('text') or ''
                if role == 'assistant':
                    content = _strip_html_from_text(str(content))
                if role == 'user':
                    current_agent.conversation_buffer.add_user_message(str(content))
                elif role == 'assistant':
                    current_agent.conversation_buffer.add_assistant_message(str(content))

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
            "metrics": result.get("metrics", {}),
            "verified": result.get("metrics", {}).get("verified", False),
        })
    except Exception as e:
        logger.error(f"❌ Erreur lors de la génération: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def status():
    current_agent = get_agent()
    return jsonify(current_agent.get_system_status())


# ==================== ROUTES UTILISATEUR - UPLOAD & INGESTION ====================

@app.route('/api/user/upload_and_ingest', methods=['POST'])
def user_upload_and_ingest():
    """Upload fichier/vidéo utilisateur avec extraction + nettoyage auto"""
    user_email = normalize_email(request.form.get('email', ''))
    session_id = request.form.get('session_id', '')
    
    if not user_email:
        return jsonify({"error": "Email manquant"}), 400
    domain_err = inetum_email_error(user_email)
    if domain_err:
        return domain_err
    user_id = get_user_id_by_email(user_email)
    if not user_id:
        return jsonify({"error": "Utilisateur inconnu. Reconnectez-vous."}), 403
    
    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nom de fichier vide"}), 400
    
    # Vérifier le doublon par hash
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file_content = file.read()
    file_hash = hashlib.sha256(file_content).hexdigest()
    file.seek(0)  # Reset position
    
    conn = get_db_connection()
    if conn:
        try:
            c = conn.cursor()
            # Check if file already ingested
            c.execute("SELECT id FROM user_documents WHERE file_hash=%s", (file_hash,))
            res = c.fetchone()
            if res:
                conn.close()
                return jsonify({
                    "error": "Ce fichier a déjà été traité",
                    "status": "duplicate"
                }), 409
        except Exception as e:
            logger.error(f"Erreur vérification doublon: {e}")
    
    # Save file
    try:
        file.save(filepath)
    except Exception as e:
        logger.error(f"Erreur sauvegarde fichier: {e}")
        return jsonify({"error": f"Erreur sauvegarde: {e}"}), 500
    
    doc_master_id = None
    user_doc_id = None
    if conn:
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO documents (filename, status, user_id) VALUES (%s, 'En attente', %s) RETURNING id",
                (file.filename, user_id),
            )
            doc_master_id = c.fetchone()[0]
            c.execute(
                """
                INSERT INTO user_documents
                (user_email, session_id, filename, file_type, file_size, file_hash,
                 status, document_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'En attente', %s)
                RETURNING id
                """,
                (
                    user_email,
                    session_id if session_id else None,
                    file.filename,
                    file.filename.split('.')[-1].lower(),
                    len(file_content),
                    file_hash,
                    doc_master_id,
                ),
            )
            user_doc_id = c.fetchone()[0]
            conn.commit()
        except Exception as e:
            logger.error(f"Erreur insertion DB: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    if not doc_master_id or not user_doc_id:
        return jsonify({"error": "Erreur enregistrement en base"}), 500
    
    thread = threading.Thread(
        target=background_ingest_user,
        args=(filepath, file.filename, user_email, session_id, user_doc_id, doc_master_id),
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "document_id": doc_master_id,
        "user_document_id": user_doc_id,
        "message": "Fichier uploadé. Extraction + nettoyage en cours...",
        "status": "processing",
    })


@app.route('/api/user/documents', methods=['GET'])
def user_get_documents():
    """Récupère les documents uploadés par l'utilisateur"""
    user_email = normalize_email(request.args.get('email', ''))
    session_id = request.args.get('session_id')
    
    if not user_email:
        return jsonify({"error": "Email manquant"}), 400
    domain_err = inetum_email_error(user_email)
    if domain_err:
        return domain_err
    
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500
    
    try:
        c = conn.cursor()

        try:
            if session_id:
                # Get documents for specific session (with progress columns)
                c.execute("""
                    SELECT id, filename, file_type, file_size, status, total_chunks,
                           processing_time, language, created_at, ingestion_timestamp,
                           progress_step, progress_percentage
                    FROM user_documents
                    WHERE user_email=%s AND session_id=%s
                    ORDER BY created_at DESC
                """, (user_email, session_id))
            else:
                # Get all documents for user (with progress columns)
                c.execute("""
                    SELECT id, filename, file_type, file_size, status, total_chunks,
                           processing_time, language, created_at, ingestion_timestamp,
                           progress_step, progress_percentage
                    FROM user_documents
                    WHERE user_email=%s
                    ORDER BY created_at DESC
                    LIMIT 100
                """, (user_email,))
            rows = c.fetchall()
            has_progress_cols = True
        except Exception:
            # Fallback for older schemas without progress columns
            if session_id:
                c.execute("""
                    SELECT id, filename, file_type, file_size, status, total_chunks,
                           processing_time, language, created_at, ingestion_timestamp
                    FROM user_documents
                    WHERE user_email=%s AND session_id=%s
                    ORDER BY created_at DESC
                """, (user_email, session_id))
            else:
                c.execute("""
                    SELECT id, filename, file_type, file_size, status, total_chunks,
                           processing_time, language, created_at, ingestion_timestamp
                    FROM user_documents
                    WHERE user_email=%s
                    ORDER BY created_at DESC
                    LIMIT 100
                """, (user_email,))
            rows = c.fetchall()
            has_progress_cols = False

        docs = []
        for row in rows:
            docs.append({
                "id": row[0],
                "filename": row[1],
                "file_type": row[2],
                "file_size": row[3],
                "status": row[4],
                "total_chunks": row[5],
                "processing_time": row[6],
                "language": row[7],
                "created_at": str(row[8]),
                "ingestion_timestamp": str(row[9]) if row[9] else None,
                "progress_step": row[10] if has_progress_cols else "En attente",
                "progress_percentage": row[11] if has_progress_cols else 0,
            })
        
        return jsonify(docs)
        
    except Exception as e:
        logger.error(f"Erreur récupération documents: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/api/user/documents/<int:doc_id>', methods=['GET'])
def user_get_document_details(doc_id):
    """Récupère les détails d'un document (métadonnées enrichies)"""
    user_email = normalize_email(request.args.get('email', ''))
    
    if not user_email:
        return jsonify({"error": "Email manquant"}), 400
    domain_err = inetum_email_error(user_email)
    if domain_err:
        return domain_err
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Erreur BD"}), 500
    
    try:
        c = conn.cursor()
        c.execute("""
            SELECT id, filename, file_type, file_size, status, total_chunks,
                   processing_time, language, keywords, extracted_entities, 
                   cleaning_stats, error_msg, created_at, ingestion_timestamp
            FROM user_documents
            WHERE id=%s AND user_email=%s
        """, (doc_id, user_email))
        
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Document non trouvé"}), 404
        
        # Parse JSON fields
        keywords = json.loads(row[8]) if row[8] else []
        entities = json.loads(row[9]) if row[9] else {}
        cleaning = json.loads(row[10]) if row[10] else {}
        
        return jsonify({
            "id": row[0],
            "filename": row[1],
            "file_type": row[2],
            "file_size": row[3],
            "status": row[4],
            "total_chunks": row[5],
            "processing_time": row[6],
            "language": row[7],
            "keywords": keywords,
            "extracted_entities": entities,
            "cleaning_stats": cleaning,
            "error_msg": row[11],
            "created_at": str(row[12]),
            "ingestion_timestamp": str(row[13]) if row[13] else None
        })
        
    except Exception as e:
        logger.error(f"Erreur détails document: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/api/user/documents/<int:doc_id>/delete', methods=['DELETE'])
def user_delete_document(doc_id):
    """Supprime un document utilisateur"""
    user_email = normalize_email(request.args.get('email', ''))
    
    if not user_email:
        return jsonify({"error": "Email manquant"}), 400
    domain_err = inetum_email_error(user_email)
    if domain_err:
        return domain_err
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Erreur BD"}), 500
    
    try:
        c = conn.cursor()
        # Soft delete
        c.execute("""
            UPDATE user_documents
            SET status='Supprimé', updated_at=CURRENT_TIMESTAMP
            WHERE id=%s AND user_email=%s
        """, (doc_id, user_email))
        
        if c.rowcount == 0:
            conn.close()
            return jsonify({"error": "Document non trouvé"}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Document supprimé"})
        
    except Exception as e:
        logger.error(f"Erreur suppression document: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ==================== ROUTES CHUNKS & TRANSCRIPTIONS ====================

@app.route('/api/documents/<int:doc_id>/chunks', methods=['GET'])
def get_document_chunks(doc_id):
    """Récupère tous les chunks d'un document"""
    try:
        from ingestion.chunk_manager import ChunkManager
        chunk_manager = ChunkManager()
        chunks = chunk_manager.get_chunks(doc_id)
        
        return jsonify({
            "document_id": doc_id,
            "total_chunks": len(chunks),
            "chunks": chunks
        })
    except Exception as e:
        logger.error(f"Erreur récupération chunks: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/documents/<int:doc_id>/content', methods=['GET'])
def get_document_full_content(doc_id):
    """Récupère le texte complet d'un document (tous les chunks combinés)"""
    try:
        from ingestion.chunk_manager import ChunkManager
        chunk_manager = ChunkManager()
        full_text = chunk_manager.get_full_text(doc_id)
        
        if not full_text:
            return jsonify({"error": "Aucun contenu trouvé pour ce document"}), 404
        
        return jsonify({
            "document_id": doc_id,
            "content": full_text,
            "content_length": len(full_text),
            "preview": full_text[:500] + "..." if len(full_text) > 500 else full_text
        })
    except Exception as e:
        logger.error(f"Erreur récupération contenu: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/documents/<int:doc_id>/stats', methods=['GET'])
def get_document_chunk_stats(doc_id):
    """Récupère les statistiques des chunks d'un document"""
    try:
        from ingestion.chunk_manager import ChunkManager
        chunk_manager = ChunkManager()
        stats = chunk_manager.get_statistics(doc_id)
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Erreur statistiques: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # L'agent est maintenant initialisé au démarrage pour éviter le retard sur la première question
    print("\n" + "="*50)
    print("SERVEUR API LANCE SUR http://localhost:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5005, debug=False, threaded=True)