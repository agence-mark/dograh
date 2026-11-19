"""[.mark] Chantier Partie 1, lot 0 : les tests de garde (L00-08 à L00-11, L00-20).

Chacun est éprouvé sur un cas rouge connu (R7) par un test voisin ``..._rouge_...``.
"""

import re
import socket

import pytest

from api.tests.mark.partie_1.mots_de_restaurant import CATEGORIES_DE_PLATS, COMMUNS
from api.tests.mark.banc_a.commun import appel_de, base_essai, base_prete, faire_monde  # noqa: F401
from api.tests.mark.partie_1.conftest import AppelAUnFournisseurDeModele

# D29 : la taille des textes finaux de B9 plus 10 %, système plus outils d'une requête, en caractères. Mesuré le 19/11 sur le rendu de B9
# (`banc-b9/resultats/conv-*entier*final*.jsonl`, maximum de `car_systeme + car_outils` par étape) : accueil 8 309, commande 11 365,
# réservation 7 886, service 6 735.
PLAFONDS = {"accueil": 9139, "commande": 12501, "reservation": 8674, "service": 7408}
MOTS_DU_METIER = frozenset(COMMUNS) | frozenset(CATEGORIES_DE_PLATS)


def depasse_le_budget(etape: str, systeme: str, outils_json: str) -> bool:
    return len(systeme) + len(outils_json) > PLAFONDS[etape]


def noms_fautifs(noms) -> list[str]:
    """Un nom d'outil ou de case qui porte un mot de restaurant (E17, M1)."""
    return sorted(n for n in noms if set(re.split(r"[_\s]+", n.lower())) & MOTS_DU_METIER)


def test_budget_de_caracteres():
    """Les textes du gabarit (lot 2, version `gemma-4`) tiennent sous le plafond de chaque étape : rouge jusqu'au lot 2 (registre, § 2)."""
    from api.services.gabarits.restauration.textes import requetes_types  # créé au lot 2

    for etape, systeme, outils_json in requetes_types("gemma-4"):
        assert not depasse_le_budget(etape, systeme, outils_json), f"{etape} : {len(systeme) + len(outils_json)} > {PLAFONDS[etape]}"


def test_budget_rouge_sur_un_texte_gonfle():
    assert depasse_le_budget("commande", "x" * 12000, "y" * 600)
    assert not depasse_le_budget("commande", "x" * 11000, "y" * 600)


def _noms_du_catalogue() -> list[str]:
    from api.services.integrations.connectors.catalogue import connecteurs

    out = []
    for c in connecteurs():
        for a in c.actions:
            out.append(a.nom)
            out += [p.nom for p in a.parametres]
    return out


def test_noms_d_outils():
    noms = _noms_du_catalogue()
    assert noms, "catalogue vide : le test ne lit rien"
    assert noms_fautifs(noms) == []


def test_noms_d_outils_rouge_sur_un_nom_fautif():
    assert noms_fautifs(["ajouter", "ajouter_pizza", "choisir_le_menu"]) == ["ajouter_pizza", "choisir_le_menu"]


async def test_requetes_par_fiche(appel_de):
    """Mesure seule au lot 0 : les requêtes à la base d'un ajout d'article (75 en médiane attendues, banc A du 18/11) ; seuil au lot 5."""
    a = await appel_de()
    await a.jouer_la_fiche("une reine normale", {"ajouter": [{"article": "reine", "quantite": 1, "variante": "Normale"}]})  # lot 3 : par la fiche
    print(f"\n[lot 0] requêtes d'une fiche « ajouter un article » : {a.connexion.requetes} en {a.connexion.secondes * 1000:.0f} ms")
    assert a.connexion.requetes > 0, "le compteur ne compte rien : il n'est pas branché sur la connexion"


def test_aucun_prix_dans_a_dire():
    """Une fiche dont `a_dire` porte un montant n'est jamais dite telle quelle : codé au lot 6 (registre, § 2)."""
    from api.services.commande.parole import a_dire_dicible  # créé au lot 6

    assert not a_dire_dicible("C'est noté, ça fera douze euros cinquante.", executes=[], paroles=["une reine"])
    assert a_dire_dicible("C'est noté. Vous voulez autre chose ?", executes=[], paroles=["une reine"])


def test_aucun_appel_a_scaleway_dans_les_tests():
    with pytest.raises(AppelAUnFournisseurDeModele):
        socket.getaddrinfo("api.scaleway.ai", 443)
    socket.getaddrinfo("localhost", 80)  # le reste du réseau local n'est pas touché
