## ChronoBrain HR Agent

Agent de questions/réponses qui s’appuie sur vos transcriptions (`data/transcripts/*.txt` ou `data/transcribe/*.txt`) et peut aussi faire des **calculs de congés/vacances**.

### Prérequis

- Python 3.10+
- Dépendances:

```bash
pip install -r requirements.txt
```

### Lancer (CLI)

```bash
python -m chronobrain_hr.cli
```

Options utiles:

```bash
python -m chronobrain_hr.cli --transcripts-dir "data/transcripts" --chroma-dir "data/chroma_hr"
```

### Exemples de questions

- “Comment sont calculées les heures supplémentaires ?”
- “Résume le process pour …”
- “Calcule mon solde de congés: début 2025-09-15, au 2026-04-07, 25 jours/an, 6 jours pris”
- “Combien de jours ouvrés entre 2026-07-01 et 2026-07-12 ?”

