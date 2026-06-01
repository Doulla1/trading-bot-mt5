# Glossaire forex et trading

## Termes generaux

| Terme | Definition |
|---|---|
| **Forex** | Foreign Exchange - marche des changes, le plus grand marche financier au monde |
| **Paire de devises** | Quotation de deux devises (ex: EUR/USD). La premiere est la devise de base, la seconde la devise de cotation |
| **Pip** | Plus petit mouvement de prix. Pour la plupart des paires, 1 pip = 0.0001. Pour le JPY, 1 pip = 0.01 |
| **Spread** | Difference entre le prix bid (vente) et ask (achat). Cout implicite du trade |
| **Lot** | Taille standard d'un trade. 1 lot = 100 000 unites de la devise de base |
| **Volume** | Taille de la position exprimee en lots (ex: 0.10 = 10 000 unites) |
| **Leverage** | Effet de levier. Exemple: 1:30 signifie que 1 000 capital controle 30 000 de position |
| **Margin** | Garantie requise pour ouvrir une position levier |

## Ordres et positions

| Terme | Definition |
|---|---|
| **BUY (Long)** | Ordre d'achat. Parie sur la hausse du prix |
| **SELL (Short)** | Ordre de vente. Parie sur la baisse du prix |
| **Stop Loss (SL)** | Ordre de cloture automatique en cas de perte. Limite le risque |
| **Take Profit (TP)** | Ordre de cloture automatique en cas de gain. Secure les profits |
| **Market order** | Ordre execute au prix courant du marche |
| **Pending order** | Ordre declenche quand le prix atteint un seuil |
| **Slippage** | Difference entre le prix demande et le prix d'execution |
| **Deviation** | Slippage maximum accepte (en pips) |

## Indicateurs techniques

| Terme | Definition |
|---|---|
| **RSI (Relative Strength Index)** | Oscillateur de 0 a 100. > 70 = surachete (possible baisse). < 30 = survendu (possible hausse) |
| **MACD (Moving Average Convergence Divergence)** | Indicateur de tendance. Croisement de la ligne MACD et de la ligne de signal = signal d'achat/vente |
| **Bandes de Bollinger** | Enveloppes autour d'une moyenne mobile. Prix touchant la bande superieure = surachete. Bande inferieure = survendu |
| **SMA (Simple Moving Average)** | Moyenne du prix de cloture sur N periodes. SMA 20 = court terme, SMA 50 = moyen terme |
| **ATR (Average True Range)** | Mesure de volatilite. Plus l'ATR est eleve, plus le marche est volatil |
| **OHLCV** | Open, High, Low, Close, Volume - les 5 valeurs par bougie |
| **Bougie / Chandelier** | Representation d'une periode (ex: 15 min) avec Open, High, Low, Close |
| **ADX (Average Directional Index)** | Indicateur 0-100. > 25 = tendance, < 20 = range. Mesure la force de la tendance, PAS sa direction |
| **Ichimoku Kinko Hyo** | Systeme complet: Tenkan (9), Kijun (26), Cloud (Senkou A/B), Chikou. Identifie tendance, supports, resistances |
| **Pivot Points** | Niveaux calcules depuis le range de la bougie precedente: PP, R1-R3, S1-S3. Utilises pour les supports/resistances intraday |
| **Pattern chandelier** | Figure formee par 1-3 bougies: doji, marteau (hammer), englobante (engulfing), etoile filante (shooting star) |
| **Structure de marche** | Succession de highs/lows: HH+HL = tendance haussiere, LH+LL = tendance baissiere |

## Chrono-analyse (analyse temporelle)

| Terme | Definition |
|---|---|
| **Timeframe** | Periode de chaque bougie: M1 (1 min), M5, M15, M30, H1, H4, D1, W1 |
| **Tendance court terme** | Compare le prix actuel a la SMA 20. "haussier" ou "baissier" |
| **Tendance moyen terme** | Compare le prix actuel a la SMA 50. "haussier", "baissier" ou "indetermine" |
| **Support** | Niveau de prix ou la demande est assez forte pour stopper une baisse |
| **Resistance** | Niveau de prix ou l'offre est assez forte pour stopper une hausse |

## Calendrier economique

| Terme | Definition |
|---|---|
| **ForexFactory** | Site web de reference pour le calendrier des evenements economiques |
| **Evenement HIGH** | Publication macroeconomique majeure (NFP, FOMC, CPI). Impact fort sur les prix |
| **NFP (Non-Farm Payrolls)** | Rapport sur l'emploi americain (1er vendredi du mois) |
| **FOMC** | Reunion de la Reserve Federale americaine sur les taux d'interet |
| **CPI (Consumer Price Index)** | Indice des prix a la consommation = inflation |
| **Previous / Forecast / Actual** | Valeur precedente, prevue, et reelle d'un indicateur |
| **Devise** | Code ISO de la monnaie (EUR, USD, GBP, JPY, CHF, AUD, NZD, CAD) |

## Architecture du bot v2.1

| Terme | Definition |
|---|---|
| **GPT-4o-mini** | Modele OpenAI utilise pour l'OCR visuel du chart genere. Ne prend PAS de decision |
| **DeepSeek V4 Pro** | Modele de decision principal. Contexte 1M tokens, recoit TOUTES les donnees + historique + memoire |
| **OCR (Optical Character Recognition)** | Ici: extraction de la structure visuelle du chart (niveaux S/R, patterns, phase) |
| **Chart genere** | Graphique cree par `chart_renderer.py` via mplfinance: Ichimoku, EMA, Bollinger, Pivots |
| **Base64** | Encodage de l'image pour transmission aux API IA |
| **JSON** | Format de la decision: action, confidence, reasoning, SL, TP, risk_level |
| **SQLite** | Base de donnees locale. Tables: `trades`, `analysis_logs`, `bot_state`, `calendar_cache` |
| **Breakeven** | Deplacement du SL au prix d'entree quand le profit atteint 1x le SL initial |
| **Trailing Stop** | SL qui suit le prix a distance fixe quand le profit atteint 2x le SL initial |
| **Time Exit** | Fermeture automatique si la position stagne depuis plus de 45 minutes |
