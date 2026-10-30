"""[.mark] agent-facon-tala, C4 : l'issue d'appel métier à TOUTE fin d'appel.

Constat du 30/10 (S2, S4, S6, S8, S11, S12) : l'issue métier (la liste ``call_dispositions`` de l'agent) n'était
posée que lorsque l'agent prenait lui-même sa fin ; un appel qui s'arrête autrement (raccrochage, inactivité, fin
du clavier) gardait le seul mécanisme (``user_hangup``). Le mécanisme existant de l'issue (le classement final
``DispositionExtractionService``) est donc appliqué à chaque fin, par le même code au téléphone
(``PipecatEngine.end_call_with_reason``) et au clavier (``complete_text_chat_session``), et il lit maintenant la
FICHE de l'appel (ce qui a été noté) en plus de la conversation, que les passations raccourcissent.

``ISSUE_FLOUE`` : quand le motif n'est pas clair (le classement ne retient aucune issue, ou ne finit pas à temps)
alors que la personne a parlé, l'issue prise est celle-là, **seulement si la liste des issues de l'agent la
contient** : jamais inventée, jamais écrite d'office. Une liste sans cette valeur garde l'état d'avant.

Aucun mot de métier : le code d'une issue vient toujours de la liste réglée sur l'agent.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Le code de la plateforme pour « le motif de l'appel n'est pas clair ».
ISSUE_FLOUE = "appel_incomplet"


def _codes(options: Iterable[Any]) -> list[str]:
    return [getattr(o, "code", None) or (o.get("code") if isinstance(o, dict) else None) for o in options]


def issue_de_secours(options: Iterable[Any]) -> str | None:
    """``ISSUE_FLOUE`` si la liste des issues de l'agent la contient (casse ignorée, code rendu tel qu'écrit
    dans la liste), sinon ``None``. ⛔ Ne lève jamais."""
    try:
        for code in _codes(options):
            if isinstance(code, str) and code.casefold() == ISSUE_FLOUE.casefold():
                return code
    except Exception:  # noqa: BLE001
        pass
    return None


def issue_finale(options: Iterable[Any], retenue: str | None, *, a_parle: bool) -> str | None:
    """L'issue à poser : celle que le classement a retenue ; faute de motif clair, ``ISSUE_FLOUE`` (si la liste
    l'a) quand la personne a parlé ; sinon ``None`` (l'état mécanique reste). ⛔ Ne lève jamais."""
    if retenue:
        return retenue
    if not a_parle:
        return None
    return issue_de_secours(options)


def texte_de_la_fiche(reglages: Any, gathered_context: dict | None) -> str | None:
    """Ce que la fiche a noté, en lignes, pour le classement final (``etat_de_la_fiche``). ``None`` quand la
    fiche est éteinte ou vide. ⛔ Ne lève jamais."""
    try:
        if not reglages or not gathered_context:
            return None
        from api.services.workflow.fiche_au_fil_de_leau import etat_de_la_fiche

        return etat_de_la_fiche(reglages, gathered_context)
    except Exception:  # noqa: BLE001 -- le classement se fait sans la fiche
        return None
