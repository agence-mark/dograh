"""[.mark] Clôture de la Partie 1, lot B3 (audit du code M5) : le journal de ce que le code a dit dans l'appel, une seule mémoire.

Avant : cinq mémoires, chacune pour un cas (la fermeture ``fermeture_dite``, les règles d'un article ``regles_dites_par_le_code``, les remises
``remises_dites``, les phrases du code dans le tour ``prefixes_dits``, la relecture) ; le minimum et le refus d'une zone n'en avaient aucune et se
redisaient à chaque fiche (C7, H6, DF7) ; aucun compteur d'échec hors du choix d'une réservation (C5, C10 : « pardon » ou le parfum quatre fois).

Le journal vit dans la conversation du dossier de l'action (le panier, le dossier de la réservation) : ``{clé du fait: {"fois": n, "tour": t}}``. La clé est le
fait lui-même (son identité : ``identite_du_refus`` pour un refus, ou un nom fermé : ``fermeture``, ``remise:<ref>``) : un fait qui change (un autre montant manquant) est un autre fait.
Jamais le texte d'une suggestion : un texte qui change d'un tour à l'autre ne remet pas le compteur à zéro.
Deux usages, lus ici seulement :
* ``une_fois`` : dit une fois par appel, jamais redit (fermeture, règle d'un article, remise) ;
* ``fait_redit`` : un refus ou un fait bloquant que la personne retombe : la première fois, la phrase entière par le code ; la deuxième, le code
  ne la redit pas et le modèle propose une issue avec ses mots ; à la troisième (deuxième échec), la sortie : proposer de laisser un message à
  l'équipe (la même consigne que le choix d'une réservation, E28). Dans un même tour, un fait n'est compté et dit qu'une fois.
"""

from __future__ import annotations

import json
from typing import Any

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import resultat as R

CLE = "journal_du_dit"
FERMETURE = "fermeture"
A_FAIRE_ISSUE = "elle a déjà entendu ce refus : ne le redis pas mot pour mot ; propose-lui une issue avec tes mots"
A_FAIRE_SORTIE = "elle revient sur la même chose sans issue : propose-lui de laisser un message à l'équipe"  # B4 (M8) : passage vers le service

PREMIERE, ISSUE, SORTIE, DEJA_DANS_CE_TOUR = "premiere", "issue", "sortie", "deja_dans_ce_tour"


_FAITS_DE_TENUE = (R.CLE_NUMERO_RETENU, R.CLE_SECOND_NUMERO_RETENU, R.CLE_NUMERO_AFFICHE, R.CLE_NUMERO_S_AFFICHE)  # ce qui change d'un tour à l'autre sans changer le refus


def identite_du_refus(refus: Any) -> str:
    """La clé du journal pour un refus d'un module : son statut, son manque et ses faits. Une valeur simple (texte, nombre, vrai/faux) entre avec sa valeur ; une liste ou un
    dictionnaire (des propositions qui changent d'un tour à l'autre) entre par son seul NOM : deux refus qui n'ont pas les mêmes faits ne se confondent jamais, et un texte
    de suggestion qui change ne remet jamais le compteur à zéro."""
    objet = {k: (v if isinstance(v, (str, int, float)) else None) for k, v in sorted((refus.faits or {}).items()) if k not in _FAITS_DE_TENUE}
    return f"refus {json.dumps([refus.statut, refus.manque, objet], ensure_ascii=False)}"


def _journal(dossier: dict[str, Any]) -> dict[str, Any]:
    """Le journal, sous la conversation du dossier (G3 : jamais à plat à côté de la commande), créé au premier besoin."""
    tenue = CONV.de(dossier)
    j = tenue.get(CLE)
    if not isinstance(j, dict):
        j = tenue[CLE] = {}
    return j


def _lu(dossier: Any) -> dict[str, Any]:
    """Le journal sans le créer (``{}`` si le dossier n'en a pas)."""
    j = (dossier.get(CONV.CLE) or {}).get(CLE) if isinstance(dossier, dict) else None
    return j if isinstance(j, dict) else {}


def oublier(dossier: dict[str, Any], cle: str) -> None:
    """Le fait n'est plus noté : ses essais repartent."""
    _lu(dossier).pop(cle, None)


def reprendre(dossier: dict[str, Any], copie: dict[str, Any], avant: dict[str, Any] | None = None) -> None:
    """Ce que la lecture jouée sur une copie a écrit au journal revient au dossier : seul lui, de la tenue, y revient. ``avant`` : le journal tel qu'il était à la copie ; seules les
    entrées que la lecture a changées ou retirées reviennent, jamais celles qu'une fiche a écrites pendant ce temps (le fait accompli, les faits d'allergie)."""
    lue = _lu(copie)
    if avant is None:
        if lue != _lu(dossier):
            CONV.de(dossier)[CLE] = lue
        return
    journal = _journal(dossier) if (lue != avant) else None
    if journal is None:
        return
    for cle, entree in lue.items():
        if avant.get(cle) != entree:
            journal[cle] = entree
    for cle in [c for c in avant if c not in lue]:
        journal.pop(cle, None)


def entree(dossier: Any, cle: str) -> dict[str, Any] | None:
    """L'entrée du journal pour ce fait (``None`` : jamais dit)."""
    e = _lu(dossier).get(cle)
    return e if isinstance(e, dict) else None


def poser(dossier: dict[str, Any], cle: str, tour: Any, **plus: Any) -> None:
    """Le fait est dit, avec ce que son entrée garde en plus (une empreinte, un texte) : l'entrée est écrite neuve."""
    _journal(dossier)[cle] = {"fois": 1, "tour": tour, **plus}


def oublier_le_groupe(dossier: dict[str, Any], groupe: str) -> None:
    """Tous les faits posés avec ce ``groupe`` (``poser(..., groupe=...)``) ne sont plus notés : le groupe est une étiquette de l'entrée, jamais lue dans le nom de la clé."""
    j = _lu(dossier)
    for cle in [c for c, e in j.items() if isinstance(e, dict) and e.get("groupe") == groupe]:
        del j[cle]


def fois(dossier: Any, cle: str) -> int:
    """Combien de fois le fait a été dit dans l'appel (0 : jamais)."""
    if not isinstance(dossier, dict):
        return 0
    return int((_lu(dossier).get(cle) or {}).get("fois") or 0)


def deja_dit(dossier: Any, cle: str) -> bool:
    return fois(dossier, cle) > 0


def noter(dossier: dict[str, Any], cle: str, tour: Any = None) -> int:
    """Le fait est dit (une fois de plus, sauf s'il l'est déjà dans ce même tour) : rend le nombre de fois."""
    e = _journal(dossier).setdefault(cle, {"fois": 0, "tour": None})
    if not (tour is not None and e.get("tour") == tour):
        e["fois"] = int(e.get("fois") or 0) + 1
        e["tour"] = tour
    return int(e["fois"])


FAIT_ACCOMPLI = "fait_accompli"  # la dernière phrase de fait accompli dite par le code (enregistrée, changée, annulée) : le repli la redit (B2, M3, règle 3 ; lot 7a, ligne 61)


def dire_le_fait(dossier: dict[str, Any], texte: str, tour: Any = None) -> None:
    """Le code vient de dire le fait accompli : une entrée du journal, avec sa phrase."""
    noter(dossier, FAIT_ACCOMPLI, tour)
    _journal(dossier)[FAIT_ACCOMPLI]["texte"] = texte


def fait_accompli(dossier: Any) -> str | None:
    """La dernière phrase de fait accompli dite par le code, ``None`` si aucune."""
    return str((_lu(dossier).get(FAIT_ACCOMPLI) or {}).get("texte") or "").strip() or None


def une_fois(dossier: dict[str, Any], cle: str, tour: Any = None) -> bool:
    """Vrai la première fois que le fait est dit dans l'appel (il est alors noté) ; ensuite, faux : il n'est jamais redit."""
    if deja_dit(dossier, cle):
        return False
    noter(dossier, cle, tour)
    return True


def fait_redit(dossier: dict[str, Any], cle: str, tour: Any, seuil: int) -> str:
    """Un refus ou un fait bloquant de plus sur la même clé : ``PREMIERE`` (le code le dit en entier), ``ISSUE`` (déjà dit : le modèle propose une
    issue), ``SORTIE`` (au ``seuil`` : le réglage du restaurant, que l'appelant donne ; proposer un message à l'équipe), ``DEJA_DANS_CE_TOUR`` (une seconde fiche du même tour : rien de plus)."""
    e = _lu(dossier).get(cle)
    if isinstance(e, dict) and tour is not None and e.get("tour") == tour:
        return DEJA_DANS_CE_TOUR
    n = noter(dossier, cle, tour)
    return PREMIERE if n == 1 else (ISSUE if n < seuil else SORTIE)


CLE_BOUCLE = "boucle"


def boucle(dossier: dict[str, Any], signature: Any, lignes_inchangees: bool, seuil: int) -> bool:
    """RC6 (contrôle long, lot 3) : la MÊME chose (la même question posée, le même fait bloquant, le même refus) rendue ``seuil`` fois de suite (le réglage du restaurant, que l'appelant donne) sans que la
    commande avance : vrai au ``seuil``, et ensuite tant que ça dure : la sortie (proposer un message à l'équipe, ``A_FAIRE_SORTIE``). Une signature vide (rien de répété),
    une autre signature ou une commande qui avance remet le compte à zéro. Le compte vit dans le dossier, comme le journal."""
    if not isinstance(dossier, dict):
        return False
    if not signature or not any(signature) or not lignes_inchangees:
        CONV.de(dossier).pop(CLE_BOUCLE, None)
        return False
    e = CONV.de(dossier).get(CLE_BOUCLE)
    if isinstance(e, dict) and e.get("signature") == signature:
        e["fois"] = int(e.get("fois") or 0) + 1
    else:
        e = CONV.de(dossier)[CLE_BOUCLE] = {"signature": signature, "fois": 1}
    return int(e["fois"]) >= seuil


def consigne(etape: str) -> str | None:
    """Ce que le retour dit au modèle selon les fois : rien la première fois (le code a parlé), l'issue, puis la sortie."""
    return {ISSUE: A_FAIRE_ISSUE, SORTIE: A_FAIRE_SORTIE}.get(etape)
