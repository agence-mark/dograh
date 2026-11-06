"""[.mark] U10 / point 7 : ce que la base de connaissances doit au portail du client.

* ``cle_stockage_valide`` : un fichier envoyé pour une organisation se range sous ``knowledge_base/{organisation}/``.
  Sans ce contrôle, un compte pourrait rattacher le fichier d'une AUTRE organisation (la clé vient du corps de la requête).
* ``remplacer_fichier`` : un PDF ou un Word se remplace par une nouvelle version SOUS LE MÊME document (même
  identifiant, donc les agents qui le consultent le gardent). Les agents lisent l'ancienne version jusqu'à ce que
  la nouvelle soit lue avec succès (l'ingestion ne remplace le texte et les morceaux qu'à la réussite).
* ``calculer_utilisation`` : « utilisé par », calculé sur la version PUBLIÉE des agents, jamais déclaré (comme les objets, D118).
"""

from __future__ import annotations

import posixpath

from loguru import logger

from api.db import db_client
from api.schemas.objets_agent import AgentUtilisateur
from api.services.gen_ai.documents_locaux import MESSAGE_FORMAT_REFUSE, format_accepte
from api.services.knowledge_base_content import enqueue_document_processing


class RemplacementRefuse(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def cle_stockage_valide(s3_key: str, organization_id: int) -> bool:
    """La clé est `knowledge_base/{organisation}/{document}/{fichier}`, sous le dossier de CETTE organisation."""
    if not isinstance(s3_key, str) or "\\" in s3_key or "\x00" in s3_key:
        return False
    if posixpath.normpath(s3_key) != s3_key:
        return False
    morceaux = s3_key.split("/")
    return (
        len(morceaux) == 4
        and morceaux[0] == "knowledge_base"
        and morceaux[1] == str(organization_id)
        and bool(morceaux[2])
        and bool(morceaux[3])
    )


def agents_qui_consultent(uuids: list[str], agents: list[tuple[int, str, str]]) -> dict[str, list[AgentUtilisateur]]:
    """Pur : ``agents`` = (id, nom, tous les textes publiés). Un agent consulte un document quand son identifiant
    figure dans sa version publiée. Dans l'ordre des agents."""
    return {u: [AgentUtilisateur(id=i, nom=nom) for i, nom, texte in agents if u in texte] for u in uuids}


async def calculer_utilisation(organization_id: int, uuids: list[str]) -> dict[str, list[AgentUtilisateur]]:
    from api.services.objets_agent.utilisation import _agents_publies

    return agents_qui_consultent(uuids, await _agents_publies(organization_id))


async def remplacer_fichier(document, s3_key: str, organization_id: int, created_by_provider_id: str):
    """Le document, en attente de lecture de son nouveau fichier. ``RemplacementRefuse`` (code HTTP) sinon."""
    if not cle_stockage_valide(s3_key, organization_id):
        raise RemplacementRefuse(422, "Invalid file location.")
    filename = s3_key.split("/")[-1]
    if not format_accepte(filename):
        raise RemplacementRefuse(422, MESSAGE_FORMAT_REFUSE)
    pris = await db_client.claim_document_for_file_replacement(
        document_uuid=document.document_uuid,
        organization_id=organization_id,
        filename=filename,
        s3_key=s3_key,
    )
    if pris is None:
        raise RemplacementRefuse(409, "This document is still processing. Try again once it finishes.")
    claimed, previous = pris
    try:
        await enqueue_document_processing(
            document_id=claimed.id,
            s3_key=s3_key,
            organization_id=organization_id,
            created_by_provider_id=created_by_provider_id,
            retrieval_mode=claimed.retrieval_mode,
        )
    except Exception as erreur:  # noqa: BLE001 -- l'ancienne version reste servie
        logger.error(f"[knowledge_base] Remplacement non mis en file pour {claimed.document_uuid}: {erreur!r}")
        await db_client.restore_document_after_failed_replacement(claimed.id, organization_id, previous)
        raise RemplacementRefuse(500, "Failed to queue the new file.") from None
    return claimed
