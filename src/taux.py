"""Taux de survie et de migration nette par tranche quinquennale (méthode des composantes).

Période par défaut : 1er janvier 2020 -> 1er janvier 2025, soit les 5 dernières
années pour lesquelles on dispose des décès par âge (Eurostat, jusqu'à 2024).

1. Mortalité : m(a) = Σ décès(t, a) / Σ population moyenne(t, a), t = 2020..2024,
   avec population moyenne = (P(1er janv. t) + P(1er janv. t+1)) / 2.
2. Table de mortalité abrégée : l(x+5) = l(x)·exp(-5·m(x)),
   L(x) = 5·(l(x) + l(x+5)) / 2, groupe ouvert L(90+) = l(90) / m(90+).
3. Survie sur 5 ans d'une tranche à la suivante : S(a) = L(a+5) / L(a) ;
   naissances -> 0-4 : L(0-4) / (5·l0) ; tranche terminale : T(90) / T(85).
4. Migration nette (méthode résiduelle) :
   M(a+5) = P(t+5, a+5) - S(a)·P(t, a), et taux = M / (S·P(t, a)),
   d'où P(t+5, a+5) = S(a)·P(t, a)·(1 + taux) en projection.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .chargement import borne_inf, ordonner_tranches

PART_GARCONS = 0.512  # part des garçons à la naissance (≈ 105 garçons pour 100 filles)


def harmoniser_90plus(pop: pd.DataFrame) -> pd.DataFrame:
    """Fusionne 90-94 et 95+ (INSEE) en 90+ pour coller aux tranches Eurostat."""
    p = pop.copy()
    p.loc[p["tranche_age"].isin(["90-94", "95+"]), "tranche_age"] = "90+"
    return p.groupby(["annee", "sexe", "tranche_age"], as_index=False)["effectif"].sum()


def taux_mortalite(pop: pd.DataFrame, deces: pd.DataFrame, annees: range) -> pd.DataFrame:
    p = harmoniser_90plus(pop).set_index(["annee", "sexe", "tranche_age"])["effectif"]
    lignes = []
    for t in annees:
        moy = (p.xs(t, level="annee") + p.xs(t + 1, level="annee")) / 2
        lignes.append(moy.rename("expo").reset_index().assign(annee=t))
    expo = pd.concat(lignes)
    d = deces[deces["annee"].isin(annees)]
    m = d.merge(expo, on=["annee", "sexe", "tranche_age"]).groupby(["sexe", "tranche_age"])[["effectif", "expo"]].sum()
    m["m"] = m["effectif"] / m["expo"]
    return m.rename(columns={"effectif": "deces"}).reset_index()


def table_survie(m: pd.DataFrame) -> pd.DataFrame:
    """Table abrégée et rapports de survie sur 5 ans pour un sexe."""
    m = m.set_index("tranche_age").loc[ordonner_tranches(m["tranche_age"])]
    l = [1.0]
    for x in m.index[:-1]:
        l.append(l[-1] * np.exp(-5 * m.loc[x, "m"]))
    m["l"] = l
    m["L"] = [5 * (l[i] + l[i + 1]) / 2 for i in range(len(l) - 1)] + [l[-1] / m["m"].iloc[-1]]
    m["T"] = m["L"][::-1].cumsum()[::-1]
    return m


def taux_survie_migration(pop: pd.DataFrame, deces: pd.DataFrame, naissances: pd.Series,
                          debut: int = 2020, duree: int = 5) -> pd.DataFrame:
    """Taux par sexe et tranche d'arrivée sur la période [debut, debut + duree].

    pop : population quinquennale (format long), deces : décès par âge (Eurostat),
    naissances : naissances totales par année (index = année).
    effectif_depart = P(debut, a) (ou naissances de la période pour la ligne « naissances »),
    effectif_arrivee = P(fin, a+5).
    """
    fin = debut + duree
    annees = range(debut, fin)
    mort = taux_mortalite(pop, deces, annees)
    p = harmoniser_90plus(pop).set_index(["annee", "sexe", "tranche_age"])["effectif"]
    res = []
    for sexe in ("Hommes", "Femmes"):
        tb = table_survie(mort[mort["sexe"] == sexe])
        tr = list(tb.index)
        part = PART_GARCONS if sexe == "Hommes" else 1 - PART_GARCONS
        n = naissances.loc[list(annees)].sum() * part
        # naissances -> 0-4
        s = tb["L"].iloc[0] / 5
        res.append((sexe, "naissances", tr[0], s, n, p[(fin, sexe, tr[0])]))
        for i in range(len(tr) - 1):
            arr = tr[i + 1]
            if i + 1 == len(tr) - 1:  # tranche terminale : (85-89 + 90+) -> 90+
                s = tb["T"].iloc[-1] / tb["T"].iloc[-2]
                depart = p[(debut, sexe, tr[i])] + p[(debut, sexe, tr[i + 1])]
                lib = f"{tr[i]} et {tr[i + 1]}"
            else:
                s = tb["L"].iloc[i + 1] / tb["L"].iloc[i]
                depart = p[(debut, sexe, tr[i])]
                lib = tr[i]
            res.append((sexe, lib, arr, s, depart, p[(fin, sexe, arr)]))
    df = pd.DataFrame(res, columns=["sexe", "tranche_depart", "tranche_arrivee", "taux_survie_5ans",
                                    "effectif_depart", "effectif_arrivee"])
    df["survivants_attendus"] = df["taux_survie_5ans"] * df["effectif_depart"]
    df["migration_nette_5ans"] = df["effectif_arrivee"] - df["survivants_attendus"]
    df["taux_migration_5ans"] = df["migration_nette_5ans"] / df["survivants_attendus"]
    df["taux_migration_annuel"] = (1 + df["taux_migration_5ans"]) ** (1 / duree) - 1
    mort_ = mort[["sexe", "tranche_age", "m"]].rename(columns={"tranche_age": "tranche_depart",
                                                               "m": "taux_mortalite_annuel"})
    df = df.merge(mort_, on=["sexe", "tranche_depart"], how="left")
    df["debut"], df["fin"] = debut, fin
    df["periode"] = f"{debut}-{fin}"
    return df
