# Depannage

## Probleme : Echec de connexion MT5

**Symptome** : `Echec connexion MT5 : (x, "message d'erreur")` dans les logs.

**Causes possibles et solutions** :

| Cause | Solution |
|---|---|
| Identifiants incorrects | Verifier `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` dans le `.env` |
| MT5 pas installe | Installer MetaTrader 5 depuis Fusion Markets |
| MT5 pas lance | Lancer le terminal MT5 (le bot a besoin du processus MT5 en execution) |
| Compte expire | Verifier que le compte demo n'est pas expire (les comptes demos Fusion Markets durent 30 jours) |
| Serveur incorrect | Demo : `FusionMarkets-Demo`, Reel : `FusionMarkets-Live` |
| Firewall / antivirus | Autoriser MT5 et Python dans le pare-feu Windows |

**Test manuel** :

```powershell
python -c "
import MetaTrader5 as mt5
if mt5.initialize(login=12345678, password='xxx', server='FusionMarkets-Demo'):
    print('OK - Connecte')
    mt5.shutdown()
else:
    print(f'ERREUR: {mt5.last_error()}')
"
```

---

## Probleme : Cle API OpenAI invalide

**Symptome** : `AuthenticationError` ou `Incorrect API key` dans les logs.

**Solutions** :
- Regenerer la cle sur [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- Verifier que la variable `OPENAI_API_KEY` est correcte dans le `.env`
- Verifier qu'il n'y a pas d'espace ou de guillemet autour de la cle
- Verifier le quota (compte gratuit = $5, valable 3 mois)

---

## Probleme : Pas de screenshot

**Symptome** : `Echec screenshot pour EURUSD` dans les logs.

**Solutions** :
- Verifier que le terminal MT5 est lance
- Verifier que le graphique du symbole existe dans MT5
- Verifier que le dossier `data/screenshots/` est accessible en ecriture

> **Note** : Contrairement a une idee recue, l'API Python MT5 n'a **pas besoin** que le terminal soit au premier plan. Le screenshot est pris en tache de fond.

---

## Probleme : Marche ferme

**Symptome** : `Marche ferme pour EURUSD - pas d'analyse` ou `trade_time == 0`.

**Causes** :
- Week-end (le marche forex ouvre dimanche 23h GMT, ferme vendredi 22h GMT)
- Jour ferie (Noel, Nouvel An, etc.)
- Symbole non disponible (ex: paire exotique non suivie par MT5)

**Solution** : Attendre la reouverture du marche. Le bot reprend automatiquement.

---

## Probleme : La reponse IA ne contient pas de JSON

**Symptome** : `Pas de JSON dans la reponse IA` ou `JSON invalide`.

**Causes** :
- Quota OpenAI epuise
- Modele `gpt-4o-mini` non disponible dans votre region
- Prompt trop long (depassement du contexte)
- L'API a retourne une erreur (rate limit, timeout)

**Solutions** :
- Verifier le quota OpenAI
- Reduire la taille du prompt (moins d'evenements calendaires, indicateurs simplifies)
- Verifier les logs pour le message d'erreur exact de l'API

---

## Probleme : Aucun trade execute

**Symptome** : Le bot tourne, l'IA repond HOLD a chaque cycle.

**Causes possibles** :
- Le marche est range, pas de signal clair
- La confiance de l'IA est < 70%
- La limite de perte journaliere est atteinte
- Le marche est ferme

**Verification** :

```powershell
# Voir les dernieres decisions de l'IA
sqlite3 data/trading.db "SELECT decision_action, decision_confidence, timestamp FROM analysis_logs ORDER BY timestamp DESC LIMIT 10;"
```

---

## Probleme : Erreur "Module not found"

**Symptome** : `ModuleNotFoundError: No module named 'src'` ou une dependance manquante.

**Solutions** :

```powershell
# Verifier que l'environnement virtuel est active
# (.venv) doit apparaitre dans le prompt

# Reinstaller les dependances
pip install -e .

# Verifier l'installation
python -c "import src; print('OK')"
```

---

## Probleme : La base de donnees est verrouillee

**Symptome** : `database is locked` dans les logs.

**Cause** : Un autre processus (ou une autre instance du bot) accede a la base.

**Solutions** :
- Arreter l'autre instance du bot
- Attendre que le verrou WAL soit libere (quelques secondes)
- En dernier recours : supprimer `data/trading.db` (perte de l'historique)

---

## Probleme : Visual Studio Code ne trouve pas les imports

**Symptome** : Erreur d'import dans VS Code alors que le bot fonctionne en ligne de commande.

**Solution** : Selectionner l'interpreteur de l'environnement virtuel :
1. `Ctrl+Shift+P`
2. `Python: Select Interpreter`
3. Choisir `.venv\Scripts\python.exe`

---

## Probleme : Le bot plante sans message d'erreur

**Solution** : Verifier le fichier de logs complet :

```powershell
Get-Content logs/trading-bot.log
```

Le dernier message avant le plantage contient generalement la cause.

---

## Probleme : Erreur 10027 - AutoTrading disabled by client

**Symptome** : `Code retour: 10027 - AutoTrading disabled by client` dans les logs.

**Cause** : Le trading algorithmique n'est pas active dans le terminal MT5. C'est un parametre de securite qui empeche tout ordre passe par l'API Python.

**Solutions** :

1. **Activer dans les options MT5** :
   - Menu `Outils` → `Options` (ou `Ctrl+O`)
   - Onglet `Expert Advisors`
   - Cocher la case **"Allow Algo Trading"**
   - Decocher eventuellement "Disable Algo Trading when the account is changed" si vous changez de compte
   - Cliquer `OK`

2. **Verifier le bouton Algo Trading** dans la barre d'outils :
   - Le bouton (icone de lecture/play) doit etre **vert** et enfonce
   - Si le bouton est rouge, cliquer dessus pour l'activer
   - S'il n'est pas visible : clic droit sur la barre d'outils → `Customize` → ajouter le raccourci `Algo Trading`

3. **Verifier les proprietes du symbole** (certains brokers desactivent l'algo trading sur certains symboles) :
   ```powershell
   python -c "import MetaTrader5 as mt5; mt5.initialize(); print(mt5.symbol_info('EURUSD').trade_mode); mt5.shutdown()"
   ```
   - `0` = trading autorise
   - `1` = pas de trading (close only)
   - `2` = trading desactive

> **Note** : Ce parametre doit etre active **une seule fois**. Il persiste au redemarrage. Si vous changez de compte MT5 (demo → reel), verifiez-le a nouveau.

---

## Probleme : Positions ouvertes non detectees

**Symptome** : Le bot ouvre une position alors qu'une est deja ouverte.

**Cause** : `get_open_positions()` filtre par symbole. Si la position est sur un autre symbole, elle n'est pas comptee.

**Verification** : Verifier `MAX_OPEN_POSITIONS` et `get_open_positions()` dans les logs.

---

## Obtenir de l'aide

Si le probleme persiste :
1. Verifiez que vous avez la derniere version du code
2. Fournissez les logs complets (`logs/trading-bot.log`)
3. Fournissez la sortie de `python run.py --once`
4. Ouvrez une issue sur le depot GitHub
