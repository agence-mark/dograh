"""[.mark] Builder, lots 5 et 6 : remplit les points d'entrée ``prompt_controler``, ``outil_essayer``, ``tests_creer`` et ``tests_rejouer``.

Les points d'entrée sont posés par ``points_d_entree.py`` (lot 1). Ce module REMPLACE leur fonction, leur schéma et leur
description dans le registre (``disponible=True``) sans toucher à ce fichier ni au moteur : les deux portes (écran et MCP) lisent le
registre après l'import de ce paquet.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel, Field

from api.services.builder.actions.registre import REGISTRE, Contexte, ErreurAction


class _Controle(BaseModel):
    workflow_id: int | None = None


class _EssaiOutil(BaseModel):
    workflow_id: int | None = None
    outil: str = Field(min_length=1, description="Name of the tool to try.")
    donnees_test: dict[str, Any] = Field(default_factory=dict, description="Test data to call it with, never a real person's data.")


class _TestACreer(BaseModel):
    workflow_id: int | None = None
    nom: str = Field(min_length=1, max_length=200)
    scenario: str | None = Field(
        default=None,
        max_length=4000,
        description="A free conversation: what the simulated caller wants. Leave empty for a test built from one reply.",
    )
    criteres: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Criteria judged by the code: etape, outil, texte_present, texte_absent, issue, appel_clos_par_l_agent, "
            "mecanique_dite, merci_en_tete, coordonnees_prises, sans_redite, sans_rigidite."
        ),
    )
    obligatoire: bool = Field(default=False, description="A required test blocks the publication when it fails.")
    run_id: int | None = Field(default=None, description="Build the test from a call (with rang).")
    rang: int | None = Field(default=None, ge=1, description="The faulty reply of the person in that call, counted from 1.")
    replique: str | None = Field(default=None, description="By hand: the person's reply, with historique.")
    historique: list[dict[str, str]] = Field(default_factory=list)
    personnage: str | None = Field(default=None, description="Slug of a caller character of the library.")
    ouverture: str | None = Field(default=None, description="The caller's first words.")
    tours_max: int | None = Field(default=None, ge=2, le=40)
    dossier: str = ""
    origine: str = Field(default="manuel", description="client | recette | code | manuel | fiche")
    description: str = ""
    questions_juge: list[str] = Field(default_factory=list, description="Questions for the non-blocking judge.")


class _TestsARejouer(BaseModel):
    workflow_id: int | None = None
    tests: list[str] | None = Field(
        default=None, description="Test names; empty replays the whole suite (only a whole replay can verify the agent)."
    )
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


async def _tests_creer(contexte: Contexte, parametres: BaseModel) -> dict[str, Any]:
    """Lot 6 : créer un test (depuis un appel, à la main, ou écrit par le builder depuis la fiche). Données rendues fictives."""
    from api.services.builder.actions._commun import agent_verifie
    from api.services.builder.tests_agent import creation, stockage
    from api.services.tests_rejouables.modele import ErreurTestRejouable

    identifiant = await agent_verifie(contexte, parametres.workflow_id)
    try:
        test = await creation.creer(
            contexte.organisation_id,
            identifiant,
            nom=parametres.nom,
            criteres=parametres.criteres,
            origine=parametres.origine,
            obligatoire=parametres.obligatoire,
            dossier=parametres.dossier,
            description=parametres.description,
            auteur=getattr(contexte.user, "email", None),
            run_id=parametres.run_id,
            rang=parametres.rang,
            replique=parametres.replique,
            historique=parametres.historique,
            scenario=parametres.scenario,
            personnage=parametres.personnage,
            ouverture=parametres.ouverture,
            tours_max=parametres.tours_max,
            questions_juge=parametres.questions_juge,
        )
    except (stockage.ErreurTest, ErreurTestRejouable) as erreur:
        raise ErreurAction(str(erreur)) from None
    resume = creation.en_resume(test)
    return {
        "ok": True,
        "test": resume,
        "elements": [{"statut": "ok", "message": f"Test « {test['nom']} » created ({resume['genre']}, personal data replaced)."}],
        "carte": {"type": "tests", "cree": resume},
    }


async def _tests_rejouer(contexte: Contexte, parametres: BaseModel) -> dict[str, Any]:
    """Lot 6 : N × 3, verdict par le code, suite complète rejouée (B38). Forme : ``{"ok", "echecs", "total", ...}``."""
    from api.services.builder.actions._commun import agent_de_l_organisation
    from api.services.builder.tests_agent import execution
    from api.services.tests_rejouables.modele import ErreurTestRejouable

    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    try:
        return await execution.rejouer_la_suite(contexte.user, workflow, noms=parametres.tests, repetitions=parametres.repetitions)
    except ErreurTestRejouable as erreur:
        raise ErreurAction(str(erreur)) from None


def _remplir(nom: str, *, description: str, parametres: type[BaseModel], fonction, ecriture: bool, groupe: str, lot: str) -> None:
    REGISTRE[nom] = dataclasses.replace(
        REGISTRE[nom],
        description=description,
        parametres=parametres,
        fonction=fonction,
        ecriture=ecriture,
        disponible=True,
        groupe=groupe,
        extras={"lot": lot},
    )


_remplir(
    "prompt_controler",
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
    lot="lot 5",
)
_remplir(
    "outil_essayer",
    description=(
        "Try an HTTP tool with FICTITIOUS test data (e-mails in .test, phone numbers in the reserved ranges) before calling it "
        "connected. Connected only on a valid JSON answer; otherwise not connected and the step falls back to demander_un_rappel. "
        "A tool whose method is not GET writes at the client's: it returns a « trial to validate » card (tool, method, address, "
        "test data) and calls nothing until a person runs the trial. Never announce a tool as connected without this proof."
    ),
    parametres=_EssaiOutil,
    fonction=_outil_essayer,
    ecriture=True,
    groupe="controle",
    lot="lot 5",
)
_remplir(
    "tests_creer",
    description=(
        "Create a test of the agent: from a reply of a real call (run_id + rang), by hand (replique + historique), or a free "
        "conversation written from the client sheet (scenario + personnage). The criteria are judged by the code. Personal data is "
        "replaced by fake data before anything is kept. A required test (obligatoire) blocks the publication when it fails."
    ),
    parametres=_TestACreer,
    fonction=_tests_creer,
    ecriture=True,
    groupe="tests",
    lot="lot 6",
)
_remplir(
    "tests_rejouer",
    description=(
        "Replay the agent's tests N times (3 by default), the verdict is given by the code. Result: ok (true only if the WHOLE suite "
        "was replayed and passes at 100 %), echecs (each with the faulty reply, the reason and a diagnosis: agent, test or execution), "
        "total. A required test that fails is enough to refuse. After any correction, replay the whole suite before saying verified."
    ),
    parametres=_TestsARejouer,
    fonction=_tests_rejouer,
    ecriture=True,
    groupe="tests",
    lot="lot 6",
)
