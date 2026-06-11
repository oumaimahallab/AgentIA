#!/usr/bin/env python3
"""
Script pour tester le pipeline d'upload/ingestion COMPLET
Simule exactement ce que fait l'interface admin
"""

import os
import sys
import hashlib
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Ajoute le chemin au projet
sys.path.insert(0, str(Path(__file__).parent / "unified-agent"))

load_dotenv()

# === ÉTAPE 1: Simule un upload et création DB ===
def test_complete_pipeline():
    print("=" * 80)
    print("🎬 TEST DU PIPELINE COMPLET: UPLOAD → TRANSCRIPTION → INGESTION → DB")
    print("=" * 80)
    
    video_path = Path("unified-agent/ui/uploads") / "[Accompagnement DEV et Support CTIME]-20260512_100450-Enregistrement de la réunion.mp4"
    
    if not video_path.exists():
        print(f"❌ Fichier pas trouvé: {video_path}")
        return False
    
    print(f"\n✓ Fichier trouvé: {video_path.name}")
    size_mb = video_path.stat().st_size / (1024*1024)
    print(f"✓ Taille: {size_mb:.2f} MB")
    
    # === ÉTAPE 2: Crée une entrée DB ===
    print("\n--- ÉTAPE 1: Création d'une entrée DB ---")
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "root")
        )
        c = conn.cursor()
        
        # Ajoute le document à la DB
        c.execute(
            "INSERT INTO documents(filename, status, created_at) VALUES(%s, %s, NOW()) RETURNING id",
            (video_path.name, "En attente")
        )
        db_doc_id = c.fetchone()[0]
        conn.commit()
        
        print(f"✓ Document créé en DB avec ID: {db_doc_id}")
        print(f"✓ Status initial: 'En attente'")
        
    except Exception as e:
        print(f"❌ Erreur DB: {e}")
        return False
    
    # === ÉTAPE 3: Teste l'ingestion ===
    print("\n--- ÉTAPE 2: Test d'ingestion (transcription + parsing) ---")
    try:
        from ingestion.unified_ingester import UnifiedIngester
        
        ingester = UnifiedIngester()
        
        # Met le status à "En cours"
        print(f"✓ Mise à jour status → 'En cours'")
        c.execute("UPDATE documents SET status='En cours' WHERE id=%s", (db_doc_id,))
        conn.commit()
        
        # Lance l'ingestion
        print(f"⏳ Lancement de la transcription (cela peut prendre 5-20 min pour 360MB)...")
        result = ingester.ingest(video_path)
        
        if result:
            chunks_text, metadata = result
            print(f"\n✅ Ingestion réussie!")
            print(f"   → Chunks créés: {len(chunks_text)}")
            print(f"   → Langue détectée: {metadata.language}")
            print(f"   → Type: {metadata.source_type.value}")
            
            # === ÉTAPE 4: Teste l'embedding et indexation ===
            print(f"\n--- ÉTAPE 3: Embedding et indexation ---")
            try:
                # Charge l'agent pour accéder aux indices
                from orchestration.agent import UnifiedAgent
                agent = UnifiedAgent.get_instance()
                
                # Crée les métadonnées
                metadatas = []
                for i, text in enumerate(chunks_text):
                    meta = {
                        "chunk_id": f"{video_path.name}_{i}",
                        "fingerprint": hashlib.sha256(text.encode()).hexdigest(),
                        "content": text,
                        "source": video_path.name,
                        "type": "video_transcription",
                        "location": "admin_upload"
                    }
                    metadatas.append(meta)
                
                # Embedding
                print(f"✓ Embedding de {len(chunks_text)} chunks...")
                embs = agent.embeddings.embed_batch(chunks_text, batch_size=32)
                
                # Index FAISS
                print(f"✓ Indexation FAISS...")
                agent.faiss.add_embeddings(embs, metadatas)
                agent.faiss.save()
                
                # Index BM25
                print(f"✓ Indexation BM25...")
                agent.bm25.add_documents(chunks_text, metadatas)
                agent.bm25.save()
                
                # === ÉTAPE 5: Mise à jour DB finale ===
                print(f"\n--- ÉTAPE 4: Mise à jour du status final ---")
                c.execute("UPDATE documents SET status='Ingéré' WHERE id=%s", (db_doc_id,))
                conn.commit()
                
                print(f"✅ Document #{db_doc_id} status: 'Ingéré'")
                print(f"\n{'='*80}")
                print(f"✅ SUCCÈS: La vidéo a été entièrement traitée!")
                print(f"{'='*80}")
                
                return True
                
            except Exception as e:
                print(f"❌ Erreur d'embedding/indexation: {e}")
                c.execute(
                    "UPDATE documents SET status='Erreur', error_msg=%s WHERE id=%s", 
                    (str(e)[:500], db_doc_id)
                )
                conn.commit()
                return False
        else:
            print(f"❌ Ingestion retourné None")
            c.execute(
                "UPDATE documents SET status='Erreur', error_msg=%s WHERE id=%s",
                ("Ingestion returned None", db_doc_id)
            )
            conn.commit()
            return False
            
    except Exception as e:
        print(f"❌ Erreur d'ingestion: {e}")
        import traceback
        traceback.print_exc()
        try:
            c.execute(
                "UPDATE documents SET status='Erreur', error_msg=%s WHERE id=%s",
                (str(e)[:500], db_doc_id)
            )
            conn.commit()
        except:
            pass
        return False
    finally:
        try:
            conn.close()
        except:
            pass

if __name__ == "__main__":
    success = test_complete_pipeline()
    sys.exit(0 if success else 1)
