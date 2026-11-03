"""[.mark] Builder : les clés de stockage, les variables d'environnement et les bornes.

Tout vit dans ``organization_configurations`` (clé texte libre, valeur JSON) : aucune migration (R0-6).
"""

from __future__ import annotations

import os

# L'organisation .mark qui porte la bibliothèque : lue par toutes, écrite par ses seuls membres.
VARIABLE_ORG_BIBLIOTHEQUE = "MARK_BIBLIOTHEQUE_ORGANISATION_ID"

PREFIXE_BIBLIO = "MARK_BIBLIO:"  # MARK_BIBLIO:<famille>:<slug>
PREFIXE_PROPOSITION = "MARK_BIBLIO_PROPOSITION:"  # MARK_BIBLIO_PROPOSITION:<id>
PREFIXE_USAGE = "MARK_BIBLIO_USAGE:"  # MARK_BIBLIO_USAGE:<famille>:<slug>
PREFIXE_BUILDER = "MARK_BUILDER:"  # MARK_BUILDER:<workflow>:fiche | contexte | conception | conversation
PREFIXE_TESTS = "MARK_TESTS:"  # MARK_TESTS:<workflow>:<test>  (lot 6)
PREFIXE_RESULTATS = "MARK_TESTS_RESULTATS:"  # MARK_TESTS_RESULTATS:<workflow>:<test>  (3 dernières exécutions)
CLE_CERVEAU = "MARK_BUILDER_CERVEAU"  # réglages du cerveau, dans l'organisation des réglages .mark
CLE_PRIX = "MARK_BUILDER_PRIX"  # table de prix par modèle (C2), même organisation que le cerveau
CLE_PREFERENCES = "MARK_BUILDER_PREFERENCES"  # user_configurations (couche 3 du contexte permanent)

# Bornes (R0-6).
VERSIONS_MAX = 20
CONTENU_MAX_OCTETS = 10_000
FICHE_MAX_OCTETS = 100_000
CONVERSATION_MESSAGES_MAX = 200
CONVERSATION_OCTETS_MAX = 1_000_000  # 1 Mo : la conversation enregistrée, vérifiée en octets (revue N4)
MESSAGE_OCTETS_MAX = 20_000  # un message seul plus long est raccourci quand plus rien d'autre ne se résume
IMPORT_MAX_OCTETS = 200_000


def organisation_bibliotheque() -> int | None:
    """L'organisation .mark de la bibliothèque (le Labo), ou ``None`` si elle n'est pas réglée.

    Source unique : l'organisation marquée Labo en base (``MARK_ESPACE``, lue par un cache court). La variable
    ``MARK_BIBLIOTHEQUE_ORGANISATION_ID`` n'est que le repli tant qu'aucune organisation n'est marquée (C8).
    """
    from api.services.equipe_mark.espaces import labo_en_cache

    marque = labo_en_cache()
    if marque is not None:
        return marque
    brut = (os.environ.get(VARIABLE_ORG_BIBLIOTHEQUE) or "").strip()
    return int(brut) if brut.isdigit() else None


def cle_builder(workflow_id: int, partie: str) -> str:
    return f"{PREFIXE_BUILDER}{workflow_id}:{partie}"


def cle_test(workflow_id: int, slug: str) -> str:
    return f"{PREFIXE_TESTS}{workflow_id}:{slug}"


def cle_resultats(workflow_id: int, slug: str) -> str:
    return f"{PREFIXE_RESULTATS}{workflow_id}:{slug}"

# U7 (bibliothèque v2) : trois lignes de l'organisation .mark, aucune migration. Leur clé ne commence pas par PREFIXE_BIBLIO
# (« MARK_BIBLIO: ») : elles ne se confondent jamais avec un élément.
CLE_FICHES = "MARK_BIBLIO_FICHES"  # {"fiches": {famille: {description, quand, comment}}}
CLE_FAMILLES = "MARK_BIBLIO_FAMILLES"  # {"familles": {slug: {libelle, groupe, cible}}} : les familles créées à l'écran
CLE_ETIQUETTES = "MARK_BIBLIO_ETIQUETTES"  # {"etiquettes": [nom, ...]}
CLE_DOSSIERS = "MARK_BIBLIO_DOSSIERS"  # {"dossiers": {famille: [chemin, ...]}} : les sous-dossiers déclarés (même vides)
DEPOT_MAX_OCTETS = 15 * 1024 * 1024
