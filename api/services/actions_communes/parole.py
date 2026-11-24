"""[.mark] Chantier Partie 1, lot 6 : la couche de parole d'une étape qui porte la fiche (version finale de B12, repli A seul d'après B13, D62).

Recopie de la boucle du tour du banc (``banc-b12/appel_b12.py`` ``tour``), répartie sur les passages que Pipecat fait déjà :

- **le retour de la fiche** (``parole_du_tour``) : ``a_dire`` est dite en UN passage (``run_llm`` faux) quand rien n'est refusé ni bloquant, qu'aucune
  question ne naît dans ce tour et que la phrase passe la barrière des chiffres ; sinon elle est jetée et le modèle repasse avec le retour ;
- **une phrase libre du modèle** (sans appel d'outil, ``phrase_libre_retenue``) est retenue, une raison à la fois, avec sa ligne d'état :
  A (aucun outil dans ce tour alors qu'un objet est en cours ou qu'une question attend, une fois par tour) ; le rattrapage après un refus (une
  fois par tour, tenu par le drapeau ``rattrapage_refus_joue``, jamais par le texte retenu) ; le repli A (après un refus de LA FICHE, jamais
  dite) ; la barrière des chiffres (toujours) ;
- **au bout** : une relance encore retenue, ou vide, est remplacée par ``repli_dit_par_le_code`` (le code redemande, il ne choisit rien) ;
- **ce que le code dit lui-même** (``textes`` : ``avant``, ``prefixe``, ``suffixe``, posés par la porte, élément 1 (b)) : le récapitulatif ou la
  confirmation est dit seul et le tour s'arrête (la phrase du modèle est jetée) ; la règle chiffrée qui bloque est dite, puis le modèle repasse ;
  le prix d'une proposition est dit juste après la phrase du modèle (gardé dans l'état du tour jusqu'à elle).

Critères structurels seulement (D1) : l'état de l'action et du tour, jamais le sens des mots. L'état du tour vit dans la fiche de l'appel
(``CLE_ETAT_DU_TOUR``), remis à zéro quand la personne reparle (``tour_de_la_personne``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from api.services.actions_communes.barriere_des_chiffres import RAPPEL_DU_CHIFFRE, chiffre_dans_la_phrase, sans_balisage
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.repli import RAPPEL_APRES_REFUS, refus_de_la_fiche, refuse

CLE_ETAT_DU_TOUR = "parole_du_tour"
CLE_TEXTES_DU_CODE = "textes_du_code_de_la_fiche"  # ce que le code dit lui-même pour la fiche du tour (``avant``, ``prefixe``, ``suffixe``), posé par la porte
CLE_DU_TOUR = "tour_de_la_personne"  # le tour de la personne, la même clé que la porte (cases_selon_l_etat.CLE_DU_TOUR)
PASSES_AU_PLUS = 5

A_DIRE_SEUL = "a_dire_seul"
SECOND_PASSAGE = "second_passage"

RAPPEL_SANS_OUTIL = "- Ta réponse précédente n'avait pas d'appel d'outil : elle n'a pas été dite, et rien n'est changé."
# Raisons de retenue d'une phrase libre (liste fermée, au glossaire)
SANS_OUTIL, APRES_REFUS, REPLI_A, CHIFFRE = "sans_outil", "rattrapage_apres_refus", "repli_a", "chiffre"
SILENCE = "silence"  # point de contrôle du lot 7 : le modèle n'a rien rendu, ni texte ni appel, au bout des passes : le repli du code est dit
SUFFIXE = "suffixe_du_code"  # pas une retenue : la phrase dite, suivie du prix dit par le code
RAPPELS = {SANS_OUTIL: RAPPEL_SANS_OUTIL, APRES_REFUS: RAPPEL_APRES_REFUS, REPLI_A: RAPPEL_APRES_REFUS, CHIFFRE: RAPPEL_DU_CHIFFRE}
QUESTION_DEJA_DONNEE = "question_deja_donnee"  # motif : la question née dans le tour, déjà donnée au modèle, posée par la phrase de sa fiche (lot 19)
FORMULE_AJOUTEE = "formule_ajoutee"  # motif : une ligne de formule ajoutée, dont le retour porte la composition (lot 11)
# Lot 20 (conv4, D36) : un retour qui porte des faits que le modèle doit dire (le code les donne, il ne parle pas) : la phrase écrite avant ce retour ne les
# connaissait pas, elle est jetée et le modèle repasse avec eux. Posé par le connecteur, lu ici sans aucun mot de métier.
FAITS_A_DIRE = "faits_a_dire"  # le MOTIF de la décision (``du.CLE_FAITS_A_DIRE`` est la clé du retour)
DU_DIT = "du_dit_par_le_code"  # pas une retenue : la phrase du modèle, suivie de ce qui manque, dit par le code (B2, M3, règle 1)


@dataclass
class EtatDuTour:
    tour: Any = None
    fiches: int = 0  # fiches exécutées dans ce tour
    apres_refus: bool = False  # la dernière fiche du tour a été refusée (fiche ou métier)
    apres_refus_de_la_fiche: bool = False  # ... pour une faute de LA FICHE (``REFUS_DE_LA_FICHE``)
    refus_de_la_fiche_dans_le_tour: bool = False
    rattrapage_a_joue: bool = False
    rattrapage_refus_joue: bool = False
    retenues: list[str] = field(default_factory=list)
    executees: list[dict] = field(default_factory=list)  # les fiches du tour (le code de remise exempte la barrière)
    suffixe: str | None = None  # le prix dit par le code juste après la prochaine phrase du modèle (D33)
    suffixe_lu: str | None = None  # le prix d'une LECTURE de ce tour (PRX5) : dit après la phrase qui suit, que ce soit un texte, ou la phrase d'une fiche (même tour)
    question_donnee: str | None = None  # lot 19 (D04) : la question née dans ce tour déjà donnée au modèle par un second passage
    lecture_pas_vue: bool = False  # P3 (lot 19 bis) : une lecture de ce tour a rendu son résultat sans que le modèle l'ait encore reçu (Pipecat attend la fin du groupe d'appels)


def etat_du_tour(fiche_de_l_appel: Any) -> EtatDuTour:
    """L'état du tour en cours, remis à zéro quand la personne reparle. Sans fiche (un essai isolé) : un état jetable."""
    if not isinstance(fiche_de_l_appel, dict):
        return EtatDuTour()
    tour = fiche_de_l_appel.get(CLE_DU_TOUR)
    brut = fiche_de_l_appel.get(CLE_ETAT_DU_TOUR)
    if isinstance(brut, dict) and brut.get("tour") == tour:
        return EtatDuTour(**{k: v for k, v in brut.items() if k in EtatDuTour.__dataclass_fields__})
    return EtatDuTour(tour=tour)


def poser_le_suffixe_lu(fiche_de_l_appel: Any, suffixe: str) -> None:
    """Lot 12 (PRX5, conversation du lot 12) : le prix qu'une lecture vient de rendre est dit par le code après la phrase du modèle ; il tient jusqu'à être dit, même si le modèle
    répond ensuite par une fiche (sa phrase ``a_dire``, dont le chiffre est retenu) : sans cela le prix lu n'était jamais dit."""
    if isinstance(fiche_de_l_appel, dict) and suffixe:
        etat = etat_du_tour(fiche_de_l_appel)
        etat.suffixe = etat.suffixe_lu = sans_balisage(suffixe) or None
        garder(fiche_de_l_appel, etat)


def noter_la_lecture_rendue(fiche_de_l_appel: Any) -> None:
    """P3 : une lecture (``lire``) vient de rendre son résultat dans ce tour. Si une fiche du même groupe d'appels est encore en cours, Pipecat ne relance pas le modèle (il attend le dernier résultat) :
    la fiche qui arrive ensuite doit alors laisser la relance (``la_fiche_laisse_la_relance``), sinon la réponse à la question ne serait jamais dite."""
    if isinstance(fiche_de_l_appel, dict):
        etat = etat_du_tour(fiche_de_l_appel)
        etat.lecture_pas_vue = True
        # Lot 20 (n11) : la lecture est la dernière chose rendue au modèle : sa phrase répond à la lecture, elle n'est plus un rattrapage du refus d'une
        # fiche d'avant (« La Napoli contient des anchois… » retenue puis remplacée par le repli). Une fiche refusée APRÈS elle repose le refus.
        etat.apres_refus = etat.apres_refus_de_la_fiche = False
        garder(fiche_de_l_appel, etat)


def la_lecture_est_vue(fiche_de_l_appel: Any) -> None:
    """P3 : le modèle part pour une requête : il reçoit tous les résultats rendus jusque-là, la lecture n'attend plus personne."""
    if isinstance(fiche_de_l_appel, dict) and (fiche_de_l_appel.get(CLE_ETAT_DU_TOUR) or {}).get("lecture_pas_vue"):
        etat = etat_du_tour(fiche_de_l_appel)
        etat.lecture_pas_vue = False
        garder(fiche_de_l_appel, etat)


def la_fiche_laisse_la_relance(fiche_de_l_appel: Any) -> bool:
    """P3 : vrai quand une lecture du même tour attend encore que le modèle la reçoive : la fiche dite seule ne coupe pas la relance (le modèle repasse, sa réponse à la lecture est dite)."""
    return etat_du_tour(fiche_de_l_appel).lecture_pas_vue


def garder(fiche_de_l_appel: Any, etat: EtatDuTour) -> None:
    if isinstance(fiche_de_l_appel, dict):
        fiche_de_l_appel[CLE_ETAT_DU_TOUR] = asdict(etat)


@dataclass(frozen=True)
class Decision:
    mode: str  # ``A_DIRE_SEUL`` ou ``SECOND_PASSAGE``
    a_dire: str | None = None
    motif: str = ""  # pourquoi ce mode (jamais une raison de refus : elles sont rangées « fiche » ou « métier »)
    prefixe: str | None = None  # dit par le code AVANT le second passage du modèle


def question_nee_dans_ce_tour(p: dict | None, tour: Any) -> bool:
    q = (p or {}).get("question") if isinstance(p, dict) else None
    return isinstance(q, dict) and q.get("nee_au_tour") == tour and tour is not None


def parole_du_tour(retour: dict, a_dire: Any, etat: EtatDuTour, paroles: list[str], p: dict | None = None, fiche: dict | None = None,
                   textes: dict | None = None, objet_en_cours: bool | None = None) -> Decision:
    """Le retour de LA fiche de ce tour, et sa phrase : dite seule (un passage), ou jetée (second passage, avec le retour). Met l'état à jour.
    ``textes`` : ce que le code dit lui-même pour cette fiche (``porte.CLE_TEXTES_DU_CODE``). Le prix d'une lecture du même tour (``suffixe_lu``) est dit après la phrase :
    ajouté à la phrase dite seule, ou gardé pour le second passage."""
    decision = _decision_du_tour(retour, a_dire, etat, paroles, p, fiche, textes, objet_en_cours)
    lu = etat.suffixe_lu
    if lu:
        if decision.mode == A_DIRE_SEUL and decision.motif == "fait":
            etat.suffixe_lu = None
            decision = replace(decision, a_dire=" ".join(x for x in (decision.a_dire, lu) if x))
        elif decision.mode == SECOND_PASSAGE and not etat.suffixe:
            etat.suffixe = lu
    return decision


def _decision_du_tour(retour: dict, a_dire: Any, etat: EtatDuTour, paroles: list[str], p: dict | None = None, fiche: dict | None = None,
                      textes: dict | None = None, objet_en_cours: bool | None = None) -> Decision:
    """La parole de ce retour : ce que le tour a déjà dit est mis à jour, puis la table (``table_de_parole``) décide."""
    from api.services.actions_communes import table_de_parole as TABLE

    textes = textes if isinstance(textes, dict) else {}
    etat.fiches += 1
    suffixe_avant = etat.suffixe  # le prix que le code dit après la phrase du modèle, posé au passage précédent (D33)
    etat.suffixe = None
    if isinstance(fiche, dict):
        etat.executees.append({k: v for k, v in fiche.items() if k == "code_de_remise"})
    etat.apres_refus = refuse(retour)
    etat.apres_refus_de_la_fiche = etat.apres_refus and refus_de_la_fiche(retour)
    etat.refus_de_la_fiche_dans_le_tour = etat.refus_de_la_fiche_dans_le_tour or etat.apres_refus_de_la_fiche
    phrase = sans_balisage(str(a_dire or ""))
    J.jeter(p, phrase, etat.tour)  # au journal de ce qui est dit (ligne 20) ; effacée si la phrase est dite en un passage
    return TABLE.decider(TABLE.entrees_du_retour(retour, phrase, etat, paroles, p, textes, objet_en_cours, suffixe_avant))


def repli_sans_le_fait_bloquant_de(p: dict | None) -> str | None:
    from api.services.actions_communes.repli import _repli_sans_le_fait_bloquant

    return _repli_sans_le_fait_bloquant(p, None, None)


def pose_une_question(phrase: str) -> bool:
    """La phrase pose-t-elle une question : sa dernière proposition se termine par « ? » (sa ponctuation, jamais ses mots). Le seul critère de la parole."""
    return sans_balisage(phrase).rstrip(" .!…").endswith("?")


MANQUE = "manque_a_demander"  # motif : ce qui manque est dû, la phrase du modèle ne le demande pas ; il repasse avec lui (B2, M3)


def avec_le_suffixe(texte: str, etat: EtatDuTour) -> str | None:
    """La phrase du modèle suivie du prix que le code dit après elle (D33) ; ``None`` sans prix en attente. Le prix n'est dit qu'une fois."""
    if not etat.suffixe:
        return None
    dit = " ".join(x for x in (sans_balisage(texte), etat.suffixe) if x)
    etat.suffixe = etat.suffixe_lu = None
    return dit


REPRISE = "reprise_de_la_question"  # pas une retenue : la phrase dite, suivie de la question en attente redite par le code (lot 20)


def reprise_apres_la_phrase(texte: str, etat: EtatDuTour, p: dict | None, texte_du_manque: Any = None, fiche: Any = None, *, rien_change: bool = False) -> str | None:
    """Lot 20 (Evan, 21/11 : « l'agent dit "je n'ai pas compris", puis reprend ce qu'il faisait ») : la question en attente, redite par le code après la
    phrase du modèle, quand rien n'a changé dans ce tour (aucune fiche) et que sa phrase ne pose pas déjà une question (une question à la fois). Sinon ``None``.
    Critère sur l'état du tour et la forme de la phrase, jamais sur ses mots.
    ``rien_change`` (M1, RC4 : trois fois la même fiche dans un tour) : la fiche qui vient de passer n'a rien changé, les fiches d'avant dans le tour ne retirent
    pas ce qui est dû : la question en attente, ou ce qui manque, suit la phrase."""
    from api.services.actions_communes.repli import _repli_sans_le_fait_bloquant

    if (etat.fiches and not rien_change) or not isinstance(p, dict) or not isinstance(p.get("question"), dict):
        return None
    if pose_une_question(texte):
        return None
    return _repli_sans_le_fait_bloquant(p, texte_du_manque, fiche)


def phrase_libre_retenue(texte: str, etat: EtatDuTour, *, objet_en_cours: bool, question_en_attente: bool, paroles: list[str], p: dict | None = None) -> str | None:
    """La raison de retenir une phrase du modèle sans appel d'outil (``None`` : elle est dite). Met l'état à jour (une retenue A et un rattrapage
    après refus au plus par tour)."""
    if etat.fiches == 0 and not etat.rattrapage_a_joue and (objet_en_cours or question_en_attente):
        etat.rattrapage_a_joue = True
        etat.retenues.append(SANS_OUTIL)
        return SANS_OUTIL
    if etat.apres_refus and not etat.rattrapage_refus_joue:
        etat.rattrapage_refus_joue = True
        etat.retenues.append(APRES_REFUS)
        return APRES_REFUS
    if etat.refus_de_la_fiche_dans_le_tour and etat.apres_refus_de_la_fiche:
        etat.retenues.append(REPLI_A)
        return REPLI_A
    if J.jetee(p, texte, etat.tour, apres_un_refus=etat.apres_refus):
        # Mesure finale 2 du lot 11 (FOR10-A) : au second passage d'une formule ajoutée, le modèle recopiait la phrase jetée qui inventait sa
        # composition : recopiée, elle n'est pas dite non plus (même égalité de texte que sur un refus, jamais une lecture du sens).
        # Point de contrôle du lot 7 (conv2) : après un refus, la relance recopiait la phrase jetée sur le hors zone (« C'est bien noté … à
        # Compiègne ») : une phrase jetée sur un refus n'est jamais dite. Hors refus, la phrase redite au second passage reste dite (B12).
        etat.retenues.append(REPLI_A)
        return REPLI_A
    if chiffre_dans_la_phrase(texte, etat.executees, paroles):
        etat.retenues.append(CHIFFRE)
        return CHIFFRE
    return None
