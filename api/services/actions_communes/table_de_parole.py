"""[.mark] Lot 7a : la table de la parole. UN seul endroit décide qui parle après une fiche : ``(Du, phrase du modèle) -> mode``.

Avant : une cascade d'une vingtaine de ``if`` (``parole._decision_du_tour``), chacun un cas nommé avec ses drapeaux. Ici : des LIGNES, lues dans l'ordre, la première
dont la condition est vraie décide. Une condition se lit sur le ``Du`` (ce qui est dû, ``du.py``), sur la forme de la phrase (vide, pose une question, porte un chiffre)
et sur l'état du tour : jamais sur les mots de la personne ni sur le nom d'une case (D1). Aucun mot du métier.

Le mode dit QUI PARLE : ``A_DIRE_SEUL`` (la phrase est dite, le tour s'arrête) ou ``SECOND_PASSAGE`` (la phrase est jetée, le modèle repasse avec le retour). Le code ne dit
mot pour mot que ses phrases réglées, après la phrase du modèle (``suffixe`` : le numéro, le total, le rendu, la question M108 ou DC10 ; C6) ; plus aucune porte ne pose ``avant`` (C6 n° 12).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from dataclasses import dataclass
from typing import Any, Callable

from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase, porte_les_chiffres, sans_balisage
from api.services.actions_communes.du import RETRAIT_D_UNE_LIGNE, RIEN_CHANGE, Du
from api.services.actions_communes.parole import (
    A_DIRE_SEUL, FAITS_A_DIRE, FORMULE_AJOUTEE, MANQUE, QUESTION_DEJA_DONNEE, SANS_OUTIL, SECOND_PASSAGE, Decision, EtatDuTour,
    apres_un_refus, pose_une_question, question_due_sans_suite, question_nee_dans_ce_tour,
)

FAIT_ACCOMPLI = "fait_accompli_du_modele"  # motif : le modèle dit le fait accompli (C6 n° 5), le code dit la suite après sa phrase


@dataclass
class Entrees:
    """Tout ce que la table lit : le ``Du``, la phrase, ce que le code dit lui-même, et l'état du tour (qui bouge dans une ligne)."""

    du: Du
    phrase: str
    avant: str
    suffixe_du_code: str | None
    exiges: dict | None  # C6 n° 5 : un fait accompli que le modèle dit, avec les valeurs exigées de sa phrase (``None`` : aucun)
    question_nee: bool  # elle est née dans CE tour
    question_id: Any
    suffixe_avant: str | None  # la phrase réglée que le code dit après la phrase (le total de la relecture), posée au passage précédent
    chiffre: bool
    objet_en_cours: bool
    en_attente: bool  # une question attend dans le dossier
    etat: EtatDuTour
    retour: dict
    p: dict | None

    @property
    def question_deja_donnee(self) -> bool:
        return bool(self.question_nee and self.question_id == self.etat.question_donnee and self.etat.question_donnee and self.phrase and not self.chiffre)

    @property
    def question_donnee_dite(self) -> bool:
        """La question du dossier (née ou non dans ce tour) a déjà été donnée au modèle, et sa phrase peut être dite."""
        return bool(self.question_id and self.question_id == self.etat.question_donnee and self.phrase and not self.chiffre)


def _texte(e: Entrees) -> Decision:
    return Decision(A_DIRE_SEUL, a_dire=e.avant, motif="texte_du_code")


def _second(motif: str, avant: Callable[[Entrees], None] | None = None) -> Callable[[Entrees], Decision]:
    def decider(e: Entrees) -> Decision:
        if avant:
            avant(e)
        return Decision(SECOND_PASSAGE, motif=motif)

    return decider


def _rendre_la_fiche(e: Entrees) -> None:
    e.etat.fiches -= 1  # une fiche vide n'est pas une fiche


def _du_a_reposer(e: Entrees) -> bool:
    """Une question attend, ou un manque est dû, et la phrase du modèle n'en pose aucune (une question à la fois) : ce que le modèle a oublié. Lu sur la forme (le « ? », le dossier), jamais sur les mots."""
    return not pose_une_question(e.phrase) and (e.en_attente or bool(e.du.manque))


def _relancer_le_fait(e: Entrees, motif: str) -> Decision | None:
    """C5 (décision d'Evan 25/11 8 h 45) : le code ne complète plus la phrase du modèle par la question ou le manque ; il le laisse repasser avec le retour, UNE fois par tour
    (``EtatDuTour.relance_du_fait``, la même que la relance du repli) ; ensuite sa phrase est dite seule. ``None`` : rien n'est dû, ou la relance est déjà faite."""
    if not _du_a_reposer(e) or e.etat.relance_du_fait:
        return None
    e.etat.relance_du_fait = True
    e.etat.suffixe = e.suffixe_avant  # le prix que le code doit dire après la phrase n'est pas perdu : il suit la phrase du second passage
    return Decision(SECOND_PASSAGE, motif=motif)


def _rien_change(e: Entrees) -> Decision:
    """Une fiche qui ne change rien est une phrase sans outil : retenue une fois par tour ; puis, si la phrase oublie la question en attente ou ce qui manque, le modèle repasse une fois ;
    ensuite dite seule (reprise R1 de C6 : le fait accompli n'est jamais redit par le code, il reste au journal) ; jamais « C'est noté » seul quand rien n'est noté."""
    etat, phrase = e.etat, e.phrase
    etat.fiches -= 1
    if not etat.rattrapage_a_joue and (e.objet_en_cours or e.en_attente):
        etat.rattrapage_a_joue = True
        etat.retenues.append(SANS_OUTIL)
        return Decision(SECOND_PASSAGE, motif=RIEN_CHANGE)
    if not phrase or e.chiffre:
        return Decision(SECOND_PASSAGE, motif="sans_phrase" if not phrase else "chiffre")
    e.etat.jetee = None
    if (relance := _relancer_le_fait(e, MANQUE)) is not None:
        return relance
    return Decision(A_DIRE_SEUL, a_dire=phrase, motif="fait")


def _question(e: Entrees) -> Decision:
    """Une question née dans ce tour. Déjà donnée au modèle : sa phrase est dite (puis la phrase réglée du code, le total de la relecture) ; si elle oublie la question, le modèle
    repasse une fois (C5) ; sinon le modèle repasse avec elle."""
    etat, phrase = e.etat, e.phrase
    if e.question_donnee_dite:
        e.etat.jetee = None
        if (relance := _relancer_le_fait(e, MANQUE)) is not None:
            return relance
        return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (phrase, e.suffixe_avant) if x), motif=QUESTION_DEJA_DONNEE)
    etat.question_donnee = e.question_id
    etat.suffixe = e.suffixe_du_code
    return Decision(SECOND_PASSAGE, motif="question_nouvelle")


def _fait_accompli(e: Entrees) -> Decision:
    """C6 n° 5 (décision d'Evan 25/11 9 h 30) : un fait accompli que le MODÈLE dit (la commande enregistrée), suivi de ce que le code dit après lui (le rendu, la question M108). Sa phrase
    part avec la suite si elle dit les valeurs exigées (l'heure), sans chiffre de plus, sans question en double, et, quand le code ne dit rien après elle et qu'une question attend (DC4,
    la proposition, la relecture de la réservation), si elle pose cette question (reprise R2) ; sinon le modèle repasse avec le retour, la suite gardée pour sa phrase."""
    etat, phrase, suite = e.etat, e.phrase, e.suffixe_du_code
    exiges = e.exiges or {}
    en_double = bool(suite) and pose_une_question(suite) and pose_une_question(phrase)
    due = question_due_sans_suite(phrase, suite, e.en_attente)
    if phrase and not apres_un_refus(etat) and not e.chiffre and not en_double and not due and porte_les_chiffres(phrase, exiges):
        etat.jetee = None
        return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (phrase, suite) if x), motif=FAIT_ACCOMPLI)
    etat.suffixe, etat.exiges = suite, exiges
    return Decision(SECOND_PASSAGE, motif=FAIT_ACCOMPLI)


def _formule(e: Entrees) -> Decision:
    e.etat.jetee_apres_une_formule = True
    return Decision(SECOND_PASSAGE, motif=FORMULE_AJOUTEE)


def _dite_ou_due(e: Entrees) -> Decision:
    """La phrase du modèle n'est dite seule que si rien n'est dû : ce qui manque, quand elle ne pose aucune question, est dû (elle est jetée, le modèle repasse)."""
    if e.du.manque and not pose_une_question(e.phrase):
        return Decision(SECOND_PASSAGE, motif=MANQUE)
    e.etat.jetee = None
    return Decision(A_DIRE_SEUL, a_dire=e.phrase, motif="fait")


# Les lignes, dans l'ordre : la première dont la condition est vraie décide.
LIGNES: tuple[tuple[str, Callable[[Entrees], bool], Callable[[Entrees], Decision]], ...] = (
    ("texte du code (exception § 2)", lambda e: bool(e.avant), _texte),
    ("fait accompli dit par le modèle", lambda e: e.exiges is not None, _fait_accompli),
    ("refus", lambda e: apres_un_refus(e.etat), _second("refus")),
    ("faits à dire sur une fiche vide", lambda e: e.du.rien_change and "faits_a_dire" in e.du.faits_au_modele, _second(FAITS_A_DIRE, avant=_rendre_la_fiche)),
    ("rien n'a changé", lambda e: e.du.rien_change and not e.question_deja_donnee, _rien_change),
    ("fait bloquant", lambda e: "fait_bloquant" in e.du.faits_au_modele, _second("fait_bloquant")),
    ("faits à dire", lambda e: "faits_a_dire" in e.du.faits_au_modele, _second(FAITS_A_DIRE)),
    ("question née", lambda e: e.question_nee, _question),
    ("ligne retirée", lambda e: RETRAIT_D_UNE_LIGNE in e.du.faits_qui_engagent, _second("retrait")),
    ("formule ajoutée", lambda e: "formule_ajoutee" in e.du.faits_qui_engagent, _formule),
    ("phrase vide", lambda e: not e.phrase, _second("sans_phrase")),
    ("phrase qui porte un chiffre", lambda e: e.chiffre, _second("chiffre")),
    ("phrase dite", lambda e: True, _dite_ou_due),
)


def ligne_qui_decide(e: Entrees) -> str:
    """Le nom de la première ligne dont la condition est vraie (la dernière répond toujours)."""
    return next(nom for nom, condition, _ in LIGNES if condition(e))


def decider(e: Entrees) -> Decision:
    """La décision de la parole pour ce retour : la première ligne dont la condition est vraie."""
    nom = ligne_qui_decide(e)
    return next(decider_ for n, _, decider_ in LIGNES if n == nom)(e)


def entrees_du_retour(retour: dict, phrase: str, etat: EtatDuTour, paroles: list[str], p: dict | None, textes: dict, objet_en_cours: bool | None,
                      suffixe_avant: str | None) -> Entrees:
    """Ce que la table lit, rassemblé depuis le retour de la fiche et l'état du tour."""
    from api.services.actions_communes.du import du_du_retour

    du = du_du_retour(retour)
    dossier_q = CONV.question_de(p)
    exiges = textes.get("chiffres_exiges") if isinstance(textes.get("chiffres_exiges"), dict) else None
    if exiges:
        etat.faits_du_refus.append(exiges)  # les valeurs exigées sont données au modèle : elles passent la barrière des chiffres, dans ce passage et le suivant
    if objet_en_cours is None:
        objet_en_cours = bool(isinstance(p, dict) and (p.get("lignes") or p.get("mode") or p.get("enregistree")))
    return Entrees(
        du=du, phrase=phrase, avant=sans_balisage(str(textes.get("avant") or "")), suffixe_du_code=sans_balisage(str(textes.get("suffixe") or "")) or None, exiges=exiges,
        question_nee=question_nee_dans_ce_tour(p, etat.tour),
        question_id=dossier_q.get("id") if isinstance(dossier_q, dict) else None, suffixe_avant=suffixe_avant,
        chiffre=bool(phrase) and chiffre_dans_la_phrase(phrase, etat.executees, paroles, etat.faits_du_refus), objet_en_cours=objet_en_cours, en_attente=isinstance(dossier_q, dict),
        etat=etat, retour=retour, p=p)
