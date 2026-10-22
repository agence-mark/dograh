"""[.mark] The catalogue of sentences (E5) and the establishment's trade terms, for a call.

Read with the establishments, from the same in-memory copy (B3), at pick-up.

- ``injecter_phrases``: each sentence of the catalogue becomes ``{{variable}}`` in the
  call context; a sentence placed at the establishment's level takes the
  establishment's content alone when one is served ([.mark] F-8: nothing is
  inherited), the organization's when none is. A value
  already in the context is kept (a replay, a pre-call fetch). Empty content: nothing.
  [.mark] Lot 4 (F6, M6): the content is filled ONCE with the call's variables, so
  ``{{etablissement}}`` written in a sentence says the fiche's name; a variable the
  call does not know stays as written, and a sentence never fills another (no chain).
- ``lexique_avec_etablissement``: the terms an establishment adds to the
  organization's vocabulary (E6: « adding a brand to the lexicon »), appended when
  none of their spellings is already there; the organization's terms never change.

⛔ Zero loss: an empty catalogue, or no establishment, gives back the SAME objects.
Nothing here raises.
"""

from __future__ import annotations

import re

from loguru import logger

from api.schemas.phrases import CataloguePhrases
from api.utils.template_renderer import (
    TEMPLATE_VAR_PATTERN,
    _resolve_template_value,
    is_builtin_variable,
)


def _vide(valeur) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def valeurs_des_phrases(catalogue: CataloguePhrases, etablissement) -> dict[str, str]:
    """[.mark] F-8 (Evan, 22/10): a sentence placed at the establishment's level takes, when an
    establishment is served, ITS content alone (none: nothing is said, never the organization's);
    with no establishment, the organization's content. A sentence at the organization's level is
    the same for everyone."""
    propres = getattr(etablissement, "phrases", None) or {}
    valeurs: dict[str, str] = {}
    for phrase in catalogue.phrases:
        contenu = phrase.contenu
        if phrase.niveau == "etablissement" and etablissement is not None:
            contenu = propres.get(phrase.variable)
        if not _vide(contenu):
            valeurs[phrase.variable] = contenu
    return valeurs


def remplir_une_fois(contenu: str, contexte: dict) -> str:
    """[.mark] Lot 4 (F6): the call's variables in a sentence, in ONE pass over ``contexte``.

    What the context does not hold is left as written (the engine renders the prompt
    later, with the same rule as before): unknown variables, and the clock's variables,
    which must stay fresh at render time. Never raises: on any problem, the sentence as is.
    """
    if "{{" not in contenu:
        return contenu

    def _remplacer(trouve: re.Match) -> str:
        try:
            chemin = trouve.group(1).strip()
            if is_builtin_variable(chemin):
                return trouve.group(0)
            filtre = trouve.group(2).strip() if trouve.group(2) else None
            valeur = _resolve_template_value(
                chemin, filtre, trouve.group(3).strip() if trouve.group(3) else None, contexte, None
            )
            if valeur is None or isinstance(valeur, (dict, list)) or str(valeur) == "":
                return trouve.group(0)
            return str(valeur)
        except Exception:  # noqa: BLE001 -- a sentence is never worth a call
            return trouve.group(0)

    try:
        return re.sub(TEMPLATE_VAR_PATTERN, _remplacer, contenu)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Sentence variables not filled, the sentence goes as written: {erreur!r}")
        return contenu


def injecter_phrases(contexte: dict, catalogue: CataloguePhrases | None, etablissement) -> dict:
    if catalogue is None or not catalogue.phrases:
        return contexte
    try:
        enrichi = dict(contexte)
        for variable, contenu in valeurs_des_phrases(catalogue, etablissement).items():
            if _vide(enrichi.get(variable)):
                # Lot 4 (F6): filled from the context as it was BEFORE any sentence went in.
                enrichi[variable] = remplir_une_fois(contenu, contexte)
        return enrichi
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.error(f"[.mark] Sentences not injected, the call goes on without them: {erreur!r}")
        return contexte


def lexique_avec_etablissement(lexique, etablissement):
    termes = getattr(etablissement, "termes_lexique", None) or []
    if not termes or lexique is None:
        return lexique
    try:
        formes: set[str] = set()
        for terme in lexique.termes:
            formes |= terme.formes_normalisees()
        ajoutes = []
        for terme in termes:
            siennes = terme.formes_normalisees()
            if siennes & formes:
                continue
            ajoutes.append(terme)
            formes |= siennes
        if not ajoutes:
            return lexique
        return lexique.model_copy(update={"termes": [*lexique.termes, *ajoutes]})
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Establishment's terms not added, the organization's vocabulary is used: {erreur!r}")
        return lexique


async def lexique_de_lappel_avec_etablissement(run_configs, organization_id, workflow_id, contexte: dict):
    """The vocabulary of a call already set up (keyboard end-of-call pass): the
    organization's, plus the terms of the establishment STAMPED on the run, so the
    pass reads what the conversation read. Never raises."""
    from api.services.etablissements.appel import CLE_ETABLISSEMENT_CHOISI, lire_lappel
    from api.services.lexique.reglages import (
        interrupteur_allume,
        lire_lexique_de_lappel,
    )

    lexique = await lire_lexique_de_lappel(run_configs, organization_id)
    try:
        estampille = ((contexte or {}).get("runtime_configuration") or {}).get("etablissement") or {}
        if not estampille.get("id") or not interrupteur_allume(run_configs):
            return lexique
        lecture = await lire_lappel(
            organization_id, workflow_id, {CLE_ETABLISSEMENT_CHOISI: estampille["id"]}
        )
        if lecture.servi is None or lecture.servi.etablissement.id != estampille["id"]:
            return lexique
        return lexique_avec_etablissement(lexique, lecture.servi.etablissement)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Establishment's terms not re-read for the end-of-call pass: {erreur!r}")
        return lexique
