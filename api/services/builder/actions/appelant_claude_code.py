"""[.mark] Builder, U12 (E104, point 2) : l'appelant simulé joué par Claude Code, en trois actions du registre partagé.

Quand la brique « appelant simulé » est sur **Claude Code**, le fork ne fait AUCUN appel à un fournisseur pour jouer l'appelant : Claude Code
le joue, tour par tour, avec un sous-agent sans le contexte du builder.

* ``test_demarrer(workflow_id, test)`` : ouvre l'appel d'essai en **mode clavier** (le chemin texte existant, outils sortants simulés),
  rend ce que l'agent dit à l'ouverture et la consigne du personnage (lue dans la bibliothèque) ;
* ``test_tour(appel, replique)`` : la réplique de l'appelant, la réponse de l'agent ;
* ``test_finir(appel)`` : relit l'appel DANS SON JOURNAL, vérifie les critères avec le MÊME code que sur clé d'API, range le résultat
  (mêmes exécutions que ``tests_rejouer``) et, si le juge des tests est sur Claude Code, range le test dans « À juger ».

Même journal, même vérification du code, même rangement qu'un test joué sur clé. Sur clé d'API, ces actions refusent avec la raison.
L'appel appartient à l'organisation de la personne (relu avec elle) ; au plus ``TOURS_MAX`` tours.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from api.services import sources_cerveaux
from api.services.builder import brouillon, consignes, stock
from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.builder.tests_agent import execution, jeu, stockage, verdict

# (organisation, appel) -> la session ouverte, gardée par ce processus. L'état qui doit survivre à un autre worker ou à un redémarrage
# vit dans la ligne ``MARK_APPEL_ESSAI:<appel>`` de l'organisation (test, lignes, tours) ; la session du moteur se relit en base (``_reouvrir``).
_SESSIONS: dict[tuple[int, int], dict[str, Any]] = {}
SESSIONS_MAX = 50
PREFIXE_APPEL = "MARK_APPEL_ESSAI:"
PERIME_APRES_S = 2 * 3600


class _Demarrer(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent (this conversation's agent by default).")
    test: str = Field(min_length=1, max_length=200, description="The test's name or slug (a conversation test, with a scenario).")


class _Tour(BaseModel):
    appel: int = Field(ge=1, description="The call id returned by test_demarrer.")
    replique: str = Field(min_length=1, max_length=2000, description="What the caller says now.")


class _Finir(BaseModel):
    appel: int = Field(ge=1, description="The call id returned by test_demarrer.")


async def _exiger_claude_code(contexte: Contexte) -> None:
    if await sources_cerveaux.source_de(contexte.organisation_id, "appelant") != "claude_code":
        raise ErreurAction(
            "The simulated caller is set on an API key: it plays itself. Set it on Claude Code (Settings > Sources) to play it from here.",
            "source_cle_api",
        )


async def _test_de(contexte: Contexte, identifiant: int, nom: str) -> dict[str, Any]:
    tests = await stockage.lister(contexte.organisation_id, identifiant)
    test = next((t for t in tests if nom in (t["slug"], t["nom"])), None)
    if test is None:
        raise ErreurAction(f"Unknown test: {nom}.", "introuvable")
    if not test.get("scenario"):
        raise ErreurAction("This test is a single reply: replay it with tests_rejouer (no caller to play).")
    return test


async def _demarrer(contexte: Contexte, p: _Demarrer) -> dict[str, Any]:
    await _exiger_claude_code(contexte)
    workflow = await agent_de_l_organisation(contexte, p.workflow_id)
    test = await _test_de(contexte, workflow.id, p.test)
    if len(_SESSIONS) >= SESSIONS_MAX:
        raise ErreurAction("Too many practice calls are open: finish one with test_finir first.", "trop_d_appels")
    moteur = execution.DEPENDANCES.moteur()
    session, ouverture = await moteur.ouvrir(workflow, test)
    scenario = test.get("scenario") or {}
    personnage = await jeu.personnage_de(scenario)
    lignes: list[tuple[str, str]] = [("agent", ouverture.texte)] if ouverture.texte else []
    ouverte = {
        "session": session,
        "moteur": moteur,
        "test": test,
        "workflow_id": workflow.id,
        "lignes": lignes,
        "tours": 0,
        "termine": ouverture.termine,
    }
    _SESSIONS[(contexte.organisation_id, int(session.run_id))] = ouverte
    await _ranger(contexte.organisation_id, int(session.run_id), ouverte, session)
    maxi = max(1, min(int(scenario.get("tours_max") or jeu.TOURS_MAX_PAR_DEFAUT), jeu.TOURS_MAX_ABSOLU))
    return {
        "ok": True,
        "appel": session.run_id,
        "agent_dit": ouverture.texte,
        "termine": ouverture.termine,
        "tours_max": maxi,
        "personnage": jeu.consigne_de_l_appelant(personnage, scenario, await consignes.consigne_appelant()),
        "ouverture_prevue": str(scenario.get("ouverture") or "").strip() or None,
        "marche": "Play ONLY the caller, from this brief, without the builder's context (a sub-agent). Send each line with test_tour, then test_finir.",
    }


async def _ranger(organisation: int, appel: int, ouverte: dict[str, Any], session: Any = None) -> None:
    """Garde en base ce qu'un autre processus doit savoir pour continuer cet appel d'essai."""
    session = session or ouverte["session"]
    await stock.ecrire(
        organisation,
        f"{PREFIXE_APPEL}{appel}",
        {
            "workflow_id": ouverte["workflow_id"],
            "test": ouverte["test"]["slug"],
            "lignes": [list(x) for x in ouverte["lignes"]][-80:],
            "tours": ouverte["tours"],
            "termine": bool(ouverte["termine"]),
            "fins": sorted(getattr(session, "noeuds_de_fin", None) or []),
            "le": stockage.maintenant(),
        },
    )


async def _reouvrir(contexte: Contexte, appel: int, ligne: dict[str, Any], workflow: Any) -> Any:
    """La session du moteur d'un appel d'essai ouvert par un autre processus : relue en base avec l'organisation de la personne."""
    from api.db import db_client

    texte = await db_client.get_workflow_run_text_session(appel, organization_id=contexte.organisation_id)
    if texte is None:
        raise ErreurAction("This practice call is no longer open: open another with test_demarrer.", "introuvable")
    return jeu.Session(appel, set(ligne.get("fins") or []), etat={"texte": texte, "workflow": workflow})


async def _session(contexte: Contexte, appel: int) -> dict[str, Any]:
    cle = (contexte.organisation_id, appel)
    ouverte = _SESSIONS.get(cle)
    if ouverte is not None:
        return ouverte
    ligne = await stock.lire(contexte.organisation_id, f"{PREFIXE_APPEL}{appel}")
    if ligne is None or _perime(ligne):
        raise ErreurAction("No open practice call under this id for your organization: open one with test_demarrer.", "introuvable")
    workflow = await agent_de_l_organisation(contexte, ligne["workflow_id"])
    try:
        test = await stockage.lire(contexte.organisation_id, workflow.id, ligne["test"])
    except stockage.ErreurTest:
        raise ErreurAction("The test of this practice call no longer exists.", "introuvable") from None
    ouverte = {
        "session": await _reouvrir(contexte, appel, ligne, workflow),
        "moteur": execution.DEPENDANCES.moteur(),
        "test": test,
        "workflow_id": workflow.id,
        "lignes": [tuple(x) for x in ligne.get("lignes") or []],
        "tours": int(ligne.get("tours") or 0),
        "termine": bool(ligne.get("termine")),
    }
    _SESSIONS[cle] = ouverte
    return ouverte


def _perime(ligne: dict[str, Any]) -> bool:
    from datetime import UTC, datetime

    try:
        return (datetime.now(UTC) - datetime.fromisoformat(str(ligne.get("le")))).total_seconds() > PERIME_APRES_S
    except ValueError:
        return True


async def _tour(contexte: Contexte, p: _Tour) -> dict[str, Any]:
    await _exiger_claude_code(contexte)
    ouverte = await _session(contexte, p.appel)
    scenario = ouverte["test"].get("scenario") or {}
    maxi = max(1, min(int(scenario.get("tours_max") or jeu.TOURS_MAX_PAR_DEFAUT), jeu.TOURS_MAX_ABSOLU))
    if ouverte["termine"]:
        raise ErreurAction("The call is over: send test_finir.", "appel_termine")
    if ouverte["tours"] >= maxi:
        raise ErreurAction(f"The call reached its {maxi} turns: send test_finir.", "tours_max")
    ouverte["lignes"].append(("moi", p.replique))
    reponse = await ouverte["moteur"].tour(ouverte["session"], p.replique)
    ouverte["tours"] += 1
    if reponse.texte:
        ouverte["lignes"].append(("agent", reponse.texte))
    ouverte["termine"] = bool(reponse.termine)
    await _ranger(contexte.organisation_id, p.appel, ouverte)
    return {"ok": True, "appel": p.appel, "agent_dit": reponse.texte, "termine": ouverte["termine"], "tour": ouverte["tours"], "tours_max": maxi}


async def _finir(contexte: Contexte, p: _Finir) -> dict[str, Any]:
    await _exiger_claude_code(contexte)
    ouverte = await _session(contexte, p.appel)
    test, moteur = ouverte["test"], ouverte["moteur"]
    workflow = await agent_de_l_organisation(contexte, ouverte["workflow_id"])
    try:
        obs = await moteur.lire(ouverte["session"])
    finally:
        try:
            await moteur.clore(ouverte["session"])
        except Exception:  # noqa: BLE001 -- un run non clos ne fait pas échouer le test
            logger.debug("[tests-agent] appel d'essai non clos")
        _SESSIONS.pop((contexte.organisation_id, p.appel), None)
        await stock.supprimer(contexte.organisation_id, f"{PREFIXE_APPEL}{p.appel}")
    criteres = verdict.evaluer_criteres(test["criteres"], obs)
    reussi = verdict.reussi(criteres)
    essai = {
        "numero": 1,
        "reussi": reussi,
        "criteres": [c.en_json() for c in criteres],
        "lignes": execution._compact(obs.lignes),
        "issue": obs.issue,
        "simules": obs.simules,
        "run_id": p.appel,
        "joue_par": "claude_code",
    }
    graphe, version = await brouillon.source_courante(workflow)
    from api.services.builder.tests_agent import boucle

    empreinte = boucle.empreinte_du_brouillon(graphe or {"nodes": [], "edges": []}, await brouillon.configurations_courantes(workflow))
    statut = "ok" if reussi else "echec"
    a_juger = False
    if test.get("questions_juge") and await sources_cerveaux.source_de(contexte.organisation_id, "juge_tests") == "claude_code":
        await execution._ranger_a_juger(contexte.organisation_id, workflow.id, test, essai["lignes"])
        a_juger = True
    await stockage.ajouter_un_resultat(
        contexte.organisation_id,
        workflow.id,
        test["slug"],
        {"le": stockage.maintenant(), "version": version, "empreinte": empreinte, "statut": statut, "reussis": 1 if reussi else 0, "total": 1, "essais": [essai], "juge": {"a_juger": True} if a_juger else None},
    )
    return {
        "ok": True,
        "appel": p.appel,
        "reussi": reussi,
        "statut": statut,
        "criteres": essai["criteres"],
        "a_juger": a_juger,
        "message": "One call is not a verdict on the test: replay it on a key or play it again for 3 calls (B12).",
    }


for _nom, _desc, _param, _fonction, _ecriture in (
    (
        "test_demarrer",
        "Open a practice call in keyboard mode when the simulated caller is on Claude Code; returns what the agent says and the caller's brief to play (a sub-agent without the builder's context).",
        _Demarrer,
        _demarrer,
        True,
    ),
    ("test_tour", "Send the caller's next line in an open practice call; returns the agent's reply.", _Tour, _tour, True),
    (
        "test_finir",
        "End a practice call: the code checks the test's criteria on the call's journal and files the result like a test played on a key.",
        _Finir,
        _finir,
        True,
    ),
):
    enregistrer(
        Action(nom=_nom, description=_desc, parametres=_param, fonction=_fonction, ecriture=_ecriture, moteur=True, mcp=True, groupe="tests", extras={"lot": "I1"})
    )
