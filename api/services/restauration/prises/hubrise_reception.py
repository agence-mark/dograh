"""[.mark] Module Restauration, lot 9 : la RÉCEPTION des messages signés de HubRise, et leur traitement hors de la requête.

La route (``routes/restauration_caisse.py``) ne fait que : lire le corps brut, vérifier la signature ``X-HubRise-Hmac-SHA256`` (HMAC-SHA256 du corps brut avec
le secret de notre application, comparaison à TEMPS CONSTANT), mettre le message en file et répondre, bien avant les 20 secondes de HubRise. Le traitement est une
tâche de fond (``traiter_le_message``) :

- le point de vente retrouve son organisation et son établissement par le lien de la base de Dograh ; un point de vente INCONNU est journalisé et jamais traité ;
- un message déjà vu (même identifiant) est ignoré : rejoué, il n'a aucun effet double ; un traitement qui ÉCHOUE est oublié pour que la nouvelle tentative le
  traite (jamais un message perdu en silence) ;
- tout ce qui s'écrit passe par la base de l'établissement retrouvé : le message d'un établissement n'écrit jamais chez un autre.

Messages traités : ``order`` (statut de NOTRE commande par le chemin fermé ; l'heure changée par la caisse), ``catalog.update`` (carte relue), ``inventory.patch``
(ruptures relues), ``location.update`` (état du restaurant relu). La commande est RELUE chez la caisse par son identifiant : le message ne porte pas de
confiance, seulement un signal.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from loguru import logger

from api.db import db_client
from api.db.bases_clients import connexion as base_client
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commande import TRANSITIONS
from api.services.base_client import rattachement
from api.services.restauration import flux
from api.services.restauration.prises.envoi import STATUT_DE_L_ETAPE
from api.services.restauration.prises.prise import ContexteDePrise, prise_de_l_etablissement
from api.services.restauration.synchro_caisse import appliquer_l_etat, appliquer_les_ruptures, code_d_erreur, dire_la_liaison, importer_la_caisse

FOURNISSEUR = "hubrise"
NOM_TACHE = "traiter_message_hubrise"
TAILLE_MAX_OCTETS = 256 * 1024
TENTATIVES_MAX = 5
ATTENTE_ENTRE_TENTATIVES_S = 30


def signature_valide(corps: bytes, signature: str | None, secret: str) -> bool:
    """HMAC-SHA256 du corps BRUT (hexadécimal) comparé à temps constant. Une signature absente ou mal formée est fausse."""
    if not signature or not isinstance(signature, str):
        return False
    attendue = hmac.new(secret.encode("utf-8"), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendue.encode("ascii"), signature.strip().lower().encode("utf-8", "replace"))


def lire_le_message(corps: bytes) -> dict[str, Any] | None:
    """Le message décodé, ou ``None`` s'il n'a ni identifiant, ni point de vente, ni type (rien à traiter)."""
    try:
        message = json.loads(corps)
    except ValueError:
        return None
    if not isinstance(message, dict) or not all(isinstance(message.get(c), str) and message[c] for c in ("id", "resource_type", "event_type")):
        return None
    if not isinstance(message.get("location_id"), str) or not message["location_id"]:
        return None
    return message


async def mettre_en_file(message: dict[str, Any], enqueue=None) -> None:
    """Met le message en file (un seul travail par identifiant de message : HubRise qui le renvoie ne le double pas)."""
    if enqueue is None:
        from api.tasks.arq import enqueue_job

        enqueue = enqueue_job
    await enqueue(NOM_TACHE, message, _job_id=f"hubrise-{message['id']}"[:200])


async def _retrouver(message: dict[str, Any]):
    """``(organization_id, nom_base, etablissement_id)`` du point de vente du message, ou ``None`` (inconnu, journalisé)."""
    lie = await db_client.retrouver_le_point_de_vente(FOURNISSEUR, message["location_id"])
    if lie is None:
        logger.warning("[.mark] HubRise message for an unknown point of sale: ignored")
        return None
    nom_base = await rattachement.nom_de_la_base(lie["organization_id"])
    if not nom_base:
        logger.warning(f"[.mark] HubRise message: organization {lie['organization_id']} has no client database")
        return None
    return lie["organization_id"], nom_base, lie["etablissement_cle"]


async def _commande(connexion, organization_id: int, etablissement_id: int, prise, ref: str) -> str:
    lue = await prise.relire_la_commande(ref)
    numero = lue.get("numero")
    actuelle = await liaison_db.etat_de_la_commande(connexion, etablissement_id, numero) if numero else None
    if actuelle is None:
        actuelle = await _par_ref(connexion, etablissement_id, ref)
    if actuelle is None:
        return "commande_de_la_caisse"  # créée dans la caisse : pas une commande de l'agent (hors de ce lot)
    numero = actuelle["numero"]
    await liaison_db.poser_ref_fournisseur(connexion, etablissement_id, numero, ref)
    vers = STATUT_DE_L_ETAPE.get(lue["etape"])
    effet = "inchange"
    if vers and vers != actuelle["statut"]:
        if vers in TRANSITIONS.get(actuelle["statut"], frozenset()):
            pas = await restauration.changer_statut(connexion, etablissement_id, numero, actuelle["statut"], vers, "caisse")
            if pas.statut == "OK":
                await flux.emettre(organization_id, etablissement_id, "commande.statut", {"numero": numero, "de": actuelle["statut"], "vers": vers, "source": "caisse"})
                effet = "statut"
        # sinon : un message en retard (la commande est déjà plus loin) ou un pas interdit : jamais un retour en arrière
    return effet


async def _par_ref(connexion, etablissement_id: int, ref: str) -> dict | None:
    numero = await liaison_db.commande_par_ref_fournisseur(connexion, etablissement_id, ref)
    return await liaison_db.etat_de_la_commande(connexion, etablissement_id, numero) if numero else None


async def _traiter(message: dict[str, Any], connexion, organization_id: int, etablissement_id: int, nom_base: str, transport) -> str:
    contexte = ContexteDePrise(connexion, organization_id, etablissement_id, nom_base, transport)
    prise = await prise_de_l_etablissement(contexte)
    type_ = f"{message['resource_type']}.{message['event_type']}"
    if message["resource_type"] == "order" and message["event_type"] in ("create", "update"):
        ref = message.get("order_id")
        return await _commande(connexion, organization_id, etablissement_id, prise, ref) if isinstance(ref, str) and ref else "sans_commande"
    if type_ == "catalog.update":
        bilan = await importer_la_caisse(prise, connexion, organization_id, etablissement_id)
        return "erreur" if bilan["erreur"] else "carte"
    if type_ == "inventory.patch":
        return f"ruptures:{await appliquer_les_ruptures(connexion, organization_id, etablissement_id, await prise.lire_ruptures(), complet=True)}"
    if type_ == "location.update":
        etat = await prise.lire_etat()
        return "etat" if etat is not None and await appliquer_l_etat(connexion, organization_id, etablissement_id, etat) else "etat_inchange"
    return "ignore"  # un type auquel nous ne sommes pas abonnés : jamais une erreur


async def traiter_le_message(ctx: dict | None, message: dict[str, Any], *, transport=None) -> dict[str, str]:
    """La tâche de fond (arq). Rejouable sans effet double ; un échec est oublié puis REPRIS (``Retry``), jamais perdu."""
    retrouve = await _retrouver(message)
    if retrouve is None:
        return {"statut": "point_de_vente_inconnu"}
    organization_id, nom_base, cle = retrouve
    connexion = await base_client.connecter(nom_base)
    try:
        etablissement_id = await liaison_db.site_par_cle(connexion, cle)
        if etablissement_id is None:
            logger.warning(f"[.mark] HubRise message: establishment key unknown in the database of organization {organization_id}")
            return {"statut": "etablissement_inconnu"}
        type_ = f"{message['resource_type']}.{message['event_type']}"
        if not await liaison_db.noter_le_message(connexion, FOURNISSEUR, message["id"], etablissement_id, type_):
            return {"statut": "deja_vu"}
        try:
            resultat = await _traiter(message, connexion, organization_id, etablissement_id, nom_base, transport)
        except Exception as erreur:  # noqa: BLE001 -- R1 : ce n'est pas perdu : oublié pour la reprise, la liaison le dit
            await liaison_db.oublier_le_message(connexion, FOURNISSEUR, message["id"])
            code = code_d_erreur(erreur)
            logger.warning(f"[.mark] HubRise message {type_} failed for establishment {etablissement_id}: {type(erreur).__name__} ({code})")
            if code != "jeton_refuse":
                await dire_la_liaison(connexion, organization_id, etablissement_id, "erreur", code)
            _reprendre(ctx, erreur)
            return {"statut": "echec", "code": code}
        await liaison_db.marquer_le_message_traite(connexion, FOURNISSEUR, message["id"])
        return {"statut": "traite", "effet": resultat}
    finally:
        await connexion.close()


def _reprendre(ctx: dict | None, erreur: BaseException) -> None:
    """Dans arq, une nouvelle tentative espacée ; hors arq (tests), rien."""
    if not ctx or code_d_erreur(erreur) == "jeton_refuse":
        return
    essai = int(ctx.get("job_try", 1))
    if essai < TENTATIVES_MAX:
        from arq import Retry

        raise Retry(defer=ATTENTE_ENTRE_TENTATIVES_S * essai)
