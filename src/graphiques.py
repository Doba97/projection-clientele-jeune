"""Graphiques."""
from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

from .chargement import ordonner_tranches

TRANCHES_JEUNES = ("15-19", "20-24", "25-29")  # définition « jeunes » : 15-29 ans

# palette de référence (dataviz) : bleu / orange, versions atténuées hors jeunes
COULEURS = {"Hommes": "#2a78d6", "Femmes": "#eb6834"}
ATTENUE = {"Hommes": "#bcd3f0", "Femmes": "#f6c9b5"}
ENCRE, ENCRE_2, GRILLE = "#0b0b0b", "#52514e", "#e4e3df"


def pyramide(pop: pd.DataFrame, annee: int, jeunes=TRANCHES_JEUNES, titre: str | None = None):
    """Pyramide des âges (hommes à gauche, femmes à droite), tranche jeunes en évidence."""
    d = pop[(pop["annee"] == annee) & pop["sexe"].isin(["Hommes", "Femmes"])]
    tr = ordonner_tranches(d["tranche_age"])
    p = d.pivot(index="tranche_age", columns="sexe", values="effectif").loc[tr]
    y = range(len(tr))
    fig, ax = plt.subplots(figsize=(9, 7.5))
    est_jeune = [t in jeunes for t in tr]
    for sexe, signe in (("Hommes", -1), ("Femmes", 1)):
        couleurs = [COULEURS[sexe] if j else ATTENUE[sexe] for j in est_jeune]
        ax.barh(y, signe * p[sexe] / 1000, color=couleurs, height=0.82,
                edgecolor="white", linewidth=1)
    # bande de mise en évidence
    idx = [i for i, j in enumerate(est_jeune) if j]
    ax.axhspan(min(idx) - 0.5, max(idx) + 0.5, color="#f1f0ec", zorder=0)
    xmax = p.max().max() / 1000 * 1.15
    ax.set_xlim(-xmax, xmax)
    # étiquettes directes sur les seules barres jeunes
    for i in idx:
        for sexe, signe, ha in (("Hommes", -1, "right"), ("Femmes", 1, "left")):
            v = p[sexe].iloc[i]
            ax.text(signe * (v / 1000 + xmax * 0.015), i, f"{v / 1000:.1f}", va="center", ha=ha,
                    fontsize=8.5, color=ENCRE)
    n_j = p.loc[list(jeunes)].sum().sum()
    sous_titre = (f"Tranche jeunes ({jeunes[0].split('-')[0]}-{jeunes[-1].split('-')[1]} ans) en évidence : "
                  f"{n_j:,.0f}".replace(",", " ")
                  + f" habitants, soit {n_j / p.sum().sum():.1%} de la population".replace(".", ","))
    ax.set_yticks(list(y), tr, fontsize=9, color=ENCRE_2)
    ticks = ax.get_xticks()
    ax.set_xticks(ticks, [f"{abs(t):.0f}" for t in ticks], fontsize=9, color=ENCRE_2)
    ax.set_xlim(-xmax, xmax)
    ax.set_xlabel("Effectif (milliers)", color=ENCRE_2)
    ax.axvline(0, color=ENCRE_2, linewidth=0.8)
    ax.grid(axis="x", color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRILLE)
    ax.tick_params(length=0)
    ax.legend(handles=[Patch(color=COULEURS["Hommes"], label="Hommes"),
                       Patch(color=COULEURS["Femmes"], label="Femmes"),
                       Patch(color=ATTENUE["Hommes"], label="hors 15-29 ans (teinte atténuée)")],
              loc="lower left", frameon=False, fontsize=9)
    ax.set_title(titre or f"Pyramide des âges du Morbihan au 1er janvier {annee}",
                 loc="left", fontsize=13, color=ENCRE, pad=26)
    ax.text(0, 1.015, sous_titre, transform=ax.transAxes, fontsize=9.5, color=ENCRE_2)
    fig.text(0.01, 0.005, "Source : Insee, estimations de population (provisoires pour 2024-2026)",
             fontsize=8, color=ENCRE_2)
    fig.tight_layout()
    return fig, ax


# --------------------------------------------------------------------------- backtest et scénarios
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # bleu, orange, aqua (ordre fixe)


def _habiller(ax, titre, sous_titre=None):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRILLE)
    ax.tick_params(length=0, colors=ENCRE_2, labelsize=9)
    ax.set_axisbelow(True)
    ax.set_title(titre, loc="left", fontsize=13, color=ENCRE, pad=26 if sous_titre else 12)
    if sous_titre:
        ax.text(0, 1.015, sous_titre, transform=ax.transAxes, fontsize=9.5, color=ENCRE_2)


def graphique_backtest(err: pd.DataFrame, titre: str, sous_titre: str | None = None):
    """Erreur relative par tranche (points), modèle vs références naïves."""
    methodes = [("modele", "Modèle (survie + migration)"), ("sans_migration", "Survie seule"),
                ("population_figee", "Population figée")]
    tr = list(err.index)
    fig, ax = plt.subplots(figsize=(9, 7))
    jeunes = [i for i, t in enumerate(tr) if t in TRANCHES_JEUNES]
    ax.axhspan(min(jeunes) - 0.5, max(jeunes) + 0.5, color="#f1f0ec", zorder=0)
    ax.axvline(0, color=ENCRE_2, linewidth=0.8)
    for (m, lib), c, d in zip(methodes, SERIES, (-0.22, 0, 0.22)):
        ax.scatter(err[f"err_rel_{m}"] * 100, [i + d for i in range(len(tr))],
                   s=46 if m == "modele" else 28, color=c, label=lib,
                   edgecolor="white", linewidth=1, zorder=3)
    ax.set_yticks(range(len(tr)), tr)
    ax.set_xlabel("Erreur relative (projeté − réel), en %", color=ENCRE_2)
    ax.grid(axis="x", color=GRILLE, linewidth=0.8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False, fontsize=9)
    _habiller(ax, titre, sous_titre)
    fig.tight_layout()
    return fig, ax


def graphique_scenarios(hist: pd.Series, scenarios: dict[str, pd.Series], mc: pd.DataFrame | None,
                        titre: str, sous_titre: str | None = None, prov: pd.Series | None = None,
                        mc_annuel: pd.DataFrame | None = None, externe: dict[str, pd.Series] | None = None):
    """Effectif des 15-29 ans : historique, scénarios déterministes, bandes des tirages.

    mc, mc_annuel : DataFrame indexé par année, colonnes q05, q50, q95.
    externe : projections externes (ex. Omphale), tracées en gris pointillé.
    """
    fig, ax = plt.subplots(figsize=(9.5, 6))
    ax.plot(hist.index, hist / 1000, color=ENCRE, linewidth=2, label="Observé (estimations Insee)")
    if prov is not None:
        ax.scatter(prov.index, prov / 1000, s=40, facecolor="white", edgecolor=ENCRE, linewidth=1.5,
                   zorder=4, label="2026 provisoire")
    for nom, s in (externe or {}).items():
        ax.plot(s.index, s / 1000, color="#8a8984", linewidth=1.8, linestyle=":", label=nom)
    if mc is not None:
        ax.fill_between(mc.index, mc["q05"] / 1000, mc["q95"] / 1000, color=SERIES[2], alpha=0.16,
                        linewidth=0, label="Tirages, 1 profil par simulation : 5-95 %")
        ax.plot(mc.index, mc["q50"] / 1000, color=SERIES[2], linewidth=2, linestyle="--",
                label="Tirages, 1 profil par simulation : médiane")
    if mc_annuel is not None:
        ax.fill_between(mc_annuel.index, mc_annuel["q05"] / 1000, mc_annuel["q95"] / 1000,
                        facecolor="none", edgecolor=SERIES[2], hatch="////", linewidth=0,
                        label="Tirages annuels (comparaison) : 5-95 %")
    for (nom, s), c in zip(scenarios.items(), SERIES[:2]):
        ax.plot(s.index, s / 1000, color=c, linewidth=2, marker="o", markersize=6, label=nom)
        ax.annotate(f"{s.iloc[-1] / 1000:.1f} k".replace(".", ","), (s.index[-1], s.iloc[-1] / 1000),
                    xytext=(7, 0), textcoords="offset points", va="center", fontsize=9, color=ENCRE)
    ax.set_ylabel("Habitants de 15 à 29 ans (milliers)", color=ENCRE_2)
    ax.grid(axis="y", color=GRILLE, linewidth=0.8)
    ax.legend(loc="lower left", frameon=False, fontsize=8.5)
    _habiller(ax, titre, sous_titre)
    fig.tight_layout()
    return fig, ax


COMPOSANTES = {  # composante -> couleur (ordre fixe)
    "cohorte entrante (10-14 → 15-19)": SERIES[0],
    "cohorte sortante (25-29 → 30-34)": SERIES[1],
    "migration nette": SERIES[2],
    "décès": "#eda100",
}


def graphique_contributions(dec: pd.DataFrame, groupes: dict[str, list[str]], titre: str,
                            sous_titre: str | None = None):
    """Barres empilées des composantes (positives au-dessus de 0, négatives en dessous)
    et losange pour la variation totale. dec : une ligne par période, colonnes = composantes."""
    fig, ax = plt.subplots(figsize=(10, 6))
    x, etiquettes, xi = [], [], 0.0
    for g, periodes in groupes.items():
        debut = xi
        for p in periodes:
            x.append(xi)
            etiquettes.append(p)
            xi += 1
        ax.text((debut + xi - 1) / 2, 1.0, g, transform=ax.get_xaxis_transform(), ha="center",
                va="bottom", fontsize=9.5, color=ENCRE_2, fontweight="bold")
        xi += 0.6
    lignes = [p for ps in groupes.values() for p in ps]
    d = dec.loc[lignes]
    haut = pd.Series(0.0, index=lignes)
    bas = pd.Series(0.0, index=lignes)
    for comp, c in COMPOSANTES.items():
        v = d[comp] / 1000
        pos, neg = v.clip(lower=0), v.clip(upper=0)
        ax.bar(x, pos, bottom=haut, color=c, width=0.7, edgecolor="white", linewidth=2, label=comp)
        ax.bar(x, neg, bottom=bas, color=c, width=0.7, edgecolor="white", linewidth=2)
        haut += pos
        bas += neg
    net = d["variation totale"] / 1000
    ax.scatter(x, net, marker="D", s=60, color=ENCRE, zorder=4, label="variation totale des 15-29 ans",
               edgecolor="white", linewidth=1.2)
    for xx, v in zip(x, net):
        ax.annotate(f"{v:+.1f} k".replace(".", ","), (xx, v), xytext=(10, 0), textcoords="offset points",
                    va="center", fontsize=9, color=ENCRE, fontweight="bold")
    ax.axhline(0, color=ENCRE_2, linewidth=0.8)
    ax.set_xticks(x, etiquettes, fontsize=9)
    ax.set_ylabel("Contribution à la variation des 15-29 ans (milliers, sur 5 ans)", color=ENCRE_2)
    ax.grid(axis="y", color=GRILLE, linewidth=0.8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False, fontsize=9)
    _habiller(ax, titre)
    ax.set_title(titre, loc="left", fontsize=13, color=ENCRE, pad=44)
    if sous_titre:
        ax.text(0, 1.075, sous_titre, transform=ax.transAxes, fontsize=9.5, color=ENCRE_2)
    fig.tight_layout()
    return fig, ax
