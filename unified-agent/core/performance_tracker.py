#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Tracker - Enregistre les interactions et les métriques dans un CSV
"""

import os
import csv
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """Gère l'enregistrement des performances dans un fichier CSV"""
    
    def __init__(self, config=None):
        if config is None:
            from config import get_config
            config = get_config()
        
        self.config = config
        self.log_dir = self.config.paths.LOGS_DIR
        self.csv_path = self.log_dir / "performance_tracking.csv"
        
        self._init_csv()
        
    def _init_csv(self):
        """Initialise le fichier CSV avec les en-têtes s'il n'existe pas"""
        if not self.csv_path.exists():
            self.log_dir.mkdir(parents=True, exist_ok=True)
            headers = [
                "Timestamp", "Question", "Answer", "Sources_Count", 
                "Duration_Sec", "Faithfulness_Score", "Relevance_Score", "Intent"
            ]
            with open(self.csv_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
            logger.info(f"✓ Fichier de tracking créé: {self.csv_path}")

    def log_interaction(self, data: Dict[str, Any]):
        """Enregistre une interaction complète"""
        try:
            # Nettoyage de la réponse pour le CSV (une seule ligne)
            clean_answer = str(data.get("Answer", "")).replace("\n", " ").replace("\r", "")
            
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                data.get("Question", ""),
                clean_answer,
                data.get("Sources_Count", 0),
                round(data.get("Duration_Sec", 0.0), 3),
                data.get("Faithfulness_Score", 0.0),
                data.get("Relevance_Score", 0.0),
                data.get("Intent", "unknown")
            ]
            
            with open(self.csv_path, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
                
            logger.debug(f"✓ Interaction logguée dans {self.csv_path.name}")
        except Exception as e:
            logger.error(f"Erreur lors du logging CSV: {str(e)}")
