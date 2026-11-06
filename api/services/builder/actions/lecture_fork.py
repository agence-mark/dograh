"""[.mark] Builder, U12 (E104, point 3) : lire le fork dans Claude Code. Huit actions de LECTURE du registre partagé (écran et MCP).

* ``fork_resume``       : ce qui a changé depuis la dernière session (nouveaux points « À améliorer », tests en échec, appels à juger,
  conversations du builder). C'est ce que le hook d'ouverture de session affiche ;
* ``executions_lister`` : les dernières exécutions des tests d'un agent, les échecs d'abord ;
* ``a_ameliorer_lire``  : les points « À améliorer » (file de tri des appels et points du juge) ;
* ``appels_lister`` / ``appel_lire`` : les appels d'un agent et la transcription numérotée d'un appel (la lecture que `/analyser` utilise) ;
* ``versions_lister``   : les versions du brouillon (instantanés) et la version publiée ;
* ``chat_etat``         : l'état d'un chat du builder de l'écran et ses derniers échanges ;
* ``qualite_lire``      : les taux d'impasse et de reprise par agent.

Toutes lisent AVEC l'organisation de la personne ; aucune n'écrit. Les résultats sont bornés (pagination, nombre de lignes).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.db import db_client
from api.services.builder import brouillon, revue, stock
from api.services.builder.actions._commun import agent_verifie
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.builder.constantes import PREFIXE_RESULTATS
from api.services.juge import a_ameliorer, appels, file
from api.services.tri import donnees, pages
from api.services.builder import fil as service_fil

PAR_PAGE_MAX = 50
EXTRAITS_MAX = 5
ECHANGES_MAX = 20


class _Rien(BaseModel):
    pass


class _Depuis(BaseModel):
    depuis: str | None = Field(default=None, max_length=40, description="ISO date-time of the last session; omit for the last 24 hours.")


class _Agent(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent (omit for all of the organization's agents when the action allows).")


class _AAmeliorer(BaseModel):
    workflow_id: int | None = None
    page: int = Field(default=0, ge=0, le=200)


class _Appels(BaseModel):
    workflow_id: int | None = None
    limite: int = Field(default=20, ge=1, le=PAR_PAGE_MAX)
    decalage: int = Field(default=0, ge=0, le=100_000)


class _Appel(BaseModel):
    run_id: int = Field(ge=1)


class _Chat(BaseModel):
    fil_id: int = Field(ge=1)
    derniers: int = Field(default=10, ge=1, le=ECHANGES_MAX)


class _Jours(BaseModel):
    jours: int = Field(default=7, ge=1, le=30)


def _depuis(valeur: str | None) -> str:
    from datetime import UTC, datetime, timedelta

    if valeur:
        try:
            datetime.fromisoformat(valeur.replace("Z", "+00:00"))
            return valeur
        except ValueError:
            raise ErreurAction("`depuis` is an ISO date-time.", "date_invalide") from None
    return (datetime.now(UTC) - timedelta(days=1)).isoformat()


async def _tests_en_echec(organisation: int, workflow_id: int | None = None) -> list[dict[str, Any]]:
    prefixe = f"{PREFIXE_RESULTATS}{workflow_id}:" if workflow_id is not None else PREFIXE_RESULTATS
    sortie = []
    for cle, ligne in await stock.lister(organisation, prefixe):
        executions = ligne.get("executions") or []
        if executions and executions[0].get("statut") != "ok":
            _, wf, slug = cle.split(":", 2)
            e = executions[0]
            sortie.append({"workflow_id": int(wf), "test": slug, "statut": e.get("statut"), "reussis": e.get("reussis"), "total": e.get("total"), "le": e.get("le")})
    return sortie


async def _resume(contexte: Contexte, p: _Depuis) -> dict[str, Any]:
    organisation = contexte.organisation_id
    depuis = _depuis(p.depuis)
    points = await a_ameliorer.lister(organisation, depuis=depuis)
    en_echec = await _tests_en_echec(organisation)
    a_juger = await file.lister(organisation)
    fils = [f for f in await db_client.lister_fils(organisation) if f.modifie_le and f.modifie_le.isoformat() > depuis and f.genre != "claude_code"]
    return {
        "ok": True,
        "depuis": depuis,
        "a_ameliorer": {"nouveaux": len(points), "extraits": [{k: x.get(k) for k in ("workflow_id", "critere", "preuve")} for x in points[:EXTRAITS_MAX]]},
        "tests_en_echec": {"total": len(en_echec), "extraits": en_echec[:EXTRAITS_MAX]},
        "appels_a_juger": {"total": len(a_juger)},
        "chats_du_builder": {"modifies": len(fils), "extraits": [{"id": f.id, "titre": f.titre, "etat": f.etat} for f in fils[:EXTRAITS_MAX]]},
    }


async def _executions(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, p.workflow_id) if (p.workflow_id or contexte.workflow_id) else None
    lignes = sorted(await _tests_en_echec(contexte.organisation_id, identifiant), key=lambda x: str(x["le"]), reverse=True)
    from api.services.builder.tests_agent import stockage

    tous = []
    if identifiant is not None:
        for test in await stockage.lister(contexte.organisation_id, identifiant):
            for e in (await stockage.resultats(contexte.organisation_id, identifiant, test["slug"]))[:3]:
                tous.append({"test": test["slug"], **{k: e.get(k) for k in ("le", "version", "statut", "reussis", "total")}})
    return {"ok": True, "en_echec": lignes, "executions": tous[:60]}


async def _a_ameliorer(contexte: Contexte, p: _AAmeliorer) -> dict[str, Any]:
    organisation = contexte.organisation_id
    identifiant = await agent_verifie(contexte, p.workflow_id) if p.workflow_id is not None else None
    runs, suite = await db_client.runs_avec(
        organisation, chemin=donnees.chemin_des_runs_a_trier(), cles=donnees.CLES_LUES_POUR_LE_TRI, page=p.page, workflow_id=identifiant
    )
    return {
        "ok": True,
        "tri": pages.lignes_de_tri(runs),
        "a_une_suite": suite,
        "page": p.page,
        "du_juge": await a_ameliorer.lister(organisation, identifiant),
    }


async def _appels(contexte: Contexte, p: _Appels) -> dict[str, Any]:
    identifiant = await agent_verifie(contexte, p.workflow_id)
    liste, total = await db_client.get_workflow_runs_by_workflow_id(
        identifiant, organization_id=contexte.organisation_id, limit=p.limite, offset=p.decalage
    )
    return {
        "ok": True,
        "total": total,
        "appels": [{"run_id": r.id, "nom": r.name, "mode": r.mode, "cree_le": str(r.created_at), "termine": r.is_completed} for r in liste],
    }


async def _appel(contexte: Contexte, p: _Appel) -> dict[str, Any]:
    # L'organisation est filtrée DANS la requête (revue serveur, mineur 6) : un run d'ailleurs n'est jamais lu.
    run = await db_client.get_workflow_run(p.run_id, organization_id=contexte.organisation_id)
    if run is None:
        raise ErreurAction("This call is not found in your organization.", "introuvable")
    from api.services.juge import verdicts as v

    dossier = appels.dossier_d_un_run(run)
    return {
        "ok": True,
        "run_id": p.run_id,
        "agent": run.workflow_id,
        "transcription": v.numerotee(dossier["lignes"]),
        "outils": dossier["outils"],
        "fiche": dossier["fiche"],
        "juge": (getattr(run, "annotations", None) or {}).get("juge"),
    }


async def _versions(contexte: Contexte, p: _Agent) -> dict[str, Any]:
    workflow = await agent_verifie(contexte, p.workflow_id)
    agent = await db_client.get_workflow(workflow, organization_id=contexte.organisation_id)
    _graphe, version = await brouillon.source_courante(agent)
    return {
        "ok": True,
        "version_courante": version,
        "publiee": bool(await db_client.workflow_a_ete_publie(workflow)),
        "instantanes": [
            {k: x.get(k) for k in ("numero", "cause", "date", "fil_id", "version_avant", "version_apres")}
            for x in await revue.instantanes(contexte.organisation_id, workflow)
        ],
    }


async def _chat(contexte: Contexte, p: _Chat) -> dict[str, Any]:
    fil = await db_client.lire_fil(contexte.organisation_id, p.fil_id)
    if fil is None:
        raise ErreurAction("Conversation not found.", "introuvable")
    evenements = await service_fil.lire_apres(fil.id, 0)
    echanges = [e for _i, e in evenements if e.get("type") in ("message", "texte", "action", "erreur", "fin")][-p.derniers :]
    resume = [{k: (str(e[k])[:300] if k == "texte" else e[k]) for k in ("type", "role", "texte", "nom", "raison") if k in e} for e in echanges]
    return {
        "ok": True,
        "id": fil.id,
        "titre": fil.titre,
        "etat": fil.etat,
        "genre": fil.genre or "principal",
        "agent": fil.workflow_id,
        "changements_a_valider": fil.changements or 0,
        "jauge": fil.jauge or 0.0,
        "cout": fil.cout or 0.0,
        "derniers": resume,
    }


async def _qualite(contexte: Contexte, p: _Jours) -> dict[str, Any]:
    lignes = await db_client.taux_de_sortie_d_impasse(contexte.organisation_id, jours=donnees.jours_des_taux(p.jours))
    return {"ok": True, "jours": donnees.jours_des_taux(p.jours), "agents": lignes}


for _nom, _desc, _param, _fonction in (
    ("fork_resume", "What changed in the fork since the last session: new improvement points, failing tests, calls to judge, builder chats.", _Depuis, _resume),
    ("executions_lister", "The last test executions of an agent, failing tests first.", _Agent, _executions),
    ("a_ameliorer_lire", "The improvement points: the triage queue of calls and the judge's failed criteria.", _AAmeliorer, _a_ameliorer),
    ("appels_lister", "An agent's calls, most recent first (paginated).", _Appels, _appels),
    ("appel_lire", "One call: numbered transcript, tools, final sheet and the judge's verdicts (what /analyser reads).", _Appel, _appel),
    ("versions_lister", "An agent's draft versions (snapshots) and its current version.", _Agent, _versions),
    ("chat_etat", "The state of a builder chat of the screen (state, gauge, cost, last exchanges).", _Chat, _chat),
    ("qualite_lire", "Quality by agent: impasse rate and recovery rate over 7 or 30 days.", _Jours, _qualite),
):
    enregistrer(
        Action(nom=_nom, description=_desc, parametres=_param, fonction=_fonction, ecriture=False, moteur=True, mcp=True, groupe="lecture", extras={"lot": "I1"})
    )
