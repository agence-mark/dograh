"""[.mark] Builder, lot 3 (B27) : la base de connaissances de l'agent, PROPOSÉE par le builder, VALIDÉE par une personne.

La fiche dit ce qui décide ; la base dit ce qu'on peut répondre (FAQ, produits, services, informations publiques,
conditions : gros et rarement demandé, B47). Le builder PROPOSE des documents tirés des dossiers déposés et du site ;
une personne les valide (ou les rejette) ; seul un document validé est créé dans la base de connaissances EXISTANTE
du fork (``routes/knowledge_base.py``, ``services/knowledge_base_content.py``), puis rattaché à une étape du brouillon.

Rangement : ``MARK_BUILDER:<agent>:base`` (les propositions et leur état). Le document lui-même vit dans la base du
fork, avec sa vectorisation habituelle.

⛔ **Jamais un tarif, un délai ou une promesse que l'audit ne contient pas.** Le code le tient, pas la bonne foi du
cerveau : chaque proposition cite des extraits qui doivent se retrouver MOT POUR MOT dans le dépôt cité ; tout nombre du
contenu doit figurer dans ces extraits ; un mot de promesse (« gratuit », « garanti »...) du contenu doit y figurer aussi.
Un contenu qui ne passe pas est refusé avec ce qui manque, et rien n'est rangé.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from api.services.builder import stock
from api.services.builder.bibliotheque.modele import maintenant
from api.services.builder.constantes import cle_builder
from api.services.builder.dossiers import depot

PROPOSITIONS_MAX = 30
CONTENU_MAX = 20000
# B27 : sous ce nombre de jetons estimés, le document est lu EN ENTIER par l'agent ; au-delà, par recherche de passages.
SEUIL_DOCUMENT_ENTIER_JETONS = 4000
MODE_DOCUMENT_ENTIER = "full_document"
MODE_PASSAGES = "chunked"

# Des mots qui engagent l'entreprise : permis dans un document de base seulement s'ils viennent de l'audit.
MOTS_DE_PROMESSE = (
    "gratuit", "gratuite", "gratuits", "gratuites", "gratuitement", "garanti", "garantie", "garantis", "garanties",
    "sans frais", "sans engagement", "sans condition", "rembours", "offert", "offerte", "satisfait ou",
    "toujours", "jamais", "systématiquement", "immédiatement", "sous 24", "sous 48", "dans les 24", "dans les 48",
)  # fmt: skip


class ErreurBase(Exception):
    def __init__(self, message: str, code: str = "refus"):
        super().__init__(message)
        self.code = code


class SourceCitee(BaseModel):
    document: str = Field(min_length=1, max_length=500, description="The deposited document (name) or site page (address).")
    page: int | None = Field(default=None, ge=1, description="The page or section number, if known.")
    extrait: str = Field(min_length=8, max_length=600, description="A passage copied WORD FOR WORD from that page.")


def mode_de_lecture(contenu: str) -> str:
    """« Document entier » sous ``SEUIL_DOCUMENT_ENTIER_JETONS`` jetons estimés, « recherche par passages » au-delà."""
    from api.services.gen_ai.documents_locaux import jetons_estimes

    return MODE_DOCUMENT_ENTIER if jetons_estimes(contenu) < SEUIL_DOCUMENT_ENTIER_JETONS else MODE_PASSAGES


class DocumentPropose(BaseModel):
    id: str
    titre: str = Field(min_length=1, max_length=200)
    contenu: str = Field(min_length=1, max_length=CONTENU_MAX)
    sources: list[SourceCitee] = Field(min_length=1, max_length=20)
    mode: Literal["full_document", "chunked"] = MODE_PASSAGES
    etat: Literal["propose", "valide", "rejete"] = "propose"
    propose_par: str = ""
    propose_le: str = ""
    valide_par: str | None = None
    valide_le: str | None = None
    motif_de_rejet: str | None = None
    document_uuid: str | None = None
    rattache_a: list[str] = Field(default_factory=list, description="Step identifiers of the draft this document is attached to.")


# --- la vérification -----------------------------------------------------------------------------------------------


def _normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFKC", texte).casefold()
    texte = texte.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
    return " ".join(texte.split())


_NOMBRE = re.compile(r"\d[\d   .,]*\d|\d")


def _nombres(texte: str) -> set[str]:
    sortie = set()
    for brut in _NOMBRE.findall(texte):
        sortie.add(re.sub(r"[\s  .,]", "", brut))
    return sortie


def _mots_de_promesse(texte: str) -> set[str]:
    bas = _normaliser(texte)
    return {m for m in MOTS_DE_PROMESSE if m in bas}


def verifier(contenu: str, sources: list[SourceCitee], textes: dict[str, dict[int, str]]) -> None:
    """``textes`` : nom du dépôt (casefold) -> {numéro de page: texte}. Lève ``ErreurBase`` avec TOUT ce qui ne va pas."""
    problemes: list[str] = []
    extraits_ok: list[str] = []
    for source in sources:
        pages = textes.get(source.document.casefold())
        if pages is None:
            problemes.append(f"Source « {source.document} » is not a deposited document of this agent.")
            continue
        champ = _normaliser(pages.get(source.page, "")) if source.page else _normaliser(" ".join(pages.values()))
        if source.page and source.page not in pages:
            problemes.append(f"« {source.document} » has no page {source.page}.")
            continue
        if _normaliser(source.extrait) not in champ:
            problemes.append(f"The excerpt « {source.extrait[:60]} » is not found word for word in « {source.document} »" + (f", page {source.page}." if source.page else "."))
            continue
        extraits_ok.append(source.extrait)
    if extraits_ok:
        appuis = " ".join(extraits_ok)
        inconnus = sorted(_nombres(contenu) - _nombres(appuis))
        if inconnus:
            problemes.append(
                f"Number(s) {', '.join(inconnus)} are not in the cited excerpts: never a price, a delay or a figure the audit does not hold."
            )
        promesses = sorted(_mots_de_promesse(contenu) - _mots_de_promesse(appuis))
        if promesses:
            problemes.append(
                f"Commitment word(s) {', '.join(repr(p) for p in promesses)} are not in the cited excerpts: never a promise the audit does not hold."
            )
    if problemes:
        raise ErreurBase(" ".join(problemes), "non_sourcee")


async def textes_deposes(organization_id: int, workflow_id: int) -> dict[str, dict[int, str]]:
    sortie: dict[str, dict[int, str]] = {}
    for dep in await depot.lister(organization_id, workflow_id):
        pages = await depot.pages_de(organization_id, dep)
        if pages:
            sortie[dep["nom"].casefold()] = {p.numero: p.texte for p in pages}
    return sortie


# --- les propositions ----------------------------------------------------------------------------------------------


def cle(workflow_id: int) -> str:
    return cle_builder(workflow_id, "base")


async def lister(organization_id: int, workflow_id: int) -> list[DocumentPropose]:
    brut = await stock.lire(organization_id, cle(workflow_id))
    return [DocumentPropose.model_validate(d) for d in (brut or {}).get("documents") or []]


async def _ecrire(organization_id: int, workflow_id: int, documents: list[DocumentPropose]) -> None:
    await stock.ecrire(organization_id, cle(workflow_id), {"documents": [d.model_dump(mode="json") for d in documents]})


async def proposer(
    organization_id: int, workflow_id: int, titre: str, contenu: str, sources: list[SourceCitee], auteur: str
) -> DocumentPropose:
    """Range une proposition APRÈS vérification. Une proposition du même titre encore « proposé » est remplacée ;
    un document déjà validé ou rejeté ne se réécrit pas (on en propose un autre titre)."""
    verifier(contenu, sources, await textes_deposes(organization_id, workflow_id))
    documents = await lister(organization_id, workflow_id)
    existant = next((d for d in documents if d.titre.casefold() == titre.casefold()), None)
    if existant is not None and existant.etat != "propose":
        raise ErreurBase(f"« {titre} » is already {existant.etat}: propose another title.")
    if existant is None and len(documents) >= PROPOSITIONS_MAX:
        raise ErreurBase(f"At most {PROPOSITIONS_MAX} proposals per agent.")
    nouveau = DocumentPropose(
        id=existant.id if existant else uuid.uuid4().hex[:10],
        titre=titre,
        contenu=contenu,
        sources=sources,
        mode=mode_de_lecture(contenu),
        propose_par=auteur,
        propose_le=maintenant().isoformat(),
    )
    await _ecrire(organization_id, workflow_id, [*(d for d in documents if d is not existant), nouveau])
    return nouveau


def _trouver(documents: list[DocumentPropose], identifiant: str) -> DocumentPropose:
    document = next((d for d in documents if d.id == identifiant), None)
    if document is None:
        raise ErreurBase(f"Unknown proposal: {identifiant!r}.", "introuvable")
    return document


def nom_de_fichier(titre: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode("ascii").lower()
    return (re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-") or "document")[:80] + ".md"


async def creer_le_document_de_base(user: Any, titre: str, contenu: str, mode: str = MODE_PASSAGES) -> str:
    """Crée le document dans la base de connaissances EXISTANTE du fork (stockage, enregistrement, vectorisation en
    tâche de fond) et rend son identifiant. Une couture : les tests la remplacent."""
    from api.db import db_client
    from api.services.knowledge_base_content import enqueue_document_processing
    from api.services.storage import storage_fs

    organisation = user.selected_organization_id
    identifiant = str(uuid.uuid4())
    nom = nom_de_fichier(titre)
    donnees = contenu.encode("utf-8")
    s3_key = f"knowledge_base/{organisation}/{identifiant}/{nom}"
    if not await storage_fs.acreate_file_from_bytes(s3_key, donnees):
        raise ErreurBase("The document could not be stored.", "stockage")
    document = await db_client.create_document(
        organization_id=organisation,
        created_by=user.id,
        filename=nom,
        file_size_bytes=len(donnees),
        file_hash="",
        mime_type="text/markdown",
        custom_metadata={"s3_key": s3_key, "origine": "builder"},
        document_uuid=identifiant,
        retrieval_mode=mode,
    )
    await enqueue_document_processing(
        document_id=document.id,
        s3_key=s3_key,
        organization_id=organisation,
        created_by_provider_id=str(user.provider_id),
        retrieval_mode=mode,
    )
    logger.info(f"[builder] document de base créé pour l'agent (org {organisation})")
    return identifiant


async def valider(user: Any, workflow_id: int, identifiant: str, auteur: str) -> DocumentPropose:
    """LE geste d'une personne : le document entre dans la base de connaissances du fork. Pas d'action du builder."""
    organisation = user.selected_organization_id
    documents = await lister(organisation, workflow_id)
    document = _trouver(documents, identifiant)
    if document.etat == "valide":
        return document
    if document.etat == "rejete":
        raise ErreurBase("This proposal was rejected: propose it again.")
    # Revérifié au moment de valider : un dépôt retiré depuis ne laisse pas passer une proposition sans source.
    verifier(document.contenu, document.sources, await textes_deposes(organisation, workflow_id))
    uuid_ = await creer_le_document_de_base(user, document.titre, document.contenu, document.mode)
    valide = document.model_copy(update={"etat": "valide", "valide_par": auteur, "valide_le": maintenant().isoformat(), "document_uuid": uuid_})
    await _ecrire(organisation, workflow_id, [valide if d.id == identifiant else d for d in documents])
    return valide


async def rejeter(organization_id: int, workflow_id: int, identifiant: str, auteur: str, motif: str | None) -> DocumentPropose:
    documents = await lister(organization_id, workflow_id)
    document = _trouver(documents, identifiant)
    if document.etat == "valide":
        raise ErreurBase("This document is already in the knowledge base: remove it there.")
    rejete = document.model_copy(update={"etat": "rejete", "valide_par": auteur, "valide_le": maintenant().isoformat(), "motif_de_rejet": motif})
    await _ecrire(organization_id, workflow_id, [rejete if d.id == identifiant else d for d in documents])
    return rejete


async def noter_le_rattachement(organization_id: int, workflow_id: int, identifiant: str, noeud: str) -> None:
    documents = await lister(organization_id, workflow_id)
    document = _trouver(documents, identifiant)
    if noeud not in document.rattache_a:
        document = document.model_copy(update={"rattache_a": [*document.rattache_a, noeud]})
    await _ecrire(organization_id, workflow_id, [document if d.id == identifiant else d for d in documents])


async def pour_rattacher(organization_id: int, workflow_id: int, identifiant: str) -> DocumentPropose:
    """Le document à rattacher : VALIDÉ seulement (rien de rattaché sans validation)."""
    document = _trouver(await lister(organization_id, workflow_id), identifiant)
    if document.etat != "valide" or not document.document_uuid:
        raise ErreurBase("Only a document validated by a person is attached: ask for the validation first.", "non_valide")
    return document
