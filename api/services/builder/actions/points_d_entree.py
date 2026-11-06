"""[.mark] Builder : les POINTS D'ENTRÉE des actions que les lots suivants remplissent (signature, schéma, renvoi).

Le moteur et le serveur MCP les connaissent déjà : un lot qui les implémente remplace seulement ``fonction`` (et
met ``disponible=True``) dans le registre, sans toucher au moteur. Tant qu'ils ne sont pas remplis, ils rendent
« pas encore disponible » : le cerveau ne doit alors RIEN annoncer comme fait (« rien n'est annoncé sans preuve »).

| Action                       | Lot | Ce que le lot y met                                                        |
|------------------------------|-----|----------------------------------------------------------------------------|
| ``fiche_tirer_des_documents``| 3   | extraction du texte des dossiers déposés, fiche sourcée, trous en questions |
| ``prompt_controler``         | 5   | contrôle du prompt par le code (bloquant)                                  |
| ``outil_essayer``            | 5   | appel d'un outil avec des données de test, « branché » seulement si valide |
| ``tests_creer``              | 6   | création d'un test (réplique, main, depuis la fiche), données fictives      |
| ``tests_rejouer``            | 6   | N × 3, verdict par le code, suite complète rejouée (B38)                   |
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.services.builder.actions.registre import Action, Contexte, enregistrer, pas_encore_disponible


class _Documents(BaseModel):
    workflow_id: int | None = None
    documents: list[str] = Field(default_factory=list, description="Identifiers of the deposited files and addresses to read.")


class _Controle(BaseModel):
    workflow_id: int | None = None


class _EssaiOutil(BaseModel):
    workflow_id: int | None = None
    outil: str = Field(min_length=1, description="Name of the tool to try.")
    donnees_test: dict[str, Any] = Field(default_factory=dict, description="Test data to call it with, never a real person's data.")


class _TestACreer(BaseModel):
    workflow_id: int | None = None
    nom: str = Field(min_length=1, max_length=200)
    scenario: str = Field(min_length=1, max_length=4000)
    criteres: list[dict[str, Any]] = Field(default_factory=list)
    obligatoire: bool = False


class _TestsARejouer(BaseModel):
    workflow_id: int | None = None
    tests: list[str] | None = Field(default=None, description="Test names; empty replays the whole suite.")
    repetitions: int = Field(default=3, ge=1, le=10)


def _point_d_entree(nom: str, lot: str):
    async def fonction(contexte: Contexte, parametres: BaseModel) -> dict[str, Any]:
        return pas_encore_disponible(nom, lot)

    return fonction


for _nom, _lot, _description, _parametres, _ecriture in (
    (
        "fiche_tirer_des_documents",
        "lot 3",
        "Read the deposited documents and propose the client sheet with a source per line. Not available yet.",
        _Documents,
        True,
    ),
    ("prompt_controler", "lot 5", "Check the agent's prompts by code (blocking defects). Not available yet.", _Controle, False),
    ("outil_essayer", "lot 5", "Try a tool with test data before calling it connected. Not available yet.", _EssaiOutil, True),
    ("tests_creer", "lot 6", "Create a replayable test. Not available yet.", _TestACreer, True),
    ("tests_rejouer", "lot 6", "Replay tests N times and give the verdict by code. Not available yet.", _TestsARejouer, True),
):
    enregistrer(
        Action(
            nom=_nom,
            description=_description,
            parametres=_parametres,
            fonction=_point_d_entree(_nom, _lot),
            ecriture=_ecriture,
            disponible=False,
            groupe="a_venir",
            extras={"lot": _lot},
        )
    )
