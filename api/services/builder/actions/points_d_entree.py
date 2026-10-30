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

from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer, pas_encore_disponible


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


async def _prompt_controler(contexte: Contexte, parametres: BaseModel) -> dict[str, Any]:
    """Lot 5 : le contrôle du prompt par le code (Q12). ``ok`` vrai = aucun défaut bloquant."""
    from api.services.builder.actions._commun import agent_de_l_organisation
    from api.services.builder.controle.service import controler_l_agent

    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    return await controler_l_agent(workflow, contexte.organisation_id)


async def _outil_essayer(contexte: Contexte, parametres: BaseModel) -> dict[str, Any]:
    """Lot 5 : l'essai d'un outil avec des données de test (Q11). « branché » seulement sur une réponse valide."""
    from api.services.builder.actions._commun import agent_verifie
    from api.services.builder.essai_outil import ErreurEssai, essayer

    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        return await essayer(contexte.organisation_id, identifiant, parametres.outil, parametres.donnees_test)
    except ErreurEssai as erreur:
        raise ErreurAction(str(erreur)) from None


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


enregistrer(
    Action(
        nom="prompt_controler",
        description=(
            "Check the agent's prompts by code (generic rules, no business vocabulary). Blocking defects stop the publication: "
            "a rule written twice or contradicted, a tool name in the text, an example value, a tool without a failure instruction, "
            "a step without a way to the end, a prompt too long, a persona with a rule of conduct, a sentence the code already says, "
            "an unknown {{variable}}. Warnings: a writing tool without a two-step read-back, persona gender vs voice, a fact written "
            "in the prompt while an object holds it. Result: ok, bloquants, avertissements, elements."
        ),
        parametres=_Controle,
        fonction=_prompt_controler,
        ecriture=False,
        groupe="controle",
        extras={"lot": "lot 5"},
    )
)
enregistrer(
    Action(
        nom="outil_essayer",
        description=(
            "Try an HTTP tool with FICTITIOUS test data (e-mails in .test, phone numbers in the reserved ranges) before calling it "
            "connected. Connected only on a valid JSON answer; otherwise not connected and the step falls back to demander_un_rappel. "
            "Never announce a tool as connected without this proof."
        ),
        parametres=_EssaiOutil,
        fonction=_outil_essayer,
        ecriture=True,
        groupe="controle",
        extras={"lot": "lot 5"},
    )
)
