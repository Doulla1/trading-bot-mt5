# Todo - Corrections post-audit performance (Bugs P0/P1/P2)

**Debut** : 2026-06-02 20:03
**Fin** : 2026-06-02 20:08

## Taches

- [x] BUG-1 (P0): Isolation DB - get_db() singleton multi-symboles -> dict keyed par path
- [x] BUG-2 (P0): Reconciliation P&L - history_deals_get(ticket=) incorrect -> history_deals_get(position=)
- [x] PROB-5 (P0): Time exit inversee - ferme les winners au lieu des losers perdants
- [x] BUG-4 (P1): Timezone run_multi.py - datetime.now() -> datetime.utcnow() + session boundaries
- [x] PROB-6 (P1): Breakeven trop tard - seuil 100% SL -> 50% SL
- [x] PROB-8 (P1): Filtre RSI/BB overbought/oversold sur entrees BUY/SELL
- [x] BUG-3 (P2): OCR ancrage prix actuel + detail="high" + max_tokens=500
- [x] get_recent_trades: filtrer par symbole pour isoler contexte DeepSeek
- [x] Mettre a jour les tests (52 tests, tout vert)
- [x] xacp + relance programme

---

# Todo - Scraper Investing.com avec Playwright

**Debut** : 2026-06-02 00:52
**Fin** : 2026-06-02 00:58

## Taches

- [x] Creer `src/data/investing_calendar.py` avec Playwright
- [x] Extraire les evenements economiques de Investing.com
- [x] Implementer le mode headless avec anti-detection
- [x] Mapper les devises (JP -> JPY, AU -> AUD, etc.)
- [x] Integrer dans `src/data/calendar.py` (Investing en principal, cascade de sources)
- [x] Installer les dependances (playwright, browser chromium)
- [x] Mettre a jour les tests (31 tests, tout vert)
- [x] Mettre a jour la documentation

---

# Todo - Corrections post-audit (CRITICAL + HIGH)

**Debut** : 2026-06-01 17:04
**Fin** : 2026-06-01 17:17

## Taches

- [x] CRITICAL-01: Corriger abs() dans la limite de perte journaliere
- [x] CRITICAL-02: Inclure floating P&L dans limite journaliere
- [x] CRITICAL-03: Corriger reference prix SL/TP (bid/ask inverses)
- [x] CRITICAL-04: Corriger is_market_open() (trade_mode)
- [x] CRITICAL-05: Ajouter reconciliation trades fermes SL/TP
- [x] CRITICAL-06: Corriger NullPointerException tick dans open_position
- [x] CRITICAL-07: Remplacer mt5.screen_shot par mss
- [x] HIGH-01: Magic number configurable
- [x] HIGH-02: Validation plages de valeurs reponse IA
- [x] HIGH-03: Corriger was_executed flag
- [x] HIGH-04: Cache + rate limiting calendrier
- [x] HIGH-05: Mecanisme reconciliation positions
- [x] HIGH-06: Remplacer time.sleep par APScheduler
- [x] HIGH-07: Filtre de spread avant execution
- [x] HIGH-08: Circuit breaker apres pertes consecutives
- [x] MED-01: Thread safety SQLite
- [x] MED-03: Ajouter tests unitaires
- [x] Mettre a jour les tests
- [x] Mettre a jour la documentation

---

## Taches

- [x] Documenter l'architecture globale du projet
- [x] Documenter le module MT5 (bridge, execution, indicateurs, screenshots)
- [x] Documenter le module IA (vision, strategie, prompts)
- [x] Documenter le module Data (calendrier, base de donnees, modeles)
- [x] Documenter le scheduler et le point d'entree
- [x] Documenter la configuration et le deploiement
- [x] Creer le README complet

---

# Todo - Trading Bot IA (Fusion Markets + MT5)

**Debut** : 2026-06-01 16:01
**Fin** : 2026-06-01 16:09

## Taches

- [x] Creer la structure du projet et pyproject.toml
- [x] Implementer le bridge MT5 (connexion, donnees, screenshots)
- [x] Implementer les indicateurs techniques
- [x] Implementer l'executeur de trades
- [x] Implementer l'analyseur IA (GPT-4o-mini Vision)
- [x] Implementer le moteur de strategie (IA + indicateurs + calendrier)
- [x] Implementer le calendrier economique (ForexFactory)
- [x] Implementer la base de donnees SQLite
- [x] Implementer le scheduler (boucle d'execution)
- [x] Creer le point d'entree (run.py) et configuration
- [x] Rediger le README
- [x] Tests unitaires (squelette pret)

---

# Todo - Architecture v2: DeepSeek V4 Pro + Position Management + Multi-TF

**Debut** : 2026-06-01 20:10
**Fin** : 2026-06-01 20:19

## Taches

- [x] Enrichir indicateurs (ADX, Ichimoku, Pivots, patterns, structure marche)
- [x] Creer src/ai/ocr.py (GPT-4o-mini → extraction visuelle chart)
- [x] Creer src/ai/analyzer.py (DeepSeek V4 Pro → decision avec contexte 1M)
- [x] Mettre a jour prompts.py (prompts separes OCR + Decision)
- [x] Ajouter gestion positions (breakeven, trailing stop, time exit)
- [x] Mettre a jour scheduler.py (pipeline multi-TF + OCR + Analyzer)
- [x] Mettre a jour les tests
- [ ] Mettre a jour la documentation

---
- [ ] Tester cycle complet

---

## Taches

- [x] Config: chemins isoles par symbole (DB, logs, screenshots)
- [x] run.py: ajouter argument --symbol
- [x] Tester: python run.py --symbol AUDUSD --stats -> DB isolee audusd
- [x] Tester: python run.py --symbol GBPUSD --stats -> DB isolee gbpusd
- [x] Bugfix: colonne `confidence` -> `decision_confidence` dans get_statistics()
- [x] Mettre a jour les tests
- [x] Mettre a jour la documentation
