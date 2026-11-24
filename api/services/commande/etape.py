"""[.mark] L'étape de la commande : stockée, changée par des transitions, écrite par CE module seulement (plan final Partie 1, lot 2, mécanisme É).

Avant : l'étape (``registre.phase``) se déduisait à chaque lecture de cinq drapeaux (``annulee``, ``enregistree``, ``relecture_acceptee``, ``relecture``,
``dits_en_attente``) que dix fichiers écrivaient librement ; l'accord de la relecture avait huit écrivains (n° 46, 72) et chaque règle qui l'annulait était une
rustine de plus (n° 8, 58, 59). Maintenant : ``p["etape"]`` est une valeur de la table fermée ``ETAPES`` ; ``transition`` est la SEULE fonction qui l'écrit,
et la seule qui écrit les faits qu'elle résume (l'accord, la relecture posée, la commande enregistrée ou annulée). Un geste dit un ÉVÈNEMENT, jamais un drapeau.

Les clés restent celles d'avant dans le panier (``enregistree``, ``annulee``, ``relecture``) : la forme lue de l'extérieur ne change pas (plan § 3). Le nom de la clé
de l'accord n'est connu que d'ici : on la lit par ``accord(p)``.
"""

from __future__ import annotations

from typing import Any

EN_COURS, A_RELIRE, ACCORDEE, ENREGISTREE, ANNULEE = "en_cours", "a_relire", "accordee", "enregistree", "annulee"
ETAPES = (EN_COURS, A_RELIRE, ACCORDEE, ENREGISTREE, ANNULEE)
FINIES = (ENREGISTREE, ANNULEE)

PANIER_TOUCHE = "panier_touche"  # un article, une quantité, le mode… a changé : la relecture et l'accord ne valent plus
RELECTURE_POSEE = "relecture_posee"  # la relecture se dit : l'accord d'avant ne vaut que pour la même relecture (``l_accord_vaut``)
ACCORD_DONNE = "accord_donne"  # « oui » à la relecture entendue
ACCORD_RETIRE = "accord_retire"  # l'accord ne vaut plus (« non », la commande a changé sous un doute…)
ALLERGIE_A_DONNER = "allergie_a_donner"  # les faits d'une allergie passent avant la relecture : elle repart de zéro
ENREGISTREE_EN_CAISSE = "enregistree"
ENREGISTREMENT_DEFAIT = "enregistrement_defait"  # une commande enregistrée est annulée pour être changée : elle redevient ce qu'elle était avant
ANNULEE_EN_COURS = "annulee"
ANNULEE_APRES_ENREGISTREMENT = "annulee_apres_enregistrement"
EVENEMENTS = (PANIER_TOUCHE, RELECTURE_POSEE, ACCORD_DONNE, ACCORD_RETIRE, ALLERGIE_A_DONNER, ENREGISTREE_EN_CAISSE, ENREGISTREMENT_DEFAIT, ANNULEE_EN_COURS,
              ANNULEE_APRES_ENREGISTREMENT)

CLE_ACCORD = "relecture_acceptee"

# La table : (étape d'avant, évènement) -> étape d'arrivée. ``None`` : l'étape se choisit d'après la relecture posée (``_selon_la_relecture``).
_ARRIVEE: dict[tuple[str, str], str | None] = {}
for _avant in (EN_COURS, A_RELIRE, ACCORDEE):
    _ARRIVEE[(_avant, PANIER_TOUCHE)] = EN_COURS
    _ARRIVEE[(_avant, RELECTURE_POSEE)] = None
    _ARRIVEE[(_avant, ACCORD_DONNE)] = ACCORDEE
    _ARRIVEE[(_avant, ACCORD_RETIRE)] = None
    _ARRIVEE[(_avant, ALLERGIE_A_DONNER)] = None
    _ARRIVEE[(_avant, ENREGISTREE_EN_CAISSE)] = ENREGISTREE
    _ARRIVEE[(_avant, ANNULEE_EN_COURS)] = ANNULEE
    _ARRIVEE[(_avant, ANNULEE_APRES_ENREGISTREMENT)] = ANNULEE
for _ev in (PANIER_TOUCHE, RELECTURE_POSEE, ACCORD_DONNE, ACCORD_RETIRE, ALLERGIE_A_DONNER, ENREGISTREE_EN_CAISSE):
    _ARRIVEE[(ENREGISTREE, _ev)] = ENREGISTREE  # enregistrée : ses faits peuvent encore se poser (l'accord, la relecture d'un changement), l'étape reste
_ARRIVEE[(ENREGISTREE, ENREGISTREMENT_DEFAIT)] = None
_ARRIVEE[(ENREGISTREE, ANNULEE_EN_COURS)] = ANNULEE
_ARRIVEE[(ENREGISTREE, ANNULEE_APRES_ENREGISTREMENT)] = ANNULEE
for _ev in (e for e in EVENEMENTS if e != ENREGISTREMENT_DEFAIT):
    _ARRIVEE[(ANNULEE, _ev)] = ANNULEE  # annulée : rien n'y revient (DC5) ; la suivante est une autre commande (``panier.repartir_de_zero``)


def courante(p: dict[str, Any]) -> str:
    """L'étape stockée (un panier neuf est en cours)."""
    return p.get("etape") or EN_COURS


def accord(p: dict[str, Any]) -> bool:
    """« Oui » à la relecture entendue : lu ici, partout (avant : un drapeau lu à quinze endroits)."""
    return bool(p.get(CLE_ACCORD))


def _relecture_posee(p: dict[str, Any]) -> bool:
    return isinstance(p.get("relecture"), dict) and bool(p["relecture"])


def _selon_la_relecture(p: dict[str, Any]) -> str:
    if accord(p):
        return ACCORDEE
    return A_RELIRE if _relecture_posee(p) else EN_COURS


def transition(p: dict[str, Any], evenement: str, **donnees: Any) -> str:
    """Un évènement arrive : les faits qu'il résume s'écrivent ICI, l'étape d'arrivée est celle de la table. Rend la nouvelle étape.

    ``RELECTURE_POSEE`` : ``relecture`` (le dictionnaire posé) et ``l_accord_vaut`` (la relecture est celle que la personne a entendue : l'accord reste).
    ``ENREGISTREE_EN_CAISSE`` : ``faits``. ``ANNULEE_APRES_ENREGISTREMENT`` : ``numero_court``."""
    avant = courante(p)
    if (avant, evenement) not in _ARRIVEE:
        raise ValueError(f"évènement inconnu de la commande : {evenement!r} depuis {avant!r}")
    if evenement == PANIER_TOUCHE:
        p["relecture"], p[CLE_ACCORD] = None, False
    elif evenement == RELECTURE_POSEE:
        if not donnees.get("l_accord_vaut"):
            p[CLE_ACCORD] = False
        p["relecture"] = donnees["relecture"]
    elif evenement == ACCORD_DONNE:
        p[CLE_ACCORD] = True
    elif evenement == ACCORD_RETIRE:
        p[CLE_ACCORD] = False
    elif evenement == ALLERGIE_A_DONNER:
        p["relecture"], p["derniere_lecture"], p[CLE_ACCORD] = None, None, False
    elif evenement == ENREGISTREE_EN_CAISSE:
        p["enregistree"] = donnees["faits"]
    elif evenement == ENREGISTREMENT_DEFAIT:
        p["enregistree"] = None
    elif evenement == ANNULEE_EN_COURS:
        p["annulee"] = True
    elif evenement == ANNULEE_APRES_ENREGISTREMENT:
        p["enregistree"], p["annulee"] = None, True
        p["commande_annulee"] = donnees.get("numero_court")
    arrivee = _ARRIVEE[(avant, evenement)]
    p["etape"] = arrivee if arrivee is not None else _selon_la_relecture(p)
    return p["etape"]
