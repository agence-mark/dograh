"""[.mark] Chantier Partie 1, lot 17 : le gabarit d'agent, figé et versionné (D11).

Un gabarit = ``<nom>/gabarit.json`` (étapes, outils, sorties, trous, variables d'appel), ses textes à trous (``textes_a_trous/``), son gabarit
de réglages (``reglages.json``) et sa ``version``. L'EMPREINTE couvre les quatre : un mot changé sans changer la version est refusé à la
première lecture en base (``figer``), jamais écrit par-dessus la version figée.

Les textes à trous sont ceux de la version finale prouvée au banc, valeurs du témoin remplacées par des trous (aucun mot changé : le test
``test_textes_a_trous_rendent_les_textes_prouves`` le prouve sur chaque carte versée).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from api.services.gabarits import trous as T

RACINE = Path(__file__).parent
RESTAURATION = "restauration"
CRLF, LF = chr(13) + chr(10), chr(10)


@dataclass(frozen=True)
class Gabarit:
    nom: str
    version: int
    definition: dict[str, Any]
    textes: dict[str, str]
    reglages: dict[str, Any]
    empreinte: str

    @property
    def trous(self) -> dict[str, dict[str, str]]:
        return self.definition["trous"]

    @property
    def variables_d_appel(self) -> list[str]:
        return list(self.definition["variables_d_appel"])

    def contenu(self) -> dict[str, Any]:
        """Ce qui est figé en base : tout le gabarit, textes et réglages compris."""
        return {"definition": self.definition, "textes": self.textes, "reglages": self.reglages}

    @property
    def principal(self) -> str:
        """L'étape qui reçoit l'appel et passe la main aux autres (``role`` ``principal`` du gabarit)."""
        return next(e for e, d in self.definition["etapes"].items() if d["role"] == "principal")

    @property
    def passages(self) -> dict[str, str]:
        """Ce que traite chaque collègue, dit à l'étape principale pour qu'elle choisisse à qui passer la main (le texte de chaque cible du passage)."""
        return dict(self.definition["passages"])

    def etapes_des_missions(self, missions: list[str]) -> list[str]:
        """Les étapes à installer pour ces missions : l'accueil toujours, puis chaque collègue d'une mission cochée, dans l'ordre du gabarit."""
        voulues = {self.principal} | {self.definition["missions"][m]["etape"] for m in missions if self.definition["missions"].get(m, {}).get("etape")}
        return [e for e in self.definition["etapes"] if e in voulues]


VERSION_FIGEE_SANS_LES_OUTILS = 6  # jusqu'à cette version, l'empreinte ne couvrait pas ``textes/<modèle>/contrats/<n>.json`` : la changer ferait refuser la version déjà figée en base


def _empreinte(definition: dict, textes: dict, reglages: dict, version: int, outils: str | None = None) -> str:
    """Pierre E : à partir de la version 7, l'empreinte couvre aussi les outils versés (``contrats/<n>.json``) : changer un outil sans changer de version est refusé (``GabaritDejaFige``)."""
    contenu = {"v": version, "d": definition, "t": textes, "r": reglages}
    if version > VERSION_FIGEE_SANS_LES_OUTILS and outils is not None:
        contenu["o"] = outils
    brut = json.dumps(contenu, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _empreinte_des_outils(nom: str, version: int) -> str | None:
    """L'empreinte des contrats des outils (``contrats/<version>.json``) versés pour cette version du gabarit (tous les modèles, dans l'ordre) ; ``None`` quand il n'en verse pas."""
    from api.services.gabarits.restauration.textes import fichier_du_contrat

    fichiers = [fichier_du_contrat(d, version) for d in sorted((RACINE / nom / "textes").iterdir()) if (d / "contrats").is_dir()]
    if not fichiers:
        return None
    return hashlib.sha256(b"".join(f.read_bytes().replace(CRLF.encode(), LF.encode()) for f in fichiers)).hexdigest()


@lru_cache(maxsize=4)
def charger(nom: str = RESTAURATION) -> Gabarit:
    dossier = RACINE / nom
    definition = json.loads((dossier / "gabarit.json").read_text(encoding="utf-8"))
    definition.pop("_source", None)
    version = int((dossier / "version").read_text(encoding="utf-8").strip())
    # Les fins de ligne du dépôt (CRLF sous Windows) ne changent ni l'empreinte ni la coupure du prompt.
    textes = {p.stem: p.read_text(encoding="utf-8").replace(CRLF, LF) for p in sorted((dossier / "textes_a_trous").glob("*.txt"))}
    reglages = json.loads((dossier / "reglages.json").read_text(encoding="utf-8"))
    reglages.pop("_source", None)
    return Gabarit(nom, version, definition, textes, reglages, _empreinte(definition, textes, reglages, version, _empreinte_des_outils(nom, version)))


# --------------------------------------------------------------------------- les trous


def noms_cites_par_les_textes(g: Gabarit) -> set[str]:
    return {n for t in g.textes.values() for n in T.noms_cites(t)}


def ecarts_des_trous(g: Gabarit) -> dict[str, list[str]]:
    """Ce qui casse la règle « les textes citent exactement la liste » : un nom cité qui n'est ni un trou ni une variable d'appel ; un trou
    qu'aucun texte ne cite ; une variable d'appel que ni un texte ni un calcul ne cite."""
    cites = noms_cites_par_les_textes(g)
    trous = set(g.trous)
    variables = set(g.variables_d_appel)
    produits_par_calcul = {n for nom in T.CALCULS for n in T.noms_cites(T.CALCULS[nom]({"services": ["emporter", "livraison", "sur_place"]}))}
    return {
        "cites_hors_liste": sorted(cites - trous - variables),
        "trous_jamais_cites": sorted(trous - cites),
        "variables_jamais_citees": sorted(variables - cites - produits_par_calcul),
    }


# --------------------------------------------------------------------------- les textes remplis d'une étape


def texte_rempli(g: Gabarit, fichier: str, valeurs: dict[str, str]) -> str:
    return T.remplir(g.textes[fichier], valeurs, trous=set(g.trous))


def prompts_de_l_etape(g: Gabarit, fichier: str, valeurs: dict[str, str]) -> tuple[str, str]:
    """(prompt général, prompt de l'étape) : coupé à « # Ta mission ici », comme le moteur les recolle (« \\n\\n »)."""
    texte = texte_rempli(g, fichier, valeurs).rstrip("\n")
    coupure = "\n\n" + g.definition["coupure_du_prompt"]
    general, mission = texte.split(coupure, 1)
    return general, coupure.lstrip("\n") + mission


# --------------------------------------------------------------------------- les outils


def outil(g: Gabarit, nom: str, etape: str) -> dict[str, Any]:
    """La définition d'un outil du gabarit dans une étape : ``{connecteur, action}`` ou ``{capacite_manquante}``."""
    d = dict(g.definition["outils"][nom])
    if d.pop("connecteur_de_l_etape", False):
        d["connecteur"] = g.definition["etapes"][etape]["connecteur"]
    return d


def outils_sans_action(g: Gabarit) -> dict[str, str]:
    """Les outils du gabarit qu'aucune action du catalogue du fork ne porte (``capacite_manquante`` écrit, ou action absente)."""
    from api.services.integrations.connectors.catalogue import connecteur

    import api.services.integrations.connectors.actions  # noqa: F401  (déclare les connecteurs)

    manquants: dict[str, str] = {}
    for etape, e in g.definition["etapes"].items():
        for n in e["noeuds"]:
            for nom in n.get("outils", []):
                d = outil(g, nom, etape)
                if "capacite_manquante" in d:
                    manquants[nom] = d["capacite_manquante"]
                    continue
                c = connecteur(d["connecteur"])
                if c is None or c.action(d["action"]) is None:
                    manquants[nom] = f"action {d['connecteur']}.{d['action']} absente du catalogue"
    return manquants


# --------------------------------------------------------------------------- la version figée en base


async def figer(g: Gabarit | None = None) -> dict[str, Any]:
    """Écrit la version en base si elle manque ; une version déjà figée avec une autre empreinte est refusée (``GabaritDejaFige``)."""
    from api.db import db_client

    g = g or charger()
    return await db_client.figer_le_gabarit(g.nom, g.version, g.contenu(), g.empreinte)
