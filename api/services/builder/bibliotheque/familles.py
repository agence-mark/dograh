"""[.mark] Bibliothèque : les familles d'éléments (``08-inventaire-bibliotheque.md``, B44).

Le contenu d'un élément est libre (un objet JSON) : le code ne connaît PAS le métier, seulement la famille.
``mode`` dit comment le builder applique la famille à un agent :

* ``applique`` : une action écrit dans l'agent (phrases du code, lexique, réglages) ;
* ``fournit``  : le builder reçoit le contenu et l'écrit lui-même avec les actions de construction.
"""

from __future__ import annotations

from dataclasses import dataclass

MODE_APPLIQUE = "applique"
MODE_FOURNIT = "fournit"


@dataclass(frozen=True)
class Famille:
    slug: str
    libelle: str
    groupe: str
    cible: str
    mode: str = MODE_FOURNIT


def _f(slug: str, libelle: str, groupe: str, cible: str, mode: str = MODE_FOURNIT) -> tuple[str, Famille]:
    return slug, Famille(slug, libelle, groupe, cible, mode)


FAMILLES: dict[str, Famille] = dict(
    [
        # 1. Ce qui construit l'agent
        _f("structures", "Structures", "construit", "graphe (nœuds, liaisons, types)"),
        _f("prompt-general", "Prompt général", "construit", "nœud global"),
        _f("moules-etape", "Moules d'étape", "construit", "prompts de nœud"),
        _f("conditions-passage", "Conditions de passage", "construit", "liaisons"),
        _f("personas", "Personas", "construit", "parties persona du prompt"),
        _f("phrases-fixes", "Phrases fixes", "construit", "phrases d'accueil et de fin"),
        _f("phrases-du-code", "Phrases du code", "construit", "réglages Phrases (catalogue des motifs)", MODE_APPLIQUE),
        _f("variables-gabarit", "Variables de gabarit", "construit", "injections au départ de l'appel"),
        # 2. Ce qui fait travailler l'agent
        _f("fiches-types", "Fiches types", "travaille", "fiche de l'appel"),
        _f("consignes-greffier", "Consignes du greffier", "travaille", "consigne du greffier"),
        _f("modeles-outils", "Modèles d'outils", "travaille", "outils (définition)"),
        _f("modeles-connecteurs", "Modèles de connecteurs", "travaille", "connecteurs (sans secret)"),
        _f("modeles-transfert", "Modèles de transfert", "travaille", "transferts humains"),
        _f("modeles-base-connaissances", "Modèles de base de connaissances", "travaille", "base de connaissances"),
        _f("objets-agent-types", "Objets de l'agent types", "travaille", "objets de l'agent"),
        # 3. Ce qui règle l'agent
        _f("modeles-reglages", "Modèles de réglages", "regle", "réglages de l'agent", MODE_APPLIQUE),
        _f("lexiques", "Lexiques", "regle", "lexique, mots-clés de la reconnaissance", MODE_APPLIQUE),
        _f("garde-fous", "Garde-fous", "regle", "registre des garde-fous"),
        # 4. Ce qui suit l'appel
        _f("apres-appel", "Après-appel", "suit", "après l'appel"),
        _f("issues-appel", "Issues d'appel", "suit", "issues réservées"),
        # 5. Le site
        _f("recettes-site", "Recettes de site", "site", "agent de site"),
        # 6. Ce qui prouve l'agent
        _f("scenarios-test", "Scénarios de test types", "prouve", "tests"),
        _f("personnages-appelant", "Personnages d'appelant", "prouve", "appelant simulé"),
        _f("serie-manipulation", "Série manipulation", "prouve", "tests"),
        _f("criteres-types", "Critères types", "prouve", "tests"),
        # 7. Ce qui guide le builder
        _f("questionnaire-audit", "Questionnaire d'audit", "guide", "builder"),
        _f("documents-conception-types", "Documents de conception types", "guide", "builder"),
        _f("conventions-mark", "Conventions .mark", "guide", "builder (couche 1 du contexte)"),
        _f("regles-redaction", "Règles de rédaction", "guide", "builder"),
        _f("methode-builder", "Méthode du builder", "guide", "builder"),
    ]
)

FAMILLE_METHODE = "methode-builder"
FAMILLE_CONVENTIONS = "conventions-mark"


def famille(slug: str) -> Famille | None:
    return FAMILLES.get(slug)
