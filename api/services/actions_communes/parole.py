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

from dataclasses import asdict, dataclass, field
from typing import Any

from api.services.actions_communes.barriere_des_chiffres import RAPPEL_DU_CHIFFRE, chiffre_dans_la_phrase, sans_balisage
from api.services.actions_communes.repli import RAPPEL_APRES_REFUS, refus_de_la_fiche, refuse

CLE_ETAT_DU_TOUR = "parole_du_tour"
CLE_DU_TOUR = "tour_de_la_personne"  # le tour de la personne, la même clé que la porte (cases_selon_l_etat.CLE_DU_TOUR)
PASSES_AU_PLUS = 5

A_DIRE_SEUL = "a_dire_seul"
SECOND_PASSAGE = "second_passage"

RAPPEL_SANS_OUTIL = "- Ta réponse précédente n'avait pas d'appel d'outil : elle n'a pas été dite, et rien n'est changé."
# Raisons de retenue d'une phrase libre (liste fermée, au glossaire)
SANS_OUTIL, APRES_REFUS, REPLI_A, CHIFFRE = "sans_outil", "rattrapage_apres_refus", "repli_a", "chiffre"
SUFFIXE = "suffixe_du_code"  # pas une retenue : la phrase dite, suivie du prix dit par le code
RAPPELS = {SANS_OUTIL: RAPPEL_SANS_OUTIL, APRES_REFUS: RAPPEL_APRES_REFUS, REPLI_A: RAPPEL_APRES_REFUS, CHIFFRE: RAPPEL_DU_CHIFFRE}
BLOQUANTS = ("PARTIEL", "REJETEE", "INTROUVABLE", "A_PRECISER")


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


def etat_du_tour(fiche_de_l_appel: Any) -> EtatDuTour:
    """L'état du tour en cours, remis à zéro quand la personne reparle. Sans fiche (un essai isolé) : un état jetable."""
    if not isinstance(fiche_de_l_appel, dict):
        return EtatDuTour()
    tour = fiche_de_l_appel.get(CLE_DU_TOUR)
    brut = fiche_de_l_appel.get(CLE_ETAT_DU_TOUR)
    if isinstance(brut, dict) and brut.get("tour") == tour:
        return EtatDuTour(**{k: v for k, v in brut.items() if k in EtatDuTour.__dataclass_fields__})
    return EtatDuTour(tour=tour)


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
    ``textes`` : ce que le code dit lui-même pour cette fiche (``porte.CLE_TEXTES_DU_CODE``)."""
    textes = textes if isinstance(textes, dict) else {}
    etat.fiches += 1
    etat.suffixe = None
    if isinstance(fiche, dict):
        etat.executees.append({k: v for k, v in fiche.items() if k == "code_de_remise"})
    etat.apres_refus = refuse(retour)
    etat.apres_refus_de_la_fiche = etat.apres_refus and refus_de_la_fiche(retour)
    etat.refus_de_la_fiche_dans_le_tour = etat.refus_de_la_fiche_dans_le_tour or etat.apres_refus_de_la_fiche
    phrase = sans_balisage(str(a_dire or ""))
    prefixe = sans_balisage(str(textes.get("prefixe") or "")) or None  # la règle chiffrée qui bloque : dite avant tout second passage
    avant = sans_balisage(str(textes.get("avant") or ""))
    if avant:
        # le récapitulatif, la confirmation : dits par le code, mot pour mot, même si une autre case est refusée (banc : ``recap_code``)
        return Decision(A_DIRE_SEUL, a_dire=avant, motif="texte_du_code")
    if etat.apres_refus:
        return Decision(SECOND_PASSAGE, motif="refus", prefixe=prefixe)
    if retour.get("statut") in BLOQUANTS or (retour.get("faits") or {}).get("fait_bloquant"):
        return Decision(SECOND_PASSAGE, motif="fait_bloquant", prefixe=prefixe)
    if question_nee_dans_ce_tour(p, etat.tour) or retour.get("prix_dit_par_le_code_apres_ta_phrase"):
        etat.suffixe = sans_balisage(str(textes.get("suffixe") or "")) or None
        return Decision(SECOND_PASSAGE, motif="question_nouvelle", prefixe=prefixe)
    if prefixe:
        return Decision(SECOND_PASSAGE, motif="fait_bloquant", prefixe=prefixe)
    if not phrase:
        return Decision(SECOND_PASSAGE, motif="sans_phrase")
    if chiffre_dans_la_phrase(phrase, etat.executees, paroles):
        return Decision(SECOND_PASSAGE, motif="chiffre")
    return Decision(A_DIRE_SEUL, a_dire=phrase, motif="fait")


def avec_le_suffixe(texte: str, etat: EtatDuTour) -> str | None:
    """La phrase du modèle suivie du prix que le code dit après elle (D33) ; ``None`` sans prix en attente. Le prix n'est dit qu'une fois."""
    if not etat.suffixe:
        return None
    dit = " ".join(x for x in (sans_balisage(texte), etat.suffixe) if x)
    etat.suffixe = None
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
    if chiffre_dans_la_phrase(texte, etat.executees, paroles):
        etat.retenues.append(CHIFFRE)
        return CHIFFRE
    return None
