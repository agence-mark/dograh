"""[.mark] builder partie 2, U4 (E42) : la liste de préparation d'un agent, CALCULÉE à l'ouverture, rien de stocké.

Chaque étape se lit dans ce que le fork sait déjà. Une étape **requise** bloque la mise en service (cercle rouge à
l'écran), une étape **conseillée** aide (cercle bleu .mark). Chaque étape porte sa ``source`` (ce qui la calcule : le « ! »
de l'écran la dit) et le ``theme`` de l'écran à ouvrir pour la régler.

| Étape | Niveau | Calculée depuis |
|---|---|---|
| ``variables``   | requis    | variables ``{{x}}`` des prompts et phrases du graphe, contre les variables du modèle et celles que le graphe extrait |
| ``briques``     | requis    | la configuration effective des modèles : cerveau, transcription, voix (ou temps réel) présents ; AUCUN appel au fournisseur |
| ``outils``      | requis    | les outils portés par les étapes existent et sont actifs ; « sans objet » quand aucun n'est branché |
| ``tests``       | requis / conseillé | tests obligatoires à jour et réussis (requis) ; aucun test du tout (conseillé) |
| ``etablissement`` | conseillé | ``etablissement_id`` pointe une fiche qui existe, avec nom et au moins une adresse ou des horaires |
| ``fiche``       | conseillé | ``fiche_champs`` définie |
| ``panne``       | conseillé | le repli en cas de panne est réglé |
| ``phrases``     | conseillé | au moins une règle de phrases du code |

Le contrôle réel d'un fournisseur reste un geste de personne (« Tester la connexion ») : une lecture ne contacte personne et
ne coûte rien. Aucun mot de métier.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

REQUIS = "requis"
CONSEILLE = "conseille"
FAIT = "fait"
A_FAIRE = "a_faire"
BLOQUANT = "bloquant"
HERITE = "herite"
SANS_OBJET = "sans_objet"


@dataclass
class Etape:
    id: str
    niveau: str
    etat: str
    theme: str
    source: str
    # Ce qui manque (noms de variables, de briques, d'outils, de tests) : l'écran les nomme.
    manquants: list[str] = field(default_factory=list)
    # [.mark] Partie 3, SA-L3a : « Prêt à publier ». L'étape où ça se règle (le thème ne suffit pas pour une étape du graphe),
    # le contrôle de publication qui la garde (``controle``) et sa position, les corrections en un clic, et « hérité du principal ».
    noeud_id: str | None = None
    controle: str | None = None
    position: str | None = None
    corrections: list[dict[str, Any]] = field(default_factory=list)
    constat: str | None = None
    liaison_id: str | None = None
    noms: list[str] = field(default_factory=list)


def _noeuds(definition: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    noeuds = (definition or {}).get("nodes")
    return [n for n in noeuds if isinstance(n, dict)] if isinstance(noeuds, list) else []


def variables_manquantes(definition: Mapping[str, Any] | None, variables_du_modele: Mapping[str, Any] | None) -> list[str]:
    """Les variables lues par le graphe que ni le modèle ni une extraction ne fournit. Un graphe illisible : aucune."""
    from api.services.workflow.dto import ReactFlowDTO
    from api.services.workflow.workflow_graph import WorkflowGraph

    try:
        graphe = WorkflowGraph(ReactFlowDTO.model_validate(dict(definition or {})))
        requises = graphe.get_required_template_variables()
    except Exception:  # noqa: BLE001 -- un graphe que le moteur ne lit pas est l'affaire du contrôle de l'agent, pas d'ici
        return []
    extraites: set[str] = set()
    for noeud in _noeuds(definition):
        for v in (noeud.get("data") or {}).get("extraction_variables") or []:
            if isinstance(v, dict) and v.get("name"):
                extraites.add(str(v["name"]))
    fournies = {c for c, v in (variables_du_modele or {}).items() if v not in (None, "")}
    return sorted(requises - extraites - fournies)


def outils_du_graphe(definition: Mapping[str, Any] | None) -> list[str]:
    vus: list[str] = []
    for noeud in _noeuds(definition):
        for u in (noeud.get("data") or {}).get("tool_uuids") or []:
            if isinstance(u, str) and u not in vus:
                vus.append(u)
    return vus


def noeud_des_variables(definition: Mapping[str, Any] | None, manquantes: list[str]) -> str | None:
    """La première étape dont un texte lit une variable manquante : l'endroit exact où la régler."""
    for noeud in _noeuds(definition):
        donnees = noeud.get("data") or {}
        texte = " ".join(str(donnees.get(c) or "") for c in ("prompt", "greeting", "premiere_replique"))
        if any(f"{{{{{v}}}}}" in texte for v in manquantes):
            return str(noeud.get("id"))
    return None


def noeud_des_outils(definition: Mapping[str, Any] | None, perdus: list[str]) -> str | None:
    for noeud in _noeuds(definition):
        if any(u in perdus for u in (noeud.get("data") or {}).get("tool_uuids") or []):
            return str(noeud.get("id"))
    return None


def briques_manquantes(effective: Any | None) -> list[str]:
    """``llm`` / ``stt`` / ``tts`` absents de la configuration effective (temps réel : ``realtime`` suffit)."""
    if effective is None:
        return ["llm", "stt", "tts"]
    if getattr(effective, "is_realtime", False):
        return [] if getattr(effective, "realtime", None) is not None else ["realtime"]
    return [b for b in ("llm", "stt", "tts") if getattr(effective, b, None) is None]


def calculer(
    *,
    definition: Mapping[str, Any] | None,
    variables_du_modele: Mapping[str, Any] | None,
    configurations: Mapping[str, Any],
    effective: Any | None,
    outils_actifs: set[str],
    fiche: Any | None,
    tests: list[dict[str, Any]],
    problemes_tests_obligatoires: list[dict[str, Any]],
    suivies_du_principal: frozenset[str] = frozenset(),
) -> list[Etape]:
    """Les étapes, dans l'ordre d'un appel. Pure. ``suivies_du_principal`` : les clés qu'un spécialisé reçoit de son principal
    (une ligne faite sur une de ces clés se dit « hérité du principal »)."""
    etapes: list[Etape] = []

    manquantes = variables_manquantes(definition, variables_du_modele)
    etapes.append(
        Etape("variables", REQUIS, A_FAIRE if manquantes else FAIT, "agent", "prompts, phrases et variables du modèle", manquantes,
              noeud_id=noeud_des_variables(definition, manquantes) if manquantes else None, controle="variables")
    )

    briques = briques_manquantes(effective)
    etapes.append(
        Etape("briques", REQUIS, A_FAIRE if briques else FAIT, "briques", "configuration effective des modèles", briques, controle="briques")
    )

    branches = outils_du_graphe(definition)
    perdus = [u for u in branches if u not in outils_actifs]
    etapes.append(
        Etape(
            "outils",
            REQUIS,
            SANS_OBJET if not branches else (A_FAIRE if perdus else FAIT),
            "agent",
            "outils portés par les étapes du graphe",
            perdus,
            noeud_id=noeud_des_outils(definition, perdus) if perdus else None,
            controle="outils",
        )
    )

    if problemes_tests_obligatoires:
        etapes.append(
            Etape("tests", REQUIS, A_FAIRE, "agent", "tests obligatoires de l'agent et leurs dernières exécutions",
                  [str(p.get("nom") or p.get("slug")) for p in problemes_tests_obligatoires], controle="tests_obligatoires")
        )
    else:
        etapes.append(
            Etape("tests", CONSEILLE, FAIT if tests else A_FAIRE, "agent", "tests de l'agent et leurs dernières exécutions")
        )

    fiche_id = configurations.get("etablissement_id")
    fiche_ok = (
        fiche is not None
        and bool(getattr(fiche, "nom", None))
        and (getattr(fiche, "adresse", None) is not None or bool(getattr(fiche, "horaires_ouverture", None)))
    )
    etapes.append(
        Etape(
            "etablissement",
            CONSEILLE,
            FAIT if fiche_ok else A_FAIRE,
            "etablissement",
            "fiche d'établissement choisie par l'agent",
            [fiche_id] if isinstance(fiche_id, str) and fiche_id and not fiche_ok else [],
        )
    )
    etapes.append(
        Etape("fiche", CONSEILLE, FAIT if configurations.get("fiche_champs") else A_FAIRE, "donnees", "champs de la fiche d'appel")
    )
    etapes.append(
        Etape("panne", CONSEILLE, FAIT if configurations.get("panne") else A_FAIRE, "etablissement", "repli en cas de panne")
    )
    etapes.append(
        Etape("phrases", CONSEILLE, FAIT if configurations.get("phrases_regles") else A_FAIRE, "phrases", "règles des phrases du code")
    )
    # Lignes conditionnelles : en temps réel la fiche d'appel n'est pas écrite pendant l'appel (sans objet) ; un spécialisé qui
    # reçoit le réglage de son principal le dit « hérité du principal » quand il est fait.
    temps_reel = bool(getattr(effective, "is_realtime", False))
    for etape in etapes:
        if etape.id == "fiche" and temps_reel:
            etape.etat = SANS_OBJET
        cle = CLES_HERITEES.get(etape.id)
        if cle in suivies_du_principal and etape.etat == FAIT:
            etape.etat = HERITE
    return etapes


# La clé de réglage que lit chaque ligne : celle qu'un spécialisé reçoit de son principal.
CLES_HERITEES = {"etablissement": "etablissement_id", "fiche": "fiche_champs", "panne": "panne", "phrases": "phrases_regles"}


def en_dicts(etapes: list[Etape]) -> list[dict[str, Any]]:
    return [asdict(e) for e in etapes]


@dataclass
class Contexte:
    """Ce que le calcul a lu : la liste « Prêt à publier » en tire aussi les réglages sans effet (même lecture, une seule fois)."""

    definition: Mapping[str, Any]
    configurations: Mapping[str, Any]
    temps_reel: bool
    specialiste: bool


async def lire(organization_id: int, workflow_id: int) -> list[Etape]:
    """Le calcul pour un agent de l'organisation (``ModeleRefuse`` 404 pour l'agent d'une autre). Lecture seule."""
    return (await lire_avec_contexte(organization_id, workflow_id))[0]


async def lire_avec_contexte(organization_id: int, workflow_id: int) -> tuple[list[Etape], Contexte]:
    from api.db import db_client
    from api.services.builder.tests_agent import publication, stockage
    from api.services.configuration.ai_model_configuration import _effective_for_workflow
    from api.services.etablissements.stockage import lire_etablissements
    from api.services.modeles_reglages import service as modeles

    active = await modeles.configuration_active(workflow_id, organization_id)
    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    brouillon = await db_client.get_draft_version(workflow_id)
    definition_modele = brouillon if brouillon is not None else getattr(workflow, "released_definition", None)
    definition = getattr(definition_modele, "workflow_json", None) or getattr(workflow, "workflow_definition", None) or {}
    variables = getattr(definition_modele, "template_context_variables", None) or {}
    configurations = active["configurations"]

    try:
        effective = await _effective_for_workflow(organization_id=organization_id, workflow_configurations=configurations)
    except Exception:  # noqa: BLE001 -- une configuration illisible = des briques manquantes, pas une erreur de page
        effective = None

    uuids = outils_du_graphe(definition)
    actifs = {t.tool_uuid for t in await db_client.get_tools_by_uuids(uuids, organization_id)} if uuids else set()

    fiche = None
    fiche_id = configurations.get("etablissement_id")
    if isinstance(fiche_id, str) and fiche_id.strip():
        catalogue = await lire_etablissements(organization_id)
        fiche = next((e for e in catalogue.etablissements if e.id == fiche_id.strip()), None)

    tests = await stockage.lister(organization_id, workflow_id)
    problemes = await publication.problemes_des_tests_obligatoires(
        organization_id, workflow_id, active.get("version_number")
    )
    from api.services.groupe.passations import agent_principal_de
    from api.services.heritage_reglages import cles_suivies_du_principal

    principal = agent_principal_de(configurations)
    etapes = calculer(
        definition=definition,
        variables_du_modele=variables,
        configurations=configurations,
        effective=effective,
        outils_actifs=actifs,
        fiche=fiche,
        tests=tests,
        problemes_tests_obligatoires=problemes,
        suivies_du_principal=cles_suivies_du_principal(configurations),
    )
    contexte = Contexte(
        definition=definition,
        configurations=configurations,
        temps_reel=bool(getattr(effective, "is_realtime", False)),
        specialiste=principal is not None and principal != workflow_id,
    )
    return etapes, contexte
