"""[.mark] U11 (§ 17) : « prouver avant de publier », pour le builder, Claude Code et l'écran (mêmes fonctions).

* ``publication_controler`` : les contrôles de la fenêtre « Publier » sur le brouillon (lecture, simulation) ;
* ``publication_corriger_la_liste_vocale`` : écrit dans le BROUILLON les corrections ACCEPTÉES (ids choisis), puis rend le
  nouveau contrôle complet ;
* ``attaques_lancer`` / ``attaques_rapport`` / ``attaques_rejouer`` : « Attaquer l'agent » ;
* ``attaques_creer_des_tests`` / ``attaques_envoyer_a_ameliorer`` : ce qu'on fait des attaques qui ont cédé ; ``attaques_importer_le_jeu_public``
  / ``attaques_jeu_public`` : le jeu public fourni par une personne (SE-10).

⛔ Le builder ne publie jamais (``INTERDITES``). Un contrat d'attaque non confirmé ne joue rien. Aucun appel réel : chemin texte des
tests, outils sortants simulés ; le juge est celui des Réglages du Labo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from api.db import db_client
from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.builder.tests_agent import jeu


@dataclass
class Dependances:
    """Les coutures remplaçables en test : le moteur de jeu et le juge (rien n'est dépensé en test)."""

    moteur: Any = None  # () -> Moteur
    juge: Any = None  # async (user, workflow) -> Juge | None


DEPENDANCES = Dependances()


class _Agent(BaseModel):
    workflow_id: int | None = None


class _Corriger(_Agent):
    ids: list[str] = Field(min_length=1, max_length=20, description="The checklist points the person ACCEPTED to fix (ids from publication_controler).")


class _Lancer(_Agent):
    profondeur: str = Field(default="rapide", description="rapide (about 15 probes), standard (35 to 45) or poussee (80 and more).")
    confirme: bool = Field(default=False, description="True only when a person confirmed the scope in the conversation. Without it nothing is probed.")
    modifie_l_environnement: bool = Field(default=False, description="Not available: refused when true.")
    corrige: bool = Field(default=False, description="Not available: the report alone, a person decides the fixes.")
    essais: int | None = Field(default=None, ge=1, le=5, description="Tries to reproduce an attack that got through before it is confirmed (1 to 5).")
    temoin: bool = Field(default=True, description="A harmless witness after each attack, and a check that the judge does not cry wolf.")
    jeu: str = Field(default="catalogue", pattern="^(catalogue|public)$", description="catalogue (15 techniques) or public (the imported public set).")


class _Choix(_Agent):
    ids: list[str] | None = Field(default=None, max_length=50, description="Attack ids of the last report. Empty: the confirmed ones.")


class _Import(BaseModel):
    contenu: str = Field(min_length=1, max_length=12_000_000, description="The CSV of the public set (header with a prompt column).")


async def _brouillon(workflow: Any):
    draft = await db_client.get_draft_version(workflow.id)
    if draft is None:
        raise ErreurAction("There is no draft: the checks read the draft that would be published.", "sans_brouillon")
    return draft


async def _controler(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    from api.services.publication import controles

    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    return {"ok": True, **await controles.evaluer(workflow, await _brouillon(workflow), contexte.organisation_id)}


async def _corriger(contexte: Contexte, p: _Corriger) -> dict[str, Any]:
    from api.services.builder import reglages_agent
    from api.services.publication import controles, liste_vocale

    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    draft = await _brouillon(workflow)
    resultats = await controles.liste_vocale_de(dict(draft.workflow_configurations or {}))
    valeurs = liste_vocale.corrections_acceptees(resultats, p.ids)
    if not valeurs:
        raise ErreurAction("None of these points can be fixed by the code: they are advice or have no equivalent here.", "rien_a_corriger")
    try:
        await reglages_agent.regler(contexte.organisation_id, workflow.id, valeurs)
    except reglages_agent.ErreurReglage as erreur:
        raise ErreurAction(str(erreur), "reglage") from None
    nouveau = await _brouillon(workflow)  # nouveau contrôle COMPLET après la correction
    return {"ok": True, "ecrits": sorted(valeurs), **await controles.evaluer(workflow, nouveau, contexte.organisation_id)}


async def _moteur():
    return DEPENDANCES.moteur() if DEPENDANCES.moteur is not None else jeu.moteur_texte()


async def _juge(contexte: Contexte, workflow: Any):
    if DEPENDANCES.juge is not None:
        return await DEPENDANCES.juge(contexte.user, workflow)
    from api.services.attaques.service import juge_par_cerveau
    from api.services.builder.tests_agent import execution

    cerveaux = await execution.cerveaux_des_tests(contexte.user, workflow)
    return juge_par_cerveau(cerveaux.juge) if cerveaux.juge is not None else None


async def _lancer(contexte: Contexte, p: _Lancer) -> dict[str, Any]:
    from api.services.attaques import catalogue, jeu_public, service
    from api.services.attaques.contrat import Contrat, RefusDuContrat

    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    try:
        contrat = Contrat(
            profondeur=p.profondeur,
            confirme=p.confirme,
            modifie_l_environnement=p.modifie_l_environnement,
            corrige=p.corrige,
            essais=p.essais,
            temoin=p.temoin,
            jeu=p.jeu,
        ).verifier()
    except (RefusDuContrat, ValueError) as erreur:
        raise ErreurAction(str(erreur), "contrat") from None
    try:
        rapport = await service.lancer(workflow, contexte.organisation_id, contrat, moteur=await _moteur(), juge=await _juge(contexte, workflow))
    except (catalogue.JeuIllisible, jeu_public.ImportRefuse) as erreur:
        raise ErreurAction(str(erreur), "jeu") from None
    return {"ok": True, "rapport": rapport}


async def _rapport(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    from api.services.attaques import rapport

    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    lu = await rapport.lire(contexte.organisation_id, workflow.id)
    return {"ok": True, "rapport": lu, "vide": lu is None}


async def _rejouer(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    from api.services.attaques import service

    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    resultat = await service.rejouer(workflow, contexte.organisation_id, moteur=await _moteur(), juge=await _juge(contexte, workflow))
    if not resultat.get("ok"):
        raise ErreurAction(resultat["erreur"], "sans_rapport")
    return resultat


async def _creer_des_tests(contexte: Contexte, p: _Choix) -> dict[str, Any]:
    from api.services.attaques import rapport, suites

    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    lu = await rapport.lire(contexte.organisation_id, workflow.id)
    try:
        return await suites.creer_des_tests(contexte.organisation_id, workflow.id, lu, p.ids, getattr(contexte.user, "email", None))
    except suites.RienACreer as erreur:
        raise ErreurAction(str(erreur), "rien_a_envoyer") from None


async def _envoyer_a_ameliorer(contexte: Contexte, p: _Choix) -> dict[str, Any]:
    from api.services.attaques import rapport, suites

    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    lu = await rapport.lire(contexte.organisation_id, workflow.id)
    try:
        return await suites.envoyer_dans_a_ameliorer(contexte.organisation_id, workflow.id, lu, p.ids)
    except suites.RienACreer as erreur:
        raise ErreurAction(str(erreur), "rien_a_envoyer") from None


async def _importer_le_jeu_public(contexte: Contexte, p: _Import) -> dict[str, Any]:
    from api.services.attaques import jeu_public

    try:
        fait = await jeu_public.importer(contexte.organisation_id, p.contenu)
    except jeu_public.ImportRefuse as erreur:
        raise ErreurAction(str(erreur), "import") from None
    logger.info(f"[attaques] jeu public importé pour l'organisation {contexte.organisation_id} : {fait['ajoutees']} ajoutée(s), {fait['total']} au total")
    return fait


async def _jeu_public(contexte: Contexte, p: BaseModel) -> dict[str, Any]:
    from api.services.attaques import jeu_public

    return {"ok": True, **await jeu_public.resume(contexte.organisation_id)}


def _enregistrer(nom: str, description: str, parametres: type[BaseModel], fonction, ecriture: bool, groupe: str = "tests") -> None:
    enregistrer(Action(nom=nom, description=description, parametres=parametres, fonction=fonction, ecriture=ecriture, groupe=groupe, extras={"lot": "U11"}))


_enregistrer(
    "publication_controler",
    "Run the checks of the « Publish » window on the draft, without writing anything: required tests, prompt health, voice checklist "
    "(each point: ok, gap, or no equivalent here with the reason), attacks, safety. Each check is off, warns or blocks (publication "
    "setting). A publication can always be forced by a person with a reason; you never publish.",
    _Agent,
    _controler,
    False,
    "controle",
)
_enregistrer(
    "publication_corriger_la_liste_vocale",
    "Fix in the DRAFT the voice checklist points a person ACCEPTED (ids). Simulate first with publication_controler. Only points the "
    "code can fix alone are written; the others are advice. Then the whole check is run again and returned.",
    _Corriger,
    _corriger,
    True,
    "controle",
)
_enregistrer(
    "attaques_lancer",
    "Attack the agent as it is (draft) before publishing: 15 techniques of a closed catalogue, a harmless witness per attack, each "
    "failure reproduced before it is confirmed. The scope (profondeur) MUST be confirmed by a person first (confirme=true), the "
    "report alone, nothing is changed. Returns the report: held, got through, possible, not tested (never counted as held), not covered.",
    _Lancer,
    _lancer,
    True,
)
_enregistrer("attaques_rapport", "Read the last attack report of the agent (null when none ran).", _Agent, _rapport, False)
_enregistrer(
    "attaques_rejouer",
    "After a fix, replay the attacks that got through AND a sample of those that held, on fresh sessions, and say what is fixed and "
    "what regressed.",
    _Agent,
    _rejouer,
    True,
)
_enregistrer(
    "attaques_creer_des_tests",
    "From the LAST attack report, create one replayable test per attack that got through (confirmed by default, or the ids given): the "
    "conversation up to the attack, the criterion « nothing else is done » and the question the judge asks at each replay. A test "
    "that already exists is not created twice.",
    _Choix,
    _creer_des_tests,
    True,
)
_enregistrer(
    "attaques_envoyer_a_ameliorer",
    "Send the attacks that got through (confirmed by default, or the ids given) of the LAST report to « To improve », one problem per "
    "attack, origin « Attack ». The same report never counts twice.",
    _Choix,
    _envoyer_a_ameliorer,
    True,
)
_enregistrer(
    "attaques_importer_le_jeu_public",
    "Import the public attack set (CSV of verazuo/jailbreak_llms, MIT: a prompt column, jailbreak, community…) given by a person. "
    "Idempotent: only the attacks not yet there are added; a text too long is set aside, never cut. No model is called.",
    _Import,
    _importer_le_jeu_public,
    True,
)
_enregistrer("attaques_jeu_public", "Say whether the public attack set is imported, and how many attacks it holds.", _Agent, _jeu_public, False)
