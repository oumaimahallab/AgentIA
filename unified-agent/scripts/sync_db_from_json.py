import json
import psycopg2
import os

# Chemins vers les fichiers JSON
DOCS_JSON = r"c:\Users\maup10458\Desktop\AG\DataCl\data\processed\documents.json"
TRANSCRIPTS_JSON = r"c:\Users\maup10458\Desktop\AG\ChronoBrain-main\data\metadata_v13\metadata_v13.json"

# Connexion à la base de données PostgreSQL
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="postgres",
            user="postgres",
            password="root"
        )
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion à PostgreSQL: {e}")
        return None

def extract_unique_sources(filepath):
    sources = set()
    if not os.path.exists(filepath):
        print(f"⚠️ Fichier introuvable : {filepath}")
        return sources

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for item in data:
                if 'source' in item and item['source']:
                    sources.add(item['source'])
    except Exception as e:
        print(f"❌ Erreur lors de la lecture de {filepath}: {e}")
    
    return sources

def main():
    print("🔄 Démarrage de la synchronisation de la base de données...")
    
    # 1. Extraire les noms de fichiers
    doc_sources = extract_unique_sources(DOCS_JSON)
    transcript_sources = extract_unique_sources(TRANSCRIPTS_JSON)
    
    all_sources = doc_sources.union(transcript_sources)
    print(f"📊 Trouvé {len(doc_sources)} documents uniques et {len(transcript_sources)} transcriptions uniques.")
    print(f"   Total de fichiers uniques à synchroniser : {len(all_sources)}")

    # 2. Insérer dans PostgreSQL
    conn = get_db_connection()
    if not conn:
        return

    try:
        c = conn.cursor()
        
        # Récupérer les fichiers déjà dans la BD pour éviter les doublons lors de l'insertion
        c.execute("SELECT filename FROM documents")
        existing_files = set(row[0] for row in c.fetchall())
        
        added_count = 0
        for filename in all_sources:
            if filename not in existing_files:
                c.execute(
                    "INSERT INTO documents (filename, status) VALUES (%s, 'Ingéré')",
                    (filename,)
                )
                added_count += 1
        
        conn.commit()
        print(f"✅ Synchronisation terminée ! {added_count} nouveaux fichiers ont été ajoutés à la table 'documents'.")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'insertion dans la base de données: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
