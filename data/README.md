# Données

Les fichiers bruts ne sont **pas** versionnés (`data/*.xlsx` et `data/raw/` sont dans `.gitignore`).

## 1. Fichiers INSEE à placer dans `data/`

| Fichier | Contenu | Source | Téléchargé le |
|---|---|---|---|
| `estim-pop-dep-sexe-aq-1975-2026.xlsx` | Population au 1er janvier par département, sexe et âge quinquennal, 1975-2026 | [INSEE, estimation de population au 1er janv. 2026](https://www.insee.fr/fr/statistiques/8721456) | 12/11/2026 |
| `estim-pop-dep-sexe-gca-1975-2026.xlsx` | Idem, grandes classes d'âge | [INSEE, estimation de population au 1er janv. 2026](https://www.insee.fr/fr/statistiques/8721456) | 12/11/2026 |
| `1_Pop_annu_compo_evol_depreg.xlsx` | Population et composantes de l'évolution (naissances, décès, variation) | [lien à vérifier] | 12/11/2026 |
| `2_Pop1janv_grands_grages_depreg.xlsx` | Population au 1er janvier par sexe et groupe d'âges | [lien à vérifier] | 12/11/2026 |
| `3_Naissances_natalite_fecondite_depreg.xlsx` | Naissances, natalité, fécondité | [lien à vérifier] | 12/11/2026 |
| `4_Deces_mortalite_espvie_depreg.xlsx` | Décès (total seulement), mortalité, espérance de vie | [lien à vérifier] | 12/11/2026 |

## 2. Téléchargement automatique (`data/raw/`)

```bash
python data/telecharger_donnees.py
```

- **Eurostat `demo_r_magec3`** : décès par sexe et tranche quinquennale, Morbihan (NUTS3 `FRH04`),
  2013-2024 (version Eurostat mise à jour le 22/09/2026, téléchargée le 12/11/2026). Nécessaire car les fichiers INSEE ne donnent que le total des décès, sans l'âge.
  Contrôle : le total colle à celui de l'INSEE (écart maximal 0,01 %). Lien : [page Eurostat du jeu].
- **INSEE Omphale 2022** ([tableaux détaillés départementaux](https://www.insee.fr/fr/statistiques/7747107)) :
  population projetée 2018-2070 par département, sexe et tranche quinquennale (arrondie à la dizaine).
  Scénarios : central, migrations basses, migrations hautes (`omphale_*.xlsx`). Téléchargés le 13/11/2026.
  Le serveur INSEE renvoie parfois des erreurs 500 ou des délais dépassés : le script réessaie
  [n tentatives, puis arrêt avec le message `...`].

## 3. Conventions

- Format long : `annee | sexe | tranche_age | effectif`. Sexe : `Ensemble`, `Femmes`, `Hommes`.
- Tranches d'âge de 5 ans ; 90-94 et 95+ fusionnées en `90+` (comme Eurostat).
- Fichier 2 : l'ordre des sexes est Ensemble / Femmes / Hommes, et la colonne « 15-49 ans »
  (femmes) est exclue car elle chevauche les autres tranches. Le code lit les en-têtes de chaque
  feuille au lieu de supposer des positions fixes.
- Fichiers 1, 3 et 4 : pas d'âge, une colonne `indicateur` (naissances, décès, etc.).
- Populations 2024-2026 : **provisoires** (susceptibles d'être révisées).

## 4. Tables produites (`data/processed/`)

Générées par `notebooks/01_donnees.ipynb` et `notebooks/02_modele.ipynb`.
[Versionnées / non versionnées : à préciser.]

| Table | Contenu | Période | Colonnes |
|---|---|---|---|
| `pop_aq` | Population par sexe et âge quinquennal | 1975-2026 | annee, sexe, tranche_age, effectif |
| `pop_gca` | Population par sexe et grande classe d'âge | 1975-2026 | annee, sexe, tranche_age, effectif |
| `pop_dep2` | Population par sexe et groupe d'âges (fichier 2) | 1975-2026 | annee, sexe, tranche_age, effectif |
| `dep1`, `dep3`, `dep4` | Composantes, naissances, décès (total) | 1975-2025 | annee, sexe, tranche_age, effectif, indicateur |
| `deces_age` | Décès par sexe et âge quinquennal (Eurostat) | 2013-2024 | annee, sexe, tranche_age, effectif |
| `taux_survie_migration_2020_2025.csv` | Survie et migration nette par tranche | 2020-2025 | [à compléter] |

## 5. Exécution

La première lecture des Excel prend plusieurs minutes. Les tables sont ensuite écrites en CSV dans
`data/processed/` et relues ; mettre `RELIRE_EXCEL = True` dans le notebook si les fichiers sources
changent.

