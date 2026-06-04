# Rapport d'Analyse Approfondie - Trades du 03-04 Juin 2026

**Date** : 2026-06-04
**Periode analysee** : 03/06/2026 00:00 - 04/06/2026 13:30 UTC
**Symboles** : EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, XAUUSD

---

## 1. Resume Global

| Indicateur | Valeur |
|---|---|
| Trades totaux (03-04 juin) | 29 (dont 3 ouverts) |
| Trades fermes | 26 |
| Gagnants | 3 |
| Perdants | 11 |
| Breakeven (TIME EXIT) | 12 |
| **P&L Total ferme** | **-34.30** |
| Gain moyen | +3.84 (3 trades) |
| Perte moyenne | -4.89 (11 trades) |
| Pire perte | -12.98 (XAUUSD) |
| Win rate reel (hors BE) | **21.4%** (3/14) |

### Par Symbole

| Symbole | Trades | Gagnants | Perdants | BE | P&L |
|---|---|---|---|---|---|
| EURUSD | 14 | 1 | 1 | 12 | -5.90 |
| XAUUSD | 3 | 0 | 2 | 1 | **-19.34** |
| GBPUSD | 4 | 0 | 4 | 0 | -5.91 |
| USDJPY | 4 | 0 | 4 | 0 | -4.97 |
| AUDUSD | 1 | 0 | 1 | 0 | -2.33 |
| USDCHF | 3 | 2 | 1 | 0 | +4.15 |

---

## 2. Les 7 Defauts Majeurs Identifies

### DEFAUT 1 [CRITIQUE] - L'ATR SL config n'est PAS applique par l'IA

**Probleme** : La config v4.0 (src/ai/strategy.py) definit XAUUSD: min_sl=150 pips, atr_mult=0.5 mais l'IA DeepSeek continue d'imposer des SL de 15-20 pips sur l'or.

**Preuves** :
| Ticket | Symbole | Entree | SL | SL Pips | Config min | Resultat |
|---|---|---|---|---|---|---|
| 411451705 | XAUUSD | 4440.47 | 4455.47 | **150** | 150 | -6.36 (SL hit) |
| 412114186 | XAUUSD | 4473.44 | 4458.44 | **150** | 150 | -12.98 (SL hit) |
| 412343274 | XAUUSD | 4474.15 | 4472.15 | **20** | 150 | ENCORE OUVERT |

**Le trade 412343274 actuellement ouvert a un SL de 20 pips sur XAUUSD alors que la config exige 150 pips minimum.** L'ATR horaire du XAUUSD est d'environ 80-150 pips. Un SL de 20 pips = traversee en quelques secondes de bruit normal.

**Cause racine** : Le code execute_decision() recoit le SL de l'IA (ex: 15-20 pips) et le passe directement a MT5 sans override par la config ATR. La section _ATR_SL_CONFIG n'est jamais utilisee pour forcer le SL minimum.

### DEFAUT 2 [CRITIQUE] - TIME EXIT toujours sur l'ancienne logique "LH cassee"

**Probleme** : Hier le correctif disait "TIME EXIT: 20-bar break au lieu de fenetres glissantes". Mais les logs du 3 juin montrent encore l'ancien pattern "LH cassee" avec les memes swings fantomes.

**Preuves du 3 juin (EURUSD)** :
`
09:46 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16241)
09:55 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16241)
10:04 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16233)
10:20 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16225)
10:24 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16225)
10:33 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16208)
10:41 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16208)
10:44 TIME EXIT: SELL structure LH cassee (recent high 1.16245 > prior 1.16208)
16:45 TIME EXIT: SELL structure LH cassee (recent high 1.16086 > prior 1.16070)
`

**12 des 14 trades EURUSD sont des TIME EXIT.** Le swing high 1.16245 (forme a 09:09) est reste dans la fenetre de comparaison pendant **1h35**, declenchant 8 TIME EXIT en cascade.

Seule exception: le 16:06 on voit TIME EXIT: ticket 411193798, stagne depuis >45 min - c'est un nouveau type de TIME EXIT (stagnation). Mais la logique "LH cassee" domine encore.

**Consequence** : Win rate reel de **21.4%**. Les 12 BE representent des trades qui auraient potentiellement pu gagner si on les avait laisses courir dans la tendance.

### DEFAUT 3 [CRITIQUE] - Contamination des bases de donnees

**Probleme** : La database data/eurusd/trading.db contient des trades de TOUS les symboles.

**Preuves** - Contenu de data/eurusd/trading.db :
| Symbole | Nombre de trades |
|---|---|
| EURUSD | 5 |
| AUDUSD | 1 |
| GBPUSD | 2 |
| USDCHF | 4 |
| USDJPY | 1 |
| XAUUSD | 1 |

Les bases par symbole (gbpusd/trading.db, xauusd/trading.db, etc.) contiennent aussi leurs propres trades. Il y a donc **double ecriture** : certains trades vont dans la bonne base ET dans la base EURUSD.

**Cause probable** : Le settings.trading_symbol n'est pas correctement isole par processus. Quand un worker demarre, il herite du mauvais 	rading_symbol. Ou le db_path est partage via un singleton non-threadsafe (_dbs dict).

### DEFAUT 4 [MAJEUR] - L'IA ne detecte pas les marches en range

**Probleme** : L'IA persiste a ouvrir des SELL en tendance baissiere alors que le marche est clairement en range depuis des heures.

**Preuves** : Le 3 juin, EURUSD etait en range [1.1605 - 1.1623] de 09:00 a 13:30 (ADX < 25). L'OCR detectait bien phase=ranging a partir de 12:19, mais l'IA a continue a suggerer SELL avec confiance 70-82%.

Pourtant, a 12:33, DeepSeek lui-meme dit : "ADX bas (23.5) indique ranging... win rate historique tres faible (22.6%)" - l'IA SAIT que c'est un range mais suggere quand meme SELL.

**Consequence** : Les positions SELL ouvertes dans un range se font systematiquement stopper par le retour au range haut (TIME EXIT ou SL).

### DEFAUT 5 [MAJEUR] - XAUUSD: Pertes massives en tres peu de temps

**Probleme** : -19.34 sur seulement 3 trades XAUUSD. C'est 56% du P&L total negatif avec seulement 10% des trades.

| Ticket | Direction | Duree | P&L | Cause |
|---|---|---|---|---|
| 411451705 | SELL | 3h50 | -6.36 | SL hit (150 pips) |
| 412114186 | BUY | 1h17 | **-12.98** | SL hit (150 pips) |
| 412343274 | BUY | EN COURS | ? | SL = 20 pips (!) |

Meme avec le bon SL de 150 pips, XAUUSD perd. Le probleme est que la direction est incorrecte. L'or a une dynamique differente du forex - les indicateurs techniques classiques (Ichimoku, RSI, MACD) y sont moins fiables.

### DEFAUT 6 [MAJEUR] - GBPUSD et USDJPY: 100% de pertes

**Probleme** : 8 trades combines, 0 gagnants, -10.88 de pertes.

| Symbole | Trades | Pertes |
|---|---|---|
| GBPUSD | 4 | -5.91 |
| USDJPY | 4 | -4.97 |

Analyse des logs GBPUSD : Les 4 SELL ont tous ete fermes en perte ou TIME EXIT. La tendance baissiere detectee n'etait pas assez forte pour ces paires. Les SL de 18-20 pips sont trop courts pour GBPUSD qui a un ATR de 12-18 pips.

### DEFAUT 7 [MODERE] - OCR hallucine les niveaux de prix

**Probleme** : L'OCR Gemini lit parfois des niveaux completement faux.

**Exemples** :
- EURUSD a 1.16: OCR lit supports [1.0600, 1.0550] (500 pips d'erreur)
- EURUSD a 1.16: OCR lit supports [1.2100, 1.2150] (500 pips d'erreur)
- EURUSD a 1.16: OCR lit supports [1.1200, 1.1150] (400 pips d'erreur)

Ces hallucinations se produisent surtout quand l'OCR est en mode "fallback" (phase=trending_down sans niveaux corrects). L'IA recoit des donnees fausses et prend des decisions basees sur des supports/resistances inexistants.

---

## 3. Analyse Comparative : 3 Juin vs 4 Juin

| Metrique | 03 Juin (13h47) | 03-04 Juin (complet) |
|---|---|---|
| Trades | 28 | 29 |
| P&L | -49.94 | -34.30 |
| Gagnants | 11 | 3 |
| Perdants | 10 | 11 |
| BE | 7 | 12 |

**Note** : Le rapport d'hier (03/06 13h47) comptait 28 trades, -49.94. Le rapport complet (03-04/06) montre -34.30. La difference vient du fait que le rapport d'hier incluait les trades du 2 juin qui etaient encore ouverts.

Le 4 juin a deja 6 trades fermes + 3 ouverts, tous perdants sauf 1 BE. **Tendance: le systeme continue de perdre de l'argent.**

---

## 4. Suggestions d'Amelioration (Ordonnees par Impact)

### Priorite 1 - CRITIQUE (a faire immediatement)

1. **Forcer le SL minimum par le code, pas par l'IA**
   - Dans execute_decision(), ajouter un override: sl_pips = max(ai_sl_pips, config_min_sl)
   - Ne pas faire confiance a l'IA pour respecter la config
   - XAUUSD doit avoir SL >= 150 pips IMPERATIVEMENT
   - CORRECTIF IMMEDIAT : Fermer le trade XAUUSD 412343274 (SL 20 pips = suicide)

2. **Reparer le TIME EXIT "LH cassee"**
   - Verifier que la v4.0 est bien deployee (20-bar break, pas fenetres glissantes)
   - Les logs montrent _check_time_exit:398 avec "LH cassee" - c'est l'ancienne version
   - La nouvelle version devrait etre "20-bar break" ou "stagnation >45min"

3. **Reparer la contamination des DB**
   - Chaque processus worker doit avoir son propre 	rading_symbol
   - Verifier que settings.trading_symbol est bien passe par processus
   - Nettoyer la DB EURUSD des trades etrangers

### Priorite 2 - HAUTE (cette semaine)

4. **Ajouter un filtre anti-range**
   - Si ADX < 25 pendant > 3 periodes consecutives: HOLD systematique
   - L'IA le sait mais ne l'applique pas - le code doit forcer
   - Regle: if ADX < 25 for 3+ bars: skip trading

5. **Desactiver XAUUSD temporairement**
   - Le modele actuel ne comprend pas la dynamique de l'or
   - Pertes: -19.34 en 3 trades = -6.45/trade
   - Revenir apres avoir developpe un modele dedie

6. **Augmenter les SL forex au-dela du minimum config**
   - GBPUSD: min SL 25 pips (au lieu de 18), USDJPY: min SL 30 pips (au lieu de 20)
   - Le bruit normal du marche traverse les SL actuels

### Priorite 3 - MOYENNE (prochaines semaines)

7. **Ajouter un filtre de confiance directionnelle**
   - Si l'IA donne confiance > 70% mais que les 3 derniers trades dans la meme direction ont perdu: reduire la taille ou HOLD
   - Anti-martingale: ne pas insister dans une direction perdante

8. **Corriger l'OCR fallback**
   - Quand l'OCR lit des niveaux aberrants (ecart > 30% du prix), ignorer et reessayer
   - Ajouter un filtre de validation: if abs(level - price) / price > 0.02: reject

9. **Implementer un veritable trailing stop**
   - Au lieu du TIME EXIT base sur la structure, utiliser un trailing stop base sur l'ATR
   - Ex: trail = 1.5x ATR, ne se declenche qu'apres avoir atteint 1x ATR de profit

---

## 5. Conclusion

Le systeme a perdu **-34.30** sur 26 trades fermes en 2 jours. Le win rate reel (hors BE) est de **21.4%**, ce qui est insoutenable.

**Les 3 problemes racines sont :**

1. **Le TIME EXIT "LH cassee"** ferme prematurement les trades gagnants (12 BE = 0 profit au lieu de gains potentiels)
2. **L'IA ignore la configuration ATR-SL** et utilise des SL inadaptes (20 pips sur XAUUSD au lieu de 150)
3. **Le systeme trade dans des ranges** sans les detecter, accumulant des petites pertes

**Action immediate recommandee** : Mettre le bot en pause (HOLD uniquement) le temps de corriger les 3 defauts critiques ci-dessus. Chaque heure de trading en l'etat coute de l'argent.

---
*Rapport genere le 2026-06-04 a 13:37 UTC - Aucune modification de code effectuee*
