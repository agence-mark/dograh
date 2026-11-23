"""[.mark] Module Restauration, lot 26, M30 : la CONNAISSANCE PAR SUJETS que l'outil ``infos_pratiques`` du connecteur ``service`` lit (un document par sujet).

Un sujet (horaires, accès, paiement, contact…) est un document texte de l'organisation, en mode « document entier » (lu tel quel, aucune recherche
approchée). Nommé ``sujet-<sujet>.txt`` : écrire un sujet deux fois met le même document à jour (idempotent). Aucun stockage de fichiers : le texte
va directement en base, ce qui marche aussi sur une instance sans stockage. Tout est filtré par l'organisation de l'appelant ; jamais un document d'une
autre organisation ni un document qui n'est pas un sujet.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from api.db import db_client

PREFIXE = "sujet-"
SUFFIXE = ".txt"
SUJET = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
TEXTE_MAX = 20_000
LIMITE = 1000


class SujetRefuse(Exception):
    pass


def nom_du_document(sujet: str) -> str:
    if not SUJET.match(sujet or ""):
        raise SujetRefuse("A subject is lowercase letters, digits, dashes or underscores (40 at most).")
    return f"{PREFIXE}{sujet}{SUFFIXE}"


def _sujet(document: Any) -> dict[str, Any] | None:
    nom = document.filename or ""
    if not (nom.startswith(PREFIXE) and nom.endswith(SUFFIXE)):
        return None
    return {"sujet": nom[len(PREFIXE) : -len(SUFFIXE)], "document_uuid": str(document.document_uuid)}


async def lister(organization_id: int) -> list[dict[str, Any]]:
    """Les sujets de CETTE organisation, par ordre alphabétique."""
    documents = await db_client.get_documents_for_organization(organization_id, limit=LIMITE)
    return sorted((s for s in map(_sujet, documents) if s), key=lambda s: s["sujet"])


async def ecrire(organization_id: int, user_id: int, sujet: str, texte: str) -> dict[str, Any]:
    """Crée le document du sujet, ou remplace son texte. Rend ``{sujet, document_uuid, taille, cree}`` : ``document_uuid`` est ce que le réglage
    ``sujets`` de l'outil ``infos_pratiques`` attend."""
    nom = nom_du_document(sujet)
    texte = (texte or "").strip()
    if not texte or len(texte) > TEXTE_MAX:
        raise SujetRefuse(f"The text of a subject has between 1 and {TEXTE_MAX} characters.")
    octets = texte.encode("utf-8")
    existant = next((d for d in await db_client.get_documents_for_organization(organization_id, limit=LIMITE) if d.filename == nom), None)
    cree = existant is None
    document = existant or await db_client.create_document(
        organization_id=organization_id, created_by=user_id, filename=nom, file_size_bytes=len(octets),
        file_hash=hashlib.sha256(octets).hexdigest(), mime_type="text/plain", retrieval_mode="full_document",
    )
    await db_client.update_document_full_text(document.id, texte)
    await db_client.update_document_status(document.id, "completed")
    return {"sujet": sujet, "document_uuid": str(document.document_uuid), "taille": len(octets), "cree": cree}
