"""Contrôles de qualité des tables chargées par src.chargement.

Chaque contrôle renvoie des lignes (controle, table, detail, ecart_max, statut).
"""
from __future__ import annotations

import pandas as pd

from .chargement import borne_inf, charger_population_age, ordonner_tranches

TOLERANCE_REL = 0.005  # 0,5 % : écart acceptable entre deux millésimes d'estimation


def _ligne(controle, table, detail, ecart, ok):
    return {"controle": controle, "table": table, "detail": detail,
            "ecart_max": ecart, "statut": "OK" if ok else "ÉCART"}


def valeurs_manquantes(tables: dict[str, pd.DataFrame]) -> list[dict]:
    res = []
    for nom, df in tables.items():
        n_na = int(df.isna().sum().sum())
        n_neg = int((df["effectif"] < 0).sum()) if "indicateur" not in df else 0
        # grille complète : chaque (année, sexe) a toutes les tranches
        cles = ["annee", "sexe"] + (["indicateur"] if "indicateur" in df else [])
        n_tr = df.groupby(cles)["tranche_age"].nunique()
        complet = n_tr.nunique() == 1
        res.append(_ligne("valeurs manquantes / négatives / grille", nom,
                          f"{n_na} NA, {n_neg} négatifs, grille {'complète' if complet else 'incomplète'}",
                          n_na + n_neg, n_na == 0 and n_neg == 0 and complet))
    return res


def tranches_identiques(tables: dict[str, pd.DataFrame]) -> list[dict]:
    """Mêmes tranches d'âge pour toutes les années et tous les sexes d'une table."""
    res = []
    for nom, df in tables.items():
        if "indicateur" in df:
            continue
        jeux = df.groupby(["annee", "sexe"])["tranche_age"].apply(lambda s: tuple(ordonner_tranches(s)))
        ok = jeux.nunique() == 1
        res.append(_ligne("tranches identiques entre années et sexes", nom,
                          " | ".join(jeux.iloc[0]) if ok else f"{jeux.nunique()} découpages différents",
                          jeux.nunique() - 1, ok))
    return res


def regrouper(df: pd.DataFrame, cible: list[str]) -> pd.DataFrame:
    """Agrège des tranches fines vers un découpage plus large (ex. quinquennal -> DEP2)."""
    bornes = sorted(borne_inf(t) for t in cible)

    def vers(t):
        b = borne_inf(t)
        return cible[[borne_inf(c) for c in cible].index(max(x for x in bornes if x <= b))]
    out = df.assign(tranche_age=df["tranche_age"].map(vers))
    return out.groupby(["annee", "sexe", "tranche_age"], as_index=False)["effectif"].sum()


def decoupages_compatibles(fin: pd.DataFrame, large: pd.DataFrame, nom: str) -> list[dict]:
    """Les bornes du découpage large sont-elles des bornes du découpage fin ?"""
    b_fin = {borne_inf(t) for t in fin["tranche_age"].unique()}
    b_large = {borne_inf(t) for t in large["tranche_age"].unique()}
    manq = sorted(b_large - b_fin)
    return [_ligne("découpage compatible avec le quinquennal", nom,
                   "bornes toutes présentes" if not manq else f"bornes absentes : {manq}",
                   len(manq), not manq)]


def coherence_sexes(tables: dict[str, pd.DataFrame]) -> list[dict]:
    """Hommes + Femmes = Ensemble."""
    res = []
    for nom, df in tables.items():
        if "indicateur" in df:
            continue
        p = df.pivot_table(index=["annee", "tranche_age"], columns="sexe", values="effectif", aggfunc="sum")
        if not {"Hommes", "Femmes"} <= set(p.columns):
            continue
        e = (p["Hommes"] + p["Femmes"] - p["Ensemble"]).abs().max()
        res.append(_ligne("Hommes + Femmes = Ensemble", nom, "par année et tranche", float(e), e < 1))
    return res


def coherence_totaux_internes() -> list[dict]:
    """Somme des tranches = colonne « Total » de chaque fichier."""
    res = []
    for cle in ("aq", "gca", "dep2"):
        df = charger_population_age(cle, inclure_total=True)
        tot = df[df["tranche_age"] == "Total"].set_index(["annee", "sexe"])["effectif"]
        som = df[df["tranche_age"] != "Total"].groupby(["annee", "sexe"])["effectif"].sum()
        e = (som - tot).abs().max()
        res.append(_ligne("somme des tranches = Total", f"pop_{cle}", "par année et sexe", float(e), e < 1))
    return res


def coherence_entre_fichiers(tables: dict[str, pd.DataFrame]) -> tuple[list[dict], pd.DataFrame]:
    """Totaux par année et regroupements de tranches cohérents entre fichiers.

    Les estimations (estim-pop) et les fichiers DEP ne sont pas forcément du même
    millésime : on tolère un écart relatif de TOLERANCE_REL.
    """
    aq, gca, dep2 = tables["pop_aq"], tables["pop_gca"], tables["pop_dep2"]
    ens = lambda d: d[d["sexe"] == "Ensemble"].groupby("annee")["effectif"].sum()
    dep1 = tables["dep1"].query("indicateur == 'population_1er_janvier'").set_index("annee")["effectif"]
    comp = pd.DataFrame({"estim_aq": ens(aq), "estim_gca": ens(gca), "dep2": ens(dep2), "dep1": dep1})
    res = []
    for col in ("estim_gca", "dep2", "dep1"):
        rel = ((comp[col] - comp["estim_aq"]) / comp["estim_aq"]).abs().dropna()
        res.append(_ligne("total population vs estim_aq", col,
                          f"pire année {rel.idxmax()} ({comp.loc[rel.idxmax(), col] - comp.loc[rel.idxmax(), 'estim_aq']:+.0f} hab.)",
                          float(rel.max()), rel.max() <= TOLERANCE_REL))
    # tranches : quinquennal regroupé vs découpages larges
    for nom, large in (("pop_gca", gca), ("pop_dep2", dep2)):
        res += decoupages_compatibles(aq, large, nom)
        cible = ordonner_tranches(large["tranche_age"])
        r = regrouper(aq, cible).merge(large, on=["annee", "sexe", "tranche_age"], suffixes=("_aq", "_large"))
        rel = ((r["effectif_large"] - r["effectif_aq"]) / r["effectif_aq"]).abs()
        pire = r.loc[rel.idxmax()]
        res.append(_ligne("tranches regroupées vs estim_aq", nom,
                          f"pire : {pire.annee} {pire.sexe} {pire.tranche_age}",
                          float(rel.max()), rel.max() <= TOLERANCE_REL))
    return res, comp


def coherence_deces(tables: dict[str, pd.DataFrame]) -> list[dict]:
    """Décès Eurostat (somme des âges) vs décès INSEE DEP4."""
    eu = tables["deces_age"].query("sexe == 'Ensemble'").groupby("annee")["effectif"].sum()
    fr = tables["dep4"].query("indicateur == 'deces'").set_index("annee")["effectif"]
    c = pd.concat([eu.rename("eurostat"), fr.rename("insee")], axis=1).dropna()
    rel = ((c["eurostat"] - c["insee"]) / c["insee"]).abs()
    return [_ligne("décès Eurostat vs INSEE DEP4", "deces_age",
                   f"{c.index.min()}-{c.index.max()}, pire année {rel.idxmax()}",
                   float(rel.max()), rel.max() <= 0.01)]


def coherence_composantes(tables: dict[str, pd.DataFrame]) -> list[dict]:
    """DEP1 vs DEP3/DEP4, et équation P(t) + variation totale = P(t+1)."""
    d1 = tables["dep1"].pivot(index="annee", columns="indicateur", values="effectif")
    res = []
    for indic, autre in (("naissances", "dep3"), ("deces", "dep4")):
        a = tables[autre].query("indicateur == @indic").set_index("annee")["effectif"]
        e = (d1[indic] - a).abs().max()
        res.append(_ligne(f"{indic} DEP1 = {autre.upper()}", "dep1", "par année", float(e), e < 1))
    aq = tables["pop_aq"].query("sexe == 'Ensemble'").groupby("annee")["effectif"].sum()
    e = (d1["population_1er_janvier"] + d1["variation_totale"] - aq.shift(-1).reindex(d1.index)).abs().max()
    res.append(_ligne("P(t) + variation totale = P(t+1)", "dep1", "variation DEP1, P(t+1) estim_aq", float(e), e < 1))
    return res


def rapport(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    lignes = (valeurs_manquantes(tables) + tranches_identiques(tables) + coherence_sexes(tables)
              + coherence_totaux_internes() + coherence_entre_fichiers(tables)[0]
              + coherence_composantes(tables) + coherence_deces(tables))
    return pd.DataFrame(lignes)
