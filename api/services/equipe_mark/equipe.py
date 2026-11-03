"""[.mark] L'équipe .mark : rôles, membres, invitations, profil. La logique ; les routes sont dans ``routes/equipe_mark.py``.

* **Invitation** : adresse + rôle, jeton à usage unique valable 48 h. Le jeton n'est JAMAIS écrit en base, seulement
  son empreinte SHA-256 ; il n'existe en clair que dans le lien rendu à l'invitant (et le mail, s'il part).
* **Mail** : par le serveur de mail déjà réglé de l'installation s'il existe ; sinon le lien est affiché pour être
  copié. Jamais d'envoi par un service payant ni par un service que l'installation n'a pas réglé.
* **Dernier administrateur** : impossible à retirer ou à rétrograder (verrouillé en base).
* **Mot de passe** : 12 caractères au moins.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from loguru import logger

from api.constants import UI_APP_URL
from api.db import db_client
from api.services.equipe_mark.espaces import synchroniser_appartenances
from api.services.equipe_mark.permissions import PERMISSIONS, permissions_valides
from api.utils.auth import create_jwt_token, hash_password, verify_password

DUREE_INVITATION = timedelta(hours=48)
MOT_DE_PASSE_MIN = 12
CLE_PROFIL = "MARK_PROFIL"
_COURRIEL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErreurEquipe(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


def empreinte_du_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def _propre(texte: str | None, maximum: int = 120) -> str:
    return " ".join("".join(c for c in (texte or "") if c.isprintable()).split())[:maximum]


def verifier_mot_de_passe(mot_de_passe: str) -> None:
    if len(mot_de_passe or "") < MOT_DE_PASSE_MIN:
        raise ErreurEquipe(422, f"The password must have at least {MOT_DE_PASSE_MIN} characters")


# ---------------------------------------------------------------------- rôles
def _normaliser_role(nom, permissions, organisations, labo_ouvert, tous_les_clients) -> tuple[str, list[str], list[int]]:
    nom = _propre(nom, 80)
    if not nom:
        raise ErreurEquipe(422, "A role needs a name")
    try:
        permissions = permissions_valides(permissions)
    except ValueError as erreur:
        raise ErreurEquipe(422, str(erreur)) from None
    return nom, permissions, sorted(set(organisations))


async def _organisations_existantes(ids: list[int]) -> None:
    connues = {i for i, _ in await db_client.lister_organisations()}
    inconnues = [i for i in ids if i not in connues]
    if inconnues:
        raise ErreurEquipe(422, f"Unknown organization: {inconnues[0]}")


async def _resynchroniser_les_membres(role_id: int) -> None:
    for user_id in await db_client.lister_utilisateurs_du_role(role_id):
        await synchroniser_appartenances(SimpleNamespace(id=user_id, selected_organization_id=None))


async def creer_role(nom, permissions, organisations, labo_ouvert, tous_les_clients) -> int:
    nom, permissions, organisations = _normaliser_role(nom, permissions, organisations, labo_ouvert, tous_les_clients)
    await _organisations_existantes(organisations)
    if await db_client.role_par_nom(nom):
        raise ErreurEquipe(409, "A role with this name already exists")
    return await db_client.creer_role(
        nom=nom,
        labo_ouvert=labo_ouvert,
        tous_les_clients=tous_les_clients,
        permissions=permissions,
        organisations=[] if tous_les_clients else organisations,
    )


async def modifier_role(role_id, nom, permissions, organisations, labo_ouvert, tous_les_clients) -> None:
    role = await db_client.obtenir_role(role_id)
    if role is None:
        raise ErreurEquipe(404, "Role not found")
    if role["fixe"]:
        raise ErreurEquipe(403, "The Administrator role cannot be changed")
    nom, permissions, organisations = _normaliser_role(nom, permissions, organisations, labo_ouvert, tous_les_clients)
    await _organisations_existantes(organisations)
    autre = await db_client.role_par_nom(nom)
    if autre and autre["id"] != role_id:
        raise ErreurEquipe(409, "A role with this name already exists")
    await db_client.modifier_role(
        role_id,
        nom=nom,
        labo_ouvert=labo_ouvert,
        tous_les_clients=tous_les_clients,
        permissions=permissions,
        organisations=[] if tous_les_clients else organisations,
    )
    # Ce que le rôle ouvre a changé : les membres rejoignent ou quittent les espaces en conséquence.
    await _resynchroniser_les_membres(role_id)


async def supprimer_role(role_id: int) -> None:
    role = await db_client.obtenir_role(role_id)
    if role is None:
        raise ErreurEquipe(404, "Role not found")
    if role["fixe"]:
        raise ErreurEquipe(403, "The Administrator role cannot be deleted")
    if role["membres"]:
        raise ErreurEquipe(409, "This role still has members: change their role first")
    await db_client.supprimer_role(role_id)


# ---------------------------------------------------------------------- membres
async def changer_role_du_membre(user_id: int, role_id: int | None) -> None:
    if role_id is not None and await db_client.obtenir_role(role_id) is None:
        raise ErreurEquipe(404, "Role not found")
    resultat = await db_client.changer_role_protege(user_id, role_id)
    if resultat == "inconnu":
        raise ErreurEquipe(404, "Member not found")
    if resultat == "dernier_administrateur":
        raise ErreurEquipe(409, "The last administrator cannot be removed or demoted")
    if role_id is not None:
        await synchroniser_appartenances(SimpleNamespace(id=user_id, selected_organization_id=None))


# ---------------------------------------------------------------------- invitations
def lien_d_invitation(jeton: str) -> str:
    return f"{UI_APP_URL.rstrip('/')}/invitation?jeton={jeton}"


async def inviter(auteur, email: str, role_id: int) -> dict:
    email = (email or "").strip().lower()
    if not _COURRIEL.match(email) or len(email) > 320:
        raise ErreurEquipe(422, "Invalid email address")
    role = await db_client.obtenir_role(role_id)
    if role is None:
        raise ErreurEquipe(404, "Role not found")
    deja = await db_client.get_user_by_email(email)
    if deja is not None:
        raise ErreurEquipe(409, "An account already exists with this email address")
    jeton = secrets.token_urlsafe(32)
    expire_le = datetime.now(UTC) + DUREE_INVITATION
    invitation_id = await db_client.creer_invitation(
        email=email,
        role_id=role_id,
        empreinte_jeton=empreinte_du_jeton(jeton),
        cree_par=getattr(auteur, "id", None),
        expire_le=expire_le,
    )
    lien = lien_d_invitation(jeton)
    return {
        "id": invitation_id,
        "email": email,
        "role_nom": role["nom"],
        "expire_le": expire_le,
        "lien": lien,
        "envoye": await _envoyer_le_mail(email, lien),
    }


async def _envoyer_le_mail(email: str, lien: str) -> bool:
    """Vrai si le serveur de mail DE L'INSTALLATION a pris le message ; faux sinon (le lien s'affiche alors à l'écran)."""
    from api.services.apres_appel.installation import lire_installation
    from api.services.apres_appel.mail import MailImpossible, envoyer

    try:
        organisation_mark, reglages = await lire_installation()
        if organisation_mark is None or not reglages.smtp.configure:
            return False
        await envoyer(
            reglages.smtp,
            organisation_mark,
            [email],
            "Invitation à rejoindre l'équipe .mark",
            "Vous êtes invité à rejoindre l'équipe .mark.\n\n"
            f"Ouvrez ce lien pour créer votre compte (valable 48 heures, à usage unique) :\n{lien}\n",
        )
        return True
    except MailImpossible as erreur:
        logger.warning(f"Invitation : le mail n'est pas parti ({erreur}) ; le lien s'affiche à l'écran")
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Invitation : envoi du mail impossible ; le lien s'affiche à l'écran")
        return False


async def lire_invitation(jeton: str) -> dict:
    """L'adresse et le rôle d'une invitation encore valable ; 410 pour inconnue, périmée ou déjà utilisée (même réponse)."""
    ligne = await db_client.invitation_par_empreinte(empreinte_du_jeton(jeton or ""))
    if (
        ligne is None
        or ligne["utilisee_le"] is not None
        or ligne["expire_le"] <= datetime.now(UTC)
    ):
        raise ErreurEquipe(410, "This invitation is no longer valid")
    role = await db_client.obtenir_role(ligne["role_id"])
    return {"email": ligne["email"], "role_nom": role["nom"] if role else ""}


async def accepter_invitation(jeton: str, prenom: str, nom: str, mot_de_passe: str) -> tuple[object, str]:
    """Crée le compte invité (rôle de l'invitation, espaces que ce rôle ouvre) ; rend (compte, jeton de session)."""
    verifier_mot_de_passe(mot_de_passe)
    prenom, nom = _propre(prenom), _propre(nom)
    if not prenom or not nom:
        raise ErreurEquipe(422, "First name and last name are required")
    invitation = await lire_invitation(jeton)
    if await db_client.get_user_by_email(invitation["email"]) is not None:
        raise ErreurEquipe(409, "An account already exists with this email address")
    # Le jeton se consomme ICI, atomiquement : deux acceptations simultanées, une seule passe.
    consommee = await db_client.consommer_invitation(empreinte_du_jeton(jeton))
    if consommee is None:
        raise ErreurEquipe(410, "This invitation is no longer valid")
    user = await db_client.create_user_with_email(
        email=consommee["email"], password_hash=hash_password(mot_de_passe)
    )
    await db_client.poser_membre(user.id, consommee["role_id"], prenom=prenom, nom=nom)
    await synchroniser_appartenances(SimpleNamespace(id=user.id, selected_organization_id=None))
    organisations = await db_client.organisations_du_compte(user.id)
    if organisations:
        await db_client.update_user_selected_organization(user.id, organisations[0])
        user.selected_organization_id = organisations[0]
    return user, create_jwt_token(user.id, user.email)


# ---------------------------------------------------------------------- profil
async def mon_profil(user) -> dict:
    acces = await db_client.acces_du_compte(user.id)
    membre = await db_client.obtenir_membre(user.id)
    preferences = await db_client.get_user_configuration_value(user.id, CLE_PROFIL) or {}
    return {
        "id": user.id,
        "email": user.email,
        "prenom": (membre or {}).get("prenom"),
        "nom": (membre or {}).get("nom"),
        "role": acces.role_nom if acces else None,
        "permissions": sorted(acces.permissions) if acces else [],
        "langue": preferences.get("langue") if preferences.get("langue") in ("fr", "en") else "fr",
        "alertes_mail": bool(preferences.get("alertes_mail", True)),
    }


async def modifier_profil(user, *, prenom, nom, langue, alertes_mail, champs: set[str]) -> dict:
    if {"prenom", "nom"} & champs:
        membre = await db_client.obtenir_membre(user.id)
        if membre is None:
            raise ErreurEquipe(403, "Only members of the .mark team have a name to change")
        await db_client.poser_membre(
            user.id,
            membre["role_id"],
            prenom=_propre(prenom) if "prenom" in champs else None,
            nom=_propre(nom) if "nom" in champs else None,
        )
    if {"langue", "alertes_mail"} & champs:
        actuel = await db_client.get_user_configuration_value(user.id, CLE_PROFIL) or {}
        if "langue" in champs:
            if langue not in ("fr", "en"):
                raise ErreurEquipe(422, "Language must be fr or en")
            actuel["langue"] = langue
        if "alertes_mail" in champs:
            actuel["alertes_mail"] = bool(alertes_mail)
        await db_client.upsert_user_configuration_value(user.id, CLE_PROFIL, actuel)
    return await mon_profil(user)


async def changer_mot_de_passe(user, actuel: str, nouveau: str) -> None:
    verifier_mot_de_passe(nouveau)
    complet = await db_client.get_user_by_id(user.id)
    if not complet or not complet.password_hash or not verify_password(actuel or "", complet.password_hash):
        raise ErreurEquipe(403, "The current password is wrong")
    await db_client.poser_mot_de_passe(user.id, hash_password(nouveau))


def catalogue_des_permissions() -> list[dict]:
    return [{"cle": cle, "groupe": groupe, "libelle": libelle} for cle, (groupe, libelle) in PERMISSIONS.items()]
