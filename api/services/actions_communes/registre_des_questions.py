"""[.mark] Lot 6 (Q) : le registre des questions, COMMUN à tous les métiers (commande, réservation). Le mécanisme est ici ; ce qui change d'un métier à
l'autre est une TABLE (``Table``), jamais du code dans la porte.

Forme :
* chaque question a un OBJET, fixé à sa naissance, et un numéro attaché à cet objet : reposée, elle garde son numéro (RC9) ;
* chaque type a une CONDITION lue dans l'état : la question n'existe que tant qu'elle est vraie, seule elle la fait tomber (la porte ne ferme rien) ;
* à la fin de chaque fiche, ``choisir`` pose UNE question : la première, dans l'ordre de la table, dont la condition est vraie (RC1) ; les autres
  restent au registre ;
* une fiche sans ``reponse`` quand une question est posée vaut « autre » pour elle (``reponse_implicite``), pour tous les types et tous les métiers (RC15) ;
* une question fermée dans ce tour et reposée dans le même tour (même signature) garde son objet, donc son numéro : c'est la même question (RC9).

Aucun mot du métier ici : les types, leur ordre et leurs conditions viennent de la table du métier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.barrieres import refus

CLE_DES_NUMEROS = "numeros_des_questions"
CLE_DES_QUESTIONS = "questions_ouvertes"  # objet → question ; une seule est posée, dans ``p["question"]``
CLE_DES_FERMEES = "questions_fermees"  # objet → {signature, tour} : les questions fermées dans ce tour (RC9)
CLE_DERNIERE_FERMEE = "derniere_question_fermee"
CLE_DU_TOUR = "tour_de_l_appel"  # le tour de la conversation, posé par la porte de chaque métier
CLE_DU_PROCHAIN = "prochain_q"  # le numéro de la prochaine question, jamais redonné dans l'appel


@dataclass(frozen=True)
class Table:
    """Ce qu'un métier dit de ses questions."""

    ordre: tuple[str, ...]  # on finit ce qui est commencé avant de proposer, de relire, d'identifier
    condition: Callable[[dict[str, Any], dict[str, Any]], bool]  # (état, question) : la question existe tant que c'est vrai
    objet_de_naissance: Callable[[dict[str, Any], dict[str, Any], bool], str] | None = None  # (question, état, naître) ; défaut : son type
    signature: Callable[[dict[str, Any]], str | None] | None = None  # ce qui fait « la même question » reposée dans le même tour ; ``None`` : aucune
    rafraichir: Callable[[dict[str, Any], dict[str, Any]], None] | None = None  # (état, question) : son texte du jour, quand il dépend de l'état


def _fermee_dans_ce_tour(t: Table, q: dict[str, Any], p: dict[str, Any]) -> str | None:
    """L'objet de la question de même signature fermée dans CE tour ; ``None`` sinon."""
    signature = t.signature(q) if t.signature else None
    if not signature:
        return None
    for cle, f in (CONV.de(p).get(CLE_DES_FERMEES) or {}).items():
        if isinstance(f, dict) and f.get("signature") == signature and f.get("tour") == CONV.de(p).get(CLE_DU_TOUR):
            return str(cle)
    return None


def _objet_de_naissance(t: Table, q: dict[str, Any], p: dict[str, Any], naitre: bool) -> str:
    return _fermee_dans_ce_tour(t, q, p) or (t.objet_de_naissance(q, p, naitre) if t.objet_de_naissance else str(q.get("type")))


def objet(t: Table, q: dict[str, Any], p: dict[str, Any]) -> str:
    """L'objet d'une question, FIXÉ À SA NAISSANCE (``nommer``) et lu ensuite dans la question, jamais recalculé ni compté de nouveau. Une question qui n'est pas
    encore née (sans ``objet``) se lit sans rien changer à l'état."""
    return str(q["objet"]) if q.get("objet") else _objet_de_naissance(t, q, p, naitre=False)


def nommer(t: Table, q: dict[str, Any], p: dict[str, Any]) -> str:
    """La naissance d'une question : son objet est calculé UNE fois ici et posé dans ``q["objet"]``."""
    if not q.get("objet"):
        q["objet"] = _objet_de_naissance(t, q, p, naitre=True)
    return str(q["objet"])


def numero(p: dict[str, Any], cle: str) -> str:
    """Le numéro attaché à l'objet : donné une fois, gardé ensuite (RC9)."""
    conversation = CONV.de(p)
    numeros = conversation.setdefault(CLE_DES_NUMEROS, {})
    if cle not in numeros:
        prochain = int(conversation.get(CLE_DU_PROCHAIN) or 1)
        numeros[cle] = prochain
        conversation[CLE_DU_PROCHAIN] = prochain + 1
    return f"Q-{numeros[cle]}"


def ouvrir(t: Table, p: dict[str, Any], q: dict[str, Any] | None) -> None:
    """Une question née d'un résultat entre au registre (ou y remplace la même question sur le même objet : son texte peut changer)."""
    if not isinstance(q, dict) or not q.get("type"):
        return
    cle = nommer(t, q, p)
    ouvertes = CONV.de(p).setdefault(CLE_DES_QUESTIONS, {})
    neuve = {**{k: v for k, v in q.items() if k not in ("id",)}, "objet": cle}
    deja = ouvertes.get(cle)
    if isinstance(deja, dict) and deja.get("texte") == neuve.get("texte") and "nee_au_tour" in deja:
        neuve["nee_au_tour"] = deja["nee_au_tour"]  # la même question redonnée (même objet, même texte) n'est pas née une seconde fois (RC3)
    ouvertes[cle] = {**deja, **neuve} if isinstance(deja, dict) and deja.get("texte") == neuve.get("texte") else neuve


def est_deja_ouverte(t: Table, p: dict[str, Any], q: dict[str, Any] | None) -> bool:
    """Cette question, née dans ce tour, est déjà au registre : la fin de la fiche ne la rouvre pas, son objet n'est pas recompté."""
    if not isinstance(q, dict):
        return False
    signature = t.signature(q) if t.signature else None
    return any(x.get("type") == q.get("type") and x.get("texte") == q.get("texte") and x.get("nee_au_tour") == q.get("nee_au_tour")
               and (t.signature(x) if t.signature else None) == signature for x in (CONV.de(p).get(CLE_DES_QUESTIONS) or {}).values() if isinstance(x, dict))


def fermee_sans_reponse_au_tour_d_avant(p: dict[str, Any], type_de_la_question: str) -> bool:
    """n° 56 : la question de ce type s'est fermée au tour d'AVANT sans avoir reçu sa réponse (« autre ») : lu dans le registre, qui l'écrit à la fermeture."""
    conversation = CONV.de(p)
    f = conversation.get(CLE_DERNIERE_FERMEE) or {}
    return f.get("type") == type_de_la_question and f.get("sens") == "autre" and f.get("tour") == int(conversation.get(CLE_DU_TOUR) or 0) - 1


def fermer(t: Table, p: dict[str, Any], q: dict[str, Any] | None, sens: str | None = None) -> None:
    """La question a reçu sa réponse (ou est tombée) : elle quitte le registre. Son numéro reste attaché à l'objet ; si elle a une signature, elle est
    gardée comme « fermée dans ce tour » (n° 57 : plus de drapeau propre à un type)."""
    if not isinstance(q, dict):
        return
    conversation = CONV.de(p)
    conversation[CLE_DERNIERE_FERMEE] = {"type": q.get("type"), "sens": sens, "tour": int(conversation.get(CLE_DU_TOUR) or 0)}
    tour = conversation.get(CLE_DU_TOUR)
    fermees = {k: f for k, f in (conversation.get(CLE_DES_FERMEES) or {}).items() if isinstance(f, dict) and f.get("tour") == tour}
    signature = t.signature(q) if t.signature else None
    if signature:
        fermees[objet(t, q, p)] = {"signature": signature, "tour": tour}
    if fermees:
        conversation[CLE_DES_FERMEES] = fermees
    else:
        conversation.pop(CLE_DES_FERMEES, None)
    (conversation.get(CLE_DES_QUESTIONS) or {}).pop(objet(t, q, p), None)
    for cle, x in list((conversation.get(CLE_DES_QUESTIONS) or {}).items()):
        if x.get("type") == q.get("type") and x.get("id_pose") == q.get("id"):
            conversation[CLE_DES_QUESTIONS].pop(cle, None)


def tout_fermer(p: dict[str, Any]) -> None:
    """Le dossier repart de zéro ou est clos : toutes ses questions tombent."""
    CONV.de(p).pop(CLE_DES_QUESTIONS, None)
    p["question"] = None


def choisir(t: Table, p: dict[str, Any], tour: int, de_l_etat: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """La question posée après la fiche : la première, dans l'ordre de la table, dont la condition est vraie ; numérotée par son objet. Celles dont la
    condition est tombée quittent le registre. ``de_l_etat`` : les questions que l'état redonne sans être gardées."""
    ouvertes = CONV.de(p).setdefault(CLE_DES_QUESTIONS, {})
    for q in de_l_etat or []:
        if isinstance(q, dict) and q.get("type"):
            cle = nommer(t, q, p)
            ouvertes.setdefault(cle, {**{k: v for k, v in q.items() if k != "id"}, "objet": cle})
    for cle, q in list(ouvertes.items()):
        if not t.condition(p, q):
            ouvertes.pop(cle)
    if not ouvertes:
        p["question"] = None
        return None
    cle, q = min(ouvertes.items(), key=lambda kv: t.ordre.index(kv[1]["type"]) if kv[1]["type"] in t.ordre else len(t.ordre))
    id_ = numero(p, cle)
    if t.rafraichir:
        t.rafraichir(p, q)
    q.setdefault("nee_au_tour", tour)
    posee = {**q, "id": id_}
    q["id_pose"] = id_
    p["question"] = posee
    return posee


def reponse_implicite(fiche: dict[str, Any], question: dict[str, Any] | None, posee: bool) -> dict[str, Any]:
    """Une question posée et une fiche sans ``reponse`` : la fiche vaut « autre » pour cette question, pour tous les types et tous les métiers. Jamais
    « accepte » ni « refuse » déduits."""
    if not question or not posee or isinstance(fiche.get("reponse"), dict):
        return fiche
    return {**fiche, "reponse": {"question_id": question.get("id"), "sens": "autre", "implicite": True}}  # ``implicite`` : la fiche n'a PAS répondu (Pierre 7, 8)


def reponse_donnee(fiche: dict[str, Any], question: dict[str, Any] | None, posee: bool) -> dict[str, Any] | None:
    """La réponse que la fiche DONNE à la question posée : la sienne, ou ``None`` quand elle vaut « autre » (``reponse_implicite``) : la question reste posée, rien n'est refusé."""
    r = reponse_implicite(fiche, question, posee).get("reponse")
    return r if isinstance(r, dict) and not r.get("implicite") else None


def question_inconnue(fiche: dict[str, Any], question: dict[str, Any] | None) -> dict[str, Any] | None:
    """Une réponse dont l'identifiant n'est pas celui de la question en attente : rien n'est rangé à la devinette (E5, A10, A28, A29). Le registre porte les
    identifiants, la règle est donc la sienne, la même pour tous les métiers (n° 9 : « reponse.question_id recopie Q-n » est une ligne du registre)."""
    r = fiche.get("reponse")
    if not isinstance(r, dict):
        return None
    if not question:
        return refus("question_inconnue", ["reponse"], a_faire="rien n'est changé : aucune question n'attend, ne mets pas reponse, dis le changement dans sa case")
    if r.get("question_id") != question.get("id"):
        return refus("question_inconnue", ["reponse"], question={k: question.get(k) for k in ("id", "type", "texte")},
                     a_faire=f"rien n'est changé : la question en attente est {question.get('id')} ; reponse.question_id recopie {question.get('id')}")
    return None
