"""[.mark] Clôture de la Partie 1, lot A4 : le moteur du test des combinaisons (audit du code § 4, audit des tests § 6), sans modèle, sur la vraie porte.

Un geste humain = une petite fonction qui lit l'état (question posée, lignes) et rend la fiche que le modèle aurait remplie, plus ce qu'elle doit
faire au panier (« chaque geste dit son effet ») ; une suite de gestes part d'un état atteint par une RECETTE de gestes sûrs (jamais écrit à la main
dans le panier). Après CHAQUE geste, les règles RC1 à RC15 (audit du code § 3) jugent l'observation : état d'avant, état d'après, retour de la porte,
textes que le code dit lui-même (copiés AVANT la décision de parole, qui les retire), décision de parole. Aucun résultat attendu écrit cas par cas :
ce sont les règles qui jugent, plus le panier attendu tenu par le test.

⛔ L'oracle ne tient que des règles simples et un panier attendu par geste d'article ; jamais une copie de la logique du moteur (revue d'ingénierie,
point 2). Le tirage est maison (``random.Random(graine)``, R5 : aucune dépendance neuve) ; une suite rouge est réduite à la plus courte qui reste rouge.
"""

from __future__ import annotations

from api.services.actions_communes.du import CLE_DU
from api.services.actions_communes import conversation as CONV

import copy
import itertools
import json
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_commande import commande_complete
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes import repli as R
from api.services.commande import contrat as CONTRAT
from api.services.commande import panier as P
from api.services.groupe import passations as PASSATIONS
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.porte_essai import Essai

GABARIT = Path(__file__).resolve().parents[3] / "services" / "gabarits" / "restauration" / "gabarit.json"

# Les articles de Casa Italia (carte de démo, ``banc_a/cartes/casa-italia.json``).
MARGHERITA, REGINA = "P-PIZZAS-TOMATE-MARGHE", "P-PIZZAS-TOMATE-REGINA"
DIT_DU_NUMERO = "zéro six douze trente-quatre cinquante-six soixante-dix-huit"
ANNONCE = "C'est noté."  # la phrase que le modèle écrit AVANT l'exécution (808 fiches sur 809 au jeu 3) : elle affirme


# --------------------------------------------------------------------------- l'observation d'un geste


@dataclass
class Observation:
    geste: str
    avant: dict[str, Any]
    apres: dict[str, Any]
    retour: dict[str, Any] | None
    textes: dict[str, str]
    decision: Any
    attendu: Counter | None
    fiche: dict[str, Any] | None
    duree_ms: float = 0.0
    consigne: str | None = None  # lot 7b-C5 : ce que le code donne au modèle muet après « pardon ? » (la consigne de relance, ses faits en JSON) ; sans elle, la phrase réglée « pas compris » (P3, reprise R1 de C6 : jamais le fait accompli) ; jamais une phrase composée
    base: dict[str, Any] | None = None  # la commande de ``resto_commande`` (et ses lignes) quand le panier en porte une enregistrée
    prise: dict[str, Any] | None = None  # ce que la prise (la caisse d'essai) a reçu pour ce numéro, la dernière fois ; pendant l'appel : rien (§ 17)
    finaliser_appels: int = 0  # combien de fois la fiche de ce geste a mené la commande à sa fin (invariant : jamais plus d'une)
    relance_du_fait: bool = False  # lot 7b-C5 : le modèle a déjà été relancé avec le fait dans ce tour (le plafond d'une relance par tour)
    identique: bool = False  # PE-1 : la fiche est celle du tour d'avant ; le juge attend le panier inchangé ET le refus qui fait demander « un de plus ou le même ? »

    @property
    def dit_par_le_code(self) -> str:
        # C6 n° 5 (décision d'Evan 25/11 9 h 30) : ce qui part à la voix par le code : ``avant`` et ``suffixe`` ; le reste des textes (valeurs exigées, fait gardé au journal) n'est pas dit
        return " ".join(str(v) for k, v in (self.textes or {}).items() if k in ("avant", "suffixe") and v)


def lignes_de(p: dict[str, Any]) -> Counter:
    c: Counter = Counter()
    for ligne in p.get("lignes") or []:
        c[ligne.get("ref")] += int(ligne.get("quantite") or 0)
    return c


def en_attente(p: dict[str, Any]) -> int:
    """Les articles dits avant le préalable (mode, adresse) : gardés de côté par le code (``dits_en_attente``), jamais perdus."""
    return sum(int(x.get("quantite") or 1) for x in p.get("dits_en_attente") or [] if isinstance(x, dict))


def question(p: dict[str, Any]) -> dict[str, Any]:
    q = CONV.question_de(p)
    return q if isinstance(q, dict) else {}


def finie(p: dict[str, Any]) -> bool:
    return bool(p.get("enregistree") or p.get("annulee"))


# --------------------------------------------------------------------------- les gestes (G1 à G36)


@dataclass(frozen=True)
class Geste:
    code: str
    nom: str
    dit: str | None  # ce que la personne dit ; None : la même fiche dans le même tour (G31)
    fiche: Callable[[dict[str, Any]], dict[str, Any] | None]  # None : pas de fiche (G35)
    effet: Callable[[Counter, dict[str, Any]], Counter | None]  # OBLIGATOIRE (Pierre 15) : le panier attendu ; ``None`` rendu = effet inconnu = le cas ÉCHOUE
    fusionnable: bool = True


def _ligne_1(p):
    lignes = p.get("lignes") or []
    return lignes[0] if lignes else None


def _n1(p):
    """Le numéro de la première ligne tel que le retour le montre au modèle (``n`` reste attaché à sa ligne : après un remplacement, la première ligne est la 2)."""
    l1 = _ligne_1(p)
    return int(l1["n"]) if l1 and l1.get("n") is not None else 1


def _plus(ref: str, n: int = 1):
    def effet(avant: Counter, p) -> Counter | None:
        if p.get("annulee"):
            return Counter(avant)  # DC5 : rien n'entre dans une commande annulée
        c = Counter(avant)
        c[ref] += n
        return c

    return effet


def _inchange(avant: Counter, p) -> Counter:
    return Counter(avant)


def _sans_ligne_1(avant: Counter, p) -> Counter | None:
    l1 = _ligne_1(p)
    if l1 is None or p.get("annulee"):
        return Counter(avant)
    c = Counter(avant)
    c[l1["ref"]] -= int(l1.get("quantite") or 0)
    if p.get("enregistree") and not +c:
        return Counter(avant)  # DC4 + M2 : tout retirer d'une commande enregistrée, c'est l'annuler (la confirmation d'abord) : rien ne change
    return +c


def _ligne_1_a(q: int):
    def effet(avant: Counter, p) -> Counter | None:
        l1 = _ligne_1(p)
        if l1 is None or p.get("annulee"):
            return Counter(avant)
        c = Counter(avant)
        c[l1["ref"]] += q - int(l1.get("quantite") or 0)
        return +c

    return effet


def _vide(avant: Counter, p) -> Counter:
    return Counter(avant) if p.get("annulee") or p.get("enregistree") else Counter()  # DC5 ; DC4 + M2 (enregistrée : la confirmation d'abord)  # DC5 : rien ne change dans une commande annulée


REFS_DE_LA_CARTE: dict[str, str] = {}  # nom (sans casse) -> ref, pour les articles que le CODE ajoute (une proposition acceptée) ; posé par ``Partie``


def _ref_du_nom(nom: Any) -> str | None:
    return REFS_DE_LA_CARTE.get(str(nom or "").casefold()) or None


# Les questions dont « oui » ne touche pas au panier ; « oui » à une proposition ajoute l'article proposé, à « une nouvelle commande ? » ouvre une commande neuve (DC5).
OUI_SANS_EFFET = {"relecture", "numero_affiche", "numero_dicte", "variante", "ambiguite", "etape", "heure_proposee", "annulation_enregistree"}


def _oui(avant: Counter, p) -> Counter | None:
    """« oui » : ce qu'il fait au panier dépend de la question posée. Un type de question qui n'est pas dans la table = effet inconnu = le cas échoue."""
    q = question(p)
    t = q.get("type")
    if p.get("annulee") and t != "nouvelle_commande":
        return Counter(avant)
    if t == "proposition":
        ref = _ref_du_nom(q.get("article_propose"))
        return _plus(ref)(avant, p) if ref else None
    if t == "nouvelle_commande":
        return Counter()  # DC5 : une commande neuve, l'ancienne n'y est plus
    if t in OUI_SANS_EFFET:
        return Counter(avant)
    return None


ARTICLES_DITS = {"margherita": MARGHERITA, "regina": REGINA}
ARTICLES_SANS_EFFET = {"bubble tea", "salmone"}  # 7c : les articles de G3 (inconnu) et G4 (ambigu, la question d'abord) : rejoués, ils ne changent pas le panier (leur effet, ``_inchange``)
QUESTIONS_SUR_UN_ARTICLE = ("variante", "ambiguite", "etape")


def _ajouts_deja_repondus(fiche: dict[str, Any], p: dict[str, Any]) -> Counter:
    """D01 et B4 (M6, appel 530), écrites : une fiche qui RÉPOND à une question sur un article (par un « oui » ou des mots) ET remet dans ``ajouter`` l'article de la ligne qui
    attend sa taille : la réponse le complète déjà, la case ``ajouter`` est refusée pour cet article (« un second exemplaire se dit après, avec sa quantité »)."""
    reponse = fiche.get("reponse")
    if not isinstance(reponse, dict) or question(p).get("type") not in QUESTIONS_SUR_UN_ARTICLE or not (reponse.get("valeurs") or reponse.get("sens") == "accepte"):
        return Counter()
    if reponse.get("question_id") != question(p).get("id"):
        return Counter()  # B1 : une réponse au mauvais numéro est écartée seule : ce n'est pas une réponse, l'article remis n'est pas refusé
    en_attente = {l.get("ref") for l in P.a_completer(p)}
    refuses: Counter = Counter()
    for a in fiche.get("ajouter") or []:
        ref = ARTICLES_DITS.get(str(a.get("article")).casefold())
        if ref in en_attente:
            refuses[ref] += int(a.get("quantite") or 1)
    return refuses


def _effet_par_numero(fiche: dict[str, Any], avant: Counter, p: dict[str, Any]) -> Counter | None:
    """Une fiche rejouée au tour suivant : retirer et changer visent des lignes PAR LEUR NUMÉRO ; un numéro qui n'existe plus n'est rien (refusé, le reste passe) ; ajouter ajoute."""
    if p.get("annulee"):
        return Counter(avant)
    lignes = {l.get("n"): l for l in p.get("lignes") or []}
    visees = [n for n in fiche.get("retirer_article") or [] if isinstance(n, int)] + [c.get("ligne") for c in fiche.get("changer_quantite") or [] if isinstance(c, dict)]
    conflit = len(visees) != len(set(visees))  # B4 (M6, RC5) : deux cases sur la même ligne sont refusées toutes les deux ; le reste de la fiche passe (7c : l'ajout aussi, comme ``fusion``)
    c = Counter(avant)
    for n in [] if conflit else fiche.get("retirer_article") or []:
        if n in lignes:
            c[lignes[n]["ref"]] -= int(lignes[n].get("quantite") or 0)
    for ch in [] if conflit else fiche.get("changer_quantite") or []:
        l = lignes.get(ch.get("ligne"))
        if l and ch.get("quantite"):
            c[l["ref"]] += int(ch["quantite"]) - int(l.get("quantite") or 0)
    for a in fiche.get("ajouter") or []:
        if str(a.get("article")).casefold() in ARTICLES_SANS_EFFET:
            continue
        ref = ARTICLES_DITS.get(str(a.get("article")).casefold())
        if ref is None:
            return None
        c[ref] += int(a.get("quantite") or 1)
    if p.get("enregistree") and not +c:
        return Counter(avant)
    return +c


def _rep(p, sens: str, **plus) -> dict | None:
    q = question(p)
    return {"reponse": {"question_id": q["id"], "sens": sens, **plus}} if q.get("id") else None


def _reponse_vivante(fiche: dict[str, Any], avant: dict[str, Any]) -> bool:
    """La réponse de la fiche vise la question posée dans cet état (sinon le code l'écarte seule, B1)."""
    reponse, q = fiche.get("reponse"), question(avant)
    return isinstance(reponse, dict) and bool(q.get("id")) and reponse.get("question_id") == q.get("id")


def _avec_ligne(f):
    return lambda p: f(p) if _ligne_1(p) else None


GESTES: dict[str, Geste] = {g.code: g for g in (
    Geste("G1", "un article complet", "une regina normale", lambda p: {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}, _plus(REGINA)),
    Geste("G2", "un article sans sa taille", "une regina", lambda p: {"ajouter": [{"article": "regina", "quantite": 1}]}, _plus(REGINA)),
    Geste("G3", "un article inconnu", "un bubble tea", lambda p: {"ajouter": [{"article": "bubble tea", "quantite": 1}]}, _inchange),
    Geste("G4", "un article ambigu", "une salmone", lambda p: {"ajouter": [{"article": "salmone", "quantite": 1}]}, _inchange),  # deux « Salmone » sur la carte de Casa : la question d'abord
    Geste("G5", "deux articles d'un coup", "une margherita normale et une regina normale",
          lambda p: {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}, {"article": "regina", "quantite": 1, "variante": "Normale"}]},
          lambda a, p: _plus(REGINA)(_plus(MARGHERITA)(a, p), p)),
    Geste("G6", "le même article redit", "encore une margherita normale",
          lambda p: {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}, _plus(MARGHERITA)),
    Geste("G7", "retirer une ligne", "enlevez la première", _avec_ligne(lambda p: {"retirer_article": [_n1(p)]}), _sans_ligne_1),
    Geste("G8", "changer une quantité", "en fait mettez-en deux", _avec_ligne(lambda p: {"changer_quantite": [{"ligne": _n1(p), "quantite": 2}]}), _ligne_1_a(2)),
    Geste("G9", "changer une taille", "en fait la mega", _avec_ligne(lambda p: {"changer_quantite": [{"ligne": _n1(p), "variante": "Mega"}]}), _inchange),
    Geste("G10", "retirer et changer la même ligne", "enlevez-la, non mettez-en deux",
          _avec_ligne(lambda p: {"retirer_article": [_n1(p)], "changer_quantite": [{"ligne": _n1(p), "quantite": 2}]}), _inchange, fusionnable=False),  # B4 : les deux cases refusées
    Geste("G11", "remplacer", "remplacez-la par une regina normale",
          _avec_ligne(lambda p: {"retirer_article": [_n1(p)], "ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}),
          lambda a, p: _plus(REGINA)(_sans_ligne_1(a, {**p, "enregistree": None}), p)),  # remplacer n'est jamais tout retirer
    Geste("G12", "vider", "on recommence tout", lambda p: {"vider_le_panier": True}, _vide),
    Geste("G13", "annuler", "annulez tout", lambda p: None if finie(p) else {"annuler_la_commande": True}, _vide),
    Geste("G14", "vider et annuler ensemble", "on vide et on annule", lambda p: None if finie(p) else {"vider_le_panier": True, "annuler_la_commande": True}, _vide),
    Geste("G15", "changer de mode", "finalement en livraison", lambda p: {"mode_de_retrait": "emporter" if p.get("mode") == "livraison" else "livraison"}, _inchange),
    Geste("G16", "adresse dans la zone", "au 12 rue de la République à Senlis", lambda p: {"adresse": "12 rue de la République", "commune": "Senlis"}, _inchange),
    Geste("G17", "adresse hors zone", "au 8 rue Solférino à Compiègne", lambda p: {"adresse": "8 rue Solférino", "commune": "Compiègne"}, _inchange),
    Geste("G18", "heure", "pour dix-neuf heures", lambda p: {"heure": "dix-neuf heures"}, _inchange),
    Geste("G19", "règlement, numéro, prénom ensemble", f"par carte, {DIT_DU_NUMERO}, c'est Léa",
          lambda p: {"moyen_de_paiement": "carte_bancaire", "telephone": "0612345678", "prenom": "Léa"}, _inchange),
    Geste("G20", "c'est tout", "c'est tout", lambda p: {"c_est_tout": True}, _inchange),
    Geste("G21", "c'est tout redit", "c'est tout je vous dis", lambda p: {"c_est_tout": True}, _inchange),
    Geste("G22", "annuler la commande enregistrée", "annulez ma commande", lambda p: {"annuler_une_commande_enregistree": True} if p.get("enregistree") else None, _inchange),  # DC4 : premier temps, la question
    Geste("G23", "oui", "oui", lambda p: _rep(p, "accepte"), _oui),
    Geste("G24", "non", "non", lambda p: _rep(p, "refuse"), _inchange),
    Geste("G25", "autre sans rien", "euh", lambda p: _rep(p, "autre"), _inchange),
    Geste("G26", "autre avec des mots", "la grande", lambda p: _rep(p, "autre", valeurs=["la grande"]), _inchange),
    Geste("G27", "réponse au mauvais numéro", "oui", lambda p: {"reponse": {"question_id": "Q-99", "sens": "accepte"}} if question(p) else None, _inchange),
    Geste("G28", "réponse sans question", "oui", lambda p: None if question(p) else {"reponse": {"question_id": "Q-1", "sens": "accepte"}}, _inchange),
    Geste("G29", "un changement seul pendant une question", "en fait mettez-en deux",
          lambda p: {"changer_quantite": [{"ligne": _n1(p), "quantite": 2}]} if question(p) and _ligne_1(p) else None, _ligne_1_a(2)),
    Geste("G30", "fiche vide", "d'accord", lambda p: {}, _inchange, fusionnable=False),
    Geste("G31", "la même fiche rejouée dans le tour", None, lambda p: "rejouer", _inchange, fusionnable=False),
    Geste("G32", "la même fiche au tour suivant", "je répète", lambda p: "rejouer", _inchange, fusionnable=False),  # l'effet du rejeu est calculé par ``Partie`` (celui du geste rejoué)
    Geste("G33", "fiche corrigée après un refus partiel", None, lambda p: "corriger", _inchange, fusionnable=False),
    Geste("G34", "fiche mal formée", "non", lambda p: {"reponse": {"question_id": question(p).get("id", "Q-1"), "sens": "refuse}"}}, _inchange, fusionnable=False),
    Geste("G35", "phrase sans outil (pas compris)", "pardon ?", lambda p: None, _inchange, fusionnable=False),
    Geste("G36", "détour (rendre la main, retour)", "et pour réserver ?", lambda p: None, _inchange, fusionnable=False),
)}

# Les gestes qui écrivent une fiche de ce qu'a dit la personne (ceux qui se fusionnent : « oui » + article, changement + « c'est tout »…)
FUSIONNABLES = [g for g in GESTES.values() if g.fusionnable]


# --------------------------------------------------------------------------- les états (E0 à E18), atteints par recette

RECETTES: dict[str, list[str]] = {
    "E0": [],
    "E1": ["mode:emporter"],
    "E2": ["mode:livraison"],
    "E3": ["mode:livraison", "G17"],
    "E4": ["mode:emporter", "margherita", "G24"],
    "E5": ["mode:emporter", "margherita_sans_taille"],
    "E6": ["mode:emporter", "G4"],
    "E7": ["mode:emporter", "margherita"],
    "E8": ["mode:emporter", "formule"],  # « un menu entreprise » : Casa Italia a la formule à étapes « Menu Entreprise » (pizza, boisson), servie de 11 h à 14 h
    "E9": ["mode:emporter"],  # le même geste que E1, mais l'horloge est celle d'un jeudi à 15 h (``FERMETURE``) : Casa est fermé de 14 h à 18 h, la commande est planifiable
    "E10": ["mode:livraison", "adresse:Chantilly", "margherita"],
    "E11": ["mode:emporter", "margherita", "G24", "G20"],
    "E12": ["mode:emporter", "margherita", "G24", "G20", "G25"],
    "E13": ["mode:emporter", "margherita", "G24", "G20", "G23"],
    "E14": ["mode:emporter", "margherita", "G24", "G20", "relu_par_carte"],
    "E15": ["mode:emporter", "margherita", "G24", "G20", "relu_par_carte", "G23"],
    "E16": ["mode:emporter", "margherita", "G24", "G20", "relu_par_carte", "G23", "prenom"],
    "E17": ["mode:emporter", "margherita", "G24", "G20", "relu_par_carte", "G23", "prenom", "G22", "G23"],  # DC4 : « annulez », puis « oui »
    "E18": ["mode:emporter", "margherita", "G24", "G20", "relu_par_carte", "G23", "prenom", "G8"],
}
ETATS = tuple(RECETTES)
FERMETURE = datetime(2026, 11, 12, 15, 0, tzinfo=ZoneInfo("Europe/Paris"))  # jeudi 15 h : Casa Italia est fermé (11 h à 14 h, 18 h à 22 h 30) ; E9 se joue sous cette horloge
# Ce que l'état doit montrer une fois la recette jouée ; sinon l'état n'est PAS atteint (dit au rapport, jamais compté comme vert).
ATTEINT: dict[str, Callable[[dict], bool]] = {
    "E0": lambda p: not p.get("mode") and not p.get("lignes"),
    "E1": lambda p: p.get("mode") == "emporter" and not p.get("lignes"),
    "E2": lambda p: p.get("mode") == "livraison" and not p.get("lignes"),
    "E3": lambda p: p.get("mode") == "livraison",
    "E4": lambda p: bool(p.get("lignes")) and not question(p) and not P.a_completer(p),
    "E5": lambda p: question(p).get("type") == "variante",
    "E6": lambda p: question(p).get("type") == "ambiguite",
    "E7": lambda p: question(p).get("type") == "proposition",
    "E8": lambda p: question(p).get("type") == "etape" and any(l.get("formule_id") for l in p.get("lignes") or []),  # une formule dont une étape attend son choix
    "E9": lambda p: question(p).get("type") == "heure_proposee" and not p.get("lignes"),  # fermé, planifiable : l'heure de la réouverture est proposée
    "E10": lambda p: p.get("mode") == "livraison" and bool(p.get("lignes")),
    "E11": lambda p: question(p).get("type") == "relecture",
    "E12": lambda p: bool(p.get("lignes")) and p.get("etape") != "accordee",
    "E13": lambda p: p.get("etape") == "accordee" and not P.moyen_du_paiement(p),
    "E14": lambda p: question(p).get("type") == "numero_affiche",
    "E15": lambda p: not p.get("enregistree") and p.get("etape") == "accordee",
    "E16": lambda p: bool(p.get("enregistree")) and not p.get("annulee"),
    "E17": lambda p: bool(p.get("annulee")) or (p.get("enregistree") or {}).get("annulee") is True,
    "E18": lambda p: bool(p.get("enregistree")) and lignes_de(p).get(MARGHERITA) == 2,
}


class Partie:
    """Une partie : un Essai neuf (un appelant neuf, la règle E30 d'une commande active par appel), sa recette, puis les gestes, chacun observé."""

    compteur = itertools.count(1)

    def __init__(self, monde, monkeypatch):
        self.e = Essai(monde, monkeypatch, appelant=f"+3361{next(Partie.compteur):07d}")
        self.monkeypatch = monkeypatch
        self.observations: list[Observation] = []
        self.journal: list[str] = []  # ce que le code a dit, tour après tour (RC3)
        self.derniere_fiche: dict[str, Any] | None = None
        self.dernier_effet: Callable | None = None  # l'effet de la dernière fiche jouée (G32 la rejoue au tour suivant : même effet)
        # (tour, fiche, sa réponse visait la question posée) de la dernière fiche qui ajoute et que le juge a attendue APPLIQUÉE (PE-1), et des fiches refaites dans ce même tour avec la
        # même case ``ajouter`` (R2 : la case déjà faite n'est pas rejouée, la fiche refaite compte aussi pour « la même au tour d'après »)
        self.ajoutees: list[tuple[int, dict[str, Any], bool]] = []
        self.fiche_du_tour: dict[str, Any] | None = None  # la fiche déjà jouée dans le tour en cours (G31 la rejoue dans CE tour ; un nouveau tour la rend au suivant, G32)
        self.attendu: Counter | None = Counter()
        for x in [*monde.carte.get("produits", []), *(monde.carte.get("formules") or [])]:
            cle = str(x["nom"]).casefold()
            REFS_DE_LA_CARTE[cle] = x["id"] if REFS_DE_LA_CARTE.get(cle, x["id"]) == x["id"] else ""  # deux articles du même nom : pas de ref sûre

    @property
    def p(self) -> dict[str, Any]:
        return self.e.p

    def fiche_de_l_appel_tour(self) -> int:
        return int(self.e.fiche_de_l_appel.get(CONTRAT.CLE_DU_TOUR) or 0)

    def _identique_au_tour_d_avant(self, fiche: dict[str, Any] | None, avant: dict[str, Any]) -> bool:
        """PE-1 (Q1/Q2 c, Pierre 26/11 ; ``bilan-point-d-etape-7b-c.md:274``) : la fiche qui ajoute, mot pour mot celle que le juge a attendue appliquée au tour d'avant (tour d'avant exactement), ou la fiche refaite dans ce tour-là (R2),
        n'est pas appliquée : le modèle demande « un de plus ou le même ? » (rien ne change, ni l'ajout ni les retraits de la même fiche). Un refus jugé n'est jamais « appliquée » : à la fiche
        suivante la même s'applique (« un autre »), le juge ne regarde que ce qu'il a lui-même attendu. « Mot pour mot » compte la réponse : une réponse qui visait la question posée au tour
        d'avant et ne vise plus rien au rejeu est écartée SEULE (B1), la fiche qui reste n'est plus celle d'avant : elle s'applique."""
        if not fiche or not fiche.get("ajouter"):
            return False
        precedent = self.fiche_de_l_appel_tour() - 1
        return any(tour == precedent and dite == fiche and vivante == _reponse_vivante(fiche, avant) for tour, dite, vivante in self.ajoutees)

    def _ranger_la_fiche_ajoutee(self, fiche: dict[str, Any] | None, avant: dict[str, Any], appliquee: bool) -> None:
        """La fiche qui ajoute et que le juge attend appliquée devient « celle du tour d'avant » pour le tour suivant ; la fiche refaite dans le même tour avec la même case ``ajouter``
        (G33, reprise R2 de l'audit PE-1) s'y ajoute : redite au tour d'après, elle n'est pas appliquée non plus."""
        if not fiche or not fiche.get("ajouter"):
            return
        tour, entree = self.fiche_de_l_appel_tour(), (self.fiche_de_l_appel_tour(), copy.deepcopy(fiche), _reponse_vivante(fiche, avant))
        if appliquee:
            self.ajoutees = [entree]
        elif any(t == tour and dite.get("ajouter") == fiche["ajouter"] for t, dite, _ in self.ajoutees):
            self.ajoutees.append(entree)

    def _compter_la_fin(self) -> list[int]:
        """L'espion de l'invariant « un seul finaliser par fiche » : chaque passage de la commande à sa fin, dans la fiche jouée, y est compté."""
        from api.services.commande import moteur

        appels: list[int] = []
        original = getattr(moteur.finaliser, "__wrapped_original__", moteur.finaliser)

        async def espion(*a, **k):
            appels.append(1)
            return await original(*a, **k)

        espion.__wrapped_original__ = original  # type: ignore[attr-defined]
        self.monkeypatch.setattr(moteur, "finaliser", espion)
        return appels

    async def _executer(self, nom: str, dit: str | None, fiche: dict[str, Any] | None, effet, rejeu: bool = False) -> Observation:
        e = self.e
        avant = copy.deepcopy(self.p)
        if dit is not None:
            e.dit(dit)
            self.fiche_du_tour = None
        retour, textes, decision, consigne, duree, nombre_de_fins = None, {}, None, None, 0.0, 0
        identique = self._identique_au_tour_d_avant(fiche, avant)
        effet_juge = _inchange if identique else effet
        attendu = effet_juge(lignes_de(avant), avant) if effet_juge is not None else None
        # « appliquée » : le juge attend qu'un article ENTRE (le code ne range que la fiche dont un article a été pris ; un retrait seul, avec un article inconnu, n'en fait pas une)
        self._ranger_la_fiche_ajoutee(fiche, avant, attendu is not None and bool(+(attendu - lignes_de(avant))))
        if fiche is not None:
            arguments = {"a_dire": ANNONCE, **fiche}
            debut = time.perf_counter()
            appels_de_la_fin = self._compter_la_fin()
            retour = await e.fiche(**fiche) if fiche else await e.fiche()
            nombre_de_fins = len(appels_de_la_fin)
            duree = (time.perf_counter() - debut) * 1000
            textes = dict(e.fiche_de_l_appel.get(PAROLE.CLE_TEXTES_DU_CODE) or {})
            decision = PF.decider_apres_la_fiche(e.fiche_de_l_appel, retour, arguments)
            self.derniere_fiche = self.fiche_du_tour = dict(fiche)
            if not rejeu and dit is not None:
                self.dernier_effet = effet  # G31 (dans le même tour) ne change pas ce que « je répète » rejouerait
        else:
            consigne = R.consigne_de_relance(self.p, e.fiche_de_l_appel, PAROLE.etat_du_tour(e.fiche_de_l_appel))
        base, prise = await self._lire_la_base()
        o = Observation(nom, avant, copy.deepcopy(self.p), retour, textes, decision, attendu, fiche, duree, consigne, base, prise, nombre_de_fins if fiche is not None else 0,
                        relance_du_fait=PAROLE.etat_du_tour(e.fiche_de_l_appel).relance_du_fait, identique=identique)
        self.observations.append(o)
        # C6 n° 5 (décision d'Evan 25/11 9 h 30) : un fait accompli neuf est dit par le modèle, suivi de la question M108 du code ; ce que la personne entend de neuf est ce fait (gardé au journal)
        fait = (o.textes or {}).get("fait_accompli")  # B9 : les faits du fait accompli (plus une phrase) ; deux fois les mêmes faits = redit
        self.journal.append(" ".join(x for x in ((json.dumps(fait, sort_keys=True, ensure_ascii=False) if fait else None), o.dit_par_le_code) if x))
        return o

    async def _lire_la_base(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Ce que ``resto_commande`` (et ses lignes) et la prise ont de la commande du panier : la vérité en base, jamais le seul panier en mémoire (Pierre 15)."""
        numero = (self.p.get("enregistree") or {}).get("numero")
        if not numero:
            return None, None
        e = self.e
        base = await commande_complete(e.monde.c, e.monde.a, numero)
        recues = [c for c in getattr(e.source.prise, "recues", []) if str(c.get("numero")) == str(numero)]
        return base, (copy.deepcopy(recues[-1]) if recues else None)

    async def finir_l_appel(self) -> list[Faute]:
        """§ 17 : la fin de l'appel jouée par le vrai crochet des modules (``Essai.finir_l_appel``), puis jugée (``rc_base_fin``)."""
        await self.e.finir_l_appel()
        return await self.juger_la_fin()

    async def juger_la_fin(self) -> list[Faute]:
        numero = (self.p.get("enregistree") or {}).get("numero")
        base = await commande_complete(self.e.monde.c, self.e.monde.a, numero) if numero else None
        lignes = await self.e.monde.c.fetch("SELECT numero::text AS numero, statut FROM mark.resto_commande WHERE appel_id = $1", str(self.e.ctx.run_id))
        return rc_base_fin(self.p, base, list(getattr(self.e.source.prise, "recues", [])), [(r["numero"], r["statut"]) for r in lignes])

    def _effet_du_rejeu(self):
        """G32 : « je répète » rejoue la fiche d'avant au tour suivant : l'effet est celui de ce geste. 7c : une réponse au numéro d'une question qui n'est plus posée est écartée SEULE
        (B1 : le reste de la fiche passe, ses articles entrent) ; une réponse qui vise maintenant la proposition posée est un « oui » à elle (``_oui`` : l'article proposé entre)."""
        fiche = self.derniere_fiche or {}
        reponse = fiche.get("reponse")
        q = question(self.p)
        vivante = _reponse_vivante(fiche, self.p)
        if isinstance(reponse, dict) and not vivante:
            return (lambda avant, p: _effet_par_numero(fiche, avant, p)) if fiche.get("retirer_article") or fiche.get("changer_quantite") or fiche.get("ajouter") else _inchange
        if vivante and reponse.get("sens") == "accepte" and q.get("type") == "proposition":
            return lambda avant, p: (lambda c: None if c is None else _oui(c, p))(_effet_par_numero(fiche, avant, p))
        if fiche.get("retirer_article") or fiche.get("changer_quantite"):
            # Les numéros de ligne restent attachés à LEUR ligne : rejoués, ils visent la ligne d'avant, qui n'existe plus si elle a été retirée ou remplacée
            return lambda avant, p: _effet_par_numero(fiche, avant, p)
        return self.dernier_effet

    async def geste(self, code: str) -> Observation | None:
        """Joue un geste ; None : sans objet dans cet état (rien n'est joué)."""
        g = GESTES[code]
        f = g.fiche(self.p)
        if f == "rejouer":
            deja = self.fiche_du_tour if g.dit is None else self.derniere_fiche
            if deja is None:
                return None
            return await self._executer(g.code, g.dit, dict(deja), _inchange if g.dit is None else self._effet_du_rejeu(), rejeu=True)
        if f == "corriger":
            # Une fiche refusée en partie (un téléphone que la personne n'a pas dit), puis la même, corrigée : l'article n'entre qu'une fois.
            await self._executer("G33a", "une regina normale", {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}], "telephone": "0699999999"},
                                 _plus(REGINA))
            return await self._executer("G33", None, {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}, _inchange)
        if f is None and code not in ("G35", "G36"):
            return None
        if code == "G36":
            self._verifier_le_detour()  # G36 : le détour est routé par le code, pas par le modèle (lot 5, R4)
        return await self._executer(g.code, g.dit, f, g.effet)

    def _verifier_le_detour(self) -> None:
        """G36 (lot 5, R4) : « et pour réserver ? » pendant une commande. L'accueil passe la main à la réservation (permis), la réservation rend la main (``rendre_la_main``) : le code
        ramène l'appel à l'agent qui TIENT la commande ouverte (``porteur_de_l_action_ouverte``), sinon à l'accueil ; et l'accueil a le droit de repasser par la commande. Le panier ne bouge pas."""
        accueil, commande, reservation = 299, 300, 301
        fiche = self.e.fiche_de_l_appel
        en_cours = bool((self.p.get("lignes") or self.p.get("mode")) and not self.p.get("enregistree") and not self.p.get("annulee"))
        PASSATIONS.noter_le_porteur(fiche, "commande", commande)  # l'agent de la commande a écrit la fiche
        for de, vers, raison in ((accueil, commande, "passer_a_l_agent_commande"), (commande, accueil, "retour"), (accueil, reservation, "passer_a_l_agent_reservation")):
            assert PASSATIONS.refus_de_passation(fiche, {}, de=de, vers=vers, raison=raison) is None, f"G36 : la passation {de} vers {vers} est refusée"
            PASSATIONS.tracer_passation(fiche, de=de, vers=vers, raison=raison, refusee=False, issue="completed")
        porteur = PASSATIONS.porteur_de_l_action_ouverte(fiche, sauf=reservation)  # la réservation rend la main : à qui le code ramène-t-il l'appel ?
        assert porteur == (commande if en_cours else None), f"G36 : l'appel doit revenir à l'agent de la commande ouverte ({en_cours}), le code a dit {porteur}"
        if en_cours:
            assert PASSATIONS.refus_de_passation(fiche, {}, de=accueil, vers=commande, raison="passer_a_l_agent_commande") is None, "G36 : repasser par la commande est permis"

    async def fusion(self, codes: tuple[str, ...]) -> Observation | None:
        """Plusieurs choses dites à la fois : les fiches de 2 ou 3 gestes réunies dans UNE fiche (là où sont nés C2, C3, C8, C9 et l'appel 450)."""
        fiche: dict[str, Any] = {}
        dits, effets = [], []
        for code in codes:
            g = GESTES[code]
            f = g.fiche(self.p)
            if not isinstance(f, dict) or not f:
                return None
            for cle, valeur in f.items():
                if cle in fiche and isinstance(valeur, list):
                    fiche[cle] = fiche[cle] + valeur
                elif cle in fiche:
                    return None  # deux valeurs pour la même case : pas une fusion, un conflit (G10 le joue)
                else:
                    fiche[cle] = valeur
            dits.append(g.dit or "")
            effets.append(g.effet)

        visees = [n for n in fiche.get("retirer_article") or [] if isinstance(n, int)] + [c.get("ligne") for c in fiche.get("changer_quantite") or [] if isinstance(c, dict)]
        conflit = len(visees) != len(set(visees))  # B4 (M6, RC5) : deux cases sur la même ligne sont refusées toutes les deux ; le reste de la fiche passe
        sans_conflit = {"G7": _inchange, "G8": _inchange, "G9": _inchange, "G29": _inchange, "G11": lambda a, p: _plus(REGINA)(a, p)}

        def effet(avant: Counter, p) -> Counter | None:
            # L'ordre du CODE (``porte.ORDRE_DES_CASES``, jamais celui de la personne) : vider et annuler d'abord, puis le reste. Annulée dans la fiche, la
            # commande n'existe plus et rien n'y entre (DC5, RC8) ; vidée, la suite se pose sur un panier vide (les lignes dites ne sont plus là).
            if p.get("annulee") and "G23" in codes and question(p).get("type") == "nouvelle_commande":
                # DC5 (Evan, 22/11) : « oui » à « voulez-vous en passer une nouvelle ? » ouvre une commande NEUVE (``registre.repartir``) : ce que la même fiche dit y entre,
                # le panier d'avant n'y est plus (l'attente du test disait « rien n'entre dans une commande annulée », vrai sans ce « oui »)
                c, vu = Counter(), {**p, "lignes": [], "annulee": False}
                for code, ef in zip(codes, effets):
                    if code != "G23":
                        c = ef(c, vu)
                        if c is None:
                            return None
                return c
            if p.get("annulee"):
                return Counter(avant)  # DC5 : rien ne change dans une commande déjà annulée
            if "G23" in codes and question(p).get("type") == "annulation_enregistree":
                # DC4 + DC5 (Evan, 22/11) : le « oui » de cette fiche confirme l'annulation de la commande enregistrée, et l'ordre du code (``ORDRE_DES_CASES`` : la réponse avant les ajouts)
                # l'annule avant tout ajout : l'ajout de la même fiche est refusé (« commande_annulee »). L'ancienne attente le posait sur une commande encore vivante.
                return Counter(avant)
            if isinstance(fiche.get("reponse"), dict) and "sens" in fiche["reponse"] and question(p).get("type") == "etape":
                return Counter(avant)  # B4 (M9) : à une étape de formule la réponse se dit dans ``valeurs`` ; ``reponse.sens`` n'est pas montré : une sous-case sans objet refuse la fiche entière
            if {"G13", "G14"} & set(codes):
                return Counter()
            if p.get("enregistree") and "G15" in codes and p.get("mode") != "livraison" and not ({"G16", "G17"} & set(codes)):
                return Counter(avant)  # E10 : changer une commande enregistrée en livraison sans adresse : « changement_incomplet », le panier d'avant revient (le retour le dit : « ta fiche n'a rien changé »)
            c, vu = Counter(avant), p
            reponse = fiche.get("reponse") if isinstance(fiche.get("reponse"), dict) else {}
            accord = reponse.get("sens") == "accepte" and question(p).get("type") == "relecture" and reponse.get("question_id") == question(p).get("id")
            # D8 (``cases_liees.DEPEND_DE_TOUT``, dit au retour) : une case de la fin (règlement, numéro, prénom) avant l'accord à la relecture est refusée, et « vider » (qui agit
            # sur toute la commande) n'est alors pas exécuté ; « annuler » l'est (le refus d'une autre case n'annule pas l'annulation voulue, RC4)
            fin_montree = bool(p.get("relecture")) and p.get("etape") != "accordee" and not accord  # sinon la fin n'est pas montrée : ses cases sont écartées seules (B4), le reste est fait
            vider = "G12" in codes and not ("G19" in codes and fin_montree)
            if vider:
                c, vu = Counter(), {**p, "lignes": []}
            for code, ef in zip(codes, effets):
                if code in ("G12", "G13", "G14"):
                    continue
                if code == "G23" and vider:
                    continue  # la question en attente portait sur le panier que cette même fiche vient de vider : la réponse n'a plus d'objet (``porte``, refus « question_inconnue »)
                ef = sans_conflit.get(code, ef) if conflit else ef
                c = ef(c, vu)
                if c is None:
                    return None
            if vider and p.get("enregistree") and not +c:
                return Counter(avant)  # DC4 + M2 : tout retirer d'une commande enregistrée, c'est l'annuler (la confirmation d'abord) : rien ne change
            return c - _ajouts_deja_repondus(fiche, p)

        return await self._executer("+".join(codes), ", ".join(dits), fiche, effet)

    async def recette(self, etat: str) -> bool:
        for pas in RECETTES[etat]:
            if pas.startswith("mode:"):
                await self._executer("recette", f"{pas[5:]}", {"mode_de_retrait": pas[5:]}, _inchange)
            elif pas == "adresse:Chantilly":
                await self._executer("recette", "4 rue de Beauvais à Chantilly", {"adresse": "4 rue de Beauvais", "commune": "Chantilly"}, _inchange)
            elif pas == "margherita":
                await self._executer("recette", "une margherita normale", {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}, _plus(MARGHERITA))
            elif pas == "margherita_sans_taille":
                await self._executer("recette", "une margherita", {"ajouter": [{"article": "margherita", "quantite": 1}]}, _plus(MARGHERITA))
            elif pas == "relu_par_carte":
                q = question(self.p)
                if not q.get("id"):
                    return False
                await self._executer("recette", "oui par carte", {"reponse": {"question_id": q["id"], "sens": "accepte"}, "moyen_de_paiement": "carte_bancaire"}, _inchange)
            elif pas == "prenom":
                await self._executer("recette", "Léa", {"prenom": "Léa"}, _inchange)
            elif pas == "regina":
                await self._executer("recette", "une regina normale", {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}, _plus(REGINA))
            elif pas == "formule":
                await self._executer("recette", "un menu entreprise", {"ajouter": [{"article": "menu entreprise", "quantite": 1}]}, _plus("F-MENU-ENTREPRISE"))
            else:
                if await self.geste(pas) is None:
                    return False
        self.observations.clear()
        self.attendu = lignes_de(self.p)
        return ATTEINT[etat](self.p)


# --------------------------------------------------------------------------- les règles (RC1 à RC15, audit du code § 3)

Faute = tuple[str, str]  # (règle, ce qui la casse)


def _refusee(r: dict | None) -> bool:
    return bool(r) and (r.get("statut") == "REJETEE" or not r.get("fiche_appliquee", True))


def _code_a_parle(o: Observation) -> bool:
    return bool(o.dit_par_le_code) or (o.decision is not None and getattr(o.decision, "motif", "") == "texte_du_code")


def _relance_deja_faite(o: Observation) -> bool:
    """La relance du modèle de ce tour a déjà eu lieu : sa phrase part seule, même sans la question (le plafond d'une relance par tour)."""
    return o.relance_du_fait


def rc1(o: Observation) -> list[Faute]:
    """Une seule question, et toujours une quand il manque quelque chose."""
    f: list[Faute] = []
    p, r = o.apres, o.retour or {}
    if o.fiche is not None and not finie(p) and p.get("lignes") is not None:
        a_dire = (r.get(CLE_DU) or {}).get("manque") or ""
        if not question(p) and not a_dire and not _code_a_parle(o) and not (r.get("faits") or {}).get("fait_bloquant") and p.get("mode"):
            f.append(("RC1", "commande ni enregistrée ni annulée : aucune question, aucune phrase de manque, rien dit par le code"))
    manque = (r.get(CLE_DU) or {}).get("manque")
    d = o.decision
    # le modèle formule la question de ce qui manque avec ses mots (Evan, 17/11) : la faute est une phrase dite seule qui n'en pose AUCUNE
    # lot 7b-C5 : ``manque`` est une valeur fermée, plus une phrase ; la table fait repasser le modèle une fois (``relance_du_fait``), ensuite sa phrase part seule
    if manque and d is not None and d.mode == PAROLE.A_DIRE_SEUL and not o.dit_par_le_code and "?" not in (d.a_dire or "") and not _relance_deja_faite(o):
        f.append(("RC1", f"ce qui manque (« {manque} ») n'est pas demandé : seule part « {d.a_dire} »"))
    dits = o.dit_par_le_code
    if dits.count("?") > 1:
        f.append(("RC1", f"le code pose plus d'une question : « {dits} »"))
    q = question(p)
    if q and q.get("texte") and q["texte"] not in dits and "?" in dits and q.get("type") not in ("proposition",):
        f.append(("RC1", f"deux questions dans le tour : la question posée « {q['texte']} » et celle du code « {dits} »"))
    return f


def rc2(o: Observation) -> list[Faute]:
    """Rien de perdu ni en double : le panier attendu (tenu par le geste) est le panier réel ; une fiche refusée en entier ne change rien. Pas d'effet déclaré = faute."""
    f: list[Faute] = []
    reel = lignes_de(o.apres)
    if o.attendu is None:
        f.append(("RC2", f"effet du geste sur le panier non déclaré ({o.geste}) : l'effet d'un geste est toujours connu, sinon le cas échoue"))
    else:
        manque, surplus = +(o.attendu - reel), +(reel - o.attendu)
        gardes = en_attente(o.apres) - en_attente(o.avant)
        liberes = en_attente(o.avant) - en_attente(o.apres)
        # ce qui manque au panier et qui est gardé de côté n'est pas perdu ; les gardés peuvent compter plus que ce qui manque : un article inconnu, dit
        # avec un connu avant le mode, est gardé lui aussi (dit introuvable quand le mode le prend) sans être dans le panier attendu (RC13, famille 1) ;
        # ce qui sort des gardés entre au panier : le surplus n'est jamais plus grand que ce qui a été libéré
        if sum(surplus.values()) > max(liberes, 0) or sum(manque.values()) > max(gardes, 0):
            f.append(("RC2", f"panier attendu {dict(+o.attendu)} / réel {dict(+reel)}"))
    if _refusee(o.retour) and lignes_de(o.avant) != reel:
        f.append(("RC2", "fiche refusée en entier, mais le panier a changé"))
    if o.identique and RAISON_DE_LA_FICHE_IDENTIQUE not in _raisons(o.retour):
        # PE-1 (Q1/Q2 c, Pierre 26/11) : la fiche identique n'est pas appliquée ET le modèle demande « un de plus ou le même ? » ; sans ce refus, l'article est perdu en silence
        f.append(("RC2", f"fiche identique au tour d'avant sans le refus {RAISON_DE_LA_FICHE_IDENTIQUE} : l'article est perdu sans rien demander"))
    return f


RAISON_DE_LA_FICHE_IDENTIQUE = "fiche_identique_au_tour_d_avant"


def _raisons(r: dict | None) -> set[str]:
    """Les raisons de refus que le retour de la fiche porte (la sienne et celles de ses refus)."""
    r = r or {}
    return {str(x) for x in [r.get("raison"), *((x or {}).get("raison") for x in r.get("refus") or [] if isinstance(x, dict))] if x}


def rc3(partie: Partie, o: Observation) -> list[Faute]:
    """Rien dit deux fois : la même phrase du code deux tours de suite (sauf la question en attente reprise après une incompréhension)."""
    j = partie.journal
    if len(j) >= 2 and j[-1] and j[-1] == j[-2] and o.geste not in ("G35",):
        q = question(o.apres)
        if not (q.get("texte") and q["texte"] == j[-1]):
            return [("RC3", f"le code redit « {j[-1]} »")]
    return []


def rc4(o: Observation) -> list[Faute]:
    """Jamais annoncé sans être fait, jamais fait sans être dit : le fait accompli (enregistrée, changée, annulée) a SES faits, ceux que le code garde comme dernier fait
    (``journal_du_dit.fait_accompli``) et dont le modèle dit la phrase (C6 n° 5 ; B9 : plus une phrase du code) ; un autre fait, même présent, ne le dit pas (Pierre 15)."""
    f: list[Faute] = []
    d = o.decision
    seule = d is not None and d.mode == PAROLE.A_DIRE_SEUL and d.motif != "texte_du_code"
    rien = lignes_de(o.avant) == lignes_de(o.apres) and question(o.avant) == question(o.apres) and o.avant.get("enregistree") == o.apres.get("enregistree")         and o.avant.get("mode") == o.apres.get("mode") and en_attente(o.avant) == en_attente(o.apres) \
        and bool(o.avant.get("annulee")) == bool(o.apres.get("annulee"))  # C6 n° 7 : une annulation est un changement, que le modèle dit
    r = o.retour or {}
    # PE-2 Q3 (décision de Pierre 26/11 22 h 05) : la phrase du modèle dite seule est permise quand la fiche rejouée est vide et que rien n'est dû (ni question, ni manque, ni fait bloquant)
    rien_de_du = o.fiche == {} and not question(o.apres) and not (r.get(CLE_DU) or {}).get("manque") and not (r.get("faits") or {}).get("fait_bloquant")
    if o.fiche is not None and seule and rien and not rien_de_du and (d.a_dire or "") == ANNONCE:
        f.append(("RC4", "rien n'a changé et la phrase du modèle (« C'est noté. », écrite avant l'exécution) est dite seule"))
    avant_e, apres_e = o.avant.get("enregistree") or {}, o.apres.get("enregistree") or {}
    fait = None
    if o.fiche is not None and apres_e and (not avant_e or apres_e.get("total") != avant_e.get("total") or apres_e.get("numero") != avant_e.get("numero")):
        fait = (("enregistree",) if not avant_e else ("changee", "enregistree"), "enregistrée" if not avant_e else "changée")  # changée : le changement ou la nouvelle confirmation (l'heure)
    if o.fiche is not None and not o.avant.get("annulee") and o.apres.get("annulee"):
        fait = (("annulee", "annulee_en_cours"), "annulée")  # les deux faits d'une annulation (enregistrée puis annulée ; en cours, ``annuler``)
    if fait:
        dit = (o.textes or {}).get("fait_accompli") or {}  # C6 n° 5 : le modèle dit le fait accompli ; le code en garde les faits au journal (B9)
        if not dit:
            f.append(("RC4", f"la commande est {fait[1]} et le code ne la fait pas dire (aucun fait accompli ; dit : « {o.dit_par_le_code} »)"))
        elif dit.get("fait") not in fait[0]:
            f.append(("RC4", f"la commande est {fait[1]} : le fait donné « {dit} » n'est pas celui du fait accompli"))
        elif J.fait_accompli(o.apres) != dit:
            f.append(("RC4", f"la commande est {fait[1]} : le fait donné « {dit} » n'est pas celui que le code garde comme dernier fait (« {J.fait_accompli(o.apres)} »)"))
    return f


def rc5(o: Observation) -> list[Faute]:
    """Fiche invalide refusée, avec exactement quoi refaire (chaque refus porte sa consigne)."""
    r = o.retour or {}
    sans = [x.get("raison") for x in r.get("refus") or [] if not x.get("a_faire")]
    f = [("RC5", f"refus sans consigne : {sans}")] if sans else []
    if r.get("statut") == "REJETEE" and not r.get("a_faire"):
        f.append(("RC5", "fiche refusée sans consigne"))
    fi = o.fiche or {}
    visees = [n for n in fi.get("retirer_article") or [] if isinstance(n, int)] + [c.get("ligne") for c in fi.get("changer_quantite") or [] if isinstance(c, dict)]
    faites = set(r.get("cases_executees") or [])
    if len(visees) != len(set(visees)) and not _refusee(r) and faites & {"retirer_article", "changer_quantite"}:  # refusées, le reste de la fiche passe
        f.append(("RC5", f"deux cases visent la même ligne dans la fiche et s'exécutent l'une après l'autre (lignes {visees}) : à refuser avec la question à poser"))
    return f


def rc6(partie: Partie) -> list[Faute]:
    """Sortie de boucle : la même question, le même fait bloquant ou le même refus rendu 3 fois de suite sans que l'état change."""
    obs = [o for o in partie.observations if o.fiche is not None][-3:]
    if len(obs) < 3:
        return []

    def signe(o: Observation):
        r = o.retour or {}
        bloquant = (r.get("faits") or {}).get("fait_bloquant")
        return (CONV.identite_de_la_question(question(o.apres)), json.dumps(bloquant, sort_keys=True) if bloquant else None, r.get("raison"))  # B3 : jamais « 'None' » ; lot 7b-C5 : la question par sa structure, plus par son texte

    sortie = J.A_FAIRE_SORTIE in str((obs[-1].retour or {}).get("a_faire") or "")  # B3 : la sortie du journal (un message à l'équipe)
    if len({signe(o) for o in obs}) == 1 and all(lignes_de(o.avant) == lignes_de(o.apres) for o in obs) and any(signe(obs[0])) and not sortie:
        return [("RC6", f"trois fois la même chose sans sortie : {signe(obs[0])}")]
    return []


def rc7(o: Observation) -> list[Faute]:
    """Incompréhension : le dire, puis reprendre la question en attente (ou le manque). Lot 7b-C5 : le code ne reprend rien de sa voix, il relance le modèle ; la consigne de relance doit porter la
    question en attente (son identifiant), ou ce qui manque. Après une action faite (enregistrée ou annulée), rien n'est dû : la phrase réglée « pas compris » part (P3 ; reprise R1 de C6,
    décisions d'Evan 25/11 8 h 45 et 9 h 30, le code ne redit plus le fait accompli)."""
    if o.geste != "G35":
        return []
    q = question(o.apres)
    if q.get("id") and f'"id": "{q["id"]}"' not in (o.consigne or ""):
        return [("RC7", f"après « pardon ? », la consigne de relance ne porte pas la question en attente : « {o.consigne} »")]
    if not finie(o.apres) and not q and not o.consigne:
        return [("RC7", "après « pardon ? », rien à redire alors que la commande n'est pas finie")]
    return []


def rc8(o: Observation) -> list[Faute]:
    """Une commande finie est fermée : annulée, aucune ligne ajoutée ; enregistrée, un changement passe par la caisse ou est refusé."""
    repart = question(o.avant).get("type") == "nouvelle_commande" and ((o.fiche or {}).get("reponse") or {}).get("sens") == "accepte"  # DC5 : « oui » = une commande neuve
    if o.avant.get("annulee") and +lignes_de(o.apres) - +lignes_de(o.avant) and not repart:
        return [("RC8", "un article entre dans une commande annulée")]
    r = o.retour or {}
    if o.avant.get("enregistree") and lignes_de(o.avant) != lignes_de(o.apres) and not P.a_completer(o.apres):  # la ligne attend sa taille : la caisse après
        ops = {x.get("operation") for x in r.get("resultats") or []}
        if "changer_la_commande_enregistree" not in ops:
            return [("RC8", "le panier d'une commande enregistrée change sans passer par la caisse")]
    return []


def rc9(o: Observation) -> list[Faute]:
    """Une question a un numéro stable et tombe avec son objet."""
    f: list[Faute] = []
    qa, qp = question(o.avant), question(o.apres)
    if qa and qp and CONV.identite_de_la_question(qa)[1:] == CONV.identite_de_la_question(qp)[1:] and qa.get("id") != qp.get("id"):  # lot 7b-C5 : la même question par sa structure (type, objet), plus par son texte
        f.append(("RC9", f"la même question change de numéro : {qa.get('id')} → {qp.get('id')}"))
    if qp.get("type") == "proposition" and qp.get("article_propose"):
        noms = {str(l.get("nom") or "") for l in o.apres.get("lignes") or []}
        if any(n.startswith(str(qp["article_propose"])) for n in noms):
            f.append(("RC9", f"la proposition « {qp['article_propose']} » reste posée, l'article est déjà dans le panier"))
    if qp.get("type") == "variante" and not P.a_completer(o.apres):
        f.append(("RC9", "une question de taille reste posée, aucune ligne n'attend"))
    if qp.get("type") == "relecture" and o.apres.get("etape") == "accordee":
        f.append(("RC9", "la relecture reste posée, l'accord est donné"))
    if qp.get("type") == "proposition" and qa.get("type") == "proposition" and qa.get("id") == qp.get("id") and o.fiche is not None \
            and (o.fiche.get("reponse") or {}).get("sens") != "accepte" and (o.retour or {}).get("statut") != "REJETEE" \
            and qa.get("nee_au_tour") != CONV.de(o.apres).get("tour_de_l_appel"):
        # refusée en entier, rien ne change (RC2) ; née dans ce tour, la personne ne l'a pas encore entendue
        f.append(("RC9", "la proposition reste posée après un tour sans « oui » (DC3)"))
    return f


def rc10(partie: Partie, o: Observation) -> list[Faute]:
    """« Dit » veut dire « parti » : une relecture marquée faite dans CE tour a son texte dans ce que le code a dit dans CE tour (pas dans un tour d'avant)."""
    rel = o.apres.get("relecture")
    avant_rel = o.avant.get("relecture") if isinstance(o.avant.get("relecture"), dict) else {}
    # une relecture « nouvelle » dit autre chose à la personne (le total, ou le texte de la question posée) : un nouveau jeton ou une empreinte qui change pour une
    # donnée qu'elle n'entend pas (une adresse sur une commande à emporter) ne change rien à ce qu'elle a entendu
    q_avant = question(o.avant) if question(o.avant).get("type") == "relecture" else {}
    if not (isinstance(rel, dict) and rel):
        return []
    nouvelle = (not avant_rel) or rel.get("total") != avant_rel.get("total") or (question(o.apres).get("type") == "relecture" and question(o.apres).get("texte") != q_avant.get("texte"))
    if nouvelle:
        q = question(o.apres)
        dit = o.dit_par_le_code
        voulu = q["texte"] if q.get("type") == "relecture" and q.get("texte") else None
        if voulu is not None and voulu not in dit:
            return [("RC10", f"relecture marquée faite dans ce tour, son texte n'a pas été dit dans ce tour (dit : « {dit} »)")]
        # C6 (décision d'Evan 25/11 9 h 30) : le modèle relit, le code dit la phrase réglée du total (ses variantes tournent) ; « dite » = notée partie à la voix, au jeton de la relecture
        if voulu is None and not PAROLE.total_dit(o.apres, rel.get("jeton")):
            return [("RC10", f"relecture marquée faite dans ce tour, sa phrase du total n'est pas partie dans ce tour (dit : « {dit} »)")]
    return []


def rc11(o: Observation) -> list[Faute]:
    """L'accord vaut pour ce qui a été lu : enregistrée, le total est celui de la dernière relecture."""
    e, rel = o.apres.get("enregistree") or {}, o.avant.get("relecture") or {}
    if e and not o.avant.get("enregistree") and rel.get("total") is not None and e.get("total") != rel.get("total"):
        return [("RC11", f"enregistrée à {e.get('total')}, relue à {rel.get('total')}")]
    return []


def manque_du_moteur(texte: str | None):
    """Le membre et les modes d'un « manque » que le moteur écrit en texte : lu ICI seulement, par l'oracle (plus aucune lecture de texte dans ``services/``)."""
    from api.services.commande.phrases_du_manque import Manque

    if not texte:
        return None, ()
    if texte.startswith(Manque.MODE):
        return Manque.MODE, tuple(m.strip() for m in texte[len(Manque.MODE):].strip(" ()").replace(" ou ", ", ").split(",") if m.strip())
    try:
        return Manque(texte), ()
    except ValueError:
        return None, ()


def rc12(o: Observation) -> list[Faute]:
    """« Ce qui manque » a une seule réponse : la valeur de manque rendue est celle du manque que le moteur bloque."""
    from api.services.commande import phrases_du_manque as M

    r = o.retour or {}
    fb = (r.get("faits") or {}).get("fait_bloquant") or {}
    if (r.get(CLE_DU) or {}).get("manque") and fb.get("manque"):
        manque, modes = manque_du_moteur(fb["manque"])
        portee = manque is None or manque in M.PORTEES_PAR_UNE_QUESTION or (manque is M.Manque.MODE and not modes)  # la question la porte, ou aucun mode ouvert
        attendu = None if portee else manque.value  # lot 7b-C5 : la valeur fermée de ce qui manque, plus sa phrase (C7 B9 : le catalogue des phrases est supprimé)
        if attendu and attendu != r[CLE_DU]["manque"]:
            return [("RC12", f"valeur de manque « {r[CLE_DU]['manque']} », le moteur bloque sur « {fb['manque']} »")]
    return []


def rc15_valeurs_nulles(o: Observation) -> list[Faute]:
    """Défaut muet (M9) : aucune valeur ``null`` là où le retour donne une heure ou un prix à dire."""
    texte = json.dumps(o.retour or {}, ensure_ascii=False)
    for cle in ('"heure_dite": null', '"quand_dit": null', '"total": null'):
        if cle in texte:
            return [("M9", f"valeur nulle dans le retour : {cle}")]
    return []


def _lignes_de_la_base(commande: dict[str, Any]) -> Counter:
    c: Counter = Counter()
    for l in commande.get("lignes") or []:
        c[(l.get("code_caisse"), tuple(sorted(l.get("retires") or [])))] += int(l.get("quantite") or 0)
    return c


def rc_base(o: Observation) -> list[Faute]:
    """Pendant l'appel : la commande enregistrée est la même dans le panier et dans ``resto_commande`` (et ses lignes) : lignes (code, retraits, quantité), total, mode ;
    elle y est « retenue » et la caisse n'en a RIEN reçu (§ 17 : elle part à la fin de l'appel, jugée par ``rc_base_fin``). Une commande fausse en base ne reste jamais verte
    parce que le panier en mémoire est juste (Pierre 15)."""
    e = o.apres.get("enregistree")
    if not e:
        return []
    f: list[Faute] = [("BASE", "la caisse a reçu la commande pendant l'appel (§ 17 : à la fin de l'appel seulement)")] if o.prise is not None else []
    b = o.base
    if b is None:
        return [*f, ("BASE", f"enregistrée dans le panier (numéro {e.get('numero')}), absente de resto_commande")]
    annulee = bool(o.apres.get("annulee") or e.get("annulee"))
    if P.a_completer(o.apres) and not annulee:
        return f  # RC8 : un changement dont une ligne attend sa taille part en caisse après sa réponse ; en attendant, la base est celle d'avant
    if annulee != (b.get("statut") == "annulee"):
        f.append(("BASE", f"panier {'annulé' if annulee else 'actif'}, resto_commande au statut « {b.get('statut')} »"))
    if annulee:
        return f
    if b.get("statut") != "retenue":
        f.append(("BASE", f"pendant l'appel, resto_commande au statut « {b.get('statut')} » (attendu : retenue)"))
    return f + _panier_face_a_la_base(o.apres, b)


def _panier_face_a_la_base(p: dict[str, Any], b: dict[str, Any]) -> list[Faute]:
    f: list[Faute] = []
    e = p.get("enregistree") or {}
    attendu = Counter()
    for l in P.lignes_pretes(p):
        attendu[(l.get("code"), tuple(sorted(l.get("retires") or [])))] += int(l.get("quantite") or 0)
    if attendu != _lignes_de_la_base(b):
        f.append(("BASE", f"lignes du panier {dict(attendu)} / lignes de resto_commande {dict(_lignes_de_la_base(b))}"))
    if e.get("total") is not None and e.get("total") != b.get("total"):
        f.append(("BASE", f"total du panier {e.get('total')} / total de resto_commande {b.get('total')}"))
    if p.get("mode") and p.get("mode") != b.get("mode"):
        f.append(("BASE", f"mode du panier {p.get('mode')} / mode de resto_commande {b.get('mode')}"))
    return f


def rc_base_fin(p: dict[str, Any], b: dict[str, Any] | None, recues: list[dict[str, Any]], lignes_de_l_appel: list[tuple[str, str]]) -> list[Faute]:
    """§ 17, après la fin de l'appel : une commande accordée (enregistrée, pas annulée) est partie, et la caisse l'a reçue UNE fois, telle que la base la porte (lignes, total,
    mode) ; une commande annulée ou jamais accordée n'a rien envoyé (sa ligne, s'il y en a une, est « annulee »). Toute autre ligne de l'appel (``lignes_de_l_appel`` :
    ``(numero, statut)`` de ``resto_commande``, une ancienne version) est « annulee » : aucune ne reste « retenue » (audit 8b-1a, R3)."""
    return _autres_lignes_de_l_appel(b, lignes_de_l_appel) + _la_commande_a_la_fin(p, b, recues)


def _autres_lignes_de_l_appel(b: dict[str, Any] | None, lignes_de_l_appel: list[tuple[str, str]]) -> list[Faute]:
    jugee = str(b.get("numero")) if b is not None else None  # la commande du panier : jugée par ``_la_commande_a_la_fin``
    return [("BASE", f"après la fin de l'appel, une autre ligne de l'appel ({numero}) au statut « {statut} » (attendu : annulee)")
            for numero, statut in lignes_de_l_appel if numero != jugee and statut != "annulee"]


def _la_commande_a_la_fin(p: dict[str, Any], b: dict[str, Any] | None, recues: list[dict[str, Any]]) -> list[Faute]:
    e = p.get("enregistree")
    if not e or p.get("annulee") or e.get("annulee"):
        f: list[Faute] = [("BASE", f"la caisse a reçu {len(recues)} envoi(s) d'une commande que l'appel n'a pas accordée")] if recues else []
        if b is not None and b.get("statut") != "annulee":
            f.append(("BASE", f"commande annulée dans l'appel, resto_commande au statut « {b.get('statut')} »"))
        return f
    if b is None:
        return [("BASE", f"enregistrée dans le panier (numéro {e.get('numero')}), absente de resto_commande")]
    f = [] if P.a_completer(p) else _panier_face_a_la_base(p, b)  # RC8 : une ligne attend sa taille ; la base est la version accordée, c'est elle qui part
    if b.get("statut") in ("retenue", "annulee"):
        f.append(("BASE", f"après la fin de l'appel, resto_commande au statut « {b.get('statut')} » (attendu : partie)"))
    siennes = [r for r in recues if str(r.get("numero")) == str(b.get("numero"))]
    if len(recues) != 1 or len(siennes) != 1:
        f.append(("BASE", f"la caisse a reçu {len(recues)} envoi(s), dont {len(siennes)} de cette commande (attendu : 1)"))
    for r in siennes[-1:]:
        if _lignes_de_la_base({"lignes": r.get("lignes")}) != _lignes_de_la_base(b):
            f.append(("BASE", "ce que la prise a reçu n'a pas les lignes de resto_commande"))
        if r.get("total") != b.get("total"):
            f.append(("BASE", f"la prise a reçu le total {r.get('total')}, resto_commande {b.get('total')}"))
        if r.get("mode") != b.get("mode"):
            f.append(("BASE", f"la prise a reçu le mode {r.get('mode')}, resto_commande {b.get('mode')}"))
    return f


def juger(partie: Partie, o: Observation) -> list[Faute]:
    f: list[Faute] = []
    for regle in (rc1, rc2, rc4, rc5, rc7, rc8, rc9, rc11, rc12, rc15_valeurs_nulles, rc_base, rc17_un_seul_finaliser):
        f += regle(o)
    f += rc3(partie, o) + rc10(partie, o) + rc6(partie) + rc16_etape(partie, o)
    return f


def phase_deduite_des_drapeaux(p: dict[str, Any]) -> str:
    """L'ancienne ``registre.phase`` (lot 2 : retirée du code, gardée ICI comme oracle) : où en est la commande, redéduit de ses faits."""
    if p.get("annulee"):
        return "annulee"
    if p.get("enregistree"):
        return "enregistree"
    if isinstance(p.get("relecture"), dict) and p["relecture"]:
        return "a_relire"
    return "en_cours"


def rc17_un_seul_finaliser(o: Observation) -> list[Faute]:
    """R2 : une fiche mène la commande à sa fin UNE fois au plus, quelles que soient les cases qu'elle porte."""
    return [("RC17", f"{o.geste} : la fiche a mené la commande à sa fin {o.finaliser_appels} fois")] if o.finaliser_appels > 1 else []


def rc16_etape(partie: Partie, o: Observation) -> list[Faute]:
    """RC16 (lot 2, mécanisme É) : l'étape STOCKÉE est celle que disent les faits de la commande, après chaque geste (le « vide » d'avant n'est plus une étape).
    Deux étapes ne se déduisent pas des faits : « accordée » (l'accord n'a plus de clé) et « à clore » (« c'est tout » dit, la relecture attend l'heure) ; elle n'est admise que si « c'est tout » figure dans
    les gestes joués de la partie (la recette comprise)."""
    if not isinstance(o.apres, dict) or "etape" not in o.apres:
        return [("RC16", "le panier n'a pas d'étape stockée")]
    attendu = phase_deduite_des_drapeaux(o.apres)
    if o.apres["etape"] == "accordee":
        # l'accord n'a plus de clé : il n'existe que dans l'étape ; il suppose une relecture posée (les faits disent « à relire »)
        return [] if attendu == "a_relire" else [("RC16", f"étape « accordée » sans relecture posée (les faits disent « {attendu} »)")]
    if o.apres["etape"] == "a_clore" and attendu == "en_cours":
        dit = any(isinstance(x.fiche, dict) and x.fiche.get("c_est_tout") for x in partie.observations)
        return [] if dit else [("RC16", "étape « à clore » sans qu'aucun geste joué n'ait dit « c'est tout »")]
    return [] if o.apres["etape"] == attendu else [("RC16", f"étape stockée « {o.apres['etape']} », les faits disent « {attendu} »")]


def rc14_gabarit() -> list[Faute]:
    """Une action ouverte reste joignable : dans le gabarit, la sortie ``rendre_la_main`` des étapes qui tiennent une action (commande, réservation)
    est fermée tant que l'action est ouverte, comme ``fin`` (M8)."""
    g = json.loads(GABARIT.read_text(encoding="utf-8"))
    fautes: list[Faute] = []
    for etape, e in (g.get("etapes") or {}).items():
        if not e.get("connecteur"):
            continue  # une étape sans action (accueil, service) n'a rien d'ouvert à garder
        for s in e.get("sorties") or []:
            # Une sortie offerte pendant une action ouverte : fermée (comme « fin »), ou un détour qui garde l'action et y revient seul.
            if not (s.get("fermee_si_action_ouverte") or s.get("garde_l_action_ouverte")):
                fautes.append(("RC14", f"{etape} : la sortie {s.get('sortie')} reste offerte, sans garder l'action, quand une action est ouverte"))
    return fautes


# --------------------------------------------------------------------------- RC13 : une fiche, c'est tout ou rien par case, même en panne

REGINA_NORMALE = {"article": "regina", "quantite": 1, "variante": "Normale"}


@dataclass(frozen=True)
class FicheEnPanne:
    """Une fiche à plusieurs cases, jouée depuis ``etat`` ; ``effets`` dit ce que chaque case fait au panier quand elle s'exécute (RC13 en a besoin : le panier
    après une panne doit être celui d'avant, ou celui que les cases DITES FAITES dans le retour expliquent)."""

    nom: str
    etat: str
    dit: str  # ce que la personne dit : les valeurs de la fiche y sont (sinon la barrière « valeur pas dans ses mots » refuse la case avant la panne)
    fiche: Callable[[dict[str, Any]], dict[str, Any]]
    effets: dict[str, Callable[[Counter], Counter]]


def _moins_la_ligne_1(avant: Counter) -> Counter:
    c = Counter(avant)
    c[MARGHERITA] -= 1  # les fiches de RC13 partent d'une margherita à la ligne 1
    return +c


FICHES_EN_PANNE = (
    FicheEnPanne("remplacer, l'heure, c'est tout", "E4", "enlevez la première, mettez une regina normale, pour dix-neuf heures, c'est tout",
                 lambda p: {"retirer_article": [_n1(p)], "ajouter": [REGINA_NORMALE], "heure": "dix-neuf heures", "c_est_tout": True},
                 {"retirer_article": _moins_la_ligne_1, "ajouter": lambda a: _plus(REGINA)(a, {})}),
    FicheEnPanne("deux quantités, un ajout, l'heure", "E4", "mettez-en deux, et une regina normale, pour dix-neuf heures",
                 lambda p: {"changer_quantite": [{"ligne": _n1(p), "quantite": 2}], "ajouter": [REGINA_NORMALE], "heure": "dix-neuf heures"},
                 {"changer_quantite": lambda a: Counter({**a, MARGHERITA: 2}), "ajouter": lambda a: _plus(REGINA)(a, {})}),
    FicheEnPanne("tout vider, un ajout, l'heure", "E4", "on recommence tout, une regina normale, pour dix-neuf heures",
                 lambda p: {"vider_le_panier": True, "ajouter": [REGINA_NORMALE], "heure": "dix-neuf heures"},
                 {"vider_le_panier": lambda a: Counter(), "ajouter": lambda a: _plus(REGINA)(a, {})}),
)
# Ce que chaque case appelle dans le code ; une panne simulée y lève une exception, comme une base ou une caisse qui lâche.
# (``informations`` : toutes les cases d'information ; ``reponse`` n'y est pas : les fiches de RC13 ne répondent à aucune question.)
APPELS_DES_CASES = {
    "vider_le_panier": ("api.services.commande.moteur", "vider_commande"), "annuler_la_commande": ("api.services.commande.porte", "annuler"),
    "retirer_article": ("api.services.commande.moteur", "retirer"), "changer_quantite": ("api.services.commande.moteur", "modifier"),
    "ajouter": ("api.services.commande.porte", "ajouter_un_article"), "informations": ("api.services.commande.porte", "_poser_les_informations"),
    "c_est_tout": ("api.services.commande.porte", "mener_a_la_fin"),
}


def cases_de_la_fiche(fiche: dict[str, Any]) -> list[str]:
    """Les cases de la fiche dans l'ordre du code, avec ses informations réunies sous ``informations`` (le code les pose en une seule opération)."""
    from api.services.commande import porte as PORTE

    vues, noms = False, []
    for case in PORTE.ordre_des_cases(fiche):
        if case in PORTE.INFORMATIONS:
            if not vues:
                noms.append("informations")
            vues = True
        elif case in APPELS_DES_CASES:
            noms.append(case)
    return noms


async def jouer_en_panne(monde, monkeypatch, modele: FicheEnPanne, case_en_panne: str) -> list[Faute]:
    """RC13 : la même fiche, jouée avec une panne à ``case_en_panne`` ; le panier est celui d'avant, ou celui des cases que le retour dit faites."""
    import importlib

    partie = Partie(monde, monkeypatch)
    if not await partie.recette(modele.etat):
        return [("RC13", f"{modele.etat} non atteint")]
    fiche = modele.fiche(partie.p)
    cases = cases_de_la_fiche(fiche)
    avant = lignes_de(partie.p)
    module, nom = APPELS_DES_CASES[case_en_panne]

    async def panne(*a, **k):
        raise RuntimeError(f"panne simulée à {case_en_panne}")

    with monkeypatch.context() as m:
        m.setattr(importlib.import_module(module), nom, panne)
        partie.e.dit(modele.dit)
        retour = await partie.e.fiche(**fiche)
    return rc13(modele, cases, case_en_panne, avant, lignes_de(partie.p), retour)


def rc13(modele: FicheEnPanne, cases: list[str], case_en_panne: str, avant: Counter, apres: Counter, retour: dict[str, Any]) -> list[Faute]:
    """Panne à une case : le retour dit que la fiche n'a pas abouti ; le panier est celui d'AVANT, ou celui des cases que le retour DIT faites (jamais un
    panier à moitié changé que personne ne sait décrire)."""
    f: list[Faute] = []
    if not (retour.get("faits") or {}).get("indisponible"):
        f.append(("RC13", f"panne à « {case_en_panne} » : le retour ne dit pas que la fiche n'a pas abouti ({retour.get('statut')}, {retour.get('raison')})"))
    if +avant == +apres:
        return f
    from api.services.commande.porte import INFORMATIONS

    faites = retour.get("cases_executees")
    faites = ["informations" if c in INFORMATIONS else c for c in faites] if isinstance(faites, list) else faites
    if not isinstance(faites, list):
        return f + [("RC13", f"panne à « {case_en_panne} » : le panier a changé ({dict(+avant)} → {dict(+apres)}) et le retour ne dit pas quelles cases sont faites")]
    attendu = Counter(avant)
    for case in faites:
        if case in modele.effets:
            attendu = modele.effets[case](attendu)
    if set(faites) - set(cases[: cases.index(case_en_panne)]):
        f.append(("RC13", f"panne à « {case_en_panne} » : le retour dit faites {faites}, qui ne sont pas celles d'avant la panne ({cases[: cases.index(case_en_panne)]})"))
    if +attendu != +apres:
        f.append(("RC13", f"panne à « {case_en_panne} » : le retour dit faites {faites} (panier attendu {dict(+attendu)}), le panier est {dict(+apres)}"))
    return f


# --------------------------------------------------------------------------- RC15 : même faute, même traitement dans tous les modules


def rc15_meme_traitement(nom: str, commande: dict[str, Any], reservation: dict[str, Any]) -> list[Faute]:
    """Une même fiche mal formée reçoit la MÊME raison de refus sur la commande et sur la réservation (les mots de la consigne peuvent différer ; le statut de
    la fiche aussi, selon le sort de la question : seul compte ce qui est refusé, et pourquoi)."""

    def signe(r: dict[str, Any]):
        return (r.get("raison"), sorted({x.get("raison") for x in r.get("refus") or []}), sorted(r.get("cases_refusees") or []))

    a, b = signe(commande), signe(reservation)
    return [] if a == b else [("RC15", f"{nom} : la commande rend {a}, la réservation rend {b}")]


# --------------------------------------------------------------------------- jouer, tirer, réduire, rapporter


@dataclass
class Resultat:
    etat: str
    suite: tuple[str, ...]
    atteint: bool
    fautes: list[tuple[str, str, str]] = field(default_factory=list)  # (geste, règle, détail)
    durees: list[float] = field(default_factory=list)
    joues: int = 0  # les gestes (ou fusions) réellement joués dans la suite
    non_applicables: int = 0  # ceux qui n'avaient pas d'objet dans l'état (rien n'est joué, aucune règle ne les voit) : comptés à part, jamais « verts »


async def jouer(monde, monkeypatch, etat: str, suite: tuple[str, ...]) -> Resultat:
    """La recette de l'état, puis la suite (un code de geste, ou plusieurs réunis par « + » : une fiche fusionnée). E9 se joue à l'heure de la fermeture."""
    if etat == "E9":
        with horloge.remplacer(monde.base, FERMETURE):
            return await _jouer(monde, monkeypatch, etat, suite)
    return await _jouer(monde, monkeypatch, etat, suite)


async def _jouer(monde, monkeypatch, etat: str, suite: tuple[str, ...]) -> Resultat:
    partie = Partie(monde, monkeypatch)
    res = Resultat(etat, suite, await partie.recette(etat))
    if not res.atteint:
        return res
    for pas in suite:
        o = await (partie.fusion(tuple(pas.split("+"))) if "+" in pas else partie.geste(pas))
        if o is None:
            res.non_applicables += 1
            continue
        res.joues += 1
        res.durees.append(o.duree_ms)
        for regle, detail in juger(partie, o):
            res.fautes.append((pas, regle, detail))
    for regle, detail in await partie.finir_l_appel():  # § 17 : la caisse se juge à la fin de l'appel
        res.fautes.append(("fin", regle, detail))
    return res


async def reduire(monde, monkeypatch, res: Resultat) -> Resultat:
    """Une suite rouge réduite à la plus courte qui reste rouge sur la même règle (retrait des gestes un à un)."""
    regles = {f[1] for f in res.fautes}
    suite = list(res.suite)
    i = 0
    while i < len(suite) and len(suite) > 1:
        essai = tuple(suite[:i] + suite[i + 1:])
        r = await jouer(monde, monkeypatch, res.etat, essai)
        if r.atteint and regles & {f[1] for f in r.fautes}:
            suite = list(essai)
            res = r
        else:
            i += 1
    return res


def tirer(graine: int, n: int, longueur: int) -> list[tuple[str, tuple[str, ...]]]:
    """``n`` suites de ``longueur`` gestes tirées au sort avec ``graine`` (écrite au rapport : une suite rouge se rejoue à l'identique)."""
    hasard = random.Random(graine)
    codes = [g.code for g in GESTES.values() if g.code not in ("G36",)]
    tirages = []
    for _ in range(n):
        suite = []
        for _ in range(longueur):
            if hasard.random() < 0.2:
                a, b = hasard.sample([g.code for g in FUSIONNABLES], 2)
                suite.append(f"{a}+{b}")
            else:
                suite.append(hasard.choice(codes))
        tirages.append((hasard.choice(ETATS), tuple(suite)))
    return tirages


def centile(valeurs: list[float], q: float) -> float:
    if not valeurs:
        return 0.0
    v = sorted(valeurs)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def rapport(resultats: list[Resultat], titre: str, graine: int | None = None) -> dict[str, Any]:
    fautes: dict[str, list[str]] = {}
    for r in resultats:
        for geste, regle, detail in r.fautes:
            fautes.setdefault(regle, []).append(f"{r.etat} → {' · '.join(r.suite)} [{geste}] : {detail}")
    durees = [d for r in resultats for d in r.durees]
    return {
        "titre": titre, "graine": graine, "cas": len(resultats), "etats_non_atteints": sorted({r.etat for r in resultats if not r.atteint}),
        # « joués » : au moins un geste réellement exécuté ; « non applicables » : tous sans objet dans l'état (jamais comptés verts)
        "cas_joues": sum(1 for r in resultats if r.atteint and r.joues), "cas_non_applicables": sum(1 for r in resultats if r.atteint and not r.joues),
        "gestes_joues": sum(r.joues for r in resultats), "gestes_non_applicables": sum(r.non_applicables for r in resultats),
        "cas_rouges": sum(1 for r in resultats if r.fautes), "fautes_par_regle": {k: len(v) for k, v in sorted(fautes.items())},
        "temps_par_fiche_ms": {"mediane": round(centile(durees, 0.5), 1), "95e": round(centile(durees, 0.95), 1), "fiches": len(durees)},
        "exemples": {k: sorted(set(v))[:12] for k, v in sorted(fautes.items())},
    }
