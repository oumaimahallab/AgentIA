import logging
from sentence_transformers import SentenceTransformer
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model_name = "intfloat/multilingual-e5-base"
logger.info(f"Test de chargement du modèle: {model_name}")

try:
    model = SentenceTransformer(model_name)
    logger.info("✅ Modèle chargé avec succès!")
    
    # Test simple d'embedding
    sentences = ["Ceci est un test", "passage: Ceci est un document"]
    embeddings = model.encode(sentences)
    logger.info(f"✅ Embedding réussi! Forme: {embeddings.shape}")
    
except Exception as e:
    logger.error(f"❌ Erreur lors du chargement: {e}")
    sys.exit(1)
