"""[.mark] Chantier Partie 1, lot 6 : la couche de parole d'une étape qui porte la fiche (version finale de B12, repli A seul d'après B13, D62).

Recopie de la boucle du tour du banc (``banc-b12/appel_b12.py`` ``tour``), répartie sur les passages que Pipecat fait déjà :

- **le retour de la fiche** (``parole_du_tour``) : ``a_dire`` est dite en UN passage (``run_llm`` faux) quand rien n'est refusé ni bloquant, qu'aucune
  question ne naît dans ce tour et que la phrase passe la barrière des chiffres ; sinon elle est jetée et le modèle repasse avec le retour ;
- **une phrase libre du modèle** (sans appel d'outil, ``phrase_libre_retenue``) est retenue, une raison à la fois, avec sa ligne d'état :
  A (aucun outil dans ce tour alors qu'un objet est en cours ou qu'une question attend, une fois par tour) ; le rattrapage après un refus (une
  fois par tour, tenu par le drapeau ``rattrapage_refus_joue``, jamais par le texte retenu) ; le repli A (après un refus de LA FICHE, jamais
  dite) ; la barrière des chiffres (toujours) ;
- **au bout** (C5, décision d'Evan 25/11 8 h 45) : le code ne compose aucune phrase ; une phrase retenue, ou un silence, relance le modèle UNE fois par tour avec le fait (``repli.consigne_de_relance``) ; si la relance échoue : la suite réglée déjà posée (``la_suite_reglee``, motifs de ``PHRASES_DU_CODE``), sinon la phrase réglée « pas compris » de l'agent (P3) ; le fait accompli n'est gardé qu'au journal ;
- **ce que le code dit lui-même** (``textes``, posés par la porte, élément 1 (b)) : C6, une phrase réglée (le numéro, le total, le rendu, la question M108 ou DC10) dite juste
  après la phrase du modèle (``suffixe``, gardé dans l'état du tour jusqu'à elle) ; plus aucune porte ne pose ``avant`` (C6 n° 12), la ligne de la table qui le lit reste sans producteur.

Critères structurels seulement (D1) : l'état de l'action et du tour, jamais le sens des mots. L'état du tour vit dans la fiche de l'appel
(``CLE_ETAT_DU_TOUR``), remis à zéro quand la personne reparle (``tour_de_la_personne``).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from dataclasses import asdict, dataclass, field
from typing import Any

from api.services.actions_communes.barriere_des_chiffres import RAPPEL_DU_CHIFFRE, chiffre_dans_la_phrase, porte_les_chiffres, sans_balisage
from api.services.actions_communes.repli import RAPPEL_APRES_REFUS, refus_de_la_fiche, refuse

CLE_ETAT_DU_TOUR = "parole_du_tour"
CLE_TEXTES_DU_CODE = "textes_du_code_de_la_fiche"  # ce que le code dit lui-même pour la fiche du tour (``avant``, ``prefixe``, ``suffixe``), posé par la porte
CLE_DU_TOUR = "tour_de_la_personne"  # le tour de la personne, la même clé que la porte (cases_selon_l_etat.CLE_DU_TOUR)

A_DIRE_SEUL = "a_dire_seul"
SECOND_PASSAGE = "second_passage"

RAPPEL_SANS_OUTIL = "- Ta réponse précédente n'avait pas d'appel d'outil : elle n'a pas été dite, et rien n'est changé."
# Raisons de retenue d'une phrase libre (liste fermée, au glossaire)
SANS_OUTIL, APRES_REFUS, REPLI_A, CHIFFRE = "sans_outil", "rattrapage_apres_refus", "repli_a", "chiffre"
# C6 : la phrase du modèle (la relecture) dit déjà ce que le CODE dit juste après elle (la question, le total) : retenue, le modèle est relancé une fois (``repli.consigne_de_ce_que_le_code_dit``).
CE_QUE_LE_CODE_DIT = "dit_ce_que_le_code_dit"
CHIFFRES_EXIGES = "chiffres_exiges"  # C6 n° 5 : la phrase du modèle ne dit pas les valeurs exigées du fait accompli (l'heure) : relancée une fois, puis la suite réglée seule, sinon P3 (reprise R1)
SILENCE = "silence"  # point de contrôle du lot 7 : le modèle n'a rien rendu, ni texte ni appel, au bout des passes : le modèle est relancé avec le fait (C5)
SUFFIXE = "suffixe_du_code"  # pas une retenue : la phrase dite, suivie de la phrase réglée du code (le total, le rendu, M108)
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
    refus_de_la_fiche_dans_le_tour: bool = False
    rattrapage_a_joue: bool = False
    rattrapage_refus_joue: bool = False
    retenues: list[str] = field(default_factory=list)
    executees: list[dict] = field(default_factory=list)  # les fiches du tour (le code de remise exempte la barrière)
    faits_du_refus: list[Any] = field(default_factory=list)  # les faits que les retours de ce tour donnent au modèle pour dire un refus, ou une lecture (C6 n° 11) : leurs valeurs passent la barrière des chiffres
    suffixe: str | None = None  # la phrase réglée que le code dit juste après la prochaine phrase du modèle (le total, le rendu, M108 ; C6)
    ancre: str | None = None  # C7 (a) : l'identité de la question qui portait la phrase réglée (``suffixe``), posée par la table avec elle ; la seule ancre de « elle attend toujours »
    question_donnee: str | None = None  # lot 19 (D04) : la question née dans ce tour déjà donnée au modèle par un second passage
    suite: list[str] = field(default_factory=list)  # ce qui s'est passé dans ce tour, dans l'ordre (refus, fait, lecture) : « après un refus » = le dernier genre est un refus (ligne 23)
    jetee: str | None = None  # la phrase jetée dans ce tour (texte net), gardée pour ne pas être dite si le modèle la recopie (lignes 19 et 20)
    jetee_apres_une_formule: bool = False  # ... jetée parce qu'une fiche venait d'ajouter une formule
    exiges: dict | None = None  # C6 n° 5 : les valeurs que la phrase du modèle doit dire avant la suite du code (l'heure de la commande enregistrée, ``porte_les_chiffres``) ; ``None`` : rien n'est exigé
    # C6 : ce qui prouve que la relecture est entendue (``{"jeton", "texte", "exiges"}``) : la phrase réglée que le code dit après la relecture du modèle (le total de la commande, la question
    # du numéro de la réservation) et les valeurs que la phrase doit dire (les personnes et l'heure de la réservation, P2) ; notée au journal quand elle part à la voix (``noter_le_total_dit``)
    total_a_dire: dict | None = None
    relance_du_fait: bool = False  # C5 : le modèle a été relancé avec le fait dans ce tour (une fois par tour de la personne, remis à zéro avec l'état)
    lecture_pas_vue: bool = False  # P3 (lot 19 bis) : une lecture de ce tour a rendu son résultat sans que le modèle l'ait encore reçu (Pipecat attend la fin du groupe d'appels)


CLE_TOTAL_DIT = "total_de_la_relecture_dit"  # entrée du journal du dit : ``jeton`` = la relecture dont la phrase du total a été dite (l'accord ne vaut que pour elle)


def _relecture_entendue_dans(attendu: dict, dit: str) -> bool:
    """La phrase partie à la voix porte la phrase réglée attendue (si elle est donnée) ET les valeurs exigées (si elles le sont) ; rien d'attendu : rien n'est entendu."""
    texte = sans_balisage(str(attendu.get("texte") or ""))
    exiges = attendu.get("exiges") if isinstance(attendu.get("exiges"), dict) else None
    if not texte and exiges is None:
        return False
    return (not texte or texte in sans_balisage(dit)) and (exiges is None or porte_les_chiffres(dit, exiges))


def noter_le_total_dit(p: Any, etat: EtatDuTour, dit: str | None) -> None:
    """C6 : ``dit`` part à la voix ; s'il porte ce qui prouve la relecture (``etat.total_a_dire`` : la phrase réglée du total, ou les valeurs exigées de la réservation), la relecture est notée
    au journal du dit, à son jeton. Un « oui » ne vaut accord que pour une relecture ainsi entendue (``total_dit``) : relance échouée sans elle, phrase réglée « pas compris », rien n'est
    noté, aucun accord."""
    attendu = etat.total_a_dire if isinstance(etat.total_a_dire, dict) else None
    if attendu and isinstance(p, dict) and dit and _relecture_entendue_dans(attendu, dit):
        J.poser(p, CLE_TOTAL_DIT, etat.tour, jeton=attendu.get("jeton"))
        etat.total_a_dire = None


def total_dit(p: Any, jeton: Any) -> bool:
    """C6 : la phrase du total de la relecture de ce ``jeton`` a-t-elle été dite ? Lu au journal du dit."""
    return bool(jeton) and (J.entree(p, CLE_TOTAL_DIT) or {}).get("jeton") == jeton


REFUS, REFUS_DE_LA_FICHE, LECTURE, FAIT = "refus", "refus_de_la_fiche", "lecture", "fait"  # les genres de la suite du tour


def _net(texte: Any) -> str:
    return " ".join(sans_balisage(str(texte or "")).casefold().split()).rstrip(" .!?…")


def apres_un_refus(etat: EtatDuTour, *, de_la_fiche: bool = False) -> bool:
    """Le dernier genre de la suite de CE tour est un refus (``de_la_fiche`` : une faute de la fiche). Une lecture n'efface rien : elle vient après."""
    return bool(etat.suite) and (etat.suite[-1] == REFUS_DE_LA_FICHE if de_la_fiche else etat.suite[-1] in (REFUS, REFUS_DE_LA_FICHE))


def jeter(etat: EtatDuTour, texte: str, *, formule: bool = False) -> None:
    """Lignes 19 et 20 : la phrase que le code vient de jeter est gardée jusqu'à la fin du tour (une phrase vide garde celle du tour). Aucune lecture du sens : une égalité de texte."""
    if _net(texte):
        etat.jetee = _net(texte)
    etat.jetee_apres_une_formule = formule


def jetee(etat: EtatDuTour, texte: str, *, apres_un_refus: bool = False) -> bool:
    """Le texte est-il la phrase jetée de CE tour, après un refus ou une formule ajoutée ?"""
    return bool(etat.jetee and _net(texte) == etat.jetee and (apres_un_refus or etat.jetee_apres_une_formule))


def etat_du_tour(fiche_de_l_appel: Any) -> EtatDuTour:
    """L'état du tour en cours, remis à zéro quand la personne reparle. Sans fiche (un essai isolé) : un état jetable."""
    if not isinstance(fiche_de_l_appel, dict):
        return EtatDuTour()
    tour = fiche_de_l_appel.get(CLE_DU_TOUR)
    brut = fiche_de_l_appel.get(CLE_ETAT_DU_TOUR)
    if isinstance(brut, dict) and brut.get("tour") == tour:
        return EtatDuTour(**{k: v for k, v in brut.items() if k in EtatDuTour.__dataclass_fields__})
    return EtatDuTour(tour=tour)


def admettre_les_valeurs(fiche_de_l_appel: Any, faits: Any) -> None:
    """C6 n° 11 (décision d'Evan 25/11 9 h 30, § 8 bis : les prix D33 passent au modèle, vérifiés par la barrière) : les valeurs que le code donne au modèle hors d'une fiche (le prix
    d'une lecture, PRX5) passent la barrière des chiffres jusqu'à la fin du tour, dans sa réponse à la lecture comme dans la phrase de sa fiche ; une autre valeur est retenue.
    Seul le prix (``faits["prix"]``) est admis : jamais le total ni le sous-total d'une lecture du panier, que la phrase réglée du code dit (brief C6 § 7, reprise R2)."""
    prix = faits.get("prix") if isinstance(faits, dict) else None
    if isinstance(fiche_de_l_appel, dict) and prix:
        etat = etat_du_tour(fiche_de_l_appel)
        etat.faits_du_refus.append({"prix": prix})
        garder(fiche_de_l_appel, etat)


def noter_la_lecture_rendue(fiche_de_l_appel: Any) -> None:
    """P3 : une lecture (``lire``) vient de rendre son résultat dans ce tour. Si une fiche du même groupe d'appels est encore en cours, Pipecat ne relance pas le modèle (il attend le dernier résultat) :
    la fiche qui arrive ensuite doit alors laisser la relance (``la_fiche_laisse_la_relance``), sinon la réponse à la question ne serait jamais dite."""
    if isinstance(fiche_de_l_appel, dict):
        etat = etat_du_tour(fiche_de_l_appel)
        etat.lecture_pas_vue = True
        # Lot 20 (n11) : la lecture est la dernière chose rendue au modèle : sa phrase répond à la lecture, elle n'est plus un rattrapage du refus d'une
        # fiche d'avant (« La Napoli contient des anchois… » retenue puis relancée avec le fait). Une fiche refusée APRÈS elle repose le refus.
        etat.suite.append(LECTURE)  # ligne 23 : le refus n'est pas effacé, la lecture vient après lui
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


def question_nee_dans_ce_tour(p: dict | None, tour: Any) -> bool:
    q = CONV.question_de(p)
    return isinstance(q, dict) and q.get("nee_au_tour") == tour and tour is not None


def parole_du_tour(retour: dict, a_dire: Any, etat: EtatDuTour, paroles: list[str], p: dict | None = None, fiche: dict | None = None,
                   textes: dict | None = None, objet_en_cours: bool | None = None) -> Decision:
    """Le retour de LA fiche de ce tour, et sa phrase : dite seule (un passage), ou jetée (second passage, avec le retour). Met l'état à jour.
    ``textes`` : ce que le code dit lui-même pour cette fiche (``porte.CLE_TEXTES_DU_CODE``). C6 n° 11 : le prix d'une lecture du même tour n'est plus dit par le code (le modèle le
    dit, ``admettre_les_valeurs``)."""
    return _decision_du_tour(retour, a_dire, etat, paroles, p, fiche, textes, objet_en_cours)


def _decision_du_tour(retour: dict, a_dire: Any, etat: EtatDuTour, paroles: list[str], p: dict | None = None, fiche: dict | None = None,
                      textes: dict | None = None, objet_en_cours: bool | None = None) -> Decision:
    """La parole de ce retour : ce que le tour a déjà dit est mis à jour, puis la table (``table_de_parole``) décide."""
    from api.services.actions_communes import table_de_parole as TABLE

    textes = textes if isinstance(textes, dict) else {}
    etat.fiches += 1
    suffixe_avant, ancre_avant = etat.suffixe, etat.ancre  # la phrase réglée que le code dit après la phrase du modèle, posée au passage précédent (C6), et sa question (C7 a)
    etat.suffixe = etat.ancre = None
    if isinstance(fiche, dict):
        etat.executees.append({k: v for k, v in fiche.items() if k == "code_de_remise"})
    from api.services.actions_communes.du import faits_du_refus

    etat.faits_du_refus.extend(faits_du_refus(retour))
    refusee = refuse(retour)
    de_la_fiche = refusee and refus_de_la_fiche(retour)
    etat.refus_de_la_fiche_dans_le_tour = etat.refus_de_la_fiche_dans_le_tour or de_la_fiche
    etat.suite.append(REFUS_DE_LA_FICHE if de_la_fiche else REFUS if refusee else FAIT)  # ligne 23
    phrase = sans_balisage(str(a_dire or ""))
    jeter(etat, phrase)  # ce qui est jeté dans le tour (ligne 20) ; oubliée si la phrase est dite en un passage
    return TABLE.decider(TABLE.entrees_du_retour(retour, phrase, etat, paroles, p, textes, objet_en_cours, suffixe_avant, ancre_avant, fiche_vide(fiche)))


def fiche_vide(arguments: Any) -> bool:
    """PE-2 (Q3) : la fiche jouée ne porte aucune case : ses arguments n'ont rien d'autre que la phrase du modèle (``a_dire``). Une forme (une case remplie ou non), jamais un mot ;
    sans arguments lisibles : faux."""
    return isinstance(arguments, dict) and not any(v for k, v in arguments.items() if k != "a_dire")


def pose_une_question(phrase: str) -> bool:
    """La phrase pose-t-elle une question : sa dernière proposition se termine par « ? » (sa ponctuation, jamais ses mots). Le seul critère de la parole."""
    return sans_balisage(phrase).rstrip(" .!…").endswith("?")


MANQUE = "manque_a_demander"  # motif : ce qui manque est dû, la phrase du modèle ne le demande pas ; il repasse avec lui (B2, M3)


def avec_le_suffixe(texte: str, etat: EtatDuTour, p: Any = None) -> str | None:
    """La phrase du modèle suivie de la phrase réglée que le code dit après elle (le total, le rendu, M108 ; C6) ; ``None`` sans rien en attente. Elle n'est dite qu'une fois.
    ``p`` : le dossier, pour noter la phrase du total dite."""
    if not etat.suffixe:
        return None
    dit = " ".join(x for x in (sans_balisage(texte), etat.suffixe) if x)
    etat.suffixe = etat.ancre = None  # la phrase dite emporte son ancre (C7 a : une ancre sans phrase ne désigne plus rien)
    noter_le_total_dit(p, etat, dit)
    return dit


def la_suite_reglee(etat: EtatDuTour) -> str | None:
    """Reprise R1 de l'audit de C6 (décisions d'Evan 25/11 8 h 45 et 9 h 30, P3) : la phrase du modèle manque (relance ratée) ; le code ne dit que la suite réglée déjà posée après elle
    (motifs de ``PHRASES_DU_CODE`` : le numéro, le total, le rendu, M108), jamais le fait accompli (gardé au journal seulement). Elle n'est dite qu'une fois. ``None`` : rien de réglé, la
    phrase réglée « pas compris » de l'agent (P3) la remplace."""
    dit = etat.suffixe or None
    etat.suffixe = etat.ancre = None
    etat.exiges = None
    return dit


def question_due_sans_suite(phrase: str, suite: str | None, en_attente: bool) -> bool:
    """Reprise R2 de C6 (ordre de « C6 révisée » : la question est la dernière) : le code ne dit rien après la phrase du modèle (``suite`` vide) et une question attend (DC4, la proposition,
    la relecture de la réservation sans numéro à relire) : la phrase doit la poser. Vrai quand elle ne la pose pas. Forme seulement (le « ? »), jamais les mots."""
    return not suite and en_attente and not pose_une_question(phrase)


def dit_ce_que_le_code_dit(texte: str, etat: EtatDuTour) -> bool:
    """C6 : le code dit une QUESTION après la phrase du modèle (``etat.suffixe`` se termine par « ? ») et la phrase du modèle en pose déjà une : deux questions dans un tour. Forme seulement."""
    return bool(etat.suffixe) and pose_une_question(etat.suffixe) and pose_une_question(texte)


REPRISE = "reprise_de_la_question"  # motif : la phrase dite n'a pas posé la question en attente ; le modèle est relancé avec elle (lot 20, C5)


def question_oubliee(texte: str, etat: EtatDuTour, p: dict | None) -> bool:
    """Lot 20 (Evan, 21/11 : « l'agent dit "je n'ai pas compris", puis reprend ce qu'il faisait ») : une question attend, rien n'a changé dans ce tour (aucune fiche) et la phrase du modèle
    n'en pose aucune (une question à la fois). C5 (décision d'Evan 25/11 8 h 45) : le code ne la redit plus, le modèle est relancé avec elle. Critère sur l'état du tour et la forme de la phrase,
    jamais sur ses mots."""
    return not etat.fiches and isinstance(p, dict) and CONV.question_de(p) is not None and not pose_une_question(texte)


def phrase_libre_retenue(texte: str, etat: EtatDuTour, *, objet_en_cours: bool, question_en_attente: bool, paroles: list[str], p: dict | None = None) -> str | None:
    """La raison de retenir une phrase du modèle sans appel d'outil (``None`` : elle est dite). Met l'état à jour (une retenue A et un rattrapage
    après refus au plus par tour)."""
    if etat.fiches == 0 and not etat.rattrapage_a_joue and (objet_en_cours or question_en_attente):
        etat.rattrapage_a_joue = True
        etat.retenues.append(SANS_OUTIL)
        return SANS_OUTIL
    apres_refus = apres_un_refus(etat)
    if apres_refus and not etat.rattrapage_refus_joue:
        etat.rattrapage_refus_joue = True
        etat.retenues.append(APRES_REFUS)
        return APRES_REFUS
    if etat.refus_de_la_fiche_dans_le_tour and apres_un_refus(etat, de_la_fiche=True):
        etat.retenues.append(REPLI_A)
        return REPLI_A
    if jetee(etat, texte, apres_un_refus=apres_refus):
        # Mesure finale 2 du lot 11 (FOR10-A) : au second passage d'une formule ajoutée, le modèle recopiait la phrase jetée qui inventait sa
        # composition : recopiée, elle n'est pas dite non plus (même égalité de texte que sur un refus, jamais une lecture du sens).
        # Point de contrôle du lot 7 (conv2) : après un refus, la relance recopiait la phrase jetée sur le hors zone (« C'est bien noté … à
        # Compiègne ») : une phrase jetée sur un refus n'est jamais dite. Hors refus, la phrase redite au second passage reste dite (B12).
        etat.retenues.append(REPLI_A)
        return REPLI_A
    if chiffre_dans_la_phrase(texte, etat.executees, paroles, etat.faits_du_refus):
        etat.retenues.append(CHIFFRE)
        return CHIFFRE
    return None
