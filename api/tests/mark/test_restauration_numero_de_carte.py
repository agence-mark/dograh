"""[.mark] Module Restauration, SA-48 : le NUMÉRO DE CARTE (capacité C2), un champ facultatif du produit et de la formule.

| Test | Ce qu'il prouve |
|---|---|
| clé écrite | « J24 », « J 24 », « 046 », « 16B » : la clé de ce que la carte écrit ; un texte qui n'est pas un numéro n'en a pas |
| clés dites | « 46 », « le 46 », « numéro 46 », « quarante-six », « J24 », « J 24 », « j vingt-quatre », « 16b », « seize b », « deux J24 », les nombres en toutes lettres |
| pas un numéro | « 4 fromages », « Coca 33 cl », « menu 1 » : la recherche par le nom suit |
| moteur : exact | chaque forme dite retient LE bon plat ; « 46 » ne donne jamais « 47 » ; un numéro inconnu est INTROUVABLE (jamais un plat au hasard) |
| moteur : ambigu | deux plats au même numéro : AMBIGU ; « n 12 » : la lecture littérale (N12) d’abord, puis « numéro 12 » |
| carte sans numéro | l'index n'a pas de couche numéro : la recherche est celle d'avant (carte de référence) |
| import | le numéro va en base, revient dans la carte, un réimport ne change rien, un numéro illisible refuse la carte entière |
| recherche réelle | ``chercher_dans_la_liste`` (le chemin de ``voir_produit`` et ``ajouter``) retrouve par numéro ; formule numérotée comprise |
"""

from __future__ import annotations

import copy

import pytest

from api.db.bases_clients import recherche_liste_moteur as m
from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_moteur import chercher_dans_l_index, construire_index
from api.db.bases_clients.recherche_liste_numero import cle_ecrite, cles_dites
from api.db.bases_clients.restauration_carte import CarteInvalide, carte_du_restaurant, importer_carte
from api.db.bases_clients.restauration_client import chercher_dans_la_liste
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, resto  # noqa: F401

DITES = {
    "46": ["46"], "le 46": ["46"], "Le 46.": ["46"], "numéro 46": ["46"], "numero quarante-six": ["46"], "quarante six": ["46"], "quarante-six": ["46"],
    "J24": ["j24"], "j 24": ["j24"], "J-24": ["j24"], "j vingt-quatre": ["j24"], "le J24": ["j24"], "un J24": ["j24"], "deux J24": ["j24"],
    "16b": ["16b"], "16 B": ["16b"], "seize b": ["16b"], "un 16b": ["16b"], "le seize b": ["16b"],
    "cent un": ["101"], "deux cent cinq": ["205"], "deux zéro un": ["201"], "mille un": ["1001"], "dix-sept": ["17"], "soixante-dix": ["70"],
    "soixante et onze": ["71"], "quatre-vingts": ["80"], "quatre-vingt-dix-sept": ["97"], "vingt et un": ["21"], "un": ["1"], "j9": ["j9"],
    "n 12": ["n12", "12"],
}


def test_cle_ecrite():
    assert cle_ecrite("J24") == cle_ecrite("J 24") == cle_ecrite("j-24") == "j24"
    assert cle_ecrite("46") == cle_ecrite("046") == "46"
    assert cle_ecrite("16B") == cle_ecrite("16 b") == "16b"
    assert cle_ecrite("M2005") == "m2005"
    for pas_un_numero in ("", "Menu A", "poulet", None, "12345", "ABC12"):
        assert cle_ecrite(pas_un_numero) is None


@pytest.mark.parametrize("dit,attendu", DITES.items())
def test_cles_dites(dit, attendu):
    assert cles_dites(dit) == attendu


@pytest.mark.parametrize("dit", ["4 fromages", "quatre fromages", "Coca 33 cl", "menu 1", "pizza reine", "7 up", "", "le", "j24 poulet", "poulet 46", "une pizza"])
def test_ce_qui_n_est_pas_un_numero(dit):
    assert cles_dites(dit) == []


# --------------------------------------------------------------------------- le moteur

PLATS = [
    Element("poulet", "Poulet au curry", (), "Poulet", (), "46"),
    Element("boeuf", "Boeuf aux oignons", (), "Boeuf", (), "47"),
    Element("maki", "Maki saumon", (), "Japonais", (), "J24"),
    Element("nems", "Nems", (), "Entrées", (), "16b"),
    Element("shanghai", "Menu Shanghai", (), "Menus", (), "M2005"),
    Element("riz", "Riz cantonais", (), "Riz", (), "401"),
    Element("quatre", "4 fromages", (), "Pizzas"),
    Element("coca", "Coca-Cola", (), "Boissons", ("Canette 33 cl",)),
]


def _cherche(dit, elements=PLATS):
    return chercher_dans_l_index(construire_index(elements, ["Poulet"]), dit)


@pytest.mark.parametrize(
    "dit,attendu",
    [
        ("46", "poulet"), ("le 46", "poulet"), ("numéro 46", "poulet"), ("quarante-six", "poulet"), ("le quarante six", "poulet"),
        ("47", "boeuf"), ("quarante-sept", "boeuf"),
        ("J24", "maki"), ("J 24", "maki"), ("j vingt-quatre", "maki"), ("deux J24", "maki"),
        ("16b", "nems"), ("seize b", "nems"), ("16 B", "nems"),
        ("M2005", "shanghai"), ("m deux mille cinq", "shanghai"), ("quatre cent un", "riz"), ("quatre zéro un", "riz"),
    ],
)
def test_le_numero_retient_le_bon_plat(dit, attendu):
    r = _cherche(dit)
    assert (r["statut"], r["retenu"], r["couche"]) == ("RETENU", attendu, "numero"), r


@pytest.mark.parametrize("dit", ["48", "45", "quarante-huit", "J25", "J 23", "16", "16a", "seize c", "400", "1", "cent un"])
def test_un_numero_inconnu_ou_voisin_est_introuvable(dit):
    r = _cherche(dit)
    assert (r["statut"], r["retenu"], r["candidats"], r["raison"]) == ("INTROUVABLE", None, [], "numero_inconnu"), r


def test_le_nom_reste_cherche_par_le_nom():
    assert _cherche("4 fromages")["retenu"] == "quatre"
    assert _cherche("poulet au curry")["retenu"] == "poulet"
    assert _cherche("une canette de coca")["retenu"] == "coca"
    assert _cherche("Coca 33 cl")["retenu"] == "coca"


def test_deux_plats_au_meme_numero_donnent_une_question():
    elements = [Element("a", "Poulet", (), "", (), "12"), Element("b", "Boeuf", (), "", (), "12")]
    r = _cherche("le 12", elements)
    assert r["statut"] == "AMBIGU" and {c["id"] for c in r["candidats"]} == {"a", "b"} and r["question"]


def test_n_est_numero_ou_lettre_et_un_est_politesse_ou_chiffre():
    elements = [Element("a", "Poulet", (), "", (), "12"), Element("b", "Boeuf", (), "", (), "N12")]
    assert _cherche("N12", elements)["retenu"] == "b"  # la lecture littérale d'abord
    assert _cherche("n 12", elements)["retenu"] == "b"
    assert _cherche("12", elements)["retenu"] == "a"
    assert _cherche("n 12", elements[:1])["retenu"] == "a"  # sans plat N12, « n » était « numéro »
    unique = [Element("a", "Poulet", (), "", (), "1"), Element("b", "Boeuf", (), "", (), "12")]
    assert _cherche("un 12", unique)["retenu"] == "b"  # « un » politesse
    assert _cherche("un", unique)["retenu"] == "a"  # « un » seul est le chiffre


def test_un_plat_indisponible_n_est_pas_rendu_par_son_numero():
    index = construire_index(PLATS, [])
    r = chercher_dans_l_index(index, "46", exclus=frozenset({"poulet"}))
    assert r["statut"] == "INTROUVABLE"


def test_une_carte_sans_numero_n_a_pas_de_couche_numero():
    elements = [Element("marg", "Margherita", (), "Pizzas"), Element("quatre", "4 fromages", (), "Pizzas"), Element("coca", "Coca-Cola", (), "Boissons")]
    index = construire_index(elements, [])
    assert index.par_numero == {}
    for dit in ("quatre fromages", "4 fromages", "46", "margherita"):  # même résultat qu'avant : aucune ligne n'est ajoutée à la recherche
        avec = chercher_dans_l_index(index, dit)
        assert avec["couche"] != "numero" and "raison" not in avec, dit
    assert chercher_dans_l_index(index, "4 fromages")["retenu"] == "quatre"
    assert chercher_dans_l_index(index, "46")["statut"] == "INTROUVABLE"


def test_la_couche_numero_est_branchee_dans_le_moteur(monkeypatch):
    """Vu rouge : sans la couche, « le 46 » ne retrouve plus le plat."""
    monkeypatch.setattr(m, "_par_numero", lambda *a, **k: None)
    assert _cherche("le 46")["retenu"] != "poulet"


# --------------------------------------------------------------------------- l'import et la recherche réelle


def _carte_numerotee():
    carte = copy.deepcopy(CARTE)
    carte["produits"][0]["numero"] = "46"
    carte["produits"][1]["numero"] = "J24"
    carte["formules"] = [{"id": "F-MENU", "nom": "Menu du jour", "code_caisse": "MENU-JOUR", "prix": 1490, "categorie_id": None, "numero": "M2005", "lignes": []}]
    return carte


async def test_le_numero_va_en_base_revient_et_ne_change_rien_au_rejeu(resto):
    c, a = resto.c, resto.a
    carte = _carte_numerotee()
    await importer_carte(c, a, carte, "caisse")
    rendue = await carte_du_restaurant(c, a)
    par_id = {p["id"]: p for p in rendue["produits"]}
    assert par_id[carte["produits"][0]["id"]]["numero"] == "46"
    assert par_id[carte["produits"][1]["id"]]["numero"] == "J24"
    assert par_id[carte["produits"][2]["id"]]["numero"] is None  # le reste de la carte n'a pas de numéro
    assert next(f for f in rendue["formules"] if f["id"] == "F-MENU")["numero"] == "M2005"
    version = rendue["version"]
    rejoue = await importer_carte(c, a, carte, "caisse")
    assert (rejoue["ajoutes"], rejoue["changes"], rejoue["retires"]) == (0, 0, 0)
    assert (await carte_du_restaurant(c, a))["version"] == version


async def test_un_numero_change_ou_retire_au_reimport(resto):
    c, a = resto.c, resto.a
    carte = _carte_numerotee()
    await importer_carte(c, a, carte, "caisse")
    carte["produits"][0]["numero"] = "47"
    carte["produits"][1].pop("numero")
    bilan = await importer_carte(c, a, carte, "caisse")
    assert bilan["changes"] == 2
    par_id = {p["id"]: p for p in (await carte_du_restaurant(c, a))["produits"]}
    assert par_id[carte["produits"][0]["id"]]["numero"] == "47" and par_id[carte["produits"][1]["id"]]["numero"] is None


@pytest.mark.parametrize("mauvais", ["poulet", "Menu A", "12345", True, 4.5, ["46"]])
async def test_un_numero_illisible_refuse_la_carte_sans_rien_ecrire(resto, mauvais):
    carte = _carte_numerotee()
    carte["produits"][2]["numero"] = mauvais
    with pytest.raises(CarteInvalide):
        await importer_carte(resto.c, resto.a, carte, "caisse")
    assert (await carte_du_restaurant(resto.c, resto.a))["produits"] == []


async def test_la_recherche_reelle_trouve_par_le_numero(resto):
    c, a = resto.c, resto.a
    carte = _carte_numerotee()
    await importer_carte(c, a, carte, "caisse")
    p0, p1 = carte["produits"][0], carte["produits"][1]
    for dit in ("46", "le 46", "numéro 46", "quarante-six"):
        r = await chercher_dans_la_liste(c, "carte", dit, a)
        assert (r.statut, r.faits["retenu"]) == ("RETENU", p0["id"]), dit
    for dit in ("J24", "J 24", "j vingt-quatre"):
        assert (await chercher_dans_la_liste(c, "carte", dit, a)).faits["retenu"] == p1["id"], dit
    assert (await chercher_dans_la_liste(c, "carte", "M2005", a)).faits["retenu"] == "F-MENU"
    inconnu = await chercher_dans_la_liste(c, "carte", "47", a)
    assert inconnu.statut == "INTROUVABLE" and inconnu.faits["retenu"] is None and inconnu.faits["raison"] == "numero_inconnu"
    assert (await chercher_dans_la_liste(c, "carte", p0["nom"], a)).faits["retenu"] == p0["id"]  # le nom marche toujours
