"""[.mark] Clôture de la Partie 1, lot B2 (audit du code M3, M4) : ce qui est dû à la personne, constaté à la sortie de TOUTE fiche, commande et
réservation (revue d'ingénierie, point 6 : même faute, même traitement).

Deux constats, posés dans le retour, lus par la parole (``actions_communes.parole``) :
* ``texte_a_dire`` : ce qui manque, quand aucune question n'attend, à la sortie d'une fiche refusée, rejouée ou exécutée (avant : seulement
  exécutée sans refus ; 42 cas rouges du test des combinaisons). Une seule place, une seule fonction par métier ;
* ``rien_change`` : la fiche n'a rien changé de ce que la personne vit ; elle vaut une phrase sans outil (règle 2 : trace 508, « C'est noté » sur
  cinq fiches vides de suite).
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable

from loguru import logger

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import consignes as C
from api.services.actions_communes import journal_du_dit as J


RIEN_CHANGE = "rien_change"
A_FAIRE_RIEN_CHANGE = "ta fiche n'a rien changé : ta phrase n'a pas été dite ; réponds à ce que la personne vient de dire"
# La tenue interne (registre des questions, mémoire des fiches, tour) : elle bouge sans que rien ne change pour la personne.
# G3 : deux objets, la commande et la conversation (``conversation.py``) : la conversation tout entière est mise de côté ; il reste les compteurs propres de la commande.
COMPTEURS_DE_LA_COMMANDE = ("version", "prochaine_ligne", "relecture")  # B4 : le compteur de version du panier bouge sur un changement sans effet (« mettez-en deux » quand il y en a deux)


CLE_DU = "du_de_la_fiche"  # ce que ``constater`` pose dans le retour, une seule clé ; jamais montré au modèle (``enveloppe_legere``)
RETRAIT_D_UNE_LIGNE = "ligne_retiree"  # un fait qui engage, posé par la porte du métier (``poser_*``) : une ligne entière vient d'être retirée ; le commun ne lit aucun nom de case
CLE_FAITS_A_DIRE = "faits_a_dire_apres_ta_phrase"  # la clé du retour (drapeau que le modèle lit) ; le MOTIF de la parole qui porte presque le même nom est ``parole.FAITS_A_DIRE``. Posé par le connecteur : des faits que le modèle doit dire (lot 20, conv4, D36)
BLOQUANTS = ("PARTIEL", "REJETEE", "INTROUVABLE", "A_PRECISER")


@dataclass(frozen=True)
class Du:
    """Lot 7a : ce qui est dû à la personne à la sortie d'une fiche, vu de deux façons : ``du_du_retour`` le lit sur la forme VIVANTE du retour (la table de la parole le RECALCULE à chaque décision, car des faits sont posés après
    le constat) ; ``constater`` en garde un exemplaire dans le retour (``CLE_DU``) dont seule ``boucle`` est relue. Chaque champ se lit sur la forme du retour, jamais sur des mots (D1).

    * ``faits_qui_engagent`` : ce que la fiche a fait et que la phrase écrite avant elle ne pouvait pas connaître (une ligne retirée, une formule ajoutée) ;
    * ``question`` : le type de la question née dans ce retour, ``None`` sans ; ``prix_apres`` : un prix que le code dit après la phrase du modèle ;
    * ``faits_au_modele`` : ce que le modèle doit dire (fait bloquant, faits à dire) ; ``manque`` : ce qui manque quand aucune question n'attend ;
    * ``rien_change`` : la fiche n'a rien changé ; ``boucle`` : la même chose redite sans issue (la sortie), calculée UNE fois par le constat de la sortie de fiche (``constater``) et relue
      telle quelle sur l'exemplaire rangé ; la table ne la lit pas ;
    * ``consignes`` : ce que le retour dit au modèle, chacune avec son rang (``consignes.py``) ; ``assembler`` les écrit toutes dans ``a_faire`` par ``une_consigne``.

    Les ``poser_*`` du métier rendent chacun UN élément de ``Du`` ; ``assembler`` les range dans le constat du retour (``CLE_DU``) et écrit les drapeaux que le modèle lit :
    aucun ``poser_*`` n'écrit plus ``prix_dit_par_le_code_apres_ta_phrase`` ni ``faits_a_dire_apres_ta_phrase``. Le code ne dit plus rien AVANT la phrase du modèle : un refus au chiffre ou au lieu
    (hors zone, minimum, règle d'une ligne ou d'un article) est un fait du retour (``CLES_DES_FAITS_DU_REFUS``), que le modèle dit."""

    faits_qui_engagent: tuple[str, ...] = ()
    question: str | None = None
    prix_apres: bool = False
    faits_au_modele: tuple[str, ...] = ()
    manque: str | None = None
    rien_change: bool = False
    boucle: bool = False
    consignes: tuple[tuple[int, str], ...] = ()

    def vers_json(self) -> dict[str, Any]:
        return asdict(self)


def _union(a: tuple, b: tuple) -> tuple:
    return tuple(dict.fromkeys((*a, *b)))


def fusionner(*elements: "Du | None") -> "Du":
    """Les éléments rendus par les ``poser_*`` (et le constat de la forme du retour) en un seul ``Du`` : les listes s'unissent, les drapeaux s'additionnent, le premier texte gagne."""
    sortie = Du()
    for e in elements:
        if e is None:
            continue
        sortie = Du(
            faits_qui_engagent=_union(sortie.faits_qui_engagent, e.faits_qui_engagent),
            question=sortie.question or e.question, prix_apres=sortie.prix_apres or e.prix_apres, faits_au_modele=_union(sortie.faits_au_modele, e.faits_au_modele),
            manque=sortie.manque or e.manque, rien_change=sortie.rien_change or e.rien_change, boucle=sortie.boucle or e.boucle,
            consignes=_union(sortie.consignes, e.consignes))
    return sortie


FAITS_A_DIRE_PAR_LE_MODELE = "faits_a_dire"  # un élément de ``faits_au_modele`` : des faits que le modèle doit dire (l'allergie)
DRAPEAUX_DU_RETOUR = (("prix_dit_par_le_code_apres_ta_phrase", lambda du: du.prix_apres), (CLE_FAITS_A_DIRE, lambda du: FAITS_A_DIRE_PAR_LE_MODELE in du.faits_au_modele))


def assembler(retour: dict[str, Any], *elements: "Du | None") -> None:
    """Range les éléments rendus par les ``poser_*`` dans le constat du retour, et écrit les drapeaux que le modèle lit (le seul endroit qui les écrit)."""
    du = fusionner(du_du_retour(retour), Du(boucle=boucle_rangee(retour)), *elements)
    retour[CLE_DU] = du.vers_json()
    for cle, vrai in DRAPEAUX_DU_RETOUR:
        if vrai(du):
            retour[cle] = True
    ecrire_la_consigne(retour, du)


def ecrire_la_consigne(retour: dict[str, Any], du: Du) -> None:
    """LE seul endroit qui écrit ``a_faire`` d'après les consignes du ``Du`` (lot 7b, ligne 28)."""
    consigne = C.une_consigne(du.consignes, du.boucle)
    if consigne:
        retour["a_faire"] = consigne


def boucle_rangee(retour: dict[str, Any]) -> bool:
    """La boucle que ``constater`` a posée sur l'exemplaire rangé du retour : la SEULE source de ``Du.boucle`` (la lecture vive du retour ne la porte pas)."""
    deja = retour.get(CLE_DU)
    return bool(deja.get("boucle")) if isinstance(deja, dict) else False


def du_du_retour(retour: dict[str, Any]) -> Du:
    """Le ``Du`` d'un retour de fiche, lu sur sa forme VIVANTE : des faits à dire (l'allergie) sont posés après le constat. La boucle (la sortie) n'en fait pas partie : seul
    ``constater`` la calcule, et seul l'exemplaire rangé (``boucle_rangee``) la porte."""
    deja = retour.get(CLE_DU)
    consignes = tuple((int(r), str(t)) for r, t in deja.get("consignes") or ()) if isinstance(deja, dict) else (((C.RESTE, str(retour["a_faire"])),) if retour.get("a_faire") else ())  # sans constat rangé : la consigne du retour est le reste
    faits = retour.get("faits") or {}
    resultats = [r for r in retour.get("resultats") or [] if isinstance(r, dict)]
    posees = tuple(deja.get("faits_qui_engagent") or ()) if isinstance(deja, dict) else ()  # ce que la porte du métier a posé (``poser_*``) dans le constat
    engagent = _union(posees, tuple(x for x in (
        "formule_ajoutee" if any(r.get("operation") == "ajouter" and isinstance((r.get("faits") or {}).get("composition"), list) for r in resultats) else None,
    ) if x))
    bloquant = retour.get("statut") in BLOQUANTS or any(faits.get(k) for k in CLES_DES_FAITS_DU_REFUS)  # un refus ou une règle que le modèle doit dire (hors zone, minimum, règle d'un article)
    q = retour.get("question") if isinstance(retour.get("question"), dict) else None
    return Du(
        faits_qui_engagent=engagent,
        question=str(q.get("type")) if q and q.get("type") else None, prix_apres=bool(retour.get("prix_dit_par_le_code_apres_ta_phrase")),
        faits_au_modele=tuple(x for x in ("fait_bloquant" if bloquant else None, FAITS_A_DIRE_PAR_LE_MODELE if retour.get(CLE_FAITS_A_DIRE) else None) if x),
        manque=str(retour.get("texte_a_dire") or "") or None, rien_change=bool(retour.get(RIEN_CHANGE)),
        consignes=consignes)


# Les faits que le retour donne au modèle pour dire un refus ou une règle avec ses chiffres et ses lieux (``enveloppe`` et les ``poser_*`` de la porte) : le refus du module, le minimum de la
# livraison, la règle d'une ligne limitée par un prix, les règles d'un article ajouté.
CLES_DES_FAITS_DU_REFUS = ("fait_bloquant", "refus_de_la_fiche", "minimum_de_la_commande", "regle_de_la_ligne", "regles_a_dire", "heure_a_dire", "horaires_libres")


def faits_du_refus(retour: Any) -> list[Any]:
    """Les faits que ce retour donne au modèle pour dire un refus : leurs valeurs (montants, heures, quantités) passent la barrière des chiffres (constat 0.1, lot 7b)."""
    faits = retour.get("faits") if isinstance(retour, dict) else None
    return [faits[k] for k in CLES_DES_FAITS_DU_REFUS if isinstance(faits, dict) and k in faits]


def ce_qui_se_voit(dossier: dict[str, Any]) -> Any:
    """L'état du dossier tel que la personne le vit (sans la tenue interne), et la question posée (numéro, texte) : deux valeurs égales avant et
    après une fiche = elle n'a rien changé."""
    q = CONV.question_de(dossier) or {}
    vue = {k: v for k, v in dossier.items() if k not in COMPTEURS_DE_LA_COMMANDE and k != CONV.CLE}
    vue[J.CLE] = (dossier.get(CONV.CLE) or {}).get(J.CLE) or {}  # ce qui est dit compte : une recherche vaine de plus est un effet, même rangé sous la conversation (R1)
    if isinstance(vue.get("lignes"), list):
        vue["lignes"] = [{k: v for k, v in l.items() if k != "n"} if isinstance(l, dict) else l for l in vue["lignes"]]  # le numéro d'une ligne est de la tenue : vider puis redire la même ne change rien
    return copy.deepcopy({**vue, "question": (q.get("id"), q.get("texte"))})


def _articles_par_ref(lignes: Any) -> dict[str, int]:
    """Les articles d'un dossier (référence → quantité totale), sans leurs précisions : de quoi dire si la commande a avancé (RC6)."""
    compte: dict[str, int] = {}
    for l in lignes or []:
        if isinstance(l, dict):
            compte[str(l.get("ref"))] = compte.get(str(l.get("ref")), 0) + int(l.get("quantite") or 0)
    return compte


def constater(retour: dict[str, Any], vu_avant: Any, dossier: dict[str, Any], texte_du_manque: Callable[[dict[str, Any]], str | None],
              seuil_de_sortie: int | None = None) -> dict[str, Any]:
    """Pose ce qui est dû dans le retour d'une fiche (``texte_a_dire``, ``rien_change``). ⛔ Ne lève jamais : dans le doute, le retour tel quel."""
    sortie, posees = False, []
    try:
        if CONV.question_de(dossier) is None and not retour.get("texte_a_dire"):
            phrase = texte_du_manque(dossier)
            if phrase:
                retour["texte_a_dire"] = phrase
        if not retour.get("refus") and retour.get("statut") != "REJETEE" and ce_qui_se_voit(dossier) == vu_avant:
            retour[RIEN_CHANGE] = True
            posees.append((C.RIEN_CHANGE, A_FAIRE_RIEN_CHANGE))
        q = CONV.question_de(dossier) or {}
        bloquant = (retour.get("faits") or {}).get("fait_bloquant")
        signature = [q.get("texte"), json.dumps(bloquant, sort_keys=True, default=str) if bloquant else None, retour.get("raison")]
        memes_lignes = _articles_par_ref((vu_avant or {}).get("lignes")) == _articles_par_ref(ce_qui_se_voit(dossier).get("lignes"))  # la commande n'avance pas : mêmes articles, mêmes quantités
        sortie = J.boucle(dossier, signature, memes_lignes, seuil_de_sortie)  # RC6 : la même chose trois fois sans issue : la sortie, dite par ``une_consigne`` d'après ``Du.boucle``
    except Exception:  # noqa: BLE001
        logger.exception("[.mark] du : la sortie d'une boucle n'a pas pu être lue")
    try:
        du = fusionner(replace(du_du_retour(retour), boucle=sortie), Du(consignes=tuple(posees)))
        retour[CLE_DU] = du.vers_json()  # lu par la parole, retiré de la copie du modèle
        ecrire_la_consigne(retour, du)
    except (AttributeError, KeyError, TypeError, ValueError):
        logger.exception("[.mark] du : le constat n'a pas pu être posé dans le retour")
    return retour
