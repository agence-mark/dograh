"""[.mark] Builder, lot 6 : rejouer la suite d'un agent et ranger les résultats (B12, B38, B40, B42).

``rejouer_la_suite`` est le corps de l'action ``tests_rejouer``. Forme rendue (contrat attendu par ``correction.py``) :

    {"ok": bool, "echecs": [...], "total": int, ...}

* ``ok`` est vrai SEULEMENT si toute la suite a été rejouée (``suite_complete``) et passe à 100 % (B38). Un sous-ensemble rejoué
  ne vérifie jamais l'agent : ``ok`` y est faux, ``partiel`` vrai.
* **B42** : un test obligatoire qui échoue suffit à refuser (``refus``) ; jamais la moyenne.
* **B40** : chaque échec porte la ``raison`` écrite sur la RÉPLIQUE fautive (``rang``, ``replique``).
* **B39** : chaque échec porte son diagnostic (agent, test ou exécution).
* ``elements`` : liste de ``{"statut", "message"}`` pour une carte générique ; ``resultats`` : l'objet brut.

Les outils sortants de la copie sont simulés et figés (B42) ; le juge à part est non bloquant et n'entre pas dans ``ok``.
Les dépendances qui touchent la base et le modèle sont rassemblées dans ``DEPENDANCES`` (remplaçables dans les tests).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.services.builder import brouillon
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau, fabriquer
from api.services.builder.tests_agent import diagnostic, jeu, juge, stockage, verdict
from api.services.builder.tests_agent.jeu import AppelantParCerveau, Moteur
from api.services.tests_rejouables.modele import ErreurTestRejouable, depuis_json, refuser_si_protege

REPETITIONS_PAR_DEFAUT = 3
LIGNES_GARDEES = 60


@dataclass
class Dependances:
    # (TestRejouable, agent_id, essais, organisation_id) -> ResultatTest ; le rejeu d'un tour (tests_rejouables.rejeu).
    rejouer_un_tour: Callable[..., Awaitable[Any]] | None = None
    moteur: Callable[[], Moteur] = jeu.moteur_texte
    # (user) -> Cerveau | None : le cerveau de l'appelant simulé et du juge (celui du builder).
    cerveau: Callable[[Any], Awaitable[Cerveau | None]] | None = None
    noms_d_outils: Callable[[Any, int], Awaitable[set[str]]] | None = None
    ecart: dict[str, Any] = field(default_factory=dict)


DEPENDANCES = Dependances()


async def _rejouer_un_tour(*args: Any, **kwargs: Any):
    if DEPENDANCES.rejouer_un_tour is not None:
        return await DEPENDANCES.rejouer_un_tour(*args, **kwargs)
    from api.services.tests_rejouables.rejeu import rejouer

    return await rejouer(*args, **kwargs)


async def cerveau_du_builder(user: Any) -> Cerveau | None:
    """Le cerveau réglé pour le builder (le même que la conversation). ``None`` : non réglé."""
    if DEPENDANCES.cerveau is not None:
        return await DEPENDANCES.cerveau(user)
    from api.services.builder.cerveau import reglages as reglages_cerveau

    try:
        organisation = await reglages_cerveau.organisation_des_reglages(user)
        reglages = await reglages_cerveau.lire(organisation)
        cle = await reglages_cerveau.lire_la_cle(organisation, reglages)
        if not reglages.modele or not cle:
            return None
        return fabriquer(reglages, cle)
    except ErreurCerveau:
        return None


# --- un test ----------------------------------------------------------------------------------------------------------------


def _compact(lignes: list[tuple[str, str]]) -> list[list[str]]:
    return [[r, t[:600]] for r, t in lignes[:LIGNES_GARDEES]]


async def _essais_d_une_replique(test: dict[str, Any], workflow: Any, organisation_id: int, n: int) -> list[dict[str, Any]]:
    rejouable = depuis_json(test, defaut_nom=test["slug"], origine=test["slug"])
    resultat = await _rejouer_un_tour(rejouable, workflow.id, n, organisation_id)
    if resultat.erreur:
        return [{"numero": i + 1, "erreur": resultat.erreur, "criteres": [], "reussi": False, "lignes": []} for i in range(n)]
    sorties = []
    for essai in resultat.essais:
        if essai.erreur:
            sorties.append({"numero": essai.numero, "erreur": essai.erreur, "criteres": [], "reussi": False, "lignes": [], "run_id": essai.run_id})
            continue
        obs = verdict.observation_depuis_un_essai(essai.observe, test.get("replique"))
        criteres = verdict.evaluer_criteres(test["criteres"], obs)
        sorties.append(
            {
                "numero": essai.numero,
                "reussi": verdict.reussi(criteres),
                "criteres": [c.en_json() for c in criteres],
                "lignes": _compact(obs.lignes),
                "run_id": essai.run_id,
                "simules": obs.simules,
            }
        )
    return sorties


async def _essais_d_une_conversation(test: dict[str, Any], workflow: Any, user: Any, n: int, cerveau: Cerveau | None) -> list[dict[str, Any]]:
    if cerveau is None:
        return [
            {"numero": i + 1, "erreur": "No brain set for the simulated caller (builder settings).", "criteres": [], "reussi": False, "lignes": []}
            for i in range(n)
        ]
    scenario = test.get("scenario") or {}
    personnage = await jeu.personnage_de(scenario)
    appelant = AppelantParCerveau(cerveau, jeu.consigne_de_l_appelant(personnage, scenario))
    moteur = DEPENDANCES.moteur()
    sorties = []
    for i in range(1, n + 1):
        try:
            obs = await jeu.jouer_une_conversation(workflow, test, appelant, moteur)
        except Exception as erreur:  # noqa: BLE001 -- un essai en erreur compte pour raté, avec sa cause
            logger.warning(f"[tests-agent] essai {i} de {test['slug']} en erreur : {type(erreur).__name__}")
            sorties.append({"numero": i, "erreur": f"{type(erreur).__name__}: {str(erreur)[:160]}", "criteres": [], "reussi": False, "lignes": []})
            continue
        criteres = verdict.evaluer_criteres(test["criteres"], obs)
        sorties.append(
            {
                "numero": i,
                "reussi": verdict.reussi(criteres),
                "criteres": [c.en_json() for c in criteres],
                "lignes": _compact(obs.lignes),
                "issue": obs.issue,
                "simules": obs.simules,
            }
        )
    return sorties


def _statut_d_un_test(essais: list[dict[str, Any]]) -> str:
    if essais and all(e.get("erreur") for e in essais):
        return "erreur"
    return "ok" if essais and all(e["reussi"] for e in essais) else "echec"


def _echecs_d_un_test(test: dict[str, Any], essais: list[dict[str, Any]], etapes: set[str], outils: set[str]) -> list[dict[str, Any]]:
    """B40 + B39 : un échec par critère raté du PREMIER essai raté (le détail complet reste dans les essais)."""
    echecs: list[dict[str, Any]] = []
    for essai in essais:
        if essai["reussi"]:
            continue
        if essai.get("erreur"):
            echecs.append(
                {
                    "test": test["slug"],
                    "nom": test["nom"],
                    "obligatoire": bool(test.get("obligatoire")),
                    "essai": essai["numero"],
                    "critere": None,
                    "raison": essai["erreur"],
                    "rang": None,
                    "replique": None,
                    "diagnostic": diagnostic.classer(None, erreur=essai["erreur"], etapes_de_l_agent=etapes, outils_de_l_agent=outils),
                }
            )
            break
        for c in essai["criteres"]:
            if c["reussi"]:
                continue
            lignes = [t for r, t in essai["lignes"] if r == "agent"]
            rang = c.get("rang")
            echecs.append(
                {
                    "test": test["slug"],
                    "nom": test["nom"],
                    "obligatoire": bool(test.get("obligatoire")),
                    "essai": essai["numero"],
                    "critere": c["critere"],
                    "raison": c.get("raison") or c["detail"],
                    "rang": rang,
                    "replique": lignes[rang] if rang is not None and 0 <= rang < len(lignes) else None,
                    "diagnostic": diagnostic.classer(c["critere"], erreur=None, etapes_de_l_agent=etapes, outils_de_l_agent=outils),
                }
            )
        break
    return echecs


async def _noms_d_outils(workflow: Any, organisation_id: int, graphe: dict[str, Any]) -> set[str]:
    if DEPENDANCES.noms_d_outils is not None:
        return await DEPENDANCES.noms_d_outils(workflow, organisation_id)
    from api.services.builder.controle.service import _outils

    return {o.nom for o in (await _outils(graphe, organisation_id)).values()}


# --- la suite ------------------------------------------------------------------------------------------------------------------


async def rejouer_la_suite(
    user: Any,
    workflow: Any,
    *,
    noms: list[str] | None = None,
    repetitions: int = REPETITIONS_PAR_DEFAUT,
    avec_le_juge: bool = True,
) -> dict[str, Any]:
    """Rejoue les tests de l'agent (tous, ou ``noms``) ``repetitions`` fois et range les résultats."""
    organisation_id = user.selected_organization_id
    refuser_si_protege(workflow.id)
    tous = await stockage.lister(organisation_id, workflow.id)
    if not tous:
        return {
            "disponible": False,
            "ok": False,
            "echecs": [],
            "total": 0,
            "message": "This agent has no test yet: create tests first, nothing can be verified.",
        }
    voulus = [t for t in tous if noms is None or t["slug"] in set(noms) or t["nom"] in set(noms)]
    if not voulus:
        return {"ok": False, "echecs": [], "total": 0, "message": "None of these tests exists.", "disponible": True}
    complete = len(voulus) == len(tous)
    graphe, version = await brouillon.source_courante(workflow)
    graphe = graphe or {"nodes": [], "edges": []}
    etapes = diagnostic.noms_de_etapes(graphe)
    outils = await _noms_d_outils(workflow, organisation_id, graphe)
    cerveau = None
    if any(t.get("scenario") or t.get("questions_juge") for t in voulus):
        cerveau = await cerveau_du_builder(user)

    resultats: list[dict[str, Any]] = []
    echecs: list[dict[str, Any]] = []
    for test in voulus:
        try:
            if test.get("scenario"):
                essais = await _essais_d_une_conversation(test, workflow, user, repetitions, cerveau)
            else:
                essais = await _essais_d_une_replique(test, workflow, organisation_id, repetitions)
        except ErreurTestRejouable as erreur:
            essais = [{"numero": 1, "erreur": str(erreur), "criteres": [], "reussi": False, "lignes": []}]
        statut = _statut_d_un_test(essais)
        avis = None
        if avec_le_juge and cerveau is not None and test.get("questions_juge") and essais and essais[0].get("lignes"):
            avis = await juge.juger(cerveau, [(r, t) for r, t in essais[0]["lignes"]], test["questions_juge"])
        reussis = sum(1 for e in essais if e["reussi"])
        entree = {
            "slug": test["slug"],
            "nom": test["nom"],
            "obligatoire": bool(test.get("obligatoire")),
            "dossier": test.get("dossier", ""),
            "origine": test.get("origine"),
            "statut": statut,
            "reussis": reussis,
            "total": len(essais),
            "essais": essais,
            "juge": avis,
        }
        resultats.append(entree)
        echecs += _echecs_d_un_test(test, essais, etapes, outils)
        await stockage.ajouter_un_resultat(
            organisation_id,
            workflow.id,
            test["slug"],
            {"le": stockage.maintenant(), "version": version, "statut": statut, "reussis": reussis, "total": len(essais), "essais": essais, "juge": avis},
        )

    tout_vert = all(r["statut"] == "ok" for r in resultats)
    refus = any(r["obligatoire"] and r["statut"] != "ok" for r in resultats)
    elements = [
        {
            "statut": r["statut"],
            "message": f"{r['nom']} : {r['reussis']}/{r['total']}" + (" (obligatoire)" if r["obligatoire"] else ""),
            "test": r["slug"],
            "obligatoire": r["obligatoire"],
        }
        for r in resultats
    ]
    from api.services.builder.tests_agent import boucle

    await boucle.noter_la_version_testee(organisation_id, workflow.id, graphe, version, tout_vert and complete)
    return {
        "ok": bool(tout_vert and complete),
        "echecs": echecs,
        "total": len(resultats),
        "reussis": sum(1 for r in resultats if r["statut"] == "ok"),
        "suite_complete": complete,
        "partiel": not complete,
        "refus": refus,
        "version": version,
        "elements": elements,
        "resultats": resultats,
        "message": "" if complete else "Only part of the suite was replayed: nothing is verified until the whole suite passes.",
        "carte": {"type": "tests", "ok": bool(tout_vert and complete), "refus": refus, "elements": elements},
    }
