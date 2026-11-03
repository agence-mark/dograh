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
) -> list[Etape]:
    """Les étapes, dans l'ordre d'un appel. Pure."""
    etapes: list[Etape] = []

    manquantes = variables_manquantes(definition, variables_du_modele)
    etapes.append(
        Etape("variables", REQUIS, A_FAIRE if manquantes else FAIT, "agent", "prompts, phrases et variables du modèle", manquantes)
    )

    briques = briques_manquantes(effective)
    etapes.append(
        Etape("briques", REQUIS, A_FAIRE if briques else FAIT, "briques", "configuration effective des modèles", briques)
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
        )
    )

    if problemes_tests_obligatoires:
        etapes.append(
            Etape("tests", REQUIS, A_FAIRE, "agent", "tests obligatoires de l'agent et leurs dernières exécutions",
                  [str(p.get("nom") or p.get("slug")) for p in problemes_tests_obligatoires])
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
    return etapes


def en_dicts(etapes: list[Etape]) -> list[dict[str, Any]]:
    return [asdict(e) for e in etapes]


async def lire(organization_id: int, workflow_id: int) -> list[Etape]:
    """Le calcul pour un agent de l'organisation (``ModeleRefuse`` 404 pour l'agent d'une autre). Lecture seule."""
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
    return calculer(
        definition=definition,
        variables_du_modele=variables,
        configurations=configurations,
        effective=effective,
        outils_actifs=actifs,
        fiche=fiche,
        tests=tests,
        problemes_tests_obligatoires=problemes,
    )
