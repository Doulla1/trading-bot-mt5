# Comment changer d'IA

Ce guide explique comment remplacer l'IA de decision (DeepSeek, GPT, Claude, Gemini...) sans modifier le code source. Tout se fait dans le fichier .env.

## Principe

Le bot utilise le SDK OpenAI, qui est compatible avec tous les fournisseurs exposant une API OpenAI-compatible. Il suffit de changer 4 variables dans .env :

| Variable | Role |
|---|---|
| AI_API_KEY | Ta cle API |
| AI_BASE_URL | L'URL de l'API du fournisseur |
| AI_MODEL | Le nom du modele |
| AI_PROVIDER | Un nom pour les logs (cosmetique) |

## Recettes pour chaque fournisseur

### DeepSeek (defaut)

`env
AI_API_KEY=sk-votre-cle-deepseek
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-v4-pro
AI_FAST_MODEL=deepseek-v4-flash
AI_PROVIDER=deepseek
`

### OpenAI (GPT-5, GPT-4o, etc.)

`env
AI_API_KEY=sk-proj-votre-cle-openai
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-5
AI_FAST_MODEL=gpt-4o-mini
AI_PROVIDER=openai
`

### OpenRouter (Claude, Gemini, et 200+ modeles)

[OpenRouter](https://openrouter.ai) est un proxy qui expose TOUS les modeles (OpenAI, Anthropic, Google, Meta, DeepSeek...) via une API OpenAI-compatible. **C'est la solution la plus flexible.**

1. Creer un compte sur [openrouter.ai](https://openrouter.ai)
2. Generer une cle API
3. Configurer .env :

`env
AI_API_KEY=sk-or-v1-votre-cle-openrouter
AI_BASE_URL=https://openrouter.ai/api/v1
# Exemples de modeles :
AI_MODEL=anthropic/claude-sonnet-4-20250514      # Claude Sonnet 4
# AI_MODEL=google/gemini-2.5-pro                  # Gemini 2.5 Pro
# AI_MODEL=openai/gpt-5                           # GPT-5
# AI_MODEL=deepseek/deepseek-v4-pro               # DeepSeek V4 Pro
# AI_MODEL=meta-llama/llama-4-maverick            # Llama 4
AI_FAST_MODEL=deepseek/deepseek-v4-flash
AI_PROVIDER=openrouter
`

### Azure OpenAI

`env
AI_API_KEY=votre-cle-azure
AI_BASE_URL=https://votre-resource.openai.azure.com/openai/deployments/votre-deploiement
AI_MODEL=gpt-4o
AI_FAST_MODEL=gpt-4o-mini
AI_PROVIDER=azure
# Si Azure utilise une version d'API specifique, ajouter ?api-version=2024-10-21 a AI_BASE_URL
`

### Fournisseur custom (toute API OpenAI-compatible)

`env
AI_API_KEY=votre-cle
AI_BASE_URL=https://votre-api.custom.com/v1
AI_MODEL=votre-modele
AI_FAST_MODEL=votre-modele-rapide
AI_PROVIDER=custom
`

## Retrocompatibilite

Si tu avais deja DEEPSEEK_API_KEY dans ton .env, il continue de fonctionner. AI_API_KEY est prioritaire, DEEPSEEK_API_KEY est utilise en fallback.

`env
# Ces deux configurations sont equivalentes :
# Nouveau (recommande) :
AI_API_KEY=sk-xxx
# Ancien (toujours supporte) :
DEEPSEEK_API_KEY=sk-xxx
`

## Verification

Apres avoir modifie .env, verifie les logs. Tu dois voir :

`
INFO | Envoi decision a openrouter/anthropic/claude-sonnet-4-20250514 pour EURUSD...
INFO | openrouter: SELL | Confiance: 82% | SL: 15pips | TP: 30pips | Risque: MEDIUM
`

Le nom du fournisseur et du modele apparaissent dans les logs, ce qui permet de savoir facilement quelle IA est active.

## Notes importantes

### OCR (analyse visuelle du chart)

L'OCR utilise **OpenAI GPT-4o** et n'est PAS affecte par le changement d'IA de decision. La variable OPENAI_API_KEY reste necessaire pour l'analyse visuelle des graphiques.

### SL/TP : l'ATR prend le dessus

Quel que soit le modele utilise, les SL/TP recommandes par l'IA sont toujours compares aux minimums bases sur l'ATR (voir [regles-gestion-risques.md](../2-fonctionnel/regles-gestion-risques.md)). Le bot utilise max(SL_IA, SL_ATR) - l'IA peut elargir le SL mais jamais le reduire en dessous du minimum de securite.

### Cout

Chaque fournisseur a sa propre grille tarifaire. Une decision DeepSeek coute environ 0.001-0.002, une decision GPT-5 ou Claude Sonnet 4 coute 0.01-0.03. Pour 96 cycles/jour (6 symboles x 16 rounds), le cout varie de 0.10/jour (DeepSeek) a 1-3/jour (GPT-5/Claude).

OpenRouter permet de tester plusieurs modeles sans changer de compte - utile pour comparer les performances.
