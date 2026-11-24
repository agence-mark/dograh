"""[.mark] Chantier Partie 1, lot 5 (n° 143, 144) : les rendus du banc, RÉFÉRENCE DES TESTS, jamais lus au fonctionnement.

Le banc final (``verser_textes.py`` du Labo) joue la version finale sans requête dans les états types, sur cinq cartes de test, et note pour
chaque état les outils tels qu'envoyés au modèle (``<version>/banc/rendus.json``). Ce sont des rendus par carte : l'instantané d'un banc, pas un
contrat. Le contrat que lit le fonctionnement est ``<version>/outils.json`` (``textes.contrat``), SANS carte, DÉRIVÉ de ces rendus par
``derivation_du_contrat`` (script ``api/outils/generer_le_contrat.py``). Les prompts des cartes ne sont plus versés : ``prompt`` les rend depuis
les textes à trous du gabarit (une seule source), les variables d'appel restant des trous.

Une règle de test (``test_p1f_lot5_contrat``) vérifie qu'aucun module du fonctionnement n'importe ce module.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from api.services.gabarits.restauration.textes import DOSSIER, TEMOIN

CARTE_TEMOIN = "300"  # Casa Italia, la carte du témoin
FIN_DU_PROMPT = "\n\n{{etat}}"  # l'état de l'appel remplace ce trou à chaque tour


def _ecarts_de_la_v7(valeur):
    """Les rendus du banc avec les écarts de la version 7 (``ecarts_v7.json``), jamais écrits dans ``rendus.json``."""
    ecarts = {e["de"]: e["vers"] for e in json.loads((DOSSIER / TEMOIN / "banc" / "ecarts_v7.json").read_text(encoding="utf-8"))["ecarts"]}
    if isinstance(valeur, dict):
        return {k: (ecarts.get(v, v) if k == "description" and isinstance(v, str) else _ecarts_de_la_v7(v)) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_ecarts_de_la_v7(v) for v in valeur]
    return valeur


@lru_cache(maxsize=8)
def rendus_du_banc(version: str = TEMOIN) -> dict:
    """``banc/rendus.json`` tel que le banc l'a produit : gelé (son empreinte est celle de la version 6, commit ``609437c5``)."""
    return json.loads((DOSSIER / version / "banc" / "rendus.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def rendus(version: str = TEMOIN) -> dict:
    """Les rendus du banc de la version 7 : ceux du banc, plus les écarts déclarés (``ecarts_v7.json``)."""
    return _ecarts_de_la_v7(rendus_du_banc(version))


def rendu(etape: str, etat: str, carte: str = CARTE_TEMOIN, version: str = TEMOIN) -> list[dict]:
    """Les outils envoyés au modèle par la version finale dans cet état (format OpenAI), sur cette carte."""
    for e in rendus(version)["cartes"][carte]:
        if e["etape"] == etape and e["etat"] == etat:
            return e["outils"]
    raise KeyError(f"aucun rendu {etape}/{etat} sur la carte {carte}")


# --------------------------------------------------------------------------- les prompts, rendus depuis les textes à trous

@lru_cache(maxsize=8)
def identites(version: str = TEMOIN) -> dict[str, dict[str, Any]]:
    return json.loads((DOSSIER / version / "banc" / "cartes.json").read_text(encoding="utf-8"))


def prompt(etape: str, carte: str = CARTE_TEMOIN, version: str = TEMOIN) -> str:
    """Le prompt système de l'étape sur cette carte : le texte à trous du gabarit rempli de l'identité de la carte, l'état remplacé par le trou
    ``{{etat}}`` ; les variables d'appel (date, horaires du jour…) restent des trous."""
    from api.services.gabarits import formulaire as F
    from api.services.gabarits import gabarit as G
    from api.services.gabarits import styles as ST
    from api.services.gabarits import trous as T

    g = G.charger()
    valeurs = T.valeurs_des_trous(g.trous, F.completer(identites(version)[carte]), ST.textes())
    return G.texte_rempli(g, etape, valeurs).rstrip("\n") + FIN_DU_PROMPT


def etats_de_reference() -> dict[str, tuple[str, str]]:
    """Par étape du gabarit : le texte de son premier nœud et l'état dans lequel le contrat montre ses outils (``etat_de_reference`` du gabarit)."""
    from api.services.gabarits import gabarit as G

    return {e: (d["noeuds"][0]["texte"], d["etat_de_reference"]) for e, d in G.charger().definition["etapes"].items()}


def requetes_types(version: str = TEMOIN):
    """(étape, prompt système, outils en JSON) des requêtes types de la carte du témoin, pour le budget de caractères (L00-08)."""
    for etape, (fichier, etat) in etats_de_reference().items():
        yield etape, prompt(fichier, version=version), json.dumps(rendu(etape, etat, version=version), ensure_ascii=False)


# --------------------------------------------------------------------------- la dérivation du contrat


def _union(a: dict, b: dict) -> dict:
    """Deux rendus d'une même case : les sous-cases des deux (un rendu d'état n'en montre qu'une partie)."""
    sortie = dict(a)
    if isinstance(b.get("properties"), dict):
        sortie["properties"] = {
            **{k: _union(v, b["properties"].get(k, {})) if k in b["properties"] else v for k, v in (a.get("properties") or {}).items()},
            **{k: v for k, v in b["properties"].items() if k not in (a.get("properties") or {})},
        }
    if isinstance(a.get("items"), dict) and isinstance(b.get("items"), dict):
        sortie["items"] = _union(a["items"], b["items"])
    return sortie


def _fiche_complete(rendus_: dict, etape: str, variantes_: set[str]) -> dict[str, Any]:
    """Toutes les cases de la fiche d'une étape avec leur texte de base : l'union des rendus sur toutes les cartes et tous les états. Le texte de
    base n'est jamais l'un des textes d'état (``variantes``) quand un autre existe."""
    proprietes: dict[str, Any] = {}
    for etats in rendus_["cartes"].values():
        for e in etats:
            if e["etape"] != etape:
                continue
            fiche = next((o["function"] for o in e["outils"] if o["function"]["name"] == "fiche"), None)
            if fiche is None:
                continue
            for nom, s in fiche["parameters"]["properties"].items():
                if nom not in proprietes:
                    proprietes[nom] = s
                elif proprietes[nom].get("description") in variantes_ and s.get("description") not in variantes_:
                    proprietes[nom] = _union(s, proprietes[nom])
                else:
                    proprietes[nom] = _union(proprietes[nom], s)
    return proprietes


def _sans_valeurs_de_carte(cases: dict[str, Any], listes: set[str]) -> dict[str, Any]:
    """Les listes fermées construites au décroché (``listes`` : chemins de case) perdent les valeurs d'une carte de test : le contrat n'en garde aucune."""
    def nettoyer(s: dict, chemin: str) -> dict:
        s = dict(s)
        if chemin in listes:
            s.pop("enum", None)
        if isinstance(s.get("properties"), dict):
            s["properties"] = {k: nettoyer(v, f"{chemin}.{k}") for k, v in s["properties"].items()}
        if isinstance(s.get("items"), dict):
            s["items"] = nettoyer(s["items"], chemin + "[]")
        return s

    return {nom: nettoyer(s, nom) for nom, s in cases.items()}


def derivation_du_contrat(rendus_: dict, listes: dict[str, set[str]]) -> dict:
    """Le contrat sans carte des rendus du banc : par étape, ses outils dans l'état de référence de la carte du témoin ;
    la fiche porte l'union des cases de tous les rendus, sans valeur de carte ; les textes qui changent avec l'état (``variantes``) ; rien d'autre."""
    variantes_ = dict(rendus_["variantes"])
    textes_d_etat = set(variantes_.values())
    etapes: dict[str, Any] = {}
    for etape, (_, etat) in etats_de_reference().items():
        outils = next(e["outils"] for e in rendus_["cartes"][CARTE_TEMOIN] if e["etape"] == etape and e["etat"] == etat)
        fiche = _fiche_complete(rendus_, etape, textes_d_etat)
        sortie = json.loads(json.dumps(outils))
        if fiche:
            laquelle = next(o["function"] for o in sortie if o["function"]["name"] == "fiche")
            laquelle["parameters"]["properties"] = _sans_valeurs_de_carte(fiche, listes.get(etape, set()))
        etapes[etape] = {"outils": sortie}
    return {"variantes": variantes_, "etapes": etapes}
