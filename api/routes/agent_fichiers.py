"""[.mark] Partie 3, N3b : l'agent en fichiers lisibles, et leur import dans son brouillon (``services/export_agent/fichiers.py``).

- ``GET  /agent-fichiers/{agent}/export``            les fichiers de l'agent en JSON (``?format=zip`` : l'archive à télécharger) ;
- ``POST /agent-fichiers/{agent}/import``            un dossier de fichiers : l'aperçu des différences (défaut), ou l'import dans le brouillon
  (``appliquer`` à vrai). Jamais en ligne ; rejoué, le même dossier ne change rien.

L'organisation vient de la session ou de la clé, jamais du corps ; un agent d'une autre organisation est un 404. Lire = tout membre ;
importer = ``agents.modifier`` (la clé du client la porte). Aucun secret n'est exporté ni importé.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.db.protection_principale import PrincipaleProtegee
from api.services import modifications_live as live
from api.services.auth.depends import get_user_with_selected_organization
from api.services.export_agent import fichiers

router = APIRouter(prefix="/agent-fichiers", tags=["agent-fichiers"])


class FichiersExportes(BaseModel):
    agent_id: int
    fichiers: dict[str, str] = Field(description="path -> text, UTF-8")
    secrets_retires: int = 0


class ImportDeFichiers(BaseModel):
    fichiers: dict[str, str] = Field(max_length=fichiers.FICHIERS_MAX, description="The files of an exported agent: path -> text.")
    appliquer: bool = Field(default=False, description="False (default): only the preview of the differences. True: import into the draft.")


class LigneApercu(BaseModel):
    fichier: str
    effet: str = Field(description="ajoute, modifie, inchange or retire (present in the agent, absent from the folder: kept)")
    detail: str | None = None


class ResultatImport(BaseModel):
    agent_id: int
    applique: bool
    fichiers: list[LigneApercu]
    tests_ecrits: int = 0
    outils_epingles: int = 0
    avertissements: list[dict[str, Any]] = Field(default_factory=list)


async def _agent_ou_404(user: UserModel, workflow_id: int) -> None:
    if await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")


def _http(erreur: fichiers.ErreurFichiers) -> HTTPException:
    return HTTPException(status_code=erreur.statut, detail=str(erreur))


@router.get("/{workflow_id}/export", response_model=FichiersExportes)
async def exporter_en_fichiers(
    workflow_id: int,
    format: str = Query("json", pattern="^(json|zip)$"),
    contenus: str | None = Query(None, max_length=120, description="Comma list: graphe, prompts, reglages, outils, blocs, tests (default: all)."),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    await _agent_ou_404(user, workflow_id)
    try:
        rendu = await fichiers.exporter(user.selected_organization_id, workflow_id)
        rendu = {**rendu, "fichiers": fichiers.filtrer(rendu["fichiers"], [c for c in contenus.split(",") if c] if contenus else None)}
    except fichiers.ErreurFichiers as erreur:
        raise _http(erreur) from None
    if format == "zip":
        return Response(
            content=fichiers.en_zip(rendu["fichiers"]),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="agent-{workflow_id}.zip"'},
        )
    return rendu


@router.post("/{workflow_id}/import", response_model=ResultatImport)
async def importer_des_fichiers(
    workflow_id: int, corps: ImportDeFichiers, user: UserModel = Depends(get_user_with_selected_organization)
):
    await _agent_ou_404(user, workflow_id)
    organisation = user.selected_organization_id
    try:
        if not corps.appliquer:
            fichiers.verifier_les_fichiers(corps.fichiers)
            apercu = await fichiers.previsualiser(organisation, workflow_id, corps.fichiers)
            return {"agent_id": workflow_id, "applique": False, "fichiers": apercu}
        rendu = await fichiers.importer(user, organisation, workflow_id, corps.fichiers)
        # U12 : l'écran ouvert sur cet agent se relit seul (jamais le contenu : seulement l'objet et le nom du geste).
        await live.noter(organisation, f"agent:{workflow_id}", "import_fichiers", source="ecran", auteur=live.auteur_de(user))
        return rendu
    except fichiers.ErreurFichiers as erreur:
        raise _http(erreur) from None
    except PrincipaleProtegee as erreur:
        raise HTTPException(status_code=409, detail=str(erreur)) from None
