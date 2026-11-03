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
from api.services.builder.cerveau import independance as independance_mod
from api.services.builder.cerveau.appel import Cerveau
from api.services.builder.tests_agent import diagnostic, jeu, juge, stockage, verdict
from api.services.builder.tests_agent.jeu import AppelantParCerveau, Moteur
from api.services.tests_rejouables.modele import (
    ErreurTestRejouable,
    depuis_json,
    refuser_si_protege,
)

REPETITIONS_PAR_DEFAUT = 3
LIGNES_GARDEES = 60


@dataclass
class Dependances:
    # (TestRejouable, agent_id, essais, organisation_id) -> ResultatTest ; le rejeu d'un tour (tests_rejouables.rejeu).
    rejouer_un_tour: Callable[..., Awaitable[Any]] | None = None
    moteur: Callable[[], Moteur] = jeu.moteur_texte
    # (user, role) -> Cerveau | None, role = « appelant » ou « juge » : les tests remplacent les deux d'un coup.
    cerveau: Callable[..., Awaitable[Cerveau | None]] | None = None
    noms_d_outils: Callable[[Any, int], Awaitable[set[str]]] | None = None
    ecart: dict[str, Any] = field(default_factory=dict)


DEPENDANCES = Dependances()


async def _rejouer_un_tour(*args: Any, **kwargs: Any):
    if DEPENDANCES.rejouer_un_tour is not None:
        return await DEPENDANCES.rejouer_un_tour(*args, **kwargs)
    from api.services.tests_rejouables.rejeu import rejouer

    return await rejouer(*args, **kwargs)


@dataclass
class CerveauxDesTests:
    """L'appelant simulé et le juge d'une suite (U6) : chacun son fournisseur et sa clé (Réglages du Labo)."""

    appelant: Any = None  # CerveauCompte | None
    juge: Any = None  # CerveauCompte | None
    source_appelant: str = "cle_api"
    source_juge: str = "cle_api"
    independance: independance_mod.Independance = field(default_factory=independance_mod.Independance)

    def depense(self) -> dict[str, Any] | None:
        comptes = {id(c): c for c in (self.appelant, self.juge) if c is not None}.values()
        if not comptes:
            return None
        return {"jetons": sum(c.depense["jetons"] for c in comptes), "cout": round(sum(c.depense["cout"] for c in comptes), 6)}

    def atteint(self) -> str | None:
        return next((q for c in (self.appelant, self.juge) if c is not None and (q := c.atteint()) is not None), None)


async def _modele_de_l_agent(workflow: Any, organisation_id: int) -> str | None:
    from api.services.configuration.ai_model_configuration import get_effective_ai_model_configuration_for_workflow

    try:
        effective = await get_effective_ai_model_configuration_for_workflow(
            organization_id=organisation_id, workflow_configurations=await brouillon.configurations_courantes(workflow)
        )
        return getattr(effective.llm, "model", None) if effective.llm is not None else None
    except Exception:  # noqa: BLE001 -- un modèle illisible : pas de refus sur ce motif, jamais un test en panne
        return None


async def cerveaux_des_tests(user: Any, workflow: Any) -> CerveauxDesTests:
    """Les cerveaux de l'appelant simulé et du juge. ``None`` : non réglé (ou source Claude Code)."""
    if DEPENDANCES.cerveau is not None:
        brut_a = await DEPENDANCES.cerveau(user, "appelant")
        brut_j = await DEPENDANCES.cerveau(user, "juge")
        appelant = CerveauCompte(brut_a, getattr(brut_a, "reglages", None)) if brut_a is not None else None
        juge_c = appelant if brut_j is brut_a else (CerveauCompte(brut_j, getattr(brut_j, "reglages", None)) if brut_j is not None else None)
        return CerveauxDesTests(appelant, juge_c)
    from api.services.appel_simule import reglages as appel_simule
    from api.services.builder.cerveau import reglages as reglages_cerveau
    from api.services.builder.cerveau import simules

    organisation_id = user.selected_organization_id
    try:
        roles = await appel_simule.lire_reglages(organisation_id)
        base = await reglages_cerveau.lire(await reglages_cerveau.organisation_des_reglages(user))
    except Exception:  # noqa: BLE001
        return CerveauxDesTests()
    modele_agent = await _modele_de_l_agent(workflow, organisation_id)
    controle = independance_mod.controler(
        source_juge=roles.juge.source, modele_juge=roles.juge.modele, modele_builder=base.modele, modele_agent=modele_agent
    )
    appelant_brut = await simules.cerveau_du_role(organisation_id, roles.appelant, base)
    juge_brut = None if controle.refuse else await simules.cerveau_du_role(organisation_id, roles.juge, base)
    return CerveauxDesTests(
        CerveauCompte(appelant_brut, simules.reglages_du_role(roles.appelant, base)) if appelant_brut is not None else None,
        CerveauCompte(juge_brut, simules.reglages_du_role(roles.juge, base)) if juge_brut is not None else None,
        roles.appelant.source,
        roles.juge.source,
        controle,
    )


# --- le plafond du rejeu (C2) ----------------------------------------------------------------------------------------------


class PlafondDuRejeu(Exception):
    def __init__(self, quoi: str):
        super().__init__(quoi)
        self.quoi = quoi


class CerveauCompte:
    """Le cerveau de l'appelant simulé et du juge, compté sur tout le rejeu (C2) : jetons et dollars (table de prix).

    Avant chaque appel, si un plafond du rejeu est atteint, ``PlafondDuRejeu`` : la suite s'arrête, rien n'est inventé pour
    les tests restants, et la question remonte à la personne (« continuer au-delà du plafond ? »)."""

    def __init__(self, cerveau: Cerveau, reglages: Any):
        self._cerveau = cerveau
        self._reglages = reglages
        self.depense: dict[str, Any] = {"jetons": 0, "cout": 0.0}

    def atteint(self) -> str | None:
        r = self._reglages
        if r is None:
            return None
        if self.depense["jetons"] >= r.plafond_rejeu_jetons:
            return "jetons"
        if r.plafond_rejeu_depense > 0 and self.depense["cout"] >= r.plafond_rejeu_depense:
            return "depense"
        return None

    async def tour(self, *, systeme: str, messages: list[dict[str, Any]], outils: list[dict[str, Any]]):
        if (quoi := self.atteint()) is not None:
            raise PlafondDuRejeu(quoi)
        async for evenement in self._cerveau.tour(systeme=systeme, messages=messages, outils=outils):
            if evenement.get("type") == "usage" and self._reglages is not None:
                entree, sortie = int(evenement.get("entree", 0) or 0), int(evenement.get("sortie", 0) or 0)
                self.depense["jetons"] += entree + sortie
                self.depense["cout"] = round(
                    self.depense["cout"]
                    + (entree * self._reglages.prix_entree_par_million + sortie * self._reglages.prix_sortie_par_million) / 1_000_000,
                    6,
                )
            yield evenement


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


async def _essais_d_une_conversation(
    test: dict[str, Any], workflow: Any, user: Any, n: int, cerveau: Cerveau | None, source: str = "cle_api"
) -> list[dict[str, Any]]:
    if cerveau is None:
        raison = (
            "The simulated caller is set on Claude Code: it plays through a Claude Code session, not here."
            if source == "claude_code"
            else "No brain set for the simulated caller (Labo settings > Simulated caller)."
        )
        return [{"numero": i + 1, "erreur": raison, "criteres": [], "reussi": False, "lignes": []} for i in range(n)]
    scenario = test.get("scenario") or {}
    personnage = await jeu.personnage_de(scenario)
    from api.services.builder import consignes

    appelant = AppelantParCerveau(cerveau, jeu.consigne_de_l_appelant(personnage, scenario, await consignes.consigne_appelant()))
    moteur = DEPENDANCES.moteur()
    sorties = []
    for i in range(1, n + 1):
        try:
            obs = await jeu.jouer_une_conversation(workflow, test, appelant, moteur)
        except PlafondDuRejeu:
            raise
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


async def _avis_du_juge(cerveaux: CerveauxDesTests, test: dict[str, Any], essais: list[dict[str, Any]]) -> dict[str, Any] | None:
    """L'avis du juge sur le premier essai, toujours à part (jamais dans le verdict). D9 : refusé s'il noterait son propre travail ;
    sur Claude Code il n'est pas rendu ici (le juge attend une session) et la mention d'exemption accompagne tout avis."""
    if cerveaux.independance.refuse:
        return {"bloquant": False, "avis": [], "erreur": cerveaux.independance.refus}
    mention = {"mention": cerveaux.independance.mention} if cerveaux.independance.mention else {}
    if cerveaux.source_juge == "claude_code":
        return {"bloquant": False, "avis": [], "a_juger": True, **mention}
    if cerveaux.juge is None:
        return None
    try:
        avis = await juge.juger(cerveaux.juge, [(r, t) for r, t in essais[0]["lignes"]], test["questions_juge"])
    except PlafondDuRejeu as atteint:
        return {"bloquant": False, "avis": [], "erreur": "replay ceiling reached", "plafond": atteint.quoi}
    return {**avis, **mention}


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
    # Revue R1 : ce que la suite a rejoué = le graphe ET les réglages du brouillon, rangés avec chaque exécution.
    from api.services.builder.tests_agent import boucle as _boucle

    empreinte_rejouee = _boucle.empreinte_du_brouillon(graphe, await brouillon.configurations_courantes(workflow))
    etapes = diagnostic.noms_de_etapes(graphe)
    outils = await _noms_d_outils(workflow, organisation_id, graphe)
    cerveaux = CerveauxDesTests()
    if any(t.get("scenario") or t.get("questions_juge") for t in voulus):
        cerveaux = await cerveaux_des_tests(user, workflow)

    resultats: list[dict[str, Any]] = []
    echecs: list[dict[str, Any]] = []
    plafond: str | None = None
    for test in voulus:
        if (plafond := cerveaux.atteint()) is not None:
            break
        try:
            if test.get("scenario"):
                essais = await _essais_d_une_conversation(test, workflow, user, repetitions, cerveaux.appelant, cerveaux.source_appelant)
            else:
                essais = await _essais_d_une_replique(test, workflow, organisation_id, repetitions)
        except ErreurTestRejouable as erreur:
            essais = [{"numero": 1, "erreur": str(erreur), "criteres": [], "reussi": False, "lignes": []}]
        except PlafondDuRejeu as atteint:
            plafond = atteint.quoi
            break
        statut = _statut_d_un_test(essais)
        avis = None
        if avec_le_juge and test.get("questions_juge") and essais and essais[0].get("lignes"):
            avis = await _avis_du_juge(cerveaux, test, essais)
            if avis is not None and avis.get("plafond"):
                plafond = avis.pop("plafond")
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
            {"le": stockage.maintenant(), "version": version, "empreinte": empreinte_rejouee, "statut": statut, "reussis": reussis, "total": len(essais), "essais": essais, "juge": avis},
        )

    if plafond is not None:
        complete = False
    tout_vert = bool(resultats) and all(r["statut"] == "ok" for r in resultats)
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
        "plafond": plafond,
        "depense": cerveaux.depense(),
        "question": (
            f"The replay's ceiling ({plafond}) is reached after {len(resultats)} of {len(voulus)} tests: raise the ceiling or replay the rest?"
            if plafond is not None
            else None
        ),
        "message": (
            f"Stopped: the replay's ceiling ({plafond}) is reached. Ask the person before going on."
            if plafond is not None
            else "" if complete else "Only part of the suite was replayed: nothing is verified until the whole suite passes."
        ),
        "carte": {"type": "tests", "ok": bool(tout_vert and complete), "refus": refus, "elements": elements},
    }
