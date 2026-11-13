"""Chargement des fichiers INSEE / Eurostat, filtrés sur le Morbihan (56), au format long.

Format long commun : annee | sexe | tranche_age | effectif
(+ colonne `indicateur` pour les fichiers qui en contiennent plusieurs).

Structure des fichiers (vérifiée sur toutes les feuilles, 1975-2026) :
- estim-pop-dep-sexe-aq / -gca : 1 feuille par année + « À savoir ».
  Ligne 4 = sexes (Ensemble, Hommes, Femmes), ligne 5 = tranches d'âge, puis
  1 ligne par département (code en colonne A, nom en colonne B).
- 2_Pop1janv (DEP2) : 1 feuille par année + « Changement de régions ».
  Ordre des sexes différent (Ensemble, Femmes, Hommes) et une colonne
  supplémentaire « De 15 à 49 ans (a) » chez les femmes (exclue : elle chevauche).
  Le nom du département est en colonne A, le code REG-DEP (5356) en colonne B.
- 1_Pop_annu (DEP1), 3_Naissances (DEP3), 4_Deces (DEP4) : totaux sans âge.
  Les en-têtes 2023-2024 de DEP1 portent des « (p) » mais les colonnes ne bougent pas.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

DEPARTEMENT = "Morbihan"
CODE_DEP = "56"
NUTS3 = "FRH04"  # Morbihan dans la nomenclature Eurostat

FICHIERS = {
    "aq": "estim-pop-dep-sexe-aq-1975-2026.xlsx",
    "gca": "estim-pop-dep-sexe-gca-1975-2026.xlsx",
    "dep1": "1_Pop_annu_compo_evol_depreg.xlsx",
    "dep2": "2_Pop1janv_grands_grages_depreg.xlsx",
    "dep3": "3_Naissances_natalite_fecondite_depreg.xlsx",
    "dep4": "4_Deces_mortalite_espvie_depreg.xlsx",
}
FICHIER_DECES_AGE = RAW_DIR / f"eurostat_demo_r_magec3_{NUTS3}.json"

SEXES = ("Ensemble", "Hommes", "Femmes")


# --------------------------------------------------------------------------- utilitaires
def normaliser_tranche(libelle: str) -> str | None:
    """'0 à 4 ans' -> '0-4', '95 ans et plus' -> '95+', 'Total' -> 'Total'.

    Renvoie None pour les colonnes à ignorer (ex. « 15 à 49 ans (a) »).
    """
    s = " ".join(str(libelle).split())
    if s.lower().startswith("total"):
        return "Total"
    if "(a)" in s:
        return None
    n = re.findall(r"\d+", s)
    if "plus" in s:
        return f"{n[0]}+"
    return f"{n[0]}-{n[1]}"


def borne_inf(tranche: str) -> int:
    return int(re.match(r"\d+", tranche).group())


def ordonner_tranches(tranches) -> list[str]:
    return sorted({t for t in tranches if t != "Total"}, key=borne_inf)


def _feuilles_annuelles(wb) -> list[str]:
    return [s for s in wb.sheetnames if s.strip().isdigit()]


def _ligne_morbihan(lignes: list[tuple]) -> tuple:
    trouvees = [
        r for r in lignes
        if r and (any(isinstance(c, str) and c.strip() == DEPARTEMENT for c in r[:2]))
    ]
    if len(trouvees) != 1:
        raise ValueError(f"{len(trouvees)} lignes « {DEPARTEMENT} » trouvées (1 attendue)")
    return trouvees[0]


def _ffill(valeurs: tuple) -> list:
    out, cour = [], None
    for v in valeurs:
        if v is not None and str(v).strip():
            cour = " ".join(str(v).split())
        out.append(cour)
    return out


# --------------------------------------------------------------------------- population par âge
def charger_population_age(cle: str, inclure_total: bool = False) -> pd.DataFrame:
    """Population au 1er janvier par sexe et tranche d'âge (fichiers aq, gca, dep2).

    Les en-têtes (sexe ligne 4, tranche ligne 5) sont lus feuille par feuille, donc
    l'ordre des colonnes peut varier d'un fichier ou d'une année à l'autre.
    """
    wb = openpyxl.load_workbook(DATA_DIR / FICHIERS[cle], read_only=True, data_only=True)
    lignes_long = []
    for feuille in _feuilles_annuelles(wb):
        lignes = list(wb[feuille].iter_rows(values_only=True))
        sexes = _ffill(lignes[3])
        tranches = lignes[4]
        morb = _ligne_morbihan(lignes)
        for j, (sexe, tranche, val) in enumerate(zip(sexes, tranches, morb)):
            if j < 2 or tranche is None or sexe not in SEXES:
                continue
            t = normaliser_tranche(tranche)
            if t is None or (t == "Total" and not inclure_total):
                continue
            lignes_long.append((int(feuille), sexe, t, val))
    df = pd.DataFrame(lignes_long, columns=["annee", "sexe", "tranche_age", "effectif"])
    df["effectif"] = pd.to_numeric(df["effectif"], errors="coerce")
    return df.sort_values(["annee", "sexe", "tranche_age"], key=_cle_tri).reset_index(drop=True)


def _cle_tri(col: pd.Series) -> pd.Series:
    if col.name == "tranche_age":
        return col.map(lambda t: 999 if t == "Total" else borne_inf(t))
    return col


# --------------------------------------------------------------------------- totaux (DEP1, DEP3, DEP4)
def _charger_dep(cle: str, colonnes: dict[int, tuple[str, str]], controle: dict[int, str]) -> pd.DataFrame:
    """colonnes : index de colonne -> (indicateur, sexe) ; controle : index -> mot attendu dans l'en-tête."""
    wb = openpyxl.load_workbook(DATA_DIR / FICHIERS[cle], read_only=True, data_only=True)
    res = []
    for feuille in _feuilles_annuelles(wb):
        lignes = list(wb[feuille].iter_rows(values_only=True))
        entete = _ffill(lignes[3])
        for j, mot in controle.items():
            if mot.lower() not in (entete[j] or "").lower():
                raise ValueError(f"{cle} {feuille} : colonne {j} = {entete[j]!r}, attendu « {mot} »")
        morb = _ligne_morbihan(lignes)
        for j, (indic, sexe) in colonnes.items():
            res.append((int(feuille), sexe, "Total", indic, morb[j]))
    df = pd.DataFrame(res, columns=["annee", "sexe", "tranche_age", "indicateur", "effectif"])
    df["effectif"] = pd.to_numeric(df["effectif"], errors="coerce")
    return df


def charger_dep1() -> pd.DataFrame:
    """Population et composantes de l'évolution (année t)."""
    return _charger_dep(
        "dep1",
        {2: ("population_1er_janvier", "Ensemble"), 5: ("naissances", "Ensemble"),
         6: ("deces", "Ensemble"), 7: ("solde_naturel", "Ensemble"),
         8: ("variation_totale", "Ensemble")},
        {2: "Population", 5: "Naissances", 6: "Décès", 7: "Solde naturel", 8: "Variation totale"},
    )


def charger_dep3() -> pd.DataFrame:
    return _charger_dep(
        "dep3",
        {2: ("naissances", "Ensemble"), 4: ("indicateur_conjoncturel_fecondite", "Femmes")},
        {2: "Naissances", 4: "fécondité"},
    )


def charger_dep4() -> pd.DataFrame:
    return _charger_dep(
        "dep4",
        {2: ("deces", "Ensemble"), 4: ("esperance_vie_naissance", "Femmes"),
         5: ("esperance_vie_naissance", "Hommes")},
        {2: "Décès", 4: "Espérance de vie"},
    )


# --------------------------------------------------------------------------- décès par âge (Eurostat)
def charger_deces_age() -> pd.DataFrame:
    """Décès par sexe et tranche quinquennale, Morbihan (Eurostat demo_r_magec3, FRH04).

    Les fichiers INSEE ne donnent que le total des décès : cette source est
    nécessaire pour les taux de survie par âge. Les décès d'âge inconnu (UNK)
    sont répartis au prorata.
    """
    if not FICHIER_DECES_AGE.exists():
        raise FileNotFoundError(f"{FICHIER_DECES_AGE} absent : lancez python data/telecharger_donnees.py")
    j = json.loads(FICHIER_DECES_AGE.read_text(encoding="utf-8"))
    dims, tailles = j["id"], j["size"]
    cats = {d: {v: k for k, v in j["dimension"][d]["category"]["index"].items()} for d in dims}
    res = []
    for idx, val in j["value"].items():
        i, pos = int(idx), {}
        for d, n in zip(reversed(dims), reversed(tailles)):
            pos[d] = cats[d][i % n]
            i //= n
        res.append((int(pos["time"]), pos["sex"], pos["age"], val))
    df = pd.DataFrame(res, columns=["annee", "sexe", "age", "effectif"])
    df["sexe"] = df["sexe"].map({"T": "Ensemble", "M": "Hommes", "F": "Femmes"})
    df = df[df["age"] != "TOTAL"]

    def conv(a):
        if a == "Y_LT5":
            return "0-4"
        if a == "Y_GE90":
            return "90+"
        if a == "UNK":
            return "UNK"
        return a[1:]
    df["tranche_age"] = df["age"].map(conv)
    # répartition des âges inconnus
    out = []
    for (an, sx), g in df.groupby(["annee", "sexe"]):
        unk = g.loc[g["tranche_age"] == "UNK", "effectif"].sum()
        g = g[g["tranche_age"] != "UNK"].copy()
        g["effectif"] = g["effectif"] + unk * g["effectif"] / g["effectif"].sum()
        out.append(g)
    df = pd.concat(out)[["annee", "sexe", "tranche_age", "effectif"]]
    return df.sort_values(["annee", "sexe", "tranche_age"], key=_cle_tri).reset_index(drop=True)


# --------------------------------------------------------------------------- projections Omphale
SCENARIOS_OMPHALE = {"Central": "central", "Mig_basse": "migrations basses", "Mig_haute": "migrations hautes"}


def charger_omphale(scenario: str = "Central") -> pd.DataFrame:
    """Projections Insee Omphale 2022 (base RP 2018), Morbihan, format long.

    Feuille « Population » : en-tête ligne 6 (ZONE, SEXE 1/2, TRAGE '[15;20[', POP_2018 … POP_2070).
    Les effectifs sont arrondis à la dizaine. Dernière tranche '[95;99+]' -> '95+'.
    """
    f = RAW_DIR / f"omphale_{scenario}.xlsx"
    if not f.exists():
        raise FileNotFoundError(f"{f} absent : lancez python data/telecharger_donnees.py")
    d = pd.read_excel(f, sheet_name="Population", header=5)
    d = d[d["ZONE"].astype(str).str.strip() == DEPARTEMENT]
    d = d.melt(id_vars=["ZONE", "SEXE", "TRAGE"], var_name="annee", value_name="effectif")
    d["annee"] = d["annee"].str.replace("POP_", "").astype(int)
    d["sexe"] = d["SEXE"].map({1: "Hommes", 2: "Femmes"})

    def tranche(t):
        a, b = re.findall(r"\d+", t)[:2]
        return f"{a}+" if "+" in t else f"{a}-{int(b) - 1}"
    d["tranche_age"] = d["TRAGE"].map(tranche)
    d["scenario"] = SCENARIOS_OMPHALE.get(scenario, scenario)
    return d[["annee", "sexe", "tranche_age", "effectif", "scenario"]].reset_index(drop=True)


# --------------------------------------------------------------------------- tout charger
NOMS_TABLES = ("pop_aq", "pop_gca", "pop_dep2", "dep1", "dep3", "dep4", "deces_age")


def charger_tout(cache: bool = True) -> dict[str, pd.DataFrame]:
    """Charge toutes les tables. Avec cache=True, relit data/processed/*.csv s'ils existent
    (la lecture des ~300 feuilles Excel prend environ 1 minute)."""
    chemins = {n: PROCESSED_DIR / f"{n}_morbihan.csv" for n in NOMS_TABLES}
    if cache and all(c.exists() for c in chemins.values()):
        return {n: pd.read_csv(c) for n, c in chemins.items()}
    tables = _charger_sources()
    sauvegarder(tables)
    return tables


def _charger_sources() -> dict[str, pd.DataFrame]:
    return {
        "pop_aq": charger_population_age("aq"),
        "pop_gca": charger_population_age("gca"),
        "pop_dep2": charger_population_age("dep2"),
        "dep1": charger_dep1(),
        "dep3": charger_dep3(),
        "dep4": charger_dep4(),
        "deces_age": charger_deces_age(),
    }


def sauvegarder(tables: dict[str, pd.DataFrame]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for nom, df in tables.items():
        df.to_csv(PROCESSED_DIR / f"{nom}_morbihan.csv", index=False, encoding="utf-8")
