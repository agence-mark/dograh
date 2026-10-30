"""[.mark] Bibliothèque : qui écrit. Tout le monde lit ; seuls les membres de l'organisation .mark écrivent (B9, Q4).

L'appartenance se juge sur la PERSONNE (``user.id``), pas sur l'organisation qu'elle a choisie à l'écran :
un membre de .mark qui travaille dans l'organisation d'un client écrit toujours dans la bibliothèque.
"""

from __future__ import annotations

from api.db import db_client
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import organisation_bibliotheque


async def est_membre_de_l_equipe(user) -> bool:
    org = organisation_bibliotheque()
    if org is None or getattr(user, "id", None) is None:
        return False
    return bool(await db_client.is_user_member_of_organization(user.id, org))


async def exiger_l_equipe(user) -> None:
    """403 pour qui n'est pas de l'équipe .mark ; 503 si la bibliothèque n'est pas réglée."""
    if organisation_bibliotheque() is None:
        raise ErreurBibliotheque("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)
    if not await est_membre_de_l_equipe(user):
        raise ErreurBibliotheque("Only members of the .mark organization write in the library.", 403)


def nom_de_l_auteur(user) -> str:
    """Le nom écrit dans l'historique : l'identifiant du compte, jamais un nom ni une adresse (convention du fork)."""
    from api.services.base_client.rattachement import auteur_de

    return auteur_de(user)
