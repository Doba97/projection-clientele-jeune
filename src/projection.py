"""Projection démographique par composantes, tranches de 5 ans, pas de 5 ans.

Un pas t -> t+5, par sexe :
- tranche a -> a+5 : P(t+5, a+5) = S(a) · P(t, a) · (1 + m(a+5))
  (survivants, plus le solde migratoire m · survivants) ;
- dernière tranche : P(t+5, 90+) = S_90 · (P(t, 85-89) + P(t, 90+)) · (1 + m(90+)) ;
- première tranche : P(t+5, 0-4) = B · S_naiss · (1 + m(0-4)), où B = naissances
  sur 5 ans, **constantes** (égales à celles de la fenêtre de calibrage).

S et m viennent de src.taux.taux_survie_migration (une fenêtre de 5 ans).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .chargement import ordonner_tranches
from .taux import harmoniser_90plus, taux_survie_migration

CLE = ["sexe", "tranche_age"]
TRANCHES_JEUNES = ("15-19", "20-24", "25-29")


# --------------------------------------------------------------------------- briques
def population_base(pop: pd.DataFrame, annee: int) -> pd.Series:
    """Population au 1er janvier `annee`, Hommes/Femmes, 90-94 et 95+ fusionnés en 90+."""
    p = harmoniser_90plus(pop)
    p = p[(p["annee"] == annee) & p["sexe"].isin(["Hommes", "Femmes"])]
    return p.set_index(CLE)["effectif"].sort_index()


def projeter_pas(pop_t: pd.Series, taux: pd.DataFrame,
                 facteur_migration: pd.Series | None = None) -> pd.Series:
    """Un pas de 5 ans.

    pop_t : Série indexée (sexe, tranche_age).
    taux : table de taux_survie_migration (une ligne par sexe et tranche d'arrivée).
      La ligne « naissances » porte dans `effectif_depart` les naissances sur 5 ans
      de la fenêtre de calibrage : elles sont reprises telles quelles (constantes).
    facteur_migration : Série (sexe, tranche_arrivee) remplaçant 1 + taux_migration_5ans
      (utilisée pour les tirages aléatoires).
    """
    res = {}
    for r in taux.itertuples():
        fm = (1 + r.taux_migration_5ans) if facteur_migration is None \
            else facteur_migration[(r.sexe, r.tranche_arrivee)]
        if r.tranche_depart == "naissances":
            depart = r.effectif_depart
        elif " et " in r.tranche_depart:  # 85-89 et 90+ -> 90+
            depart = sum(pop_t[(r.sexe, t)] for t in r.tranche_depart.split(" et "))
        else:
            depart = pop_t[(r.sexe, r.tranche_depart)]
        res[(r.sexe, r.tranche_arrivee)] = r.taux_survie_5ans * depart * fm
    out = pd.Series(res, name="effectif")
    out.index.names = CLE
    return out.sort_index()


def projeter(pop_base: pd.Series, taux: pd.DataFrame, annee_base: int, n_pas: int = 2) -> pd.DataFrame:
    """Projection déterministe à taux constants. Renvoie le format long (base incluse)."""
    etapes, p = {annee_base: pop_base}, pop_base
    for k in range(1, n_pas + 1):
        p = projeter_pas(p, taux)
        etapes[annee_base + 5 * k] = p
    return en_long(etapes)


def en_long(etapes: dict[int, pd.Series]) -> pd.DataFrame:
    return (pd.concat(etapes, names=["annee"]).rename("effectif").reset_index()
            [["annee", "sexe", "tranche_age", "effectif"]])


def total_jeunes(df: pd.DataFrame, tranches=TRANCHES_JEUNES, par: list[str] | None = None) -> pd.Series:
    par = par or ["annee"]
    return df[df["tranche_age"].isin(tranches)].groupby(par)["effectif"].sum()


def interpoler(p0: pd.Series, p1: pd.Series, a0: int, a1: int, annee: int) -> pd.Series:
    """Interpolation géométrique entre deux pas (ex. 2026 entre 2025 et 2030)."""
    return p0 * (p1 / p0) ** ((annee - a0) / (a1 - a0))


# --------------------------------------------------------------------------- backtest
def backtest(pop: pd.DataFrame, deces: pd.DataFrame, naissances: pd.Series,
             debut_calib: int = 2013, duree: int = 5) -> pd.DataFrame:
    """Calibre sur [debut, debut+5], projette de debut+5 à debut+10, compare au réel.

    Deux références naïves pour juger le modèle :
    - « sans migration » : survie seule ;
    - « population figée » : P(t+5, a) = P(t, a).
    """
    taux = taux_survie_migration(pop, deces, naissances, debut=debut_calib, duree=duree)
    base = debut_calib + duree
    cible = base + duree
    p_base = population_base(pop, base)
    reel = population_base(pop, cible)
    t0 = taux.assign(taux_migration_5ans=0.0)
    # « migration connue à l'avance » : survie et naissances calibrées, mais migration de la
    # période projetée elle-même. L'erreur restante ne vient que de la survie et des naissances.
    m_reelle = (taux_survie_migration(pop, deces, naissances, debut=base, duree=duree)
                .set_index(["sexe", "tranche_arrivee"])["taux_migration_5ans"])
    t_oracle = taux.assign(taux_migration_5ans=taux.set_index(["sexe", "tranche_arrivee"]).index.map(m_reelle))
    res = pd.DataFrame({
        "reel": reel,
        "modele": projeter_pas(p_base, taux),
        "migration_connue": projeter_pas(p_base, t_oracle),
        "sans_migration": projeter_pas(p_base, t0),
        "population_figee": p_base,
    })
    res.attrs.update(calibrage=f"{debut_calib}-{base}", base=base, cible=cible)
    return res.reset_index()


METHODES = ("modele", "migration_connue", "sans_migration", "population_figee")


def erreurs(bt: pd.DataFrame, methodes=METHODES, par: str = "tranche_age") -> pd.DataFrame:
    """Erreur (projeté - réel) et erreur relative par tranche, sexes cumulés si par='tranche_age'."""
    g = bt.groupby(par)[["reel", *methodes]].sum()
    if par == "tranche_age":
        g = g.loc[ordonner_tranches(g.index)]
    for m in methodes:
        g[f"err_{m}"] = g[m] - g["reel"]
        g[f"err_rel_{m}"] = g[f"err_{m}"] / g["reel"]
    return g


def resume_erreurs(bt: pd.DataFrame, methodes=METHODES,
                   tranches_jeunes=TRANCHES_JEUNES) -> pd.DataFrame:
    """MAPE par tranche (sexe x tranche), erreur sur le total et sur les jeunes."""
    lignes = {}
    j = bt[bt["tranche_age"].isin(tranches_jeunes)]
    for m in methodes:
        ape = ((bt[m] - bt["reel"]) / bt["reel"]).abs()
        lignes[m] = {
            "MAPE sexe x tranche": ape.mean(),
            "erreur max sexe x tranche": ape.max(),
            "erreur population totale": bt[m].sum() / bt["reel"].sum() - 1,
            "erreur 15-29 ans": j[m].sum() / j["reel"].sum() - 1,
        }
    return pd.DataFrame(lignes).T


# --------------------------------------------------------------------------- incertitude
def taux_fenetres(pop, deces, naissances, debuts) -> pd.DataFrame:
    """Taux pour plusieurs fenêtres glissantes de 5 ans (une par année de début)."""
    return pd.concat([taux_survie_migration(pop, deces, naissances, debut=d) for d in debuts],
                     ignore_index=True)


def monte_carlo(pop_base: pd.Series, taux: pd.DataFrame, fenetres: pd.DataFrame, annee_base: int,
                n_pas: int = 2, n_sim: int = 2000, graine: int = 0, mode: str = "simulation") -> pd.DataFrame:
    """Tirages aléatoires du profil de migration parmi les fenêtres de `fenetres`.

    Un profil = les taux de migration annualisés de tous les âges et sexes d'une fenêtre
    (tirés ensemble pour garder la cohérence du profil).

    - mode="simulation" (défaut) : **un profil par simulation**, appliqué à tout l'horizon.
      Les régimes de migration durent (2013-2018 puis 2018-2023 sont deux niveaux distincts) :
      c'est l'hypothèse retenue.
    - mode="annuel" : un profil tiré **chaque année**. Sur 10 ans, les tirages hauts et bas se
      compensent (moyenne de 10 tirages) : l'intervalle obtenu sous-estime l'incertitude,
      puisqu'un régime durablement bas ou haut devient quasi impossible.

    Sur un pas de 5 ans : facteur = Π_{5 années} (1 + taux_migration_annuel tiré).
    La survie et les naissances restent celles de `taux` (fenêtre la plus récente).
    """
    if mode not in ("simulation", "annuel"):
        raise ValueError("mode = 'simulation' ou 'annuel'")
    rng = np.random.default_rng(graine)
    profils = fenetres.pivot_table(index=["sexe", "tranche_arrivee"], columns="debut",
                                   values="taux_migration_annuel")
    log1p = np.log1p(profils.to_numpy())  # (n_groupes, n_fenetres)
    sims = []
    for s in range(n_sim):
        p, etapes = pop_base, {annee_base: pop_base}
        profil_sim = rng.integers(0, log1p.shape[1])
        for k in range(1, n_pas + 1):
            tirage = (np.full(5, profil_sim) if mode == "simulation"
                      else rng.integers(0, log1p.shape[1], size=5))
            fm = pd.Series(np.exp(log1p[:, tirage].sum(axis=1)), index=profils.index)
            p = projeter_pas(p, taux, facteur_migration=fm)
            etapes[annee_base + 5 * k] = p
        sims.append(en_long(etapes).assign(sim=s))
    return pd.concat(sims, ignore_index=True)


# --------------------------------------------------------------------------- décomposition
def decomposition_jeunes(pop_t: pd.Series, taux: pd.DataFrame, tranches=TRANCHES_JEUNES) -> pd.Series:
    """Décomposition exacte de la variation des jeunes sur un pas de 5 ans.

    J(t+5) = Σ_{a ∈ 10-14, 15-19, 20-24} S(a)·P(t, a)·(1 + m), d'où
    J(t+5) − J(t) = P(t, 10-14)                 cohorte entrante
                  − P(t, 25-29)                 cohorte sortante (passe à 30-34)
                  + Σ (S − 1)·P(t, a)           décès
                  + Σ S·P(t, a)·m               migration nette
    """
    t = taux[taux["tranche_arrivee"].isin(tranches)]
    depart = pd.Series([pop_t[(r.sexe, r.tranche_depart)] for r in t.itertuples()], index=t.index)
    entrante = depart[t["tranche_arrivee"] == tranches[0]].sum()  # P(t, 10-14)
    sortante = sum(pop_t[(s, tranches[-1])] for s in ("Hommes", "Femmes"))
    deces = ((t["taux_survie_5ans"] - 1) * depart).sum()
    migration = (t["taux_survie_5ans"] * depart * t["taux_migration_5ans"]).sum()
    return _serie_decomposition(entrante, sortante, deces, migration)


def decomposition_observee(p_t: pd.Series, p_t5: pd.Series, taux: pd.DataFrame,
                           tranches=TRANCHES_JEUNES) -> pd.Series:
    """Même décomposition à partir de deux populations données (observées, ou Omphale).

    Les décès sont estimés avec la survie de `taux` ; la migration est le résidu :
    migration = ΔJ − (entrante − sortante) − décès.
    """
    t = taux[taux["tranche_arrivee"].isin(tranches)]
    depart = pd.Series([p_t[(r.sexe, r.tranche_depart)] for r in t.itertuples()], index=t.index)
    entrante = depart[t["tranche_arrivee"] == tranches[0]].sum()
    sortante = sum(p_t[(s, tranches[-1])] for s in ("Hommes", "Femmes"))
    deces = ((t["taux_survie_5ans"] - 1) * depart).sum()
    jeunes = lambda p: p[p.index.get_level_values("tranche_age").isin(tranches)].sum()
    migration = jeunes(p_t5) - jeunes(p_t) - (entrante - sortante) - deces
    return _serie_decomposition(entrante, sortante, deces, migration)


def _serie_decomposition(entrante, sortante, deces, migration) -> pd.Series:
    return pd.Series({"cohorte entrante (10-14 → 15-19)": entrante,
                      "cohorte sortante (25-29 → 30-34)": -sortante,
                      "décès": deces, "migration nette": migration,
                      "variation totale": entrante - sortante + deces + migration})


# --------------------------------------------------------------------------- clientèle
def projeter_clients(pop_proj: pd.DataFrame, taux_penetration: pd.DataFrame) -> pd.DataFrame:
    """Clients = population x taux de pénétration (colonnes sexe?, tranche_age, taux)."""
    cles = [c for c in ("annee", "sexe", "tranche_age") if c in taux_penetration.columns]
    df = pop_proj.merge(taux_penetration, on=cles)
    df["clients"] = df["effectif"] * df["taux"]
    return df
