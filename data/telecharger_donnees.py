"""Télécharge les données qui ne sont pas fournies sous forme de fichiers Excel INSEE.

Les fichiers INSEE (.xlsx) sont à placer à la main dans data/ (voir data/README.md).
Ce script récupère les décès par âge et sexe du Morbihan (Eurostat) dans data/raw/.
"""
import time
from pathlib import Path

import requests

RAW_DIR = Path(__file__).parent / "raw"

# nom du fichier local -> URL
SOURCES = {
    "eurostat_demo_r_magec3_FRH04.json": (
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
        "demo_r_magec3?geo=FRH04&format=JSON&lang=fr"
    ),
    # Insee, projections Omphale 2022 (base RP 2018), tableaux détaillés départementaux
    # https://www.insee.fr/fr/statistiques/7747107
    **{
        f"omphale_{s}.xlsx": f"https://www.insee.fr/fr/statistiques/fichier/7747107/donnees_det_{s}.xlsx"
        for s in ("Central", "Mig_basse", "Mig_haute")
    },
}


def telecharger(nom: str, url: str, forcer: bool = False) -> None:
    dest = RAW_DIR / nom
    if dest.exists() and not forcer:
        print(f"déjà présent : {dest}")
        return
    print(f"téléchargement : {url}")
    for essai in range(4):  # le serveur Insee renvoie parfois des erreurs 500 passagères
        r = requests.get(url, timeout=600)
        if r.ok:
            break
        time.sleep(5 * (essai + 1))
    r.raise_for_status()
    dest.write_bytes(r.content)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for nom, url in SOURCES.items():
        telecharger(nom, url)


if __name__ == "__main__":
    main()
