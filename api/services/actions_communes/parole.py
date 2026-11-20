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
BLOQUANTS = ("PARTIEL", "REJETEE", "INTROUVABLE", "A_PRECISER")
QUESTION_DEJA_DONNEE = "question_deja_donnee"  # motif : la question née dans le tour, déjà donnée au modèle, posée par la phrase de sa fiche (lot 19)
FORMULE_AJOUTEE = "formule_ajoutee"  # motif : une ligne de formule ajoutée, dont le retour porte la composition (lot 11)
RETRAIT_D_UNE_LIGNE = "retirer_article"  # la case de la fiche qui retire une ligne entière (contrat de la commande)


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
    a_dire_jetee: str | None = None  # la phrase ``a_dire`` d'une fiche de ce tour jetée au second passage : jamais dite après un refus
    apres_formule: bool = False  # la dernière fiche du tour a ajouté une formule (motif ``FORMULE_AJOUTEE``) : sa phrase jetée n'est jamais dite non plus
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
                   textes: dict | None = None) -> Decision:
    """Le retour de LA fiche de ce tour, et sa phrase : dite seule (un passage), ou jetée (second passage, avec le retour). Met l'état à jour.
    ``textes`` : ce que le code dit lui-même pour cette fiche (``porte.CLE_TEXTES_DU_CODE``). Le prix d'une lecture du même tour (``suffixe_lu``) est dit après la phrase :
    ajouté à la phrase dite seule, ou gardé pour le second passage."""
    decision = _decision_du_tour(retour, a_dire, etat, paroles, p, fiche, textes)
    lu = etat.suffixe_lu
    if lu:
        if decision.mode == A_DIRE_SEUL and decision.motif == "fait":
            etat.suffixe_lu = None
            decision = replace(decision, a_dire=" ".join(x for x in (decision.a_dire, lu) if x))
        elif decision.mode == SECOND_PASSAGE and not etat.suffixe:
            etat.suffixe = lu
    return decision


def _decision_du_tour(retour: dict, a_dire: Any, etat: EtatDuTour, paroles: list[str], p: dict | None = None, fiche: dict | None = None,
                      textes: dict | None = None) -> Decision:
    textes = textes if isinstance(textes, dict) else {}
    etat.fiches += 1
    suffixe_avant = etat.suffixe  # le prix que le code dit après la phrase du modèle, posé au passage précédent (D33)
    etat.suffixe = None
    if isinstance(fiche, dict):
        etat.executees.append({k: v for k, v in fiche.items() if k == "code_de_remise"})
    etat.apres_refus = refuse(retour)
    etat.apres_formule = False
    etat.apres_refus_de_la_fiche = etat.apres_refus and refus_de_la_fiche(retour)
    etat.refus_de_la_fiche_dans_le_tour = etat.refus_de_la_fiche_dans_le_tour or etat.apres_refus_de_la_fiche
    phrase = sans_balisage(str(a_dire or ""))
    etat.a_dire_jetee = phrase or etat.a_dire_jetee  # posée ici, effacée si la phrase est dite en un passage
    prefixe = sans_balisage(str(textes.get("prefixe") or "")) or None  # la règle chiffrée qui bloque : dite avant tout second passage
    avant = sans_balisage(str(textes.get("avant") or ""))
    if avant:
        # le récapitulatif, la confirmation : dits par le code, mot pour mot, même si une autre case est refusée (banc : ``recap_code``)
        return Decision(A_DIRE_SEUL, a_dire=avant, motif="texte_du_code")
    remplace = phrase_du_code_qui_remplace(retour, p, etat.tour, prefixe)
    if remplace:
        # Lot 9 (OPT3-A, OPT8-B ; recommandation 1 de SA-5, retenue par le coordinateur) : une question d'ambiguïté née dans le tour ou le refus d'un
        # maximum est dit par le code, à la place de la phrase du modèle (« je ne trouve pas de bubble tea » quand le code demandait « Bubble tea ? »)
        return Decision(A_DIRE_SEUL, a_dire=remplace, motif="texte_du_code")
    if etat.apres_refus:
        return Decision(SECOND_PASSAGE, motif="refus", prefixe=prefixe)
    if retour.get("statut") in BLOQUANTS or (retour.get("faits") or {}).get("fait_bloquant"):
        return Decision(SECOND_PASSAGE, motif="fait_bloquant", prefixe=prefixe)
    if question_nee_dans_ce_tour(p, etat.tour) or retour.get("prix_dit_par_le_code_apres_ta_phrase"):
        question_id = ((p or {}).get("question") or {}).get("id") if isinstance(p, dict) else None
        if (question_id and question_id == etat.question_donnee and not retour.get("prix_dit_par_le_code_apres_ta_phrase") and not prefixe and phrase
                and not chiffre_dans_la_phrase(phrase, etat.executees, paroles)):
            # Lot 19 (D04 ; styles du lot 17, SOBRE-A) : la question née dans ce tour a déjà été donnée au modèle par un second passage ; il y répond
            # par une fiche qui ne change rien et pose la question dans sa phrase : elle est dite (puis le prix dû après elle), jamais un passage de plus
            etat.a_dire_jetee = None
            return Decision(A_DIRE_SEUL, a_dire=" ".join(x for x in (phrase, suffixe_avant) if x), motif=QUESTION_DEJA_DONNEE)
        etat.question_donnee = question_id
        etat.suffixe = sans_balisage(str(textes.get("suffixe") or "")) or None
        return Decision(SECOND_PASSAGE, motif="question_nouvelle", prefixe=prefixe)
    if prefixe:
        return Decision(SECOND_PASSAGE, motif="fait_bloquant", prefixe=prefixe)
    if RETRAIT_D_UNE_LIGNE in (retour.get("cases_executees") or []):
        # Point de contrôle du lot 7 (f307) : la phrase est écrite AVANT que le code exécute ; une ligne retirée n'est jamais annoncée par elle
        # (« je change la boisson » quand le menu entier partait) : le modèle repasse avec le retour, qui dit ce qui est retiré.
        return Decision(SECOND_PASSAGE, motif="retrait")
    if compose_une_formule(retour):
        # Conversations du lot 11 (mesure finale) : la phrase écrite avant le retour inventait la composition d'une formule qu'elle ne connaissait pas
        # (« le choix entre une boisson et un dessert » pour entrée et plat) : le modèle repasse avec le retour, qui porte ses étapes et ses choix.
        etat.apres_formule = True
        return Decision(SECOND_PASSAGE, motif=FORMULE_AJOUTEE)
    if not phrase:
        return Decision(SECOND_PASSAGE, motif="sans_phrase")
    if chiffre_dans_la_phrase(phrase, etat.executees, paroles):
        return Decision(SECOND_PASSAGE, motif="chiffre")
    etat.a_dire_jetee = None
    return Decision(A_DIRE_SEUL, a_dire=phrase, motif="fait")


def phrase_du_code_qui_remplace(retour: dict, p: dict | None, tour: Any, prefixe: str | None) -> str | None:
    """La phrase du code qui remplace celle du modèle, ou ``None`` : le refus d'un maximum (un résultat ``MAXIMUM_ATTEINT``, sa phrase dans le préfixe), suivi
    de la question en attente s'il y en a une ; une question d'ambiguïté née dans ce tour (``question.type`` ``ambiguite``). Critère sur la forme du retour,
    jamais sur les mots (D1)."""
    q = retour.get("question") if isinstance(retour.get("question"), dict) else None
    texte_q = sans_balisage(str((q or {}).get("texte") or "")) or None
    maximum = bool(prefixe) and any(isinstance(r, dict) and r.get("statut_du_module") == "MAXIMUM_ATTEINT" for r in retour.get("resultats") or [])
    ambiguite = q is not None and q.get("type") == "ambiguite" and texte_q is not None and question_nee_dans_ce_tour(p, tour)
    if maximum:
        return " ".join(x for x in (prefixe, texte_q if question_nee_dans_ce_tour(p, tour) else None) if x)
    if ambiguite:
        return " ".join(x for x in (prefixe, texte_q) if x)
    return None


def compose_une_formule(retour: dict) -> bool:
    """Le retour ajoute-t-il une ligne dont il porte la composition (``faits.composition`` d'un résultat ``ajouter``) ? Critère sur la forme du retour, jamais
    sur les mots (D1)."""
    return any(isinstance(r, dict) and r.get("operation") == "ajouter" and isinstance((r.get("faits") or {}).get("composition"), list)
               for r in retour.get("resultats") or [])


def _meme_phrase(a: str, b: str) -> bool:
    """La même phrase, aux espaces, à la casse et à la ponctuation de fin près (une égalité de texte, jamais une lecture du sens)."""
    def net(t: str) -> str:
        return " ".join(sans_balisage(str(t or "")).casefold().split()).rstrip(" .!?…")

    return bool(net(a)) and net(a) == net(b)


def avec_le_suffixe(texte: str, etat: EtatDuTour) -> str | None:
    """La phrase du modèle suivie du prix que le code dit après elle (D33) ; ``None`` sans prix en attente. Le prix n'est dit qu'une fois."""
    if not etat.suffixe:
        return None
    dit = " ".join(x for x in (sans_balisage(texte), etat.suffixe) if x)
    etat.suffixe = etat.suffixe_lu = None
    return dit


def phrase_libre_retenue(texte: str, etat: EtatDuTour, *, objet_en_cours: bool, question_en_attente: bool, paroles: list[str]) -> str | None:
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
    if (etat.apres_refus or etat.apres_formule) and etat.a_dire_jetee and _meme_phrase(texte, etat.a_dire_jetee):
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
