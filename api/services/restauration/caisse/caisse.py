"""[.mark] Module Restauration, lot 9 : ce que le portail demande à la liaison avec la caisse (fiche de liaison, rupture poussée à la caisse).

Générique : seule la FICHE de la prise est lue, jamais un nom de fournisseur. Rien de ce qui part vers la caisse ne bloque le classeur : une rupture est d'abord
posée chez nous (l'agent la respecte aussitôt), puis poussée ; si la caisse ne répond pas, la liaison le dit (code fermé) et la réponse dit
``poussee_a_la_caisse: false`` : jamais un échec silencieux (R1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commun import Connexion
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.caisse.prises.capacites import Capacites
from api.services.restauration.caisse.prises.prise import (
    ContexteDePrise,
    capacites_de,
    prise_de_l_etablissement,
)
from api.services.restauration.caisse.synchro_caisse import code_d_erreur, dire_la_liaison

PRISE_SANS_CAISSE = "portail"
PRISES_QUI_SE_BRANCHENT = ("hubrise", "imprimante")  # la liste fermée de l'écran « Caisse » (F8)


def capacites_rendues(capacites: Capacites) -> dict[str, Any]:
    """La fiche pour l'écran : listes triées, sans l'adresse des fournisseurs (liste fermée côté serveur seulement)."""
    return {
        "carte": capacites.carte, "carte_notifiee": capacites.carte_notifiee, "ruptures": capacites.ruptures,
        "ruptures_posees_par_nous": capacites.ruptures_posees_par_nous, "etat_restaurant": capacites.etat_restaurant,
        "temps_preparation": capacites.temps_preparation, "horaires": capacites.horaires, "commande_non_payee": capacites.commande_non_payee,
        "controle_avant_creation": capacites.controle_avant_creation, "annulation": capacites.annulation, "etapes": sorted(capacites.etapes),
        "anti_doublon": capacites.anti_doublon, "notifications": capacites.notifications, "clients_lus": capacites.clients_lus,
        "remises_lues": capacites.remises_lues, "represente": sorted(capacites.represente), "limites": list(capacites.limites),
    }


async def fiche_de_liaison(connexion: Connexion, etablissement_id: int) -> dict[str, Any]:
    """``GET …/caisse`` : prise, capacités, état, dernière erreur, dernière synchro, état que la caisse porte. Sans liaison : le portail, état ``aucune``."""
    liaison = await liaison_db.liaison(connexion, etablissement_id)
    nom = liaison["prise"] if liaison else PRISE_SANS_CAISSE
    etat = await restauration.etat_caisse(connexion, etablissement_id)
    return {
        "prise": nom,
        "etat": liaison["etat"] if liaison else "aucune",
        "derniere_erreur": liaison["derniere_erreur"] if liaison else None,
        "derniere_synchro": liaison["derniere_synchro"] if liaison else None,
        "point_de_vente": liaison["point_de_vente"] if liaison else None,
        "mode_passif": liaison["mode_passif"] if liaison else False,
        "derniere_releve": liaison["derniere_releve"] if liaison else None,
        "avertissements": liaison["avertissements"] if liaison else [],
        "etat_caisse": None if etat is None else {k: etat[k] for k in ("mode", "minutes_en_plus", "reprise", "temps_preparation")},
        "capacites": capacites_rendues(capacites_de(nom)),
        "prises": {p: capacites_rendues(capacites_de(p)) for p in PRISES_QUI_SE_BRANCHENT},
    }


async def poser_la_rupture(
    connexion: Connexion, organization_id: int, etablissement_id: int, code_caisse: str, disponible: bool, fin: datetime | None,
    *, nom_base: str | None = None, transport: Any = None
) -> tuple[Any, bool]:
    """Pose (ou lève) la rupture dans le classeur, émet ``rupture.changee``, puis la pousse à la caisse si la prise sait la poser.
    Rend ``(Resultat du classeur, poussee_a_la_caisse)``. Un échec de la caisse laisse la rupture posée chez nous."""
    resultat = await restauration.poser_rupture(connexion, etablissement_id, code_caisse, disponible, fin, "portail")
    if resultat.statut != "OK":
        return resultat, False
    donnees: dict[str, Any] = {"code_caisse": code_caisse, "disponible": disponible}
    if fin is not None and not disponible:
        donnees["fin"] = fin
    await flux.emettre(organization_id, etablissement_id, "rupture.changee", donnees)
    if await liaison_db.liaison(connexion, etablissement_id) is None:
        return resultat, False  # pas de caisse : le classeur est maître, il n'y a rien à pousser
    prise = await prise_de_l_etablissement(ContexteDePrise(connexion, organization_id, etablissement_id, nom_base, transport))
    if not prise.capacites.ruptures_posees_par_nous:
        return resultat, False
    try:
        await prise.poser_rupture(code_caisse, disponible, fin)
    except Exception as erreur:  # noqa: BLE001 -- R1 : la caisse qui ne répond pas se voit sur la liaison, la rupture reste posée chez nous
        code = code_d_erreur(erreur)
        logger.warning(f"[.mark] Stock-out not pushed to the till for establishment {etablissement_id}: {type(erreur).__name__}")
        if code != "jeton_refuse":  # un jeton refusé a déjà passé la liaison à « rompue » (la prise l'a dit)
            await dire_la_liaison(connexion, organization_id, etablissement_id, "erreur", code)
        return resultat, False
    return resultat, True


async def resynchroniser(
    connexion: Connexion, organization_id: int, etablissement_id: int, *, nom_base: str | None = None, transport: Any = None
) -> dict[str, Any] | None:
    """Lot 13 (M6) : relit la caisse (carte, ruptures, état, selon la fiche de la prise), comme au branchement. ``None`` : aucune caisse n'est reliée.
    Rend ``{carte, ruptures, etat, erreur}`` (``erreur`` : un code fermé ou ``None``) ; la liaison dit elle-même si l'import a réussi (R1, jamais silencieux)."""
    from api.services.restauration.caisse.synchro_caisse import importer_la_caisse

    if await liaison_db.liaison(connexion, etablissement_id) is None:
        return None
    prise = await prise_de_l_etablissement(ContexteDePrise(connexion, organization_id, etablissement_id, nom_base, transport))
    return await importer_la_caisse(prise, connexion, organization_id, etablissement_id)


async def debrancher(connexion: Connexion, organization_id: int, etablissement_id: int) -> bool:
    """Lot 13 (M6) : coupe la liaison de CET établissement avec sa caisse. Le point de vente est libéré, le jeton du coffre est désactivé, la liaison et l'état
    que la caisse portait sont retirés : le classeur redevient maître. La carte, les ruptures et les commandes déjà lues sont GARDÉES (rien n'est supprimé).
    Faux : aucune caisse n'était reliée. Émet ``caisse.liaison`` (état ``rompue`` : l'écran dit « débranchée »)."""
    from api.db import db_client

    liaison = await liaison_db.liaison(connexion, etablissement_id)
    if liaison is None:
        return False
    reference = await liaison_db.acces(connexion, etablissement_id)
    cle = await liaison_db.cle_du_site(connexion, etablissement_id)
    if cle is not None:
        await db_client.delier_le_point_de_vente(organization_id, liaison["prise"], cle)
    await liaison_db.supprimer_la_liaison(connexion, etablissement_id)
    await liaison_db.retirer_l_etat_de_la_caisse(connexion, etablissement_id)
    if reference:
        await db_client.delete_credential(reference, organization_id)  # désactivé (jamais lu ailleurs que par la prise de cet établissement)
    await flux.emettre(organization_id, etablissement_id, "caisse.liaison", {"etat": "rompue"})
    return True


async def commande_d_essai(connexion: Connexion, organization_id: int, etablissement_id: int, *, nom_base: str | None = None, transport: Any = None) -> dict[str, Any]:
    """Lot 13 (F8) : une commande d'essai d'un article, envoyée à la caisse de DÉMO du Labo (interne, aucun tiers). Contre une vraie caisse : refusée
    (``vraie_caisse``), l'essai réel se fait au lot 19. Rend ``{statut, numero_court, envoi}`` ou ``{statut: "refusee", raison}`` : jamais d'exception."""
    from api.db import db_client
    from api.db.bases_clients.restauration_carte import carte_du_restaurant
    from api.services.restauration.caisse.caisse_demo import garde
    from api.services.restauration.caisse.prises.envoi import declencheur_vers_la_prise

    reference = await liaison_db.acces(connexion, etablissement_id)
    credential = await db_client.get_credential_by_uuid(reference, organization_id) if reference else None
    donnees = (credential.credential_data or {}) if credential else {}
    if not donnees.get("demo"):
        return {"statut": "refusee", "raison": "vraie_caisse" if reference else "aucune_caisse"}
    if not await garde.caisse_de_demo_permise(organization_id):
        return {"statut": "refusee", "raison": "demo_non_permise"}
    carte = await carte_du_restaurant(connexion, etablissement_id)
    code = next((d["code_caisse"] for p in carte["produits"] for d in p.get("declinaisons", []) if d.get("code_caisse") and d.get("disponible", True)), None)
    if code is None:
        return {"statut": "refusee", "raison": "carte_vide"}
    prise = await prise_de_l_etablissement(ContexteDePrise(connexion, organization_id, etablissement_id, nom_base, transport))
    brouillon = {
        "mode": "emporter", "client": {"telephone": "+33600000000", "prenom": "Essai"}, "lignes": [{"code_caisse": code, "quantite": 1}],
        "paiement": {"moyens": [], "reste_par_moyen": {"carte": 0}}, "note": "Commande d'essai du portail", "cree_par": "portail",
    }
    envoi = declencheur_vers_la_prise(connexion, etablissement_id, prise)
    r = await restauration.enregistrer_commande(connexion, etablissement_id, brouillon, "essai-portail", declencher_envoi=envoi)
    if r.statut == "INCOMPLETE" and r.manque == "paiement" and isinstance(r.faits.get("total"), int):  # le total est chiffré par le classeur : on règle exactement ce montant
        brouillon["paiement"] = {"moyens": [], "reste_par_moyen": {"carte": r.faits["total"]}}
        r = await restauration.enregistrer_commande(connexion, etablissement_id, brouillon, "essai-portail", declencher_envoi=envoi)
    if r.statut != "ENREGISTREE":
        return {"statut": "refusee", "raison": str(r.faits.get("raison") or r.statut).lower()}
    etat = await liaison_db.etat_de_la_commande(connexion, etablissement_id, str(r.faits.get("numero")))
    return {"statut": "enregistree", "numero_court": r.faits.get("numero_court"), "envoi": etat["statut"] if etat else None}
