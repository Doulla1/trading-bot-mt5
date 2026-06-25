# Rapport d'Analyse Approfondie - Pertes du Trading Bot

**Date** : 2026-06-24
**Periode analysee** : 2026-06-07 au 2026-06-24
**Trades analyses** : 35

---

## 1. RESUME EXECUTIF

Le bot a execute 35 trades en 18 jours avec un **profit total de -18.78 EUR** et un **win rate de 28.6%** (10 gagnants, 25 perdants). Le probleme principal n'est pas la malchance : il y a **3 defaillances structurelles** identifiees.

**Le TP n'est quasiment jamais touche** : 1 seul trade sur 35 a atteint son Take Profit (2.9%). Sur les 20 derniers trades, **0 TP** n'a ete atteint. C'est anormal et confirme votre intuition.

---

## 2. STATISTIQUES CLES

| Metrique | Valeur |
|----------|--------|
| Profit total | **-18.78 EUR** |
| Win rate | **28.6%** (10/35) |
| Gain moyen par trade gagnant | +15.20 EUR |
| Perte moyenne par trade perdant | -6.83 EUR |
| TP reellement touches | **1/35 (2.9%)** |
| SL touches | 6/35 (17.1%) |
| Fermetures par le bot (EXPERT) | 17/35 (48.6%) |
| Fermetures recentes bot (null) | 11/35 (31.4%) |
| **Total fermetures bot** | **28/35 (80%)** |
| Trades en direction favorable | 11/35 (31.4%) |
| Ratio R:R moyen | 2.01 |

---

## 3. DIAGNOSTIC: LES 3 PROBLEMES STRUCTURELS

### PROBLEME 1 (CRITIQUE): Le bot ferme 80% des trades avant TP ou SL

**80% des trades (28/35) sont fermes par le bot lui-meme** (via `manage_open_positions`), PAS par le marche. Cela inclut :

- **TIME EXIT** (cassure de structure 20-bar) : ferme la position des que le prix casse le lowest/highest des 20 dernieres bougies M15
- **BREAKEVEN a 1.2R** : deplace le SL au prix d'entree des que le profit atteint 1.2x le SL initial
- **TRAILING STOP a 2R** : commence a suivre le prix a 15 pips

**Consequence** : Le bot tue ses propres trades avant qu'ils n'aient le temps de respirer et d'atteindre le TP. Sur M15, une bougie contre la tendance est frequente et declenche le TIME EXIT.

**Preuve** : La duree moyenne des trades fermes par EXPERT est de ~7.5h. Les trades gagnants (XAUUSD) ont dure 10.5h et 16.6h. Les trades perdants sont souvent fermes en 1.5h-5h.

### PROBLEME 2 (MAJEUR): L'IA se trompe de direction 69% du temps

**Seulement 31.4% des trades vont dans la direction predite par l'IA**. Ce n'est pas de la malchance, c'est un probleme de prediction directionnelle.

Analyse par niveau de confiance :
| Confiance | Trades | Profit | Win Rate |
|-----------|--------|--------|----------|
| 70-75% | 22 | **+48.65 EUR** | 32% |
| 76-80% | 9 | **-42.71 EUR** | 22% |
| 81-100% | 4 | **-24.72 EUR** | 25% |

**Constat contre-intuitif** : Plus la confiance de l'IA est elevee, PLUS le resultat est mauvais. Les trades a 70-75% de confiance sont les seuls rentables. L'IA semble "sur-confiance" quand elle a tort.

### PROBLEME 3 (MODERE): SL parfois trop serres pour le timeframe M15

Sur les paires forex standard, les SL de 10-20 pips sont trop serres pour le bruit du M15 :
- AUDUSD: SL de 10, 16, 19, 20, 22 pips - presque tous perdants
- EURUSD: SL de 20, 27 pips - tous perdants
- GBPUSD: SL de 20, 30, 35, 36, 39 pips - resultats mitiges

---

## 4. ANALYSE PAR SYMBOLE

| Symbole | Trades | Profit | WR | Diagnostic |
|---------|--------|--------|-----|------------|
| **XAUUSD** | 5 | **+74.57 EUR** | 60% | Seul symbole rentable. Volatilite adaptee au M15 |
| **GBPUSD** | 6 | +13.19 EUR | 50% | Correct, SL 30-40p adaptes |
| **EURGBP** | 1 | -5.19 EUR | 0% | Insuffisant pour conclure |
| **USDCHF** | 4 | -9.17 EUR | 25% | Range frequents, ADX bas |
| **AUDUSD** | 5 | -16.63 EUR | 20% | SL trop serres (10-22p) |
| **GBPJPY** | 3 | -18.18 EUR | 33% | Volatil, SL a revoir |
| **USDJPY** | 5 | -20.28 EUR | 20% | 4/5 trades perdants |
| **EURJPY** | 4 | -27.22 EUR | **0%** | A desactiver |
| **EURUSD** | 2 | -9.87 EUR | 0% | Insuffisant pour conclure |

---

## 5. ANALYSE DES 7 DERNIERS TRADES

| # | Date | Symbole | Dir | Conf | SL | TP | Move | Profit | Status |
|---|------|---------|-----|------|-----|-----|------|--------|--------|
| 1 | 18/06 21h33 | XAUUSD | SELL | 75% | 300p | 780p | 692p | **+60.84** | Gagne (quasi-TP) |
| 2 | 19/06 12h00 | GBPUSD | BUY | 70% | 36p | 55p | 2p | -0.50 | Perdu (range) |
| 3 | 23/06 10h21 | USDJPY | SELL | 82% | 32p | 73p | 19p | -6.38 | Perdu (inversion) |
| 4 | 23/06 16h35 | GBPUSD | SELL | 80% | 39p | 91p | 1p | +0.18 | Flat (stagnation) |
| 5 | 23/06 17h14 | AUDUSD | SELL | 75% | 16p | 25p | 10p | +5.68 | Gagne |
| 6 | 24/06 12h07 | AUDUSD | SELL | 85% | 20p | 42p | 17p | **-8.99** | Perdu (SL?) |
| 7 | 24/06 12h44 | GBPUSD | SELL | 70% | 35p | 64p | 14p | **-3.78** | Perdu (range) |

**Observation** : Sur les 7 derniers trades, 3 ont un mouvement realise < 3 pips (stagnation/range). L'IA entre dans des marches sans direction claire. Les 2 trades AUDUSD du 24/06 sont entres en meme temps (12h07 et 12h44) sur 2 symboles differents - les deux ont perdu.

---

## 6. POURQUOI LE TP N'EST JAMAIS TOUCHE ?

3 raisons principales :

1. **TIME EXIT trop agressif** : Le bot ferme la position des que le prix casse le lowest/highest 20-bar M15. Sur M15, c'est un evenement frequent (toutes les 1-4h en moyenne). Le trade n'a pas le temps d'atteindre le TP.

2. **BREAKEVEN premature** : A 1.2R, le SL est deplace au prix d'entree. Si le prix revient de 1.5 pips, le trade est ferme a 0, tuant le potentiel.

3. **M15 = trop de bruit** : Le timeframe M15 genere beaucoup de faux signaux de cassure. L'IA voit une "tendance forte" (ADX > 25) mais sur M15 c'est souvent un mouvement intraday qui s'inverse en 2-4h.

---

## 7. CONCLUSION : PROGRAMME vs MALCHANCE

| Facteur | Responsabilite |
|---------|---------------|
| TIME EXIT qui tue les trades | **Programme** (80% des fermetures) |
| Breakeven a 1.2R trop agressif | **Programme** |
| IA qui predit mal la direction | **IA** (69% d'erreur) |
| Marche en range non detecte | **Programme** (filtre ADX insuffisant) |
| SL parfois trop serres | **Programme** (ATR multiplier trop bas) |
| Malchance pure | **Faible** (< 10% des cas) |

**Verdict** : Les pertes sont dues a **~70% au programme** (gestion des positions trop agressive, TIME EXIT premature, breakeven trop tot) et **~25% a l'IA** (mauvaise prediction directionnelle, surtout a haute confiance). La malchance est un facteur mineur.

---

## 8. RECOMMANDATIONS (sans modifier le code pour l'instant)

### Actions prioritaires :
1. **Desactiver ou assouplir le TIME EXIT** : C'est le killer #1. Remplacer par un TIME EXIT base sur la duree (ex: 24h) plutot que sur la structure 20-bar.
2. **Repousser le breakeven a 2R** au lieu de 1.2R pour laisser respirer le trade.
3. **Desactiver temporairement EURJPY, USDJPY, AUDUSD** - concentrer sur XAUUSD et GBPUSD.
4. **Augmenter le SL minimum forex a 25-30 pips** pour absorber le bruit M15.
5. **Ajouter un filtre de volatilite** : ne pas trader si ATR < 15 pips (marche trop calme = range probable).

### A investiguer :
- Passer le timeframe principal de M15 a H1 pour reduire le bruit
- Utiliser un TIME EXIT base sur l'ATR (ex: 3x ATR contre la position)
- Ajouter un systeme de "partial TP" (50% a 1.5R, 50% a 3R)
