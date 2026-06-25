# Module Pivots - Reference API

> **Module** : `src/pivots/`
> **Fichier principal** : `src/pivots/types.py`
> **Date** : 2026-06-25

Le module `src/pivots/` fournit les fonctions de calcul de 5 types de points pivots et une dataclass `PivotLevels` unifiee. Les fonctions de calcul sont pures (pas de dependance a MT5 ou pandas). Les helpers de pipeline (`compute_pivots_from_daily`, `align_pivots_to_intraday`) utilisent pandas pour le traitement par lots.

---

## 1. Dataclass `PivotLevels`

```python
from src.pivots.types import PivotLevels
```

### Champs

| Champ | Type | Description |
|---|---|---|
| `pp` | `float` | Pivot Point central |
| `r1`, `s1` | `float` | Resistance/Support 1 |
| `r2`, `s2` | `float` | Resistance/Support 2 |
| `r3`, `s3` | `float` | Resistance/Support 3 |
| `r4`, `s4` | `Optional[float]` | Resistance/Support 4 (Camarilla uniquement) |
| `tc` | `Optional[float]` | CPR Top Central (CPR uniquement) |
| `bc` | `Optional[float]` | CPR Bottom Central (CPR uniquement) |

### Methodes

#### `to_dict() -> dict`

Retourne un dictionnaire avec tous les champs, arrondis a 5 decimales. Les champs `None` restent `None`.

```python
>>> levels = compute_classic_pivots(1.0850, 1.0810, 1.0835)
>>> levels.to_dict()
{'pp': 1.08317, 'r1': 1.08533, 's1': 1.08133, 'r2': 1.0875, 's2': 1.07883, ...}
```

#### `all_levels() -> dict[str, float]`

Retourne tous les niveaux non-None, cles en majuscules (S4, S3, S2, S1, PP, R1, R2, R3, R4, TC, BC).

```python
>>> levels = compute_cpr(1.0850, 1.0810, 1.0835)
>>> levels.all_levels()
{'S1': 1.08133, 'PP': 1.08317, 'R1': 1.08533, 'TC': 1.08433, 'BC': 1.083}
```

#### `nearest_support(price: float) -> tuple[str, float] | None`

Trouve le nom et la valeur du support le plus proche sous le prix donne.

```python
>>> levels.nearest_support(1.0830)
('S1', 1.08133)
```

#### `nearest_resistance(price: float) -> tuple[str, float] | None`

Trouve le nom et la valeur de la resistance la plus proche au-dessus du prix donne.

```python
>>> levels.nearest_resistance(1.0835)
('R1', 1.08533)
```

#### `distance_to_nearest_support(price: float) -> float | None`

Distance absolue en unites de prix jusqu'au support le plus proche.

#### `distance_to_nearest_resistance(price: float) -> float | None`

Distance absolue en unites de prix jusqu'a la resistance la plus proche.

---

## 2. Fonctions de calcul (pures)

Chaque fonction prend les prix High, Low, Close de la periode precedente et retourne un `PivotLevels`.

### `compute_classic_pivots(h, l, c) -> PivotLevels`

Pivots Classic floor-trader. Formules :

```
PP = (H + L + C) / 3
R1 = 2*PP - L    S1 = 2*PP - H
R2 = PP + (H-L)  S2 = PP - (H-L)
R3 = H + 2*(PP-L)  S3 = L - 2*(H-PP)
```

**Niveaux produits** : PP, R1-R3, S1-S3

```python
>>> compute_classic_pivots(1.0850, 1.0810, 1.0835)
PivotLevels(pp=1.08317, r1=1.08533, s1=1.08133, r2=1.08717, s2=1.07917, r3=1.08933, s3=1.07717)
```

### `compute_camarilla_pivots(h, l, c) -> PivotLevels`

Pivots Camarilla (Nick Scott). Utilise un multiplicateur 1.1x du range reparti sur 4 niveaux. Les niveaux S4/R4 sont les plus extremes et historiquement les plus reactifs.

Formules :

```
Range = H - L
R4 = C + Range * 1.1 / 2    S4 = C - Range * 1.1 / 2
R3 = C + Range * 1.1 / 4    S3 = C - Range * 1.1 / 4
R2 = C + Range * 1.1 / 6    S2 = C - Range * 1.1 / 6
R1 = C + Range * 1.1 / 12   S1 = C - Range * 1.1 / 12
PP = (H + L + C) / 3
```

**Niveaux produits** : PP, R1-R4, S1-S4

### `compute_woodie_pivots(h, l, c, o=None) -> PivotLevels`

Pivots Woodie. Differt de Classic par le calcul du PP : `(H + L + 2*C) / 4`, donnant plus de poids a la cloture.

**Niveaux produits** : PP, R1-R3, S1-S3

### `compute_fibonacci_pivots(h, l, c) -> PivotLevels`

Pivots bases sur les retracements de Fibonacci (38.2%, 61.8%, 100%) du range precedent. PP identique a Classic.

```
R1 = PP + 0.382 * Range    S1 = PP - 0.382 * Range
R2 = PP + 0.618 * Range    S2 = PP - 0.618 * Range
R3 = PP + 1.000 * Range    S3 = PP - 1.000 * Range
```

**Niveaux produits** : PP, R1-R3, S1-S3

### `compute_cpr(h, l, c) -> PivotLevels`

Central Pivot Range (CPR). Calcule TC (Top Central) et BC (Bottom Central) en plus du PP.

```
PP = (H + L + C) / 3
BC = (H + L) / 2
TC = (PP - BC) + PP
```

**Niveaux produits** : PP, R1, S1, TC, BC. R2-R3/S2-S3 sont `None`.

---

## 3. Helpers de pipeline (pandas)

### `compute_pivots_from_daily(df_daily, pivot_types=None) -> pd.DataFrame`

Calcule tous les types de pivots demandes a partir d'un DataFrame daily OHLC.

**Args** :
- `df_daily` : DataFrame avec colonnes `datetime`, `high`, `low`, `close`, `open`.
- `pivot_types` : liste de types (defaut: `['classic', 'camarilla', 'woodie', 'fibonacci', 'cpr']`).

**Retourne** : DataFrame avec colonnes `datetime`, `pivot_{type}_{field}`, `high`, `low`, `close`.

**Colonnes produites** par type (exemple Classic) :
`pivot_classic_pp`, `pivot_classic_r1`, `pivot_classic_s1`, `pivot_classic_r2`, `pivot_classic_s2`, `pivot_classic_r3`, `pivot_classic_s3`.

**Attention** : utilise le H/L/C de la veille (`shift(1)`) pour eviter le look-ahead bias.

### `resample_to_weekly(df_daily) -> pd.DataFrame`

Reechantillonne un DataFrame daily en bougies hebdomadaires (OHLC).

### `resample_to_monthly(df_daily) -> pd.DataFrame`

Reechantillonne un DataFrame daily en bougies mensuelles (OHLC).

### `align_pivots_to_intraday(df_intraday, df_pivots_daily, pivot_type='classic') -> pd.DataFrame`

Aligne les niveaux pivots daily sur les bougies intraday via `pd.merge_asof` (direction backward). Chaque bougie intraday recoit les niveaux calcules a partir du D1 precedent le plus recent.

**Args** :
- `df_intraday` : DataFrame intraday (M15, H1...) avec colonne `datetime`.
- `df_pivots_daily` : DataFrame produit par `compute_pivots_from_daily()`.
- `pivot_type` : quel type de pivot aligner (ex: `'classic'`).

**Retourne** : DataFrame merge avec les colonnes intraday + les colonnes `pivot_{type}_*`.

---

## 4. Exemple complet

```python
import pandas as pd
from src.pivots.types import (
    compute_pivots_from_daily,
    resample_to_weekly,
    align_pivots_to_intraday,
)

# 1. Charger les donnees D1
df_d1 = pd.read_csv("data/historical/eurusd_d1_1y.csv")
df_d1["datetime"] = pd.to_datetime(df_d1["datetime"])

# 2. Calculer tous les types de pivots daily
df_daily_pivots = compute_pivots_from_daily(df_d1, pivot_types=["classic", "camarilla"])

# 3. Pivots weekly
df_weekly = resample_to_weekly(df_d1)
df_weekly_pivots = compute_pivots_from_daily(df_weekly, pivot_types=["classic"])

# 4. Pivots monthly
df_monthly = resample_to_monthly(df_d1)
df_monthly_pivots = compute_pivots_from_daily(df_monthly, pivot_types=["classic"])

# 5. Aligner sur l'intraday
df_m15 = pd.read_csv("data/historical/eurusd_M15_1y.csv")
df_m15["datetime"] = pd.to_datetime(df_m15["datetime"])

df_merged = align_pivots_to_intraday(df_m15, df_daily_pivots, pivot_type="classic")

# 6. Interroger les niveaux
from src.pivots.types import compute_classic_pivots
levels = compute_classic_pivots(1.0850, 1.0810, 1.0835)
print(f"Support le plus proche de 1.0830: {levels.nearest_support(1.0830)}")
print(f"Resistance la plus proche de 1.0830: {levels.nearest_resistance(1.0830)}")
```

---

## 5. Types de pivots - Comparaison

| Propriete | Classic | Camarilla | Woodie | Fibonacci | CPR |
|---|---|---|---|---|---|
| Niveaux | R1-R3, S1-S3 | R1-R4, S1-S4 | R1-R3, S1-S3 | R1-R3, S1-S3 | R1, S1, TC, BC |
| Formule PP | (H+L+C)/3 | (H+L+C)/3 | (H+L+2C)/4 | (H+L+C)/3 | (H+L+C)/3 |
| Particularite | Standard | Niveaux extremes S4/R4 | Poids 2x sur Close | Retracements Fibo | Zone TC-BC |
| Usage recommande | Reference generale | Retournements extremes | Confirmation tendance | Cibles de profit | Confluence zone |
