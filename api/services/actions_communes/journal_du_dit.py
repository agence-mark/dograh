"""[.mark] Clôture de la Partie 1, lot B3 (audit du code M5) : le journal de ce que le code a dit dans l'appel, une seule mémoire.

Avant : cinq mémoires, chacune pour un cas (la fermeture ``fermeture_dite``, les règles d'un article ``regles_dites_par_le_code``, les remises
``remises_dites``, les phrases du code dans le tour ``prefixes_dits``, la relecture) ; le minimum et le refus d'une zone n'en avaient aucune et se
redisaient à chaque fiche (C7, H6, DF7) ; aucun compteur d'échec hors du choix d'une réservation (C5, C10 : « pardon » ou le parfum quatre fois).

Le journal vit dans la conversation du dossier de l'action (le panier, le dossier de la réservation) : ``{clé du fait: {"fois": n, "tour": t}}``. La clé est le
fait lui-même (sa phrase, ou un nom fermé : ``fermeture``, ``remise:<ref>``) : un fait qui change (un autre montant manquant) est un autre fait.
Deux usages, lus ici seulement :
* ``une_fois`` : dit une fois par appel, jamais redit (fermeture, règle d'un article, remise) ;
* ``fait_redit`` : un refus ou un fait bloquant que la personne retombe : la première fois, la phrase entière par le code ; la deuxième, le code
  ne la redit pas et le modèle propose une issue avec ses mots ; à la troisième (deuxième échec), la sortie : proposer de laisser un message à
  l'équipe (la même consigne que le choix d'une réservation, E28). Dans un même tour, un fait n'est compté et dit qu'une fois.
"""

from __future__ import annotations

from typing import Any

from api.services.actions_communes import conversation as CONV

CLE = "journal_du_dit"
FERMETURE = "fermeture"
A_FAIRE_ISSUE = "elle a déjà entendu ce refus : ne le redis pas mot pour mot ; propose-lui une issue avec tes mots"
A_FAIRE_SORTIE = "elle y revient pour la troisième fois sans issue : propose-lui de laisser un message à l'équipe"  # B4 (M8) : passage vers le service

PREMIERE, ISSUE, SORTIE, DEJA_DANS_CE_TOUR = "premiere", "issue", "sortie", "deja_dans_ce_tour"


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


def reprendre(dossier: dict[str, Any], copie: dict[str, Any]) -> None:
    """Le journal d'une copie du dossier (une lecture jouée sur une copie) revient au dossier : seul lui, de la tenue, y revient."""
    if _lu(copie) != _lu(dossier) and isinstance(_lu(copie), dict):
        CONV.de(dossier)[CLE] = _lu(copie)


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


JETEE = "phrase_jetee"  # la phrase écrite avant une fiche et jetée dans ce tour (refus, formule ajoutée) : UNE place, propre au tour


def _net(texte: Any) -> str:
    from api.services.actions_communes.barriere_des_chiffres import sans_balisage

    return " ".join(sans_balisage(str(texte or "")).casefold().split()).rstrip(" .!?…")


def jeter(dossier: Any, texte: str, tour: Any, *, formule: bool = False) -> None:
    """Lot 7a (ligne 20) : la phrase que le code vient de jeter est gardée jusqu'à la fin du tour, pour ne pas être dite si le modèle la recopie. Une phrase vide garde celle
    du même tour ; une fiche de plus (``formule`` faux) retire le drapeau de la formule. Aucune lecture du sens : une égalité de texte (espaces, casse, ponctuation de fin)."""
    if not isinstance(dossier, dict):
        return
    e = _journal(dossier).setdefault(JETEE, {"fois": 0, "tour": None, "texte": None, "formule": False})
    if _net(texte):
        e["texte"] = _net(texte)
    elif e.get("tour") != tour:
        e["texte"] = None
    e["tour"], e["formule"] = tour, formule


def jeter_apres_une_formule(dossier: Any) -> None:
    """La dernière fiche du tour a ajouté une formule : sa phrase jetée n'est jamais dite non plus (mesure finale 2 du lot 11)."""
    e = _lu(dossier).get(JETEE)
    if isinstance(e, dict):
        e["formule"] = True


def jetee(dossier: Any, texte: str, tour: Any, *, apres_un_refus: bool = False) -> bool:
    """Le texte est-il la phrase jetée de CE tour, après un refus ou une formule ajoutée ?"""
    e = _lu(dossier).get(JETEE)
    return bool(isinstance(e, dict) and e.get("tour") == tour and e.get("texte") and _net(texte) == e["texte"] and (apres_un_refus or e.get("formule")))


def une_fois(dossier: dict[str, Any], cle: str, tour: Any = None) -> bool:
    """Vrai la première fois que le fait est dit dans l'appel (il est alors noté) ; ensuite, faux : il n'est jamais redit."""
    if deja_dit(dossier, cle):
        return False
    noter(dossier, cle, tour)
    return True


def fait_redit(dossier: dict[str, Any], cle: str, tour: Any) -> str:
    """Un refus ou un fait bloquant de plus sur la même clé : ``PREMIERE`` (le code le dit en entier), ``ISSUE`` (déjà dit : le modèle propose une
    issue), ``SORTIE`` (au seuil ``FOIS_AVANT_LA_SORTIE``, le même que ``boucle`` : proposer un message à l'équipe), ``DEJA_DANS_CE_TOUR`` (une seconde fiche du même tour : rien de plus)."""
    e = _lu(dossier).get(cle)
    if isinstance(e, dict) and tour is not None and e.get("tour") == tour:
        return DEJA_DANS_CE_TOUR
    n = noter(dossier, cle, tour)
    return PREMIERE if n == 1 else (ISSUE if n < FOIS_AVANT_LA_SORTIE else SORTIE)


CLE_BOUCLE = "boucle"
FOIS_AVANT_LA_SORTIE = 3


def boucle(dossier: dict[str, Any], signature: Any, lignes_inchangees: bool) -> bool:
    """RC6 (contrôle long, lot 3) : la MÊME chose (la même question posée, le même fait bloquant, le même refus) rendue ``FOIS_AVANT_LA_SORTIE`` fois de suite sans que la
    commande avance : vrai à la troisième, et ensuite tant que ça dure : la sortie (proposer un message à l'équipe, ``A_FAIRE_SORTIE``). Une signature vide (rien de répété),
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
    return int(e["fois"]) >= FOIS_AVANT_LA_SORTIE


def consigne(etape: str) -> str | None:
    """Ce que le retour dit au modèle selon les fois : rien la première fois (le code a parlé), l'issue, puis la sortie."""
    return {ISSUE: A_FAIRE_ISSUE, SORTIE: A_FAIRE_SORTIE}.get(etape)
