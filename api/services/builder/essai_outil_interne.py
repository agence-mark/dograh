"""[.mark] Builder, lot 26 (M31) : l'essai d'un outil INTERNE (``commande``, ``reservation``, ``service``) avant de le déclarer « branché ».

Un outil interne ne passe pas par le relais HTTP : il est joué dans le fork, contre le classeur de l'établissement. L'essai le joue par le MÊME chemin que
l'appel (``connectors.execution.executer``), avec les réglages de l'agent, un numéro d'appelant fictif et des données de test (jamais de vraies).

⛔ Jamais une vraie caisse : un geste qui ÉCRIT (enregistrer une commande, une réservation, un message) ne part que si l'établissement n'a pas de caisse
(la commande reste au portail) ou si sa liaison est celle de la CAISSE DE DÉMO. Sinon : « non essayé », rien n'a été appelé, l'étape ne promet rien.

« Branché » = l'outil a répondu et n'est pas tombé en panne (``INDISPONIBLE``, repli, erreur). Un refus normal (« quelle taille ? », un créneau complet) prouve
que l'outil répond : branché. ⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder.essai_outil import _ranger, _verdict

CONNECTEURS_ESSAYABLES = ("commande", "reservation", "service")
APPELANT_FICTIF = "+33639980001"  # plage ARCEP réservée à la fiction (06 39 98 xx xx)
PRISES_SANS_CAISSE = ("portail",)


def connecteur_interne_essayable(outil: Any) -> bool:
    from api.services.integrations.connectors.outil import config_de, connecteur_interne

    c = connecteur_interne(outil)
    return c is not None and c.nom in CONNECTEURS_ESSAYABLES and bool(config_de(outil).get("action"))


async def _sans_vraie_caisse(organisation_id: int) -> bool:
    """Vrai quand écrire ne touche aucune vraie caisse : l'établissement sert la commande au portail, ou sa liaison est la caisse de démo. Au doute : faux."""
    from api.db.bases_clients import restauration_liaison as liaison_db
    from api.db.bases_clients.connexion import connecter
    from api.db.bases_clients.restauration_reglage import prise_de_l_etablissement
    from api.services.base_client.rattachement import nom_de_la_base
    from api.services.restauration.appel import identifiant_de_l_etablissement

    nom_base = await nom_de_la_base(organisation_id)
    if not nom_base:
        return False
    connexion = await connecter(nom_base)
    try:
        etablissement = await identifiant_de_l_etablissement(connexion, None)
        prise = await prise_de_l_etablissement(connexion, etablissement)
        if prise in PRISES_SANS_CAISSE:
            return True
        reference = await liaison_db.acces(connexion, etablissement)
        credential = await db_client.get_credential_by_uuid(reference, organisation_id) if reference else None
        return bool(credential and (credential.credential_data or {}).get("demo"))
    except Exception as erreur:  # noqa: BLE001 -- au doute, on n'écrit pas
        logger.warning(f"[builder] essai interne : la caisse n'a pas pu être reconnue ({type(erreur).__name__})")
        return False
    finally:
        await connexion.close()


async def _configurations_de_l_agent(organisation_id: int, workflow_id: int | None) -> dict[str, Any]:
    if workflow_id is None:
        return {}
    workflow = await db_client.get_workflow(workflow_id, organization_id=organisation_id)
    return dict(getattr(workflow, "workflow_configurations", None) or {})


async def essayer_un_outil_interne(organisation_id: int, workflow_id: int | None, outil: Any, donnees_test: dict[str, Any]) -> dict[str, Any]:
    from api.services.integrations.connectors.catalogue import trouver
    from api.services.integrations.connectors.execution import executer
    from api.services.integrations.connectors.outil import config_de

    config = config_de(outil)
    trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
    if trouve is None:
        return await _rendre(organisation_id, workflow_id, _verdict(outil.name, False, "The action of this tool does not exist.", None, 0))
    _, action = trouve
    if action.ecrit and not await _sans_vraie_caisse(organisation_id):
        raison = "This trial would write at the client's: it only runs on an establishment without a till or on the demo till."
        return await _rendre(organisation_id, workflow_id, _verdict(outil.name, False, f"Not tried: {raison}", None, 0))
    configurations = await _configurations_de_l_agent(organisation_id, workflow_id)
    appel = {"caller_number": APPELANT_FICTIF}
    debut = time.perf_counter()
    try:
        resultat = await executer(organisation_id, config, donnees_test, {}, APPELANT_FICTIF, None, appel=appel, run_id=None, configurations=configurations)
    except Exception as erreur:  # noqa: BLE001 -- un outil qui plante = non branché, jamais une panne du builder
        logger.warning(f"[builder] essai de l'outil interne {outil.name} en échec : {type(erreur).__name__}")
        return await _rendre(organisation_id, workflow_id, _verdict(outil.name, False, f"The tool failed ({type(erreur).__name__}).", None, 0))
    duree_ms = round((time.perf_counter() - debut) * 1000)
    donnees = resultat.donnees if isinstance(resultat.donnees, dict) else {}
    statut = str(donnees.get("statut") or "")
    if resultat.statut != "ok":
        verdict = _verdict(outil.name, False, f"The tool did not answer ({resultat.message or resultat.statut}).", None, duree_ms)
    elif statut == "INDISPONIBLE" or not statut:
        verdict = _verdict(outil.name, False, "The tool answered « unavailable »: the establishment's record book is not reachable or the module is off for this agent.", None, duree_ms)
    else:
        verdict = _verdict(outil.name, True, f"The tool answered ({statut}).", None, duree_ms, {"statut": statut, "suggestion": donnees.get("suggestion")})
    return await _rendre(organisation_id, workflow_id, verdict)


async def _rendre(organisation_id: int, workflow_id: int | None, verdict: dict[str, Any]) -> dict[str, Any]:
    await _ranger(organisation_id, workflow_id, verdict)
    return verdict

