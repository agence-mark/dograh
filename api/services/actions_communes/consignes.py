"""[.mark] Lot 7b, ligne 28 : les consignes qu'un retour de fiche donne au modèle (``a_faire``), écrites en UN seul endroit, avec leur rang.

Chaque ``poser_*`` du métier rend sa consigne ET son rang dans ``Du.consignes`` ; ``une_consigne`` les range par priorité, sans doublon, et n'en jette aucune qui soit due :
la sortie (proposer de laisser un message à l'équipe) remplace les consignes de refus, d'issue et de question, jamais celle de l'allergie.
"""

from __future__ import annotations

from collections.abc import Iterable

from api.services.actions_communes import journal_du_dit as J

# Le rang, du plus prioritaire au moins prioritaire : allergie > sortie > issue > refus à dire > question > rien changé > reste.
ALLERGIE, SORTIE, ISSUE, REFUS_A_DIRE, QUESTION, RIEN_CHANGE, RESTE = range(7)
RANGS_QUE_LA_SORTIE_REMPLACE = frozenset({ISSUE, REFUS_A_DIRE, QUESTION})
SEPARATEUR = " ; "


def en_une_phrase(textes: Iterable[str | None]) -> str | None:
    """Les textes de consigne mis bout à bout, sans doublon ni vide ; ``None`` s'il n'en reste aucun."""
    return SEPARATEUR.join(dict.fromkeys(t for t in textes if t)) or None


def une_consigne(consignes: Iterable[tuple[int, str]], boucle: bool = False) -> str | None:
    """Ce que le retour dit au modèle : toutes les consignes dues, par rang. ``boucle`` (la même chose redite sans issue, ``Du.boucle``) pose la sortie ; une sortie, d'où qu'elle
    vienne, remplace les consignes d'issue, de refus à dire et de question. ``None`` : rien à dire."""
    posees = [(int(rang), str(texte)) for rang, texte in consignes if texte]
    if boucle:
        posees.append((SORTIE, J.A_FAIRE_SORTIE))
    if any(rang == SORTIE for rang, _ in posees):
        posees = [(rang, texte) for rang, texte in posees if rang not in RANGS_QUE_LA_SORTIE_REMPLACE]
    return en_une_phrase(texte for _, texte in sorted(posees, key=lambda x: x[0]))
