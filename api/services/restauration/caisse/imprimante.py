"""[.mark] Module Restauration, lot 10 : poser l'imprimante d'un établissement et retrouver l'établissement d'une interrogation.

Le JETON de l'imprimante est ``<organisation>-<secret>`` : l'organisation (un numéro, pas un secret) dit dans quelle base chercher ; le secret (256 bits, aléatoire) n'est
JAMAIS gardé en clair, seulement son empreinte SHA-256. Il se voit UNE fois, dans l'adresse à saisir dans l'imprimante ; le perdre = en poser un nouveau (l'ancien cesse de marcher).
Une imprimante peut se poser à CÔTÉ d'une caisse déjà reliée : elle sert alors de SECOURS (premier échelon de l'échelle de Pierre quand l'envoi à la caisse échoue,
``secours.py``) et la liaison de la caisse reste celle de l'établissement. Sans autre caisse, elle devient la liaison de l'établissement (la prise qui reçoit les commandes).
"""

from __future__ import annotations

import re
import secrets

from loguru import logger

from api.constants import BACKEND_API_ENDPOINT
from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commun import Connexion
from api.services.base_client import rattachement
from api.services.restauration.caisse.prises.prise_imprimante import NOM

CHEMIN = "/api/v1/restauration/imprimante/"
_JETON = re.compile(r"^([0-9]{1,12})-([A-Za-z0-9_-]{20,80})$")


def adresse_de_l_imprimante(jeton: str) -> str:
    return BACKEND_API_ENDPOINT.rstrip("/") + CHEMIN + jeton


async def poser_l_imprimante(
    connexion: Connexion, organization_id: int, etablissement_id: int, *, nom: str | None = None, mode_planifiee: str = "differe", minutes_avant: int = 20
) -> str:
    """Pose (ou remplace) l'imprimante de CET établissement ; rend le jeton, à ne montrer qu'une fois."""
    if mode_planifiee not in ("differe", "immediat") or not 0 <= minutes_avant <= 240:
        raise ValueError("mode_planifiee ou minutes_avant hors des bornes")
    existante = await liaison_db.liaison(connexion, etablissement_id)
    jeton = f"{organization_id}-{secrets.token_urlsafe(32)}"
    await liaison_db.poser_imprimante(connexion, etablissement_id, jeton, nom=nom, mode_planifiee=mode_planifiee, minutes_avant=minutes_avant)
    if existante is None:  # sans autre caisse : l'imprimante EST la liaison ; avec une caisse : elle reste en secours
        await liaison_db.poser_liaison(connexion, etablissement_id, NOM, None, "ok", source="mark", auteur="imprimante")
    return jeton


async def retrouver(jeton: str):
    """``(connexion, organization_id, imprimante)`` d'un jeton valide, ou ``None`` (mal formé, organisation sans base, jeton inconnu : toujours la même réponse, jamais un
    moyen de sonder). La connexion est ouverte : l'appelant la ferme."""
    trouve = _JETON.match(jeton or "")
    if not trouve:
        return None
    organization_id = int(trouve.group(1))
    nom_base = await rattachement.nom_de_la_base(organization_id)
    if not nom_base:
        return None
    try:
        connexion = await base_client.connecter(nom_base)
    except Exception:  # une base injoignable : l'imprimante réessaiera à sa prochaine interrogation, la panne se voit au journal
        logger.exception("[.mark] Printer poll: the client database is unreachable")
        return None
    imprimante = await liaison_db.imprimante_par_jeton(connexion, jeton)
    if imprimante is None:
        await connexion.close()
        return None
    return connexion, organization_id, imprimante
