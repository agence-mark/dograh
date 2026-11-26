"""[.mark] Lot 7b-C7a, aides publiques du test de garde du signal : ce que le modèle lit d'un retour du module, et la comparaison « le signal porte la valeur ».

Le signal est le statut du module, ce qui manque et les faits bruts, tels que le modèle les reçoit :
- ``F`` (la fiche) : les faits publics du refus, puis la copie allégée de ``enveloppe_legere.pour_le_modele`` (``outil.py``) ;
- ``L`` (lire) : les faits bruts (``lire.py``), seuls le panier et le prix à dire sont retirés ;
- ``S`` (le suivi d'une commande) : les faits sans le panier ni les candidats (``commande/porte.py``) ;
- ``Rv`` (réservation) : ``resultat_public`` de la porte commune ; ``RvQ`` y ajoute ``candidats_dits``, la question de choix que pose la porte de la réservation.
Une valeur est comparée ENTIÈRE (``norm``), jamais comme sous-chaîne : « Oise » n'est pas trouvé dans « Val-d'Oise ». Un nombre se compare par ses formes
(``valeurs_des_faits`` : « 1500 », « quinze euros »). Un drapeau vrai (``panier_vide: true``) compte pour son nom.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from api.services.actions_communes import porte_commune as PC
from api.services.commande.briques import formule as FO
from api.services.actions_communes.barriere_des_chiffres import valeurs_des_faits
from api.services.actions_communes.enveloppe_legere import pour_le_modele
from api.services.actions_communes.forme import norm
from api.services.commande.porte import faits_vus_par_le_modele
from api.services.reservation.porte import FAITS_GARDES_PAR_LA_RESERVATION

CHEMINS = ("F", "L", "S", "Rv", "RvQ")
Valeurs = list[tuple[str, str]]


def feuilles(x: Any) -> set[str]:
    """Chaque valeur du signal : un texte tel quel, un nombre sous ses formes, un drapeau vrai sous son nom (les clés des dictionnaires ne sont pas des valeurs)."""
    if isinstance(x, dict):
        sortie: set[str] = set()
        for cle, v in x.items():
            if v is True:
                sortie.add(norm(str(cle)))
            sortie |= feuilles(v)
        return sortie
    if isinstance(x, (list, tuple)):
        return set().union(set(), *(feuilles(v) for v in x))
    if x is None or isinstance(x, bool):
        return set()
    if isinstance(x, (int, float)):
        return {norm(v) for v in valeurs_des_faits(x)}
    return {norm(str(x))}


FAITS_CACHES_DU_SUIVI = ("panier", "candidats")  # ce que la porte de la commande retire du suivi d'une commande (``commande/porte.py``, ``faits_du_suivi``)


def signal(r: Any, chemin: str, operation: str = "fiche") -> Any:
    """Ce que le modèle lit du retour ``r`` d'un module, selon le chemin par lequel il le lit.

    ``S`` (le suivi d'une commande) et ``RvQ`` (le choix d'une réservation) recopient ce que leur porte fait du retour : la première n'a pas de fonction publique
    pour ses faits, la seconde pose sa question (``candidats_dits``) à côté des faits ; une porte qui change ce qu'elle montre change aussi ce chemin."""
    if chemin == "F":
        publics = faits_vus_par_le_modele(r)
        fait = {"statut_du_module": r.statut, "manque": r.manque, "faits": publics}
        return pour_le_modele({"resultats": [fait], "faits": {"refus_de_la_fiche": [fait]}})
    if chemin == "L":
        return {"statut_du_module": r.statut, "manque": r.manque, "faits": {k: v for k, v in r.faits.items() if k not in ("panier", "prix_a_dire")}}
    if chemin == "S":
        return {"statut_du_module": r.statut, "manque": r.manque, "faits": {k: v for k, v in r.faits.items() if k not in FAITS_CACHES_DU_SUIVI}}
    if chemin == "Rv":
        return PC.resultat_public(operation, r, FAITS_GARDES_PAR_LA_RESERVATION)
    if chemin == "RvQ":
        candidats = (r.faits or {}).get("candidats") or []
        return {**PC.resultat_public(operation, r, FAITS_GARDES_PAR_LA_RESERVATION), "candidats_dits": [c["dit"] for c in candidats if isinstance(c, dict) and c.get("dit")]}
    raise ValueError(chemin)


def valeurs_absentes(r: Any, chemin: str, valeurs: list[tuple[str, str]], discriminant: str) -> list[str]:
    """Ce que le signal ne porte pas : le discriminant (statut, raison ou manque qui distingue ce refus d'un autre) puis chaque valeur que le texte disait."""
    vus = feuilles(signal(r, chemin))
    absentes = [] if norm(discriminant) in vus else [f"discriminant « {discriminant} »"]
    return absentes + [dans_le_signal for dans_le_signal, _ in valeurs if norm(dans_le_signal) not in vus]


def pareilles(*mots: str) -> Valeurs:
    """Des valeurs dites telles quelles : la forme du signal est celle du texte."""
    return [(m, m) for m in mots]


@dataclass
class Cas:
    """Un texte de secours et le scénario qui joue le vrai module : le signal doit porter son discriminant et chaque valeur que le texte disait."""

    nom: str
    texte: Callable[[dict], str] | None  # le texte de secours d'avant, refait des faits qu'il lisait (``None`` : aucun mot à vérifier)
    scenario: Callable[..., Any]         # joue le vrai module et rend son retour
    chemin: str                          # un des ``CHEMINS``
    valeurs: Valeurs | Callable[[Any], Valeurs]  # ``(forme dans le signal, forme dans le texte)``, ou une fonction du retour qui les rend
    discriminant: str                    # ce qui distingue ce refus d'un autre : statut, raison ou manque
    manque: str | None = None            # le fait qui manque encore (xfail strict), ou ``None``


def valeurs_du_cas(cas: Cas, r: Any) -> Valeurs:
    return cas.valeurs(r) if callable(cas.valeurs) else cas.valeurs


def parametres(cas_list: list[Cas]):
    """Un paramètre par cas ; un cas dont le fait manque encore est un xfail strict qui ne passe qu'au vert du commit du fait."""
    return [pytest.param(c, id=c.nom, marks=[pytest.mark.xfail(strict=True, raises=AssertionError, reason=c.manque)] if c.manque else []) for c in cas_list]


def controler(cas: Cas, r: Any) -> None:
    absentes = valeurs_absentes(r, cas.chemin, valeurs_du_cas(cas, r), cas.discriminant)
    assert not absentes, f"{cas.nom} : le signal ne porte pas {absentes}"


def fidele(cas: Cas, r: Any) -> None:
    """La table dit ce que disait le texte : chaque valeur est dans le texte d'avant, refait des faits qu'il lisait (les faits publics de la fiche, sinon ceux du module)."""
    if cas.texte is None:
        return
    lus = faits_vus_par_le_modele(r) if cas.chemin == "F" else r.faits
    texte = norm(cas.texte(lus))
    pas_dites = [d for _, d in valeurs_du_cas(cas, r) if norm(d) not in texte]
    assert not pas_dites, f"{cas.nom} : le texte ne disait pas {pas_dites} : {texte}"


async def jouer(scenario: Callable[..., Any], *args: Any) -> Any:
    r = scenario(*args)
    return await r if hasattr(r, "__await__") else r


def etape_de_boissons(**en_plus):
    def opt(code, nom, alt=None, decl=()):
        return {"code": code, "nom": nom, "produit": nom, "alternative": alt, "declinaisons_du_produit": list(decl)}
    return {"id": "e1", "nom": "Boisson", "role": FO.ROLE_ETAPE, "options": [opt("B", "Coca Bouteille", 0), opt("C", "Coca Canette", 1), opt("F", "Fanta", 1)],
            "alternatives": [{"quantite": 1, "codes": ["B"]}, {"quantite": 3, "codes": ["C", "F"]}], **en_plus}


def formule_du_menu(etape, taille=None):
    article = {"formule": True, "groupes": [etape], "declinaisons": [{"code": "M", "taille": taille}]}
    ligne = {"nom": "Menu partage", "code": "M", "choix": [{"option_code": c, "nom": c, "quantite": 1, "choix": [], "etape": etape["id"]} for c in ("B", "C")]}
    return article, ligne



# ── les doubles des sources de l'allergie et de la carte (déplacés des tests du lot 7b-C3 : un module public, refus 6) ─────────────────────────────────

LIBELLES_ALLERGIE = {"lait": "du lait", "gluten": "du gluten"}


class SourceAllergie:
    """Ne connaît que le lait et le gluten ; ``halal`` est le seul régime étiqueté."""

    def __init__(self, halal: bool = True):
        self.halal = halal

    def signalement_dit(self, texte: str):
        return next((c for c, libelle in LIBELLES_ALLERGIE.items() if texte in (c, libelle)), None)  # le code, ou son libellé (le multiple redonne le libellé)

    def signalements_dits(self, texte: str):
        mots = [m.strip() for m in texte.split(" et ")]
        return [m for m in mots if m in LIBELLES_ALLERGIE], any(m not in LIBELLES_ALLERGIE for m in mots)

    def regime_code(self, texte: str):
        return "halal" if texte == "halal" else ("vegetarien" if texte == "végétarien" else None)


def fiche(signalements: list[str] | None, **plus: Any) -> dict[str, Any]:
    return {"nom": "Pizza reine", "declinaisons": [], "groupes": [], "signalements": None if signalements is None else [{"code": c} for c in signalements],
            "signalements_libelles": LIBELLES_ALLERGIE, **plus}


def option(nom: str, signalements: list[str] | None) -> dict[str, Any]:
    return {"nom": nom, "signalements": None if signalements is None else [{"code": c} for c in signalements], "signalements_du_nom": []}


LIBELLES_CARTE = {"gluten": "le gluten", "lait": "le lait", "oeufs": "l'œuf"}


class Carte:
    """Une carte d'essai : ses articles (``nom``, ``categorie``, ``signalements``, ``ingredients``, ``obligatoires``), sans réseau ; ``libelles`` : le nom dit de chaque code."""

    modes = ["sur_place"]

    def __init__(self, articles: list[dict[str, Any]], fiche: dict[str, Any] | None = None, libelles: dict[str, str] | None = None):
        self.articles, self._fiche, self.libelles = articles, fiche, LIBELLES_CARTE if libelles is None else libelles

    async def catalogue(self, mode):
        return {"articles": self.articles, "libelles": self.libelles}

    def signalement_dit(self, texte):
        return next((c for c, libelle in self.libelles.items() if texte.strip() in (c, libelle, libelle.split(" ", 1)[-1], libelle.lstrip("l'"))), None)

    def signalements_dits(self, texte):
        code = self.signalement_dit(texte)
        return ([code] if code else []), code is None

    def codes_d_un_nom(self, nom):
        return []

    async def chercher(self, texte):
        trouve = next((a for a in self.articles if a["nom"].casefold() == texte.casefold()), None)
        return SimpleNamespace(statut="RETENU" if trouve else "INTROUVABLE", faits={"retenu": trouve["nom"]} if trouve else {}, suggestion="", manque=None)

    async def article(self, nom, mode):
        return self._fiche


def article_de_carte(nom: str, signalements: list[str] | None, ingredients: list[str] | None = None, categorie: str = "pizzas") -> dict[str, Any]:
    return {"nom": nom, "categorie": categorie, "signalements": None if signalements is None else [{"code": c} for c in signalements], "ingredients": ingredients,
            "obligatoires": []}
