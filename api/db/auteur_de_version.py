"""[.mark] Clôture, É36 : l'auteur d'une version d'agent, posé par la requête et lu à la création de la version.

Un seul point d'entrée côté requête : ``get_user`` (la session ou la clé d'API), jamais le corps d'une requête. Les chemins qui créent
une version (écran, builder, MCP, fusion, retour en arrière) lisent ``courant()`` dans la couche de base ; le builder se déclare avec
``en_tant_que_builder`` le temps de son geste (une personne qui accepte ses changements se dit avec ``accepte_par``). Sans requête
(tâche de fond, script), personne : les colonnes restent vides et l'écran met « – ».
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, NamedTuple

PERSONNE = "personne"
BUILDER = "builder"
CLE_API = "cle_api"
LIBELLE_MAX = 160


class Auteur(NamedTuple):
    type: str | None = None
    user_id: int | None = None
    libelle: str | None = None
    accepte_par: int | None = None


_COURANT: ContextVar[Auteur | None] = ContextVar("mark_auteur_de_version", default=None)


def courant() -> Auteur:
    return _COURANT.get() or Auteur()


def _borne(texte: Any) -> str | None:
    propre = " ".join("".join(c for c in str(texte or "") if c.isprintable()).split())
    return propre[:LIBELLE_MAX] or None


def poser(auteur: Auteur | None) -> None:
    _COURANT.set(auteur)


def depuis_l_utilisateur(user: Any) -> Auteur:
    """Qui écrit, d'après le compte authentifié : la clé d'API (son nom, ou l'auteur du portail) ou la personne connectée."""
    identifiant = getattr(user, "id", None)
    if getattr(user, "par_cle_api", False):
        libelle = getattr(user, "mark_auteur", None) or getattr(user, "cle_api_nom", None)
        return Auteur(CLE_API, identifiant, _borne(libelle))
    return Auteur(PERSONNE, identifiant)


def poser_depuis(user: Any) -> None:
    poser(depuis_l_utilisateur(user))


@contextmanager
def en_tant_que_builder(accepte_par: int | None = None) -> Iterator[None]:
    """Le temps d'un geste du builder : ce qu'il écrit est « Builder ». ``accepte_par`` : la personne qui a accepté le changement."""
    jeton = _COURANT.set(Auteur(BUILDER, None, None, accepte_par))
    try:
        yield
    finally:
        _COURANT.reset(jeton)


def colonnes(auteur: Auteur | None = None) -> dict[str, Any]:
    """Les valeurs des colonnes de ``workflow_definitions`` pour cet auteur (le courant par défaut)."""
    a = auteur if auteur is not None else courant()
    return {
        "auteur_type": a.type,
        "auteur_user_id": a.user_id,
        "auteur_libelle": a.libelle,
        "accepte_par_user_id": a.accepte_par,
    }
