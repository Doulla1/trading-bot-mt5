# Rapport d'Analyse - Trades du 03 Juin 2026

**Date** : 2026-06-03
**Période analysée** : 00:00 - 13:47 UTC
**Symboles** : EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, XAUUSD

---

## 1. Résumé Global

| Indicateur | Valeur |
|---|---|
| Trades totaux | 28 |
| Gagnants | 11 |
| Perdants | 10 |
| Breakeven (TIME EXIT) | 7 |
| **P&L Total** | **-49.94** |
| Gain moyen | +1.13 |
| Perte moyenne | -6.23 |
| Pire perte | -10.33 (XAUUSD) |
| Win rate réel | 52% (hors BE) |

### Par Symbole

| Symbole | Trades | Gagnants | Perdants | BE | P&L |
|---|---|---|---|---|---|
| EURUSD | 11 | 7 | 4 | 0 | -0.89 |
| XAUUSD | 5 | 0 | 3 | 2 | **-27.57** |
| USDJPY | 5 | 2 | 1 | 2 | -7.73 |
| GBPUSD | 2 | 0 | 1 | 1 | -9.10 |
| AUDUSD | 1 | 0 | 1 | 0 | -5.37 |
| USDCHF | 4 | 2 | 0 | 2 | +0.72 |

---

## 2. Les 8 Défauts Majeurs Identifiés

### DÉFAUT 1 [CRITIQUE] - TIME EXIT : Détection de structure cassée par un swing fantôme

**Problème** : La fonction _check_time_exit() compare max(highs[-5:]) vs max(highs[-10:-5]). Quand un swing high important (ex: 1.16245 sur EURUSD) entre dans la fenêtre, il déclenche des TIME EXIT en cascade même si la tendance baissière est intacte.

**Preuves** :
- EURUSD : le même ecent high 1.16245 > prior a déclenché **7 TIME EXIT consécutifs** entre 09:46 et 10:44
- USDCHF : le même ecent low 0.78836 < prior a déclenché **4 TIME EXIT** en 30 minutes
- USDJPY : ecent high 159.864 > prior a déclenché 2 TIME EXIT

**Conséquence** : Les positions sont fermées prématurément alors qu'elles étaient alignées avec la tendance. Les 7 breakeven trades (profit=0.00) sont TOUS des TIME EXIT sur structure.

**Exemple concret EURUSD** :
`
09:48 SELL 1.16211 ? 09:55 TIME EXIT (LH cassee: 1.16245 > 1.16241)  [7 min, +1.08]
10:01 SELL 1.16153 ? 10:04 TIME EXIT (LH cassee: 1.16245 > 1.16233)  [3 min, +0.66]
10:15 SELL 1.16108 ? 10:20 TIME EXIT (LH cassee: 1.16245 > 1.16225)  [5 min, -1.21]
10:21 SELL 1.16128 ? 10:24 TIME EXIT (LH cassee: 1.16245 > 1.16225)  [3 min, +0.90]
10:25 SELL 1.16113 ? 10:33 TIME EXIT (LH cassee: 1.16245 > 1.16208)  [8 min, -0.10]
10:34 SELL 1.16108 ? 10:41 TIME EXIT (LH cassee: 1.16245 > 1.16208)  [7 min, +2.17]
10:42 SELL 1.16068 ? 10:44 TIME EXIT (LH cassee: 1.16245 > 1.16208)  [2 min, +0.21]
10:45 SELL 1.16070 ? 12:09 SL HIT                               [84 min, -8.97]
`

Le swing high 1.16245 (formé à 09:09) est resté dans la fenêtre [-10:-5] pendant plus d'une heure, bloquant TOUTES les positions SELL.

---

### DÉFAUT 2 [CRITIQUE] - XAUUSD : SL inadapté à la volatilité de l'or

**Problème** : Le SL de 15-20 pips sur XAUUSD est absurde. L'or bouge de 200-500 pips par bougie H1. Un SL de 20 pips est traversé en quelques secondes de bruit normal.

**Preuves** :
| Ticket | Entrée | SL | Sortie | Durée | Pertes |
|---|---|---|---|---|---|
| 410772162 | 4466.38 | 4468.38 (+20 pips) | 4468.38 | 3 min | -10.33 |
| 410776627 | 4469.68 | 4471.18 (+15 pips) | 4471.18 | 8 min | -8.80 |
| 410855994 | 4452.29 | 4454.29 (+20 pips) | 4454.29 | 3 min | -8.44 |

3 trades = **-27.57 en 14 minutes cumulées**. Les 3 SL ont été touchés en moins de 8 minutes chacun.

**Note** : Le 1er trade XAUUSD (T=410756180, entrée 4458.82, SL=4463.82 = 50 pips) a survécu 80 minutes avant d'être fermé par TIME EXIT à breakeven. Un SL à 50 pips fonctionne, un SL à 15-20 pips est suicidaire.

---

### DÉFAUT 3 [MAJEUR] - Absence de SL dynamique basé sur l'ATR

**Problème** : Le SL est fixé arbitrairement par DeepSeek (15-20 pips) sans tenir compte de l'ATR réel du marché.

| Symbole | ATR approximatif | SL utilisé | Ratio |
|---|---|---|---|
| EURUSD | 10-15 pips | 15-18 pips | ~1x ATR |
| GBPUSD | 12-18 pips | 15 pips | ~1x ATR |
| XAUUSD | 40-80 pips | 15-20 pips | **0.25-0.5x ATR** |
| USDJPY | 15-25 pips | 15-20 pips | ~1x ATR |

Un SL doit être au minimum 1.5-2x l'ATR pour absorber le bruit normal du marché.

---

### DÉFAUT 4 [MAJEUR] - Re-entry sans période de refroidissement

**Problème** : Après un TIME EXIT, le cycle suivant (15 min plus tard) peut immédiatement rouvrir une position dans la même direction. Aucun délai de carence.

**Conséquence** : Le bot "chasse" le marché, entrant et sortant frénétiquement. La séquence EURUSD ci-dessus (8 entrées en 56 minutes) est du scalping non intentionnel qui génère des frais de spread et expose à des retournements.

---

### DÉFAUT 5 [MAJEUR] - Circuit breaker contourné par les TIME EXIT

**Problème** : Le circuit breaker se déclenche après 4 pertes consécutives. Mais les TIME EXIT produisent des micro-gains (+0.21, +0.66) qui réinitialisent le compteur.

Sur EURUSD, entre 09:48 et 10:45 :
- Pertes réelles : -1.21, -0.10, -8.97 = **-10.28**
- Mais le compteur de pertes consécutives n'a jamais atteint 4 car il y avait des micro-gains intercalés

---

### DÉFAUT 6 [MAJEUR] - Limite de perte journalière globale, pas par symbole

**Problème** : La limite de 3% est calculée sur le P&L total (tous symboles). XAUUSD a perdu -27.57 avant 10h30, déclenchant la limite pour TOUS les symboles.

À partir de 10:39 UTC, le guard LIMITE PERTE JOURNALIERE ATTEINTE bloque toutes les nouvelles entrées sur XAUUSD (et potentiellement d'autres symboles). Pourtant EURUSD et USDCHF étaient encore rentables à ce moment-là.

---

### DÉFAUT 7 [MODÉRÉ] - DeepSeek biaisé vers la continuation de tendance

**Problème** : L'IA donne systématiquement 75-85% de confiance pour suivre la tendance, même après plusieurs pertes. Elle ne pondère pas assez l'historique récent des pertes.

**Exemple** : Après que XAUUSD ait perdu -10.33 en 3 minutes, le cycle suivant (4 minutes plus tard) DeepSeek recommande à nouveau SELL avec 75% de confiance et un SL de 15 pips... qui sera également touché en 8 minutes (-8.80).

---

### DÉFAUT 8 [MODÉRÉ] - TP/SL ratio sous-optimal

**Problème** : La validation 	p < sl * 1.5 force un ratio minimum de 1.5:1, mais le SL est déjà trop serré. Résultat : le TP est souvent à 23-25 pips avec un SL à 15 pips.

Avec un win rate réel de ~52% et un ratio moyen de 1:5.5 (gain moyen +1.13 vs perte moyenne -6.23), le système est mathématiquement perdant.

Ratio risque/récompense effectif : 1.13/6.23 = **0.18**, alors qu'il faudrait >1.0.

---

## 3. Classification par Impact

| Défaut | Sévérité | Impact P&L estimé | Correction estimée |
|---|---|---|---|
| #1 TIME EXIT swing fantôme | CRITIQUE | ~-15 (trades fermés trop tôt + re-entry) | 2-4h |
| #2 XAUUSD SL inadapté | CRITIQUE | -27.57 (direct) | 1-2h |
| #3 SL non-ATR | MAJEUR | ~-10 (tous symboles) | 2-3h |
| #4 Absence cooldown | MAJEUR | ~-5 (frais spread + mauvais timing) | 1h |
| #5 Circuit breaker inefficace | MAJEUR | ~-8 (pertes évitables) | 1-2h |
| #6 Limite globale vs par symbole | MAJEUR | Opportunités manquées | 1h |
| #7 Biais DeepSeek | MODÉRÉ | Structurel | Prompt engineering |
| #8 Ratio TP/SL | MODÉRÉ | Structurel | Revoir validation |

---

## 4. Recommandations (par ordre de priorité)

### Priorité 1 - Immédiat (aujourd'hui)
1. **Désactiver XAUUSD** jusqu'à ce que le SL soit corrigé (min 50-80 pips ou 1.5x ATR)
2. **Fixer le TIME EXIT** : utiliser une comparaison de structure glissante qui nettoie les vieux swings (max 10 bougies) OU désactiver temporairement le TIME EXIT structurel et revenir au time-out simple de 4h

### Priorité 2 - Court terme (cette semaine)
3. **SL dynamique ATR** : SL = max(15, ATR_14 * 1.5) avec un minimum par symbole
4. **Cooldown post-TIME EXIT** : 30 minutes sans nouvelle entrée dans la même direction
5. **Circuit breaker amélioré** : compter les pertes sur 5 trades glissants (pas seulement consécutifs)
6. **Limite de perte par symbole** : 2% par symbole + 3% global

### Priorité 3 - Moyen terme
7. **Ajuster les prompts DeepSeek** pour inclure l'historique récent des pertes et le contexte de drawdown
8. **Ratio TP/SL minimum de 2:1** ou basé sur l'ATR

---

*Rapport généré le 2026-06-03 13:48 UTC*
