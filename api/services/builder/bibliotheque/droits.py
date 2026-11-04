"""[.mark] Bibliothèque : qui écrit. Tout le monde lit ; seuls les membres de l'organisation .mark écrivent (B9, Q4).

L'appartenance se juge sur la PERSONNE (``user.id``), pas sur l'organisation qu'elle a choisie à l'écran. Écrire DANS LA BIBLIOTHÈQUE
exige en plus d'être dans le Labo (``exiger_l_equipe_au_labo``, U2 quater, E57).
"""

from __future__ import annotations

from api.db import db_client
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import organisation_bibliotheque


async def est_membre_de_l_equipe(user) -> bool:
    """Une clé d'API n'est jamais l'équipe, même créée par un membre (revue serveur B1)."""
    from api.services.equipe_mark.acces import est_par_cle_api

    if est_par_cle_api(user):
        return False
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


async def exiger_l_equipe_au_labo(user) -> None:
    """Écrire DANS LA BIBLIOTHÈQUE : l'équipe .mark, et depuis le Labo seulement (U2 quater, E57).

    Dans l'espace d'un client, le builder lit la bibliothèque et n'y écrit pas : rien ne remonte au Labo sans « Ramener au Labo ».
    Les autres gestes de l'équipe (régler le cerveau, lire les prix) restent ceux de ``exiger_l_equipe`` : le builder d'un client
    prend le cerveau et la clé du Labo."""
    await exiger_l_equipe(user)
    if getattr(user, "selected_organization_id", None) != organisation_bibliotheque():
        raise ErreurBibliotheque("In a client space the library is read-only: write in it from the Labo.", 403)


def nom_de_l_auteur(user) -> str:
    """Le nom écrit dans l'historique : l'identifiant du compte, jamais un nom ni une adresse (convention du fork)."""
    from api.services.base_client.rattachement import auteur_de

    return auteur_de(user)
