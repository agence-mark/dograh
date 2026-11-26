"""[.mark] Lot 8a : les crochets des modules, l'UNIQUE endroit par où le moteur d'appel (voix et clavier) parle aux modules.

Le moteur ne nomme aucun module : il joue « les modules allumés ». Chaque module déclare ses crochets au registre (``registre.Module``) ; ce fichier sait seulement
lesquels sont déclarés, si le module est allumé pour l'agent (même règle que les étiquettes : ``interrupteur_des_etiquettes`` ou le sien) et les résoudre.

- ``au_demarrage()`` : une fois par processus qui joue des appels (l'API, l'ouvrier). Pas de garde : un métier qui ne s'inscrit pas doit se voir (une allergie non branchée
  ne se tait jamais), l'erreur remonte ;
- ``au_decroche(Decroche)`` : trois moments, dans l'ordre de l'appel : ``CONTEXTE`` (avant le moteur : le contexte de l'appel s'enrichit), ``CANAL`` (le canal d'événements
  de l'appel se compose), ``MONTAGE`` (le moteur existe : le chargement de l'appel part ; au clavier, le premier tour l'attend, borné) ;
- ``fin_du_tour(FinDeTour)`` (clavier) et ``fin_de_l_appel(FinDeLAppel)`` (voix, ``finally`` ; clavier, fin de la partie) : sans effet double si rejoués ;
- ``issue_de_fin(fiche)`` : l'issue « abandonnée » que les connecteurs déclarent (``Connecteur.issue_de_fin``), une seule par appel, selon ``ORDRE_DES_ISSUES``.

⛔ Un crochet qui lève ne coupe jamais l'appel : l'échec est écrit au journal standard (le module, le crochet, la pile ; notre message ne porte jamais de valeur d'appel).
"""

from __future__ import annotations

import importlib
import inspect
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from api.services.modules.etat import interrupteur_allume
from api.services.modules.registre import MODULES, PAR_CODE, Module

CROCHETS = ("au_demarrage", "au_decroche", "fin_du_tour", "fin_de_l_appel")
CONTEXTE, CANAL, MONTAGE = "contexte", "canal", "montage"

# Deux connecteurs qui déclarent chacun une issue « abandonnée » dans le même appel : le premier de cette liste la donne (un connecteur qui n'y est pas passe après,
# par son nom). Une issue déjà posée dans l'appel n'est jamais écrasée : chaque connecteur la lit sur la fiche.
ORDRE_DES_ISSUES = ("commande", "reservation")


@dataclass
class Decroche:
    """Ce que les modules lisent et écrivent au décroché ; ``moment`` dit où en est le moteur. Les crochets modifient l'objet (``contexte``, ``canal``)."""

    moment: str
    contexte: dict
    run_configs: Mapping | None
    organization_id: int | None
    workflow_id: int | None
    run_id: int
    reglages_annonce: Any = None
    direction: Any = None
    cle_de_l_etablissement: Any = None  # l'établissement servi par l'appel (``None`` : inconnu)
    canal: Callable | None = None  # le canal d'événements de l'appel (``CANAL``)
    fiche: dict | None = None  # la fiche de l'appel (``MONTAGE``)
    au_clavier: bool = False


@dataclass(frozen=True)
class FinDeTour:
    run_id: Any
    termine: bool  # l'appel est terminé, ou le tour a levé


@dataclass(frozen=True)
class FinDeLAppel:
    run_id: Any
    fiche: dict | None  # la fiche de l'appel telle qu'elle finit ; ``None`` : illisible (un montage tombé)
    organization_id: int | None = None
    run_configs: Mapping | None = None  # informatif : ``fin_de_l_appel`` n'écarte aucun module (la fermeture ne dépend d'aucun interrupteur)
    au_clavier: bool = False


def resoudre(chemin: str) -> Callable:
    nom_du_module, _, nom = chemin.partition(":")
    return getattr(importlib.import_module(nom_du_module), nom)


def est_allume(module: Module, run_configs: Mapping | None) -> bool:
    """``run_configs`` ``None`` (inconnu) : allumé. Sinon l'interrupteur du module, ou de celui dont il suit l'interrupteur."""
    if run_configs is None:
        return True
    return interrupteur_allume(PAR_CODE.get(module.interrupteur_des_etiquettes or module.code, module), run_configs)


def crochets_resolus(nom: str, run_configs: Mapping | None = None) -> list[tuple[Module, Callable]]:
    """Les fonctions du crochet ``nom`` des modules allumés, dans l'ordre du registre."""
    return [(m, resoudre(chemin)) for m in MODULES if (chemin := getattr(m, nom)) and est_allume(m, run_configs)]


async def _jouer(nom: str, argument: Any, run_configs: Mapping | None) -> None:
    try:
        crochets = crochets_resolus(nom, run_configs)
    except Exception:
        logging.exception(f"[.mark] Hook {nom}: a module hook could not be loaded")  # le journal standard : l'erreur y est écrite avec sa pile ; un crochet qui ne se résout pas ne coupe pas l'appel
        return
    for module, fonction in crochets:
        try:
            resultat = fonction(argument)
            if inspect.isawaitable(resultat):
                await resultat
        except Exception:  # ⛔ un crochet ne coupe jamais l'appel
            logging.exception(f"[.mark] Hook {nom} of module {module.code} failed, the call goes on")


def au_demarrage() -> None:
    """Une fois par processus qui joue des appels. Ne rattrape rien : un métier non inscrit est un défaut qui doit arrêter le démarrage."""
    for module in MODULES:
        if module.au_demarrage:
            resoudre(module.au_demarrage)()


async def au_decroche(decroche: Decroche) -> Decroche:
    await _jouer("au_decroche", decroche, decroche.run_configs)
    return decroche


async def fin_du_tour(fin: FinDeTour) -> None:
    await _jouer("fin_du_tour", fin, None)


async def fin_de_l_appel(fin: FinDeLAppel) -> None:
    # Sans filtre, comme ``fin_du_tour`` : la fin ferme ce que l'appel a ouvert (connexion, direct), quel que soit l'interrupteur d'un module (la réservation ouvre la connexion sans la commande).
    await _jouer("fin_de_l_appel", fin, None)


def issue_de_fin(fiche: Any) -> str | None:
    """L'issue « abandonnée » de cet appel : celle du premier connecteur (``ORDRE_DES_ISSUES``) qui en déclare une pour la fiche, ``None`` sinon. Ne pose rien : l'appelant la range."""
    from api.services.integrations.connectors.catalogue import connecteurs

    rang = {nom: i for i, nom in enumerate(ORDRE_DES_ISSUES)}
    for connecteur in sorted(connecteurs(), key=lambda c: (rang.get(c.nom, len(rang)), c.nom)):
        if connecteur.issue_de_fin is not None and (issue := connecteur.issue_de_fin(fiche)):
            return issue
    return None
