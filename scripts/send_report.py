#!/usr/bin/env python
"""Script standalone pour tester l'envoi du rapport journalier.

Usage:
    python scripts/send_report.py           # Rapport du jour
    python scripts/send_report.py 2026-06-01 # Rapport d'une date specifique
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ajouter le projet au PYTHONPATH
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.reports.daily_report import send_daily_report

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d")
        except ValueError:
            print(f"Format de date invalide: {sys.argv[1]}. Utiliser YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = datetime.now(timezone.utc)

    print(f"Envoi du rapport pour le {target_date.strftime('%d/%m/%Y')}...")
    success = send_daily_report(target_date)

    if success:
        print("Rapport envoye avec succes!")
    else:
        print("Echec de l'envoi du rapport. Verifiez les logs.")
        sys.exit(1)
