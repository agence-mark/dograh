"""[.mark] Module Restauration, lot 4 : le moteur de recherche dans une liste fermée (couches, options, zéro faux sûr).

| Test | Ce qu'il prouve |
|---|---|
| exact, nettoyage | casse, accents, ponctuation, pluriel, petits mots et politesse ne changent rien |
| « canette de Coca » | RETENU, contenant lu comme option (et la taille) ; le nom de base est retenu, ses variantes ne le sont pas |
| contenu | un mot d'un nom retient seulement s'il est seul à le porter ; sinon AMBIGU avec 2 ou 3 choix et la question |
| même nom, deux rangements | AMBIGU, la question dit le rangement ; jamais choisi au hasard |
| lettres, son | une faute proche est retenue seulement si elle est très proche ; un son identique retient ; un son voisin propose |
| sens | propose seulement, jamais retenu même à 1,0 ; éteint par défaut |
| liste qui n'est pas une carte | la même recherche sert une liste de marques d'appareils |
| INTROUVABLE | les plus proches sont rendus, rien d'inventé ; mot absent : liste vide |
| vitesse | moins de 50 ms par recherche sur 82 éléments (index préparé) |
| branchement | ``poser_moteur`` : ``recherche_liste.chercher`` est le vrai moteur ; par la vraie fonction ``chercher_dans_la_liste`` aussi (R1) |
| chaque couche vue rouge | une couche retirée change le résultat attendu |
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from api.db.bases_clients import recherche_liste, recherche_liste_moteur as m
from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_moteur import Reglages, chercher_dans_l_index, construire_index

CARTE_ESSAI = Path(__file__).parent / "cartes_essai" / "carte-reference.json"


def _carte_essai():
    c = json.loads(CARTE_ESSAI.read_text(encoding="utf-8"))
    rangement = {x["id"]: x["nom"] for x in c["categories"]}
    elements = [Element(p["id"], p["nom"], (), rangement.get(p["categorie_id"], ""), tuple(d["nom"] for d in p["declinaisons"])) for p in c["produits"]]
    return elements, list(rangement.values())


BOISSONS = [
    Element("coca", "Coca-Cola", (), "Boissons", ("Canette 33 cl", "Bouteille 1,5 l")),
    Element("coca0", "Coca-Cola Zéro", (), "Boissons", ("Canette 33 cl",)),
    Element("fo", "Fanta Orange", (), "Boissons"),
    Element("fc", "Fanta Citron", (), "Boissons"),
    Element("eau", "Eau plate", ("eau minérale",), "Boissons"),
    Element("tira", "Tiramisu", (), "Desserts"),
    Element("marg", "Margherita", (), "Pizzas"),
]


def _chercher(elements, texte, **reglages):
    return chercher_dans_l_index(construire_index(elements, reglages.pop("categories", ())), texte, Reglages(**reglages))


@pytest.mark.parametrize("dit", ["Tiramisu", "TIRAMISU !", "  tiramisu ", "tiramisus", "je voudrais un tiramisu s'il vous plaît", "Un tiramisu, svp", "Tiramisù"])
def test_le_nettoyage_ne_change_rien(dit):
    r = _chercher(BOISSONS, dit)
    assert (r["statut"], r["retenu"], r["couche"]) == ("RETENU", "tira", "exact")


def test_canette_de_coca_est_retenu_avec_son_contenant_et_sa_taille():
    r = _chercher(BOISSONS, "canette de Coca")
    assert (r["statut"], r["retenu"]) == ("RETENU", "coca") and r["options"] == {"contenant": "canette", "variante": "Canette 33 cl"} or r["options"].get("contenant") == "canette"
    r = _chercher(BOISSONS, "une bouteille de Coca 33 cl")
    assert (r["statut"], r["retenu"]) == ("RETENU", "coca") and r["options"]["taille"] == "33cl" and r["options"]["contenant"] == "bouteille"
    r = _chercher(BOISSONS, "canette de coca 33 cl")
    assert r["retenu"] == "coca" and r["options"] == {"contenant": "canette", "taille": "33cl", "variante": "Canette 33 cl"}
    # le nom de base est retenu, sa variante ne l'est que si elle est dite
    assert _chercher(BOISSONS, "coca")["retenu"] == "coca" and _chercher(BOISSONS, "coca zéro")["retenu"] == "coca0"
    assert _chercher(BOISSONS, "canette de coca zero")["retenu"] == "coca0"


def test_un_mot_commun_a_deux_noms_pose_la_question_avec_deux_ou_trois_choix():
    r = _chercher(BOISSONS, "fanta")
    assert r["statut"] == "AMBIGU" and r["retenu"] is None
    assert {c["id"] for c in r["candidats"]} == {"fo", "fc"} and r["question"] == "Vous voulez dire : Fanta Orange ou Fanta Citron ?"
    trois = BOISSONS + [Element("fl", "Fanta Limon")]
    r = _chercher(trois, "fanta")
    assert len(r["candidats"]) == 3 and "Fanta Limon" in r["question"] and r["question"].count(",") == 1 and " ou " in r["question"]
    assert len(_chercher(trois + [Element("fz", "Fanta Zéro")], "fanta")["candidats"]) == 3  # jamais plus de trois


def test_un_meme_nom_dans_deux_rangements_est_ambigu_et_la_question_dit_lequel():
    deux = BOISSONS + [Element("marg2", "Margherita", (), "Calzones")]
    r = _chercher(deux, "margherita")
    assert r["statut"] == "AMBIGU" and r["retenu"] is None and {c["id"] for c in r["candidats"]} == {"marg", "marg2"}
    assert r["question"] == "Vous voulez dire : Margherita (Pizzas) ou Margherita (Calzones) ?"


def test_une_faute_tres_proche_est_retenue_une_faute_plus_large_est_proposee():
    assert _chercher(BOISSONS, "tiramissu")["retenu"] == "tira"  # lettres : très proche
    r = _chercher(BOISSONS, "margarita")  # plus large : proposé, jamais retenu
    assert (r["statut"], r["retenu"], r["candidats"][0]["id"]) == ("AMBIGU", None, "marg")
    assert r["question"] == "Vous voulez dire : Margherita ?"


def test_un_son_identique_retient_un_son_voisin_propose():
    marques = [Element("godin", "Godin"), Element("invicta", "Invicta"), Element("jotul", "Jøtul", ("jotul",)), Element("deville", "Deville"), Element("supra", "Supra")]
    assert _chercher(marques, "godin")["retenu"] == "godin"
    r = _chercher(marques, "gaudin")  # même son, lettres éloignées : retenu par le son
    assert (r["statut"], r["retenu"], r["couche"]) == ("RETENU", "godin", "son")
    sans_son = _chercher(marques, "gaudin", couche_son=False)  # sans la couche son : seulement une proposition, jamais retenu
    assert sans_son["retenu"] is None and all(c["couche"] != "son" for c in sans_son["candidats"])
    voisin = _chercher(marques, "yotul")  # son voisin : propose, ne retient pas
    assert voisin["retenu"] is None and voisin["candidats"][0]["id"] == "jotul"


def test_le_sens_propose_seulement_il_ne_retient_jamais_et_il_est_eteint_par_defaut():
    appels = []

    def sens(texte, elements):
        appels.append(texte)
        return [("tira", 1.0), ("eau", 0.95)]

    index = construire_index(BOISSONS)
    eteint = chercher_dans_l_index(index, "le dessert italien au café", Reglages(), sens=sens)
    assert appels == [] and eteint["statut"] == "INTROUVABLE"  # éteint : jamais appelé
    allume = chercher_dans_l_index(index, "le dessert italien au café", Reglages(couche_sens=True), sens=sens)
    assert appels and allume["statut"] == "AMBIGU" and allume["retenu"] is None  # il propose, à confirmer
    assert {c["id"] for c in allume["candidats"][:2]} == {"tira", "eau"} and all(c["couche"] == "sens" for c in allume["candidats"][:2])
    assert max(c["score"] for c in allume["candidats"]) < 0.90


def test_un_mot_absent_n_est_pas_invente_les_plus_proches_sont_rendus():
    r = _chercher(BOISSONS, "kebab")
    assert (r["statut"], r["retenu"], r["candidats"]) == ("INTROUVABLE", None, [])
    r = _chercher(BOISSONS, "tarte")
    assert r["statut"] == "INTROUVABLE" and r["retenu"] is None
    for vide in ("", "   ", "de la", "s'il vous plaît"):
        assert _chercher(BOISSONS, vide)["statut"] == "INTROUVABLE", vide


def test_un_nom_de_plus_ne_retient_pas_un_autre_produit():
    r = _chercher(BOISSONS, "tiramisu et margherita")
    assert r["retenu"] is None and r["statut"] in ("AMBIGU", "INTROUVABLE")


def test_un_element_retire_n_est_jamais_rendu():
    index = construire_index(BOISSONS)
    r = chercher_dans_l_index(index, "tiramisu", exclus=frozenset({"tira"}))
    assert r["retenu"] is None and "tira" not in [c["id"] for c in r["candidats"]]


def test_les_mots_de_categorie_sont_ecartes_sans_etre_la_seule_lecture():
    elements = [Element("a", "Reine", (), "Pizzas"), Element("b", "Pizza du chef", (), "Pizzas")]
    assert _chercher(elements, "pizza reine", categories=["Pizzas"])["retenu"] == "a"
    assert _chercher(elements, "pizza du chef", categories=["Pizzas"])["retenu"] == "b"  # le mot de catégorie fait partie du nom : exact
    assert _chercher(elements, "pizza", categories=["Pizzas"])["retenu"] is None  # il ne reste rien à chercher : jamais le premier venu


def test_les_synonymes_servent_de_noms():
    assert _chercher(BOISSONS, "eau minérale")["retenu"] == "eau" and _chercher(BOISSONS, "eau plate")["retenu"] == "eau"


def test_la_meme_recherche_sert_la_carte_d_essai_en_moins_de_50_ms():
    elements, categories = _carte_essai()
    index = construire_index(elements, categories)
    for dit in ("canette de coca", "une margherita", "tiramisu", "fanta", "napoli", "4 formaggi", "bouteille de coca 33 cl", "kebab", "orangina s'il vous plait"):
        debut = time.perf_counter()
        chercher_dans_l_index(index, dit)
        assert time.perf_counter() - debut < 0.05, dit
    assert chercher_dans_l_index(index, "canette de Coca")["statut"] == "RETENU"
    assert chercher_dans_l_index(index, "4 formaggi")["statut"] == "AMBIGU"  # le même nom deux fois dans la carte d'essai


def test_le_moteur_remplace_le_moteur_minimal_par_poser_moteur():
    elements, _ = _carte_essai()
    # le moteur minimal ne retenait que l'exact : « canette de coca » n'existait pas pour lui
    assert recherche_liste._moteur is m.moteur_par_defaut
    assert recherche_liste.chercher(elements, "canette de Coca")["statut"] == "RETENU"
    assert set(recherche_liste.chercher(elements, "canette de Coca")) >= {"statut", "retenu", "candidats"}  # même forme de retour
    assert recherche_liste._minimal(elements, "canette de Coca")["statut"] != "RETENU"  # le cas rouge : sans le moteur, rien
    recherche_liste.poser_moteur(recherche_liste._minimal)
    try:
        assert recherche_liste.chercher(elements, "canette de Coca")["statut"] != "RETENU"
    finally:
        m.installer()
    assert recherche_liste.chercher(elements, "canette de Coca")["statut"] == "RETENU"


# --------------------------------------------------------------------------- par la vraie fonction du comptoir (R1)

from api.db.bases_clients.restauration_carte import importer_carte  # noqa: E402
from api.db.bases_clients.restauration_client import chercher_dans_la_liste  # noqa: E402
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: E402, F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, resto  # noqa: E402, F401


async def test_par_la_vraie_fonction_canette_de_coca_est_retenu(resto):  # noqa: F811
    await importer_carte(resto.c, resto.a, CARTE, "caisse")
    r = await chercher_dans_la_liste(resto.c, "carte", "une canette de Coca", resto.a)
    assert r.statut == "RETENU" and r.faits["options"].get("contenant") == "canette"
    assert (await chercher_dans_la_liste(resto.c, "carte", "kebab", resto.a)).statut == "INTROUVABLE"
