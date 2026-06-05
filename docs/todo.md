# Todo - Correctifs post-analyse 03-05 Juin 2026

**Debut** : 2026-06-05 00:46
**Fin** : 2026-06-05 01:09

## Taches

- [x] Forcer SL minimum imperatif dans execute_decision (bypass IA)
- [x] Reparer contamination DB (symbole explicite dans get_db/log_trade)
- [x] Ajouter filtre anti-range (HOLD si ADX < 25 depuis 3+ periodes)
- [x] Desactiver XAUUSD temporairement
- [x] Augmenter SL minimum GBPUSD et USDJPY
- [x] Mettre a jour les tests
- [x] Mettre a jour la documentation

---

# Todo - Analyse approfondie trades 03-04 Juin 2026

**Debut** : 2026-06-04 12:30
**Fin** : 2026-06-04 13:37

## Taches

- [x] Collecter les trades 03-04 juin depuis toutes les DB
- [x] Analyser les logs EURUSD, XAUUSD, GBPUSD, USDJPY
- [x] Identifier les defauts et patterns de pertes
- [x] Rediger le rapport complet
- [x] Ne rien modifier (rapport uniquement)

---

# Todo - Corrections post-analyse du 2026-06-03

**D�but** : 2026-06-03 14:22
**Fin** : 2026-06-03 14:24

## T�ches

- [x] Fixer TIME EXIT (20-bar break au lieu de fenetres glissantes)
- [x] Ajouter SL/TP bases sur l'ATR par symbole
- [x] XAUUSD: min SL 150 pips, ATR*0.5
- [x] Forex: min SL 15-20 pips, ATR*1.5
- [x] Ajouter cooldown 30min post TIME EXIT
- [x] Reset des bases de donnees (trades du jour + bot_state)
- [x] Relancer l'application

---
# Todo - Analyse approfondie des trades du 2026-06-03

**D�but** : 2026-06-03 13:48
**Fin** : 2026-06-03 13:57

## T�ches

- [x] Collecter les logs de trading de tous les symboles
- [x] Extraire les trades depuis les bases de donn�es
- [x] Analyser les patterns de pertes par symbole
- [x] Identifier les d�fauts du syst�me
- [x] R�diger le rapport d'analyse
