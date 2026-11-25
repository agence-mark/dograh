"""[.mark] Lot 7b-C7a, aides publiques du test de garde du signal : ce que le modèle lit d'un retour du module, et la comparaison « le signal porte la valeur ».

Le signal est le statut du module, ce qui manque et les faits bruts, tels que le modèle les reçoit :
- ``F`` (la fiche) : les faits publics du refus, puis la copie allégée de ``enveloppe_legere.pour_le_modele`` (``outil.py``) ;
- ``L`` (lire) : les faits bruts (``lire.py``), seuls le panier et le prix à dire sont retirés ;
- ``Rv`` (réservation) : ``resultat_public`` de la porte commune.
Une valeur est comparée ENTIÈRE (``norm``), jamais comme sous-chaîne : « Oise » n'est pas trouvé dans « Val-d'Oise ». Un nombre se compare par ses formes
(``valeurs_des_faits`` : « 1500 », « quinze euros »). Un drapeau vrai (``panier_vide: true``) compte pour son nom.
"""

from __future__ import annotations

from typing import Any

from api.services.actions_communes import porte_commune as PC
from api.services.commande.briques import formule as FO
from api.services.actions_communes.barriere_des_chiffres import valeurs_des_faits
from api.services.actions_communes.enveloppe_legere import pour_le_modele
from api.services.actions_communes.forme import norm
from api.services.commande.porte import faits_vus_par_le_modele
from api.services.reservation.porte import FAITS_GARDES_PAR_LA_RESERVATION

CHEMINS = ("F", "L", "Rv")


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


def signal(r: Any, chemin: str, operation: str = "fiche") -> Any:
    """Ce que le modèle lit du retour ``r`` d'un module, selon le chemin par lequel il le lit."""
    if chemin == "F":
        publics = faits_vus_par_le_modele(r)
        fait = {"statut_du_module": r.statut, "manque": r.manque, "faits": publics}
        return pour_le_modele({"resultats": [fait], "faits": {"refus_de_la_fiche": [fait]}})
    if chemin == "L":
        return {"statut_du_module": r.statut, "manque": r.manque, "faits": {k: v for k, v in r.faits.items() if k not in ("panier", "prix_a_dire")}}
    if chemin == "Rv":
        return PC.resultat_public(operation, r, FAITS_GARDES_PAR_LA_RESERVATION)
    raise ValueError(chemin)


def valeurs_absentes(r: Any, chemin: str, valeurs: list[tuple[str, str]], discriminant: str) -> list[str]:
    """Ce que le signal ne porte pas : le discriminant (statut, raison ou manque qui distingue ce refus d'un autre) puis chaque valeur que le texte disait."""
    vus = feuilles(signal(r, chemin))
    absentes = [] if norm(discriminant) in vus else [f"discriminant « {discriminant} »"]
    return absentes + [dans_le_signal for dans_le_signal, _ in valeurs if norm(dans_le_signal) not in vus]


def etape_de_boissons(**en_plus):
    def opt(code, nom, alt=None, decl=()):
        return {"code": code, "nom": nom, "produit": nom, "alternative": alt, "declinaisons_du_produit": list(decl)}
    return {"id": "e1", "nom": "Boisson", "role": FO.ROLE_ETAPE, "options": [opt("B", "Coca Bouteille", 0), opt("C", "Coca Canette", 1), opt("F", "Fanta", 1)],
            "alternatives": [{"quantite": 1, "codes": ["B"]}, {"quantite": 3, "codes": ["C", "F"]}], **en_plus}


def formule_du_menu(etape, taille=None):
    article = {"formule": True, "groupes": [etape], "declinaisons": [{"code": "M", "taille": taille}]}
    ligne = {"nom": "Menu partage", "code": "M", "choix": [{"option_code": c, "nom": c, "quantite": 1, "choix": [], "etape": etape["id"]} for c in ("B", "C")]}
    return article, ligne

