"""Generate documentation files for the reports module."""
from pathlib import Path

TECH_DOC = r'''# Module Rapports Journaliers : mailer.py, generator.py, analyzer.py, daily_report.py

**Fichiers** : `src/reports/mailer.py`, `src/reports/generator.py`, `src/reports/analyzer.py`, `src/reports/daily_report.py`

## Vue d'ensemble

Le module `src/reports/` genere et envoie un rapport journalier complet par email. Il consolide les trades de toutes les paires, calcule des statistiques, demande une analyse a DeepSeek V4 Pro, et envoie le tout par email via l'API `mailing.weltaare-tech.com`.

```mermaid
flowchart TD
    SEND[send_daily_report] --> GEN[generator.generate_daily_report]
    GEN --> DISCOVER[_discover_symbol_dbs]
    DISCOVER --> READ[Lit chaque data/SYM/trading.db]
    READ --> STATS[_compute_symbol_stats + _compute_global_stats]
    STATS --> HTML[_render_html]
    HTML --> REPORT[dict: stats + trades + symbols + html]
    SEND --> DETAIL[generator.get_symbols_detail_text]
    SEND --> AI[analyzer.analyze_daily_results]
    AI --> PROMPT[Construit prompt avec stats + trades]
    PROMPT --> DS[DeepSeek V4 Pro - analyse en francais]
    DS --> TEXT[Texte: Resume, Forces, Faiblesses, Recommandations]
    SEND --> FORMAT[_format_analysis_html]
    SEND --> SUBJECT[Sujet dynamique: P&L + Win Rate]
    SEND --> MAIL[mailer.send_email]
    MAIL --> API[POST mailing.weltaare-tech.com/api/v1/emails]
    API --> OK{201?}
    OK -->|Oui| SUCCESS[Email envoye]
    OK -->|Non| RETRY[Retry tenacity x3]
```

---

## `mailer.py` - Client HTTP pour l'API d'envoi

**Fichier** : `src/reports/mailer.py`

### `send_email(recipient_email, subject, body_html, recipient_name="", sender_name="") -> bool`

Envoie un email via l'API REST `mailing.weltaare-tech.com`.

**Authentification** : Header `X-API-Secret` avec la cle configuree dans `MAILER_API_SECRET`.

**Retry** : 3 tentatives avec backoff exponentiel (2s, 4s, 8s) via `tenacity`.

**Codes de retour** :
| Code | Signification |
|---|---|
| `201` | Email envoye avec succes. Le corps contient l'UUID de l'email. |
| `401` | `X-API-Secret` invalide. Verifier `MAILER_API_SECRET` dans `.env`. |
| `429` | Rate limit atteint. Le retry automatique gere ce cas. |
| Autre | Erreur logguee, retourne `False`. |

**Payload** :
```json
{
    "recipient_email": "dialloabdoul99c@gmail.com",
    "subject": "Rapport Trading 01/06/2026 | 5 trades | P&L: +42.50 $ | WR: 60.0%",
    "body_html": "<html>...</html>",
    "recipient_name": "Abdoul",
    "sender_name": "Trading Bot MT5"
}
```

**Dependances** : `httpx` (HTTP client), `tenacity` (retry).

---

## `generator.py` - Generateur de rapport

**Fichier** : `src/reports/generator.py`

### `generate_daily_report(date=None) -> dict`

Point d'entree principal du generateur. Decouvre toutes les bases de donnees par symbole, calcule les statistiques et produit le HTML.

**Decouverte des bases** : La fonction `_discover_symbol_dbs()` parcourt `data/` et trouve tous les fichiers `SYM/trading.db` (EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, XAUUSD).

**Retour** :
```python
{
    "stats": {                     # Statistiques globales
        "total_trades": 8,
        "closed": 6,
        "open": 2,
        "wins": 4,
        "losses": 2,
        "win_rate": 66.7,
        "total_profit": 42.50,
        "best_trade": 25.00,
        "worst_trade": -15.30,
        "avg_profit": 7.08,
        "avg_confidence": 78.5,
        "avg_duration": "12.3 min",
        "symbols_count": 3,
    },
    "trades": [...],               # Liste de tous les trades du jour
    "symbols": {                   # Detail par symbole
        "EURUSD": {
            "stats": {...},        # Memes cles que global
            "trades": [...]
        },
        ...
    },
    "html": "<html>...</html>",    # Rapport HTML complet
    "has_trades": True,
}
```

### `get_symbols_detail_text(symbols_data) -> str`

Genere un texte formate avec les details par symbole, destine au prompt DeepSeek.

```
- EURUSD: 3 trades, 2W/1L (WR: 66.7%), P&L: +15.20 $, moy/trade: +5.07 $
- GBPUSD: 2 trades, 1W/1L (WR: 50.0%), P&L: -8.50 $, moy/trade: -4.25 $
```

### `_compute_symbol_stats(trades) -> dict`

Calcule les statistiques pour un symbole : wins, losses, win rate, P&L total, meilleur/pire trade, profit moyen, duree moyenne, confiance moyenne.

### `_compute_global_stats(all_trades, symbols_data) -> dict`

Calcule les memes statistiques au niveau global (tous symboles confondus).

### `_render_html(date_display, global_stats, symbols_data, all_trades) -> str`

Produit le HTML complet du rapport :

- **Theme** : Dark mode (fond `#020617`, cartes `#0f172a`)
- **En-tete** : Titre + date + mention "Genere automatiquement"
- **Cartes resume** : Total trades, Gagnants (vert), Perdants (rouge), Win Rate, P&L Total
- **Ligne details** : Meilleur trade, Pire trade, Moyen, Duree moyenne, Confiance moyenne
- **Par symbole** : Une carte par paire avec mini-stats + tableau des trades (ouverture, direction, volume, prix, P&L)
- **Placeholder** : `{{ANALYSIS_PLACEHOLDER}}` pour l'analyse DeepSeek (remplace par `daily_report.py`)
- **Pied de page** : Nombre de paires surveillees

---

## `analyzer.py` - Analyse DeepSeek V4 Pro

**Fichier** : `src/reports/analyzer.py`

### `analyze_daily_results(stats, trades, symbols_detail) -> str`

Envoie les statistiques et trades du jour a DeepSeek V4 Pro pour une analyse approfondie.

**Prompt** : Inclut les statistiques globales, le detail par symbole, et la liste des trades (max 50). Demande une analyse en francais structuree en 4 sections :

| Section | Contenu |
|---|---|
| **Resume** | Synthese des performances du jour en 2-3 phrases |
| **Forces** | Ce qui a bien fonctionne (paires, patterns, moments de la journee) |
| **Faiblesses** | Ce qui a mal fonctionne, pertes notables, erreurs potentielles |
| **Recommandations** | Suggestions concretes (parametres, gestion du risque, filtres, horaires) |

**Modele** : `deepseek-v4-pro`, max 2000 tokens, temperature 0.4.

**Retry** : 2 tentatives avec backoff exponentiel (3s, 6s).

**Fallback** : Si `DEEPSEEK_API_KEY` est vide, retourne un message indiquant que l'analyse est indisponible.

---

## `daily_report.py` - Orchestrateur

**Fichier** : `src/reports/daily_report.py`

### `send_daily_report(date=None) -> bool`

Orchestre le pipeline complet :

1. **Generation** - `generate_daily_report(date)` : statistiques + HTML
2. **Analyse** - `analyze_daily_results(stats, trades, symbols_detail)` : texte DeepSeek
3. **Formatage** - `_format_analysis_html(text)` : conversion du texte en HTML (paragraphes, gras, emojis)
4. **Sujet** - Construction dynamique : `Rapport Trading {date} | {N} trades | P&L: +/-XX.XX $ | WR: XX%`
5. **Envoi** - `send_email(...)` vers le destinataire configure

### `_format_analysis_html(text) -> str`

Convertit le texte brut de l'analyse en HTML :
- Lignes vides -> `</p><p>`
- `**texte**` -> `<strong>texte</strong>`
- Lignes commencant par `- ` -> `<li>` (dans une `<ul>`)
- Lignes commencant par `### ` -> `<h3>`
- Echappement HTML (`&`, `<`, `>`)

---

## Integration Scheduler

Dans `src/scheduler/scheduler.py`, la fonction `run_forever()` ajoute un job CronTrigger :

```python
scheduler.add_job(
    send_daily_report,
    CronTrigger(hour=settings.report_send_hour_utc, minute=settings.report_send_minute_utc),
    id="daily_report",
    name="Rapport journalier par email",
    max_instances=1,
    misfire_grace_time=300,
)
```

- **Horaire par defaut** : 23:00 UTC (configurable via `REPORT_SEND_HOUR_UTC` / `REPORT_SEND_MINUTE_UTC`)
- **Misfire grace** : 5 minutes (si le scheduler est occupe, le rapport peut partir avec 5 min de retard)
- **Max instances** : 1 (pas d'envoi concurrent)

---

## Script standalone

**Fichier** : `scripts/send_report.py`

```powershell
# Rapport du jour (date UTC courante)
python scripts/send_report.py

# Rapport d'une date specifique
python scripts/send_report.py 2026-06-01
```

Utile pour tester la configuration mailer ou regenerer un rapport pour une date passee.
'''

FUNC_DOC = r'''# Rapport quotidien par email

Le bot genere et envoie automatiquement un rapport journalier par email a 23:00 UTC. Ce rapport consolide tous les trades de la journee, calcule des statistiques de performance, et inclut une analyse approfondie generee par DeepSeek V4 Pro.

## Objectif

Fournir un resume quotidien clair et actionnable des performances du bot, sans avoir a se connecter au serveur ou a consulter les logs. L'analyse DeepSeek identifie les patterns, forces, faiblesses et suggere des ameliorations concretes.

## Contenu du rapport

```mermaid
flowchart LR
    subgraph Rapport
        A[En-tete: date + origine] --> B[Cartes resume]
        B --> C[Details par paire]
        C --> D[Analyse DeepSeek]
        D --> E[Pied de page]
    end
    subgraph Cartes
        B1[Total trades]
        B2[Gagnants]
        B3[Perdants]
        B4[Win Rate]
        B5[P&amp;L Total]
    end
    subgraph Analyse
        D1[Resume]
        D2[Forces]
        D3[Faiblesses]
        D4[Recommandations]
    end
```

### 1. Cartes resume

Blocs visuels affichant les indicateurs cles de la journee :

| Indicateur | Description |
|---|---|
| **Total trades** | Nombre total de trades (ouverts + fermes) |
| **Gagnants** | Trades avec profit > 0 (vert) |
| **Perdants** | Trades avec profit <= 0 (rouge) |
| **Win Rate** | Pourcentage de trades gagnants |
| **P&amp;L Total** | Profit/Perte net de la journee en dollars (vert si positif, rouge si negatif) |

Une ligne secondaire affiche : meilleur trade, pire trade, profit moyen, duree moyenne des trades, confiance moyenne.

### 2. Details par paire

Une section par paire de devises (EURUSD, GBPUSD, XAUUSD, etc.) avec :

- **Mini-statistiques** : nombre de trades, gagnants/perdants, win rate, P&amp;L, profit moyen, duree moyenne
- **Tableau des trades** : heure d'ouverture, direction (BUY/SELL), volume, prix d'entree, P&amp;L

Les paires sans trade du jour sont ignorees.

### 3. Analyse DeepSeek V4 Pro

DeepSeek V4 Pro analyse les resultats et produit une analyse en francais structuree en 4 sections :

| Section | Questions abordees |
|---|---|
| **Resume** | Performance globale du jour. Positif ou negatif ? Tendance ? |
| **Forces** | Quelles paires ont performe ? Quels patterns ont fonctionne ? A quel moment de la journee ? |
| **Faiblesses** | Quelles pertes ? Y a-t-il un pattern recurrent dans les echecs ? Erreurs potentielles ? |
| **Recommandations** | Faut-il ajuster les parametres ? Eviter certaines paires ou horaires ? Modifier la gestion du risque ? |

L'analyse est honnete et directe. Si les resultats sont mauvais, elle le dit clairement.

### 4. Sujet de l'email

Le sujet est dynamique et inclut les indicateurs cles :

```
Rapport Trading 01/06/2026 | 8 trades | P&amp;L: +42.50 $ | WR: 62.5%
```

Cela permet d'evaluer la journee d'un coup d'oeil sans ouvrir l'email.

## Horaire d'envoi

Le rapport est envoye automatiquement a **23:00 UTC** chaque jour (configurable).

Cela correspond a :
- 01:00 heure de Paris (ete, UTC+2)
- 00:00 heure de Paris (hiver, UTC+1)
- 19:00 heure de New York (UTC-4)

Le creneau de 23:00 UTC est choisi car il se situe apres la fermeture de New York (22:00 UTC) et avant l'ouverture de la session Asiatique. Tous les trades de la journee de trading sont normalement termines.

## Destinataire

Configure par defaut sur `dialloabdoul99c@gmail.com`. Modifiable via `REPORT_RECIPIENT_EMAIL` dans le `.env`.

Un nom de destinataire optionnel (`REPORT_RECIPIENT_NAME`) peut etre ajoute pour personnaliser l'email.

## Design de l'email

- **Theme** : Dark mode (fond sombre `#020617`, cartes `#0f172a`)
- **Responsive** : S'adapte aux ecrans mobile et desktop (max-width 680px)
- **Palette** : Vert (`#22c55e`) pour les gains, rouge (`#ef4444`) pour les pertes, gris (`#94a3b8`) pour le texte secondaire
- **Typographie** : System font stack (-apple-system, BlinkMacSystemFont, Segoe UI, Roboto)

## Cas particuliers

| Cas | Comportement |
|---|---|
| **Aucun trade du jour** | Rapport envoye avec le message "Aucun trade aujourd'hui" |
| **Cle DeepSeek absente** | Analyse remplacee par "_Analyse DeepSeek non disponible_" |
| **Cle Mailer absente** | Erreur logguee, email non envoye |
| **Rate limit API mailer** | 3 tentatives avec backoff exponentiel |
| **Base de donnees vide** | Rapport envoye sans trades ni stats |
| **Une seule paire avec trades** | Rapport normal, une seule carte "Details par Paire" |

## Test manuel

```powershell
# Envoyer le rapport du jour
python scripts/send_report.py

# Envoyer le rapport d'une date passee
python scripts/send_report.py 2026-05-30
```

## Configuration

| Variable | Defaut | Description |
|---|---|---|
| `MAILER_API_SECRET` | _(requis)_ | Cle API pour `mailing.weltaare-tech.com` |
| `MAILER_API_URL` | `https://mailing.weltaare-tech.com/api/v1/emails` | URL de l'API d'envoi |
| `REPORT_RECIPIENT_EMAIL` | `dialloabdoul99c@gmail.com` | Destinataire du rapport |
| `REPORT_RECIPIENT_NAME` | _(vide)_ | Nom du destinataire (optionnel) |
| `REPORT_SENDER_NAME` | `Trading Bot MT5` | Nom de l'expediteur dans l'email |
| `REPORT_SEND_HOUR_UTC` | `23` | Heure d'envoi UTC (0-23) |
| `REPORT_SEND_MINUTE_UTC` | `0` | Minute d'envoi UTC (0-59) |

Voir [Configuration](../4-technique/configuration.md) et [Module Rapports](../4-technique/backend/rapport-journalier.md) pour les details techniques.
'''

if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    tech_path = base / "docs" / "content" / "4-technique" / "backend" / "rapport-journalier.md"
    func_path = base / "docs" / "content" / "2-fonctionnel" / "rapport-quotidien.md"
    tech_path.write_text(TECH_DOC, encoding="utf-8")
    func_path.write_text(FUNC_DOC, encoding="utf-8")
    print(f"Created: {tech_path}")
    print(f"Created: {func_path}")
