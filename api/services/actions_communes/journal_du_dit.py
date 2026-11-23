"""[.mark] Clôture de la Partie 1, lot B3 (audit du code M5) : le journal de ce que le code a dit dans l'appel, une seule mémoire.

Avant : cinq mémoires, chacune pour un cas (la fermeture ``fermeture_dite``, les règles d'un article ``regles_dites_par_le_code``, les remises
``remises_dites``, les phrases du code dans le tour ``prefixes_dits``, la relecture) ; le minimum et le refus d'une zone n'en avaient aucune et se
redisaient à chaque fiche (C7, H6, DF7) ; aucun compteur d'échec hors du choix d'une réservation (C5, C10 : « pardon » ou le parfum quatre fois).

Le journal vit dans le dossier de l'action (le panier, le dossier de la réservation) : ``{clé du fait: {"fois": n, "tour": t}}``. La clé est le
fait lui-même (sa phrase, ou un nom fermé : ``fermeture``, ``remise:<ref>``) : un fait qui change (un autre montant manquant) est un autre fait.
Deux usages, lus ici seulement :
* ``une_fois`` : dit une fois par appel, jamais redit (fermeture, règle d'un article, remise) ;
* ``fait_redit`` : un refus ou un fait bloquant que la personne retombe : la première fois, la phrase entière par le code ; la deuxième, le code
  ne la redit pas et le modèle propose une issue avec ses mots ; à la troisième (deuxième échec), la sortie : proposer de laisser un message à
  l'équipe (la même consigne que le choix d'une réservation, E28). Dans un même tour, un fait n'est compté et dit qu'une fois.
"""

from __future__ import annotations

from typing import Any

CLE = "journal_du_dit"
FERMETURE = "fermeture"
A_FAIRE_ISSUE = "le code le lui a déjà dit : ne le redis pas mot pour mot ; propose-lui une issue avec tes mots"
A_FAIRE_SORTIE = "elle y revient pour la troisième fois sans issue : propose-lui de laisser un message à l'équipe"  # B4 (M8) : passage vers le service

PREMIERE, ISSUE, SORTIE, DEJA_DANS_CE_TOUR = "premiere", "issue", "sortie", "deja_dans_ce_tour"


def _journal(dossier: dict[str, Any]) -> dict[str, Any]:
    j = dossier.get(CLE)
    if not isinstance(j, dict):
        j = dossier[CLE] = {}
    return j


def fois(dossier: Any, cle: str) -> int:
    """Combien de fois le fait a été dit dans l'appel (0 : jamais)."""
    if not isinstance(dossier, dict):
        return 0
    return int(((dossier.get(CLE) or {}).get(cle) or {}).get("fois") or 0)


def deja_dit(dossier: Any, cle: str) -> bool:
    return fois(dossier, cle) > 0


def noter(dossier: dict[str, Any], cle: str, tour: Any = None) -> int:
    """Le fait est dit (une fois de plus, sauf s'il l'est déjà dans ce même tour) : rend le nombre de fois."""
    e = _journal(dossier).setdefault(cle, {"fois": 0, "tour": None})
    if not (tour is not None and e.get("tour") == tour):
        e["fois"] = int(e.get("fois") or 0) + 1
        e["tour"] = tour
    return int(e["fois"])


def une_fois(dossier: dict[str, Any], cle: str, tour: Any = None) -> bool:
    """Vrai la première fois que le fait est dit dans l'appel (il est alors noté) ; ensuite, faux : il n'est jamais redit."""
    if deja_dit(dossier, cle):
        return False
    noter(dossier, cle, tour)
    return True


def fait_redit(dossier: dict[str, Any], cle: str, tour: Any) -> str:
    """Un refus ou un fait bloquant de plus sur la même clé : ``PREMIERE`` (le code le dit en entier), ``ISSUE`` (déjà dit : le modèle propose une
    issue), ``SORTIE`` (deuxième échec : proposer un message à l'équipe), ``DEJA_DANS_CE_TOUR`` (une seconde fiche du même tour : rien de plus)."""
    e = (dossier.get(CLE) or {}).get(cle) if isinstance(dossier.get(CLE), dict) else None
    if isinstance(e, dict) and tour is not None and e.get("tour") == tour:
        return DEJA_DANS_CE_TOUR
    n = noter(dossier, cle, tour)
    return PREMIERE if n == 1 else (ISSUE if n == 2 else SORTIE)


CLE_BOUCLE = "boucle"
FOIS_AVANT_LA_SORTIE = 3


def boucle(dossier: dict[str, Any], signature: Any, lignes_inchangees: bool) -> bool:
    """RC6 (contrôle long, lot 3) : la MÊME chose (la même question posée, le même fait bloquant, le même refus) rendue ``FOIS_AVANT_LA_SORTIE`` fois de suite sans que la
    commande avance : vrai à la troisième, et ensuite tant que ça dure : la sortie (proposer un message à l'équipe, ``A_FAIRE_SORTIE``). Une signature vide (rien de répété),
    une autre signature ou une commande qui avance remet le compte à zéro. Le compte vit dans le dossier, comme le journal."""
    if not isinstance(dossier, dict):
        return False
    if not signature or not any(signature) or not lignes_inchangees:
        dossier.pop(CLE_BOUCLE, None)
        return False
    e = dossier.get(CLE_BOUCLE)
    if isinstance(e, dict) and e.get("signature") == signature:
        e["fois"] = int(e.get("fois") or 0) + 1
    else:
        e = dossier[CLE_BOUCLE] = {"signature": signature, "fois": 1}
    return int(e["fois"]) >= FOIS_AVANT_LA_SORTIE


def consigne(etape: str) -> str | None:
    """Ce que le retour dit au modèle selon les fois : rien la première fois (le code a parlé), l'issue, puis la sortie."""
    return {ISSUE: A_FAIRE_ISSUE, SORTIE: A_FAIRE_SORTIE}.get(etape)
