"""[.mark] Lot 7a : la table de la parole. UN seul endroit décide qui parle après une fiche : ``(Du, phrase du modèle) -> mode``.

Avant : une cascade d'une vingtaine de ``if`` (``parole._decision_du_tour``), chacun un cas nommé avec ses drapeaux. Ici : des LIGNES, lues dans l'ordre, la première
dont la condition est vraie décide. Une condition se lit sur le ``Du`` (ce qui est dû, ``du.py``), sur la forme de la phrase (vide, pose une question, porte un chiffre)
et sur l'état du tour : jamais sur les mots de la personne ni sur le nom d'une case (D1). Aucun mot du métier.

Le mode dit QUI PARLE : ``A_DIRE_SEUL`` (la phrase est dite, le tour s'arrête) ou ``SECOND_PASSAGE`` (la phrase est jetée, le modèle repasse avec le retour). Le code ne dit
mot pour mot que les exceptions du § 2 du plan (relecture, total, numéro, confirmation, fait accompli : leur texte arrive dans ``avant``).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from dataclasses import dataclass
from typing import Any, Callable

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase, sans_balisage
from api.services.actions_communes.du import RETRAIT_D_UNE_LIGNE, RIEN_CHANGE, Du
from api.services.actions_communes.parole import (
    A_DIRE_SEUL, FAITS_A_DIRE, FORMULE_AJOUTEE, MANQUE, QUESTION_DEJA_DONNEE, REPRISE, SANS_OUTIL, SECOND_PASSAGE, Decision, EtatDuTour,
    pose_une_question, question_nee_dans_ce_tour, reprise_apres_la_phrase, repli_sans_le_fait_bloquant_de,
)


@dataclass
class Entrees:
    """Tout ce que la table lit : le ``Du``, la phrase, ce que le code dit lui-même, et l'état du tour (qui bouge dans une ligne)."""

    du: Du
    phrase: str
    avant: str
    prefixe: str | None
    suffixe_du_code: str | None
    texte_de_la_question: str | None  # la question née dans ce retour, telle que la porte la pose
    question_nee: bool  # elle est née dans CE tour
    question_id: Any
    suffixe_avant: str | None  # le prix que le code dit après la phrase, posé au passage précédent
    chiffre: bool
    objet_en_cours: bool
    en_attente: bool  # une question attend dans le dossier
    etat: EtatDuTour
    retour: dict
    p: dict | None

    @property
    def question_deja_donnee(self) -> bool:
        return bool(self.question_nee and self.question_id == self.etat.question_donnee and self.etat.question_donnee and self._prix_deja_dit
                    and not self.prefixe and self.phrase and not self.chiffre)

    @property
    def _prix_deja_dit(self) -> bool:
        return not self.du.prix_apres or bool(self.suffixe_avant)

    @property
    def question_donnee_dite(self) -> bool:
        """La question du dossier (née ou non dans ce tour) a déjà été donnée au modèle, et sa phrase peut être dite."""
        return bool(self.question_id and self.question_id == self.etat.question_donnee and self._prix_deja_dit and not self.prefixe and self.phrase and not self.chiffre)


def _texte(e: Entrees) -> Decision:
    return Decision(A_DIRE_SEUL, a_dire=e.avant, motif="texte_du_code")


def _maximum_ou_doute(e: Entrees) -> bool:
    return (bool(e.prefixe) and e.du.maximum) or (e.du.question == "ambiguite" and e.texte_de_la_question is not None and e.question_nee)


def _remplace(e: Entrees) -> Decision:
    """Un maximum atteint, ou une question d'ambiguïté née dans ce tour : le code dit le refus (préfixe), suivi de la question."""
    if e.du.maximum and e.prefixe:
        return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (e.prefixe, e.texte_de_la_question if e.question_nee else None) if x), motif="texte_du_code")
    return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (e.prefixe, e.texte_de_la_question) if x), motif="texte_du_code")


def _second(motif: str, prefixe: bool = True, avant: Callable[[Entrees], None] | None = None) -> Callable[[Entrees], Decision]:
    def decider(e: Entrees) -> Decision:
        if avant:
            avant(e)
        return Decision(SECOND_PASSAGE, motif=motif, prefixe=e.prefixe if prefixe else None)

    return decider


def _rendre_la_fiche(e: Entrees) -> None:
    e.etat.fiches -= 1  # une fiche vide n'est pas une fiche


def _rien_change(e: Entrees) -> Decision:
    """Une fiche qui ne change rien est une phrase sans outil : retenue une fois par tour, puis dite avec la question en attente reposée (ou ce qui manque) ;
    jamais « C'est noté » seul quand rien n'est noté."""
    etat, phrase = e.etat, e.phrase
    etat.fiches -= 1
    if not etat.rattrapage_a_joue and (e.objet_en_cours or e.en_attente):
        etat.rattrapage_a_joue = True
        etat.retenues.append(SANS_OUTIL)
        return Decision(SECOND_PASSAGE, motif=RIEN_CHANGE, prefixe=e.prefixe)
    if not phrase or e.chiffre:
        return Decision(SECOND_PASSAGE, motif="sans_phrase" if not phrase else "chiffre", prefixe=e.prefixe)
    J.oublier(e.p, J.JETEE)
    reprise = reprise_apres_la_phrase(phrase, etat, e.p, rien_change=True) or (None if pose_une_question(phrase) else sans_balisage(e.du.manque or "") or None)
    if not reprise and not pose_une_question(phrase) and isinstance(e.p, dict):
        reprise = J.fait_accompli(e.p)  # RC4 : le fait accompli, que le code redit
    if reprise:
        return Decision(A_DIRE_SEUL, a_dire=f"{phrase} {reprise}", motif=REPRISE)
    return Decision(A_DIRE_SEUL, a_dire=phrase, motif="fait")


def _question(e: Entrees) -> Decision:
    """Une question née dans ce tour, ou un prix à dire après la phrase. Déjà donnée au modèle : sa phrase est dite (puis le prix dû) ; sinon le modèle repasse avec elle."""
    etat, phrase = e.etat, e.phrase
    if e.question_donnee_dite:
        J.oublier(e.p, J.JETEE)
        suite = None if pose_une_question(phrase) else repli_sans_le_fait_bloquant_de(e.p)  # une seule question : celle du code suit « C'est noté »
        return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (phrase, suite or e.suffixe_avant) if x), motif=QUESTION_DEJA_DONNEE)
    etat.question_donnee = e.question_id
    etat.suffixe = e.suffixe_du_code
    return Decision(SECOND_PASSAGE, motif="question_nouvelle", prefixe=e.prefixe)


def _formule(e: Entrees) -> Decision:
    J.jeter_apres_une_formule(e.p)
    return Decision(SECOND_PASSAGE, motif=FORMULE_AJOUTEE)


def _dite_ou_due(e: Entrees) -> Decision:
    """La phrase du modèle n'est dite seule que si rien n'est dû : ce qui manque, quand elle ne pose aucune question, est dû (elle est jetée, le modèle repasse)."""
    if e.du.manque and not pose_une_question(e.phrase):
        return Decision(SECOND_PASSAGE, motif=MANQUE)
    J.oublier(e.p, J.JETEE)
    return Decision(A_DIRE_SEUL, a_dire=e.phrase, motif="fait")


# Les lignes, dans l'ordre : la première dont la condition est vraie décide.
LIGNES: tuple[tuple[str, Callable[[Entrees], bool], Callable[[Entrees], Decision]], ...] = (
    ("texte du code (exception § 2)", lambda e: bool(e.avant), _texte),
    ("maximum atteint ou doute né dans le tour", _maximum_ou_doute, _remplace),
    ("refus", lambda e: J.apres_un_refus(e.p, e.etat.tour), _second("refus")),
    ("faits à dire sur une fiche vide", lambda e: e.du.rien_change and "faits_a_dire" in e.du.faits_au_modele, _second(FAITS_A_DIRE, avant=_rendre_la_fiche)),
    ("rien n'a changé", lambda e: e.du.rien_change and not e.question_deja_donnee, _rien_change),
    ("fait bloquant", lambda e: "fait_bloquant" in e.du.faits_au_modele, _second("fait_bloquant")),
    ("faits à dire", lambda e: "faits_a_dire" in e.du.faits_au_modele, _second(FAITS_A_DIRE)),
    ("question née ou prix à dire", lambda e: e.question_nee or e.du.prix_apres, _question),
    ("règle chiffrée qui bloque", lambda e: bool(e.prefixe), _second("fait_bloquant")),
    ("ligne retirée", lambda e: RETRAIT_D_UNE_LIGNE in e.du.faits_qui_engagent, _second("retrait", prefixe=False)),
    ("formule ajoutée", lambda e: "formule_ajoutee" in e.du.faits_qui_engagent, _formule),
    ("phrase vide", lambda e: not e.phrase, _second("sans_phrase", prefixe=False)),
    ("phrase qui porte un chiffre", lambda e: e.chiffre, _second("chiffre", prefixe=False)),
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
    q = retour.get("question") if isinstance(retour.get("question"), dict) else None
    prefixe = sans_balisage(str(textes.get("prefixe") or "")) or None
    dossier_q = CONV.question_de(p)
    if objet_en_cours is None:
        objet_en_cours = bool(isinstance(p, dict) and (p.get("lignes") or p.get("mode") or p.get("enregistree")))
    return Entrees(
        du=du, phrase=phrase, avant=sans_balisage(str(textes.get("avant") or "")), prefixe=prefixe, suffixe_du_code=sans_balisage(str(textes.get("suffixe") or "")) or None,
        texte_de_la_question=sans_balisage(str((q or {}).get("texte") or "")) or None, question_nee=question_nee_dans_ce_tour(p, etat.tour),
        question_id=dossier_q.get("id") if isinstance(dossier_q, dict) else None, suffixe_avant=suffixe_avant,
        chiffre=bool(phrase) and chiffre_dans_la_phrase(phrase, etat.executees, paroles), objet_en_cours=objet_en_cours, en_attente=isinstance(dossier_q, dict),
        etat=etat, retour=retour, p=p)
