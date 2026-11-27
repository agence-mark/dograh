"""[.mark] L'étape de la commande (plan final Partie 1, lot 2, mécanisme É) : une valeur de la table fermée ``ETAPES``, stockée dans le panier, changée par des évènements ;
``transition`` est la seule à l'écrire, avec les faits qu'elle résume (la relecture posée, la commande enregistrée ou annulée). L'accord de la relecture est l'étape « accordée » :
il n'a pas de clé à lui."""

from __future__ import annotations

from typing import Any

EN_COURS, A_CLORE, A_RELIRE, ACCORDEE, ENREGISTREE, ANNULEE = "en_cours", "a_clore", "a_relire", "accordee", "enregistree", "annulee"
ETAPES = (EN_COURS, A_CLORE, A_RELIRE, ACCORDEE, ENREGISTREE, ANNULEE)
FINIES = (ENREGISTREE, ANNULEE)

C_EST_TOUT_DIT = "c_est_tout_dit"  # n° 45 : « c'est tout » est dit mais la relecture attend un fait (l'heure proposée) : la commande est à clore, plus à prendre
PANIER_TOUCHE = "panier_touche"  # un article, une quantité, le mode… a changé : la relecture et l'accord ne valent plus
RELECTURE_POSEE = "relecture_posee"  # la relecture se dit : l'accord d'avant ne vaut que pour la même relecture (``l_accord_vaut``)
ACCORD_DONNE = "accord_donne"  # « oui » à la relecture entendue
ACCORD_RETIRE = "accord_retire"  # l'accord ne vaut plus (« non », la commande a changé sous un doute…)
ALLERGIE_A_DONNER = "allergie_a_donner"  # les faits d'une allergie passent avant la relecture : elle repart de zéro
ENREGISTREE_EN_BASE = "enregistree"  # E9 (§ 17) : la commande est écrite EN BASE au « oui » ; la caisse la reçoit à la fin de l'appel. La valeur stockée ne change pas : les paniers existants restent lisibles
ENREGISTREMENT_DEFAIT = "enregistrement_defait"  # une commande enregistrée est annulée pour être changée : elle redevient ce qu'elle était avant
CLE_DE_LA_LIGNE_ANNULEE = "numero_de_la_ligne_annulee"  # le numéro (identifiant) de la ligne de la base que cet appel a annulée ; une donnée, jamais un drapeau
ANNULEE_EN_COURS = "annulee"
ANNULEE_APRES_ENREGISTREMENT = "annulee_apres_enregistrement"
EVENEMENTS = (C_EST_TOUT_DIT, PANIER_TOUCHE, RELECTURE_POSEE, ACCORD_DONNE, ACCORD_RETIRE, ALLERGIE_A_DONNER, ENREGISTREE_EN_BASE, ENREGISTREMENT_DEFAIT, ANNULEE_EN_COURS,
              ANNULEE_APRES_ENREGISTREMENT)

# La table : (étape d'avant, évènement) -> étape d'arrivée. ``None`` : l'étape se choisit d'après la relecture posée (``_selon_la_relecture``).
_ARRIVEE: dict[tuple[str, str], str | None] = {}
for _avant in (EN_COURS, A_CLORE, A_RELIRE, ACCORDEE):
    _ARRIVEE[(_avant, PANIER_TOUCHE)] = A_CLORE if _avant == A_CLORE else EN_COURS  # à clore, un article de plus ne rouvre pas la prise : « c'est tout » reste dit
    _ARRIVEE[(_avant, RELECTURE_POSEE)] = None
    _ARRIVEE[(_avant, ACCORD_DONNE)] = ACCORDEE
    _ARRIVEE[(_avant, ACCORD_RETIRE)] = None
    _ARRIVEE[(_avant, ALLERGIE_A_DONNER)] = None
    _ARRIVEE[(_avant, ENREGISTREE_EN_BASE)] = ENREGISTREE
    _ARRIVEE[(_avant, ANNULEE_EN_COURS)] = ANNULEE
    _ARRIVEE[(_avant, ANNULEE_APRES_ENREGISTREMENT)] = ANNULEE
for _avant in (EN_COURS, A_CLORE):
    _ARRIVEE[(_avant, C_EST_TOUT_DIT)] = A_CLORE
for _ev in (PANIER_TOUCHE, RELECTURE_POSEE, ACCORD_DONNE, ACCORD_RETIRE, ALLERGIE_A_DONNER, ENREGISTREE_EN_BASE):
    _ARRIVEE[(ENREGISTREE, _ev)] = ENREGISTREE  # enregistrée : ses faits peuvent encore se poser (l'accord, la relecture d'un changement), l'étape reste
_ARRIVEE[(ENREGISTREE, ENREGISTREMENT_DEFAIT)] = None
_ARRIVEE[(ENREGISTREE, ANNULEE_EN_COURS)] = ANNULEE
_ARRIVEE[(ENREGISTREE, ANNULEE_APRES_ENREGISTREMENT)] = ANNULEE
for _ev in (e for e in EVENEMENTS if e != ENREGISTREMENT_DEFAIT):
    _ARRIVEE[(ANNULEE, _ev)] = ANNULEE
_ARRIVEE[(ANNULEE, PANIER_TOUCHE)] = EN_COURS  # § 17 l.407 : annuler = vider le panier ; un article dit après repart d'un panier vide, dans le même appel (plus de refus ni de « nouvelle commande »)


def monter(p: dict[str, Any], empreinte: Any = None) -> dict[str, Any]:
    """LA fonction de montée : un panier stocké avant le lot 2 (une fiche d'appel déjà enregistrée) n'a pas d'étape ; elle se lit de ses faits, UNE fois, ici,
    quand le panier est lu du dossier (``panier.du_dossier``), et se range dans le panier. Un panier qui a une étape n'est pas touché. L'accord d'un ancien panier n'est pas repris : la relecture se redit."""
    if not p.get("etape"):
        if p.get("annulee"):
            p["etape"] = ANNULEE
        elif p.get("enregistree"):
            p["etape"] = ENREGISTREE
        else:
            p["etape"] = _selon_la_relecture(p)
    if p.get("enregistree") and not p.get("empreinte_enregistree") and empreinte is not None:
        p["empreinte_enregistree"] = empreinte(p)  # une commande enregistrée avant ce mécanisme : son empreinte est celle du panier tel qu'il est à la première lecture
    return p


def courante(p: dict[str, Any]) -> str:
    """L'étape stockée, rien d'autre : elle ne se déduit plus des drapeaux (``monter`` s'en charge pour un vieux panier, à la lecture du dossier)."""
    return p["etape"]


def accord(p: dict[str, Any]) -> bool:
    """« Oui » à la relecture entendue : l'étape est « accordée », ou plus loin (une commande enregistrée a eu son accord : ses cases de fin restent montrées, et refusées)."""
    return courante(p) in (ACCORDEE, ENREGISTREE)


def c_est_tout_dit(p: dict[str, Any]) -> bool:
    """n° 45 : « c'est tout » a été dit et la relecture attend encore un fait (l'heure) : lu dans l'étape, plus un drapeau posé sur la question."""
    return courante(p) == A_CLORE


def enregistree(p: dict[str, Any]) -> bool:
    """La commande de cet appel est enregistrée (vrai jusqu'à ce qu'elle soit annulée)."""
    return courante(p) == ENREGISTREE


def annulee(p: dict[str, Any]) -> bool:
    return courante(p) == ANNULEE


def finie(p: dict[str, Any]) -> bool:
    return courante(p) in FINIES


def _relecture_posee(p: dict[str, Any]) -> bool:
    return isinstance(p.get("relecture"), dict) and bool(p["relecture"])


def _selon_la_relecture(p: dict[str, Any]) -> str:
    return A_RELIRE if _relecture_posee(p) else EN_COURS


def _panier_touche(p: dict[str, Any], d: dict[str, Any]) -> None:
    p["relecture"] = None
    p.pop("annulee", None)  # un panier touché après une annulation est de nouveau une commande à prendre (l'étape repart en cours, ``_ARRIVEE``)


def _relecture_posee_effet(p: dict[str, Any], d: dict[str, Any]) -> None:
    p["relecture"] = d["relecture"]


def _allergie(p: dict[str, Any], d: dict[str, Any]) -> None:
    p["relecture"], p["derniere_lecture"] = None, None


def _annulee_apres_enregistrement(p: dict[str, Any], d: dict[str, Any]) -> None:
    p["enregistree"], p["annulee"] = None, True
    p["numero_de_la_commande_annulee"] = d.get("numero_court")
    p[CLE_DE_LA_LIGNE_ANNULEE] = d.get("numero")  # la ligne de la base, rouverte si le client recommande dans cet appel (8b-2) ; la copie de ce que la base avait reçu n'a plus d'objet
    p["empreinte_enregistree"] = p["commande_enregistree"] = None


def _enregistree_en_base(p: dict[str, Any], d: dict[str, Any]) -> None:
    p["enregistree"] = d["faits"]
    p["empreinte_enregistree"] = d["empreinte"]  # le panier tel que la base l'a reçu : un changement se compare à lui, jamais au panier du début du tour
    p.pop(CLE_DE_LA_LIGNE_ANNULEE, None)  # elle a été rouverte, ou la nouvelle est écrite : plus de ligne annulée à reprendre
    p["commande_enregistree"] = d.get("commande")  # 7c R1, T13 : sa copie (``panier.commande_recue``) ; ce que l'empreinte ne lit pas se compare à elle


_EFFETS = {
    PANIER_TOUCHE: _panier_touche,
    RELECTURE_POSEE: _relecture_posee_effet,
    C_EST_TOUT_DIT: lambda p, d: None,
    ACCORD_DONNE: lambda p, d: None,
    ACCORD_RETIRE: lambda p, d: None,
    ALLERGIE_A_DONNER: _allergie,
    ENREGISTREE_EN_BASE: _enregistree_en_base,
    ENREGISTREMENT_DEFAIT: lambda p, d: p.__setitem__("enregistree", None),
    ANNULEE_EN_COURS: lambda p, d: p.__setitem__("annulee", True),
    ANNULEE_APRES_ENREGISTREMENT: _annulee_apres_enregistrement,
}


def transition(p: dict[str, Any], evenement: str, **donnees: Any) -> str:
    """Un évènement arrive : les faits qu'il résume s'écrivent ICI, l'étape d'arrivée est celle de la table. Rend la nouvelle étape.

    ``RELECTURE_POSEE`` : ``relecture`` (le dictionnaire posé) et ``l_accord_vaut`` (la relecture est celle que la personne a entendue : l'étape reste « accordée »).
    ``ENREGISTREE_EN_BASE`` : ``faits``, ``empreinte`` et ``commande`` (sa copie, ``panier.commande_recue``) du panier écrit. ``ANNULEE_APRES_ENREGISTREMENT`` : ``numero_court`` et ``numero``."""
    avant = courante(p)
    if (avant, evenement) not in _ARRIVEE:
        raise ValueError(f"évènement inconnu de la commande : {evenement!r} depuis {avant!r}")
    _EFFETS[evenement](p, donnees)
    arrivee = _ARRIVEE[(avant, evenement)]
    if arrivee is None:
        garde_l_accord = evenement == RELECTURE_POSEE and avant == ACCORDEE and bool(donnees.get("l_accord_vaut"))
        arrivee = ACCORDEE if garde_l_accord else _selon_la_relecture(p)
    p["etape"] = arrivee
    return p["etape"]
