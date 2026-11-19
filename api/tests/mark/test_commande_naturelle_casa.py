"""[.mark] SA-50 (appel 2598) : la phrase la plus courante d'une pizzeria, prise en entier, avec la vraie carte de Casa Italia.

« Bonsoir, c'est pour une livraison : deux reines grandes taille, dont une sans champignons, et une quatre fromages normale. »

| Test | Ce qu'il prouve |
|---|---|
| M116 | ``choisir_mode`` sans articles dit que le panier est vide et demande les plats |
| M117 | chaque article d'une phrase est traité ; un introuvable ne fait jamais perdre les autres ; le pluriel (« reines ») est lu |
| M118 | les mots de taille usuels (« grande », « petite », « XL »…) se rapprochent de l'ordre des déclinaisons ; jamais deviné quand c'est ambigu |
| M119 | « deux X dont une sans Y » : deux lignes ; le ``sans`` de l'appel va au bon article ; aucune moitié inventée |
| M120 | une réponse de choix va à la question en attente ; une taille dite départage deux homonymes |

Lot 4 de la partie 1 (D49) : réécrit sur la fiche. Le modèle découpe la phrase en articles (D1) : chaque article arrive structuré
(nom, quantité, variante dite, retraits) ; le code retrouve les noms (pluriel, homonymes) et les tailles dites en mots usuels.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_ecran import poser_les_synonymes
from api.services.commande import moteur, panier, tailles
from api.services.commande.moteur import Reglages
from api.services.restauration.appel import Lieu
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark import commande_sur_la_fiche as F
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

DOSSIER = Path(__file__).parent / "cartes_essai"
CARTE_CASA = json.loads((DOSSIER / "carte-casa-italia.json").read_text(encoding="utf-8"))
SYNONYMES_CASA = {k: v for k, v in json.loads((DOSSIER / "synonymes-casa-italia.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
# « une Reine » donne la Regina en production (synonyme posé à l'écran) : le même synonyme ici.
SYNONYMES_CASA["P-PIZZAS-TOMATE-REGINA"] = ["reine", "la reine", "pizza reine"]
# « deux reines grandes taille, dont une sans champignons, et une quatre fromages normale », rangée par le modèle dans la case ``ajouter``
ARTICLES_2598 = (A("reines", 1, "grandes taille"), A("reines", 1, "grandes taille", sans=["champignons"]), A("quatre fromages", 1, "normale"))


@pytest.fixture
async def casa(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Casa')")
        site = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'casa', 'Casa', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        for jour in range(1, 8):
            for ouverture, fermeture in (("11:00", "14:00"), ("18:00", "22:30")):
                await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, $3::text::time, $4::text::time)", site, jour, ouverture, fermeture)
        await c.execute("INSERT INTO mark.resto_reglage (site_id, prefixe_numero_court, moyens_paiement) VALUES ($1, 'C', '{carte,especes}')", site)
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, delai_annonce) VALUES ($1, 'emporter', 20)", site)
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type) VALUES ($1, 'livraison')", site)
        zone = await c.fetchval(
            "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, minimum, frais, delai) VALUES ($1, 'Senlis', 'communes', '{60612}', 0, 0, 30) RETURNING id", site
        )
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            await importer_carte(c, site, CARTE_CASA, "caisse")
            for ref, synonymes in SYNONYMES_CASA.items():
                assert await poser_les_synonymes(c, site, ref, synonymes, "essai")
            yield SimpleNamespace(c=c, a=site, base=base_prete, zone=zone)
    finally:
        await c.close()


class Appel:
    def __init__(self, casa):
        self.source = SourceClasseur(casa.c, Lieu(casa.base, casa.a, 1), nom_prise="test", prise=PriseTest())
        self.p = panier.nouveau()
        self.regles = Reglages(vente_en_plus=False)

    async def a_emporter(self):
        await moteur.choisir_mode(self.source, self.p, self.regles, "emporter")
        return self

    async def ajouter(self, *articles):
        return await F.ajouter(self.source, self.p, self.regles, *articles)

    async def repondre(self, choix):
        return await F.repondre(self.source, self.p, self.regles, choix)

    def lignes(self):
        return sorted((l["nom"], l["quantite"], tuple(sorted(l["retires"]))) for l in self.p["lignes"])


def prix(ref: str, taille: str) -> int:
    produit = next(p for p in CARTE_CASA["produits"] if p["id"] == ref)
    return next(d["prix"] for d in produit["declinaisons"] if d["nom"] == taille)


REGINA, FORMAGGI = "P-PIZZAS-TOMATE-REGINA", "P-PIZZAS-TOMATE-4-FORM"
LIGNES_2598 = sorted([("4 Formaggi Normale", 1, ()), ("Regina Mega", 1, ()), ("Regina Mega", 1, ("champignons",))])


# --------------------------------------------------------------------------- #
# M116 : choisir_mode ne perd jamais les articles dits, et dit quand rien n'est pris
# --------------------------------------------------------------------------- #




async def test_m116_le_mode_seul_dit_que_rien_n_est_pris(casa):
    a = Appel(casa)
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    assert r.manque == "zone" and r.faits.get("panier_vide") is True, r
    r = await moteur.verifier_adresse(a.source, a.p, a.regles, "12 rue de Beauvais, 60300 Senlis")
    assert r.statut == "RETENU" and r.manque == "articles" and r.faits.get("panier_vide") is True, r


# --------------------------------------------------------------------------- #
# M117, M119 : la phrase de 2598 en un seul ajouter
# --------------------------------------------------------------------------- #


async def test_m117_la_phrase_de_2598_donne_trois_lignes_et_le_bon_total(casa):
    a = await Appel(casa).a_emporter()
    r = await a.ajouter(*ARTICLES_2598)
    assert r.statut == "OK", r
    assert a.lignes() == LIGNES_2598, a.p["lignes"]
    assert r.faits["total"] == 2 * prix(REGINA, "Mega") + prix(FORMAGGI, "Normale"), r


# test_m117_la_phrase_redite_par_le_modele_en_grande : supprimé au lot 4 (D49), même sens que la phrase de 2598 rangée dans la fiche : test_m117_la_phrase_de_2598_donne_trois_lignes_et_le_bon_total.


async def test_m117_un_introuvable_ne_fait_jamais_perdre_les_autres(casa):
    a = await Appel(casa).a_emporter()
    retours = [await moteur.ajouter_un_article(a.source, a.p, a.regles, x)
               for x in (A("margherita", 2, "grandes"), A("pizza schtroumpf"), A("quatre fromages", 1, "normale"))]
    assert [r.statut for r in retours] == ["OK", "INTROUVABLE", "OK"], retours  # chaque article a son résultat (la porte les rend tous)
    assert a.lignes() == [("4 Formaggi Normale", 1, ()), ("Margherita Mega", 2, ())]


async def test_m117_deux_margherita_grandes(casa):
    a = await Appel(casa).a_emporter()
    r = await a.ajouter(A("margherita", 2, "grandes"))
    assert r.statut == "OK", r
    assert a.lignes() == [("Margherita Mega", 2, ())]


async def test_m117_une_calzone_petite_et_deux_reines(casa):
    a = await Appel(casa).a_emporter()
    r = await a.ajouter(A("calzone", 1, "petite"), A("reines", 2))
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.manque == "taille", r  # la Regina attend sa taille, la Calzone est prise
    assert ("Calzone Normale", 1, ()) in a.lignes()
    r = await a.repondre("la grande")
    assert r.statut == "OK", r
    assert a.lignes() == [("Calzone Normale", 1, ()), ("Regina Mega", 2, ())]


async def test_m119_trois_pizzas_dont_deux_sans(casa):
    a = await Appel(casa).a_emporter()
    r = await a.ajouter(A("pizzas reine", 1, "normales"), A("pizzas reine", 2, "normales", sans=["champignons"]))
    assert r.statut == "OK", r
    assert a.lignes() == [("Regina Normale", 1, ()), ("Regina Normale", 2, ("champignons",))]


async def test_m119_deux_x_une_sans_y(casa):
    a = await Appel(casa).a_emporter()
    r = await a.ajouter(A("margherita", 1, "normales"), A("margherita", 1, "normales", sans=["olives"]))
    assert r.statut == "OK", r
    assert a.lignes() == [("Margherita Normale", 1, ()), ("Margherita Normale", 1, ("olives",))]


# --------------------------------------------------------------------------- #
# M118 : les mots de taille usuels
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("dit", ["une grande", "en grande", "grande taille", "la grande", "une large", "XL", "Mega"])
async def test_m118_la_taille_dite_en_mots_usuels_repond_a_la_question(casa, dit):
    a = await Appel(casa).a_emporter()
    assert (await a.ajouter("regina")).manque == "taille"
    r = await a.repondre(dit)
    assert r.statut == "OK", r
    assert a.lignes() == [("Regina Mega", 1, ())]


@pytest.mark.parametrize("dit", ["une petite", "la petite", "normale"])
async def test_m118_la_petite_est_la_plus_petite(casa, dit):
    a = await Appel(casa).a_emporter()
    await a.ajouter("regina")
    r = await a.repondre(dit)
    assert r.statut == "OK", r
    assert a.lignes() == [("Regina Normale", 1, ())]


async def test_m118_moyenne_avec_deux_tailles_redemande(casa):
    a = await Appel(casa).a_emporter()
    await a.ajouter("regina")
    r = await a.repondre("moyenne")
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.manque == "taille", r


def _d(*noms_prix):
    return [{"nom": n, "prix": p, "vendable": True, "rupture": False, "code": n} for n, p in noms_prix]


def test_m118_la_table_standard_et_l_ordre_des_declinaisons():
    trois = _d(("S", 900), ("M", 1200), ("L", 1500))
    deux = _d(("Normale", 1090), ("Mega", 1890))
    assert tailles.declinaison_par_mot(trois, "grande")["nom"] == "L"
    assert tailles.declinaison_par_mot(trois, "moyenne")["nom"] == "M"
    assert tailles.declinaison_par_mot(trois, "petites")["nom"] == "S"
    assert tailles.declinaison_par_mot(deux, "moyenne") is None  # deux tailles : « moyenne » est un doute, on demande
    assert tailles.declinaison_par_mot(deux, "XL")["nom"] == "Mega"
    assert tailles.declinaison_par_mot(_d(("A", 1000), ("B", 1000)), "grande") is None  # même prix : aucun ordre sûr
    assert tailles.declinaison_par_mot(_d(("Unique", 1000)), "grande") is None
    assert tailles.declinaison_par_mot(deux, "jambon") is None
    # Réglable : une surcouche ajoute ou retire un mot.
    assert tailles.declinaison_par_mot(deux, "familiale", {"familiale": "plus_grande"})["nom"] == "Mega"
    assert tailles.declinaison_par_mot(deux, "grande", {"grande": None}) is None


# --------------------------------------------------------------------------- #
# M120 : la réponse de choix va à la question en attente ; la taille départage les homonymes
# --------------------------------------------------------------------------- #


# test_m120_la_phrase_renvoyee_avec_le_choix_repond_a_la_question : supprimé au lot 4 (D49), la réponse à la question passe par ``reponse`` et ``ajouter`` additionne (E3) ; sens repris par partie_1/test_l03_porte.py::test_reponse_manquante_refusee et test_m118_la_taille_dite_en_mots_usuels_repond_a_la_question.


@pytest.mark.parametrize("dit", [A("4 fromages", 1, "normale"), A("quatre fromages", 1, "normale"), A("quatre fromages", 1, "grande")])
async def test_m120_une_taille_dite_departage_les_homonymes(casa, dit):
    a = await Appel(casa).a_emporter()
    r = await a.ajouter(dit)
    assert r.statut == "OK", r
    assert [l["ref"] for l in a.p["lignes"]] == [FORMAGGI]


async def test_m120_quatre_fromages_seule_reste_un_vrai_doute(casa):
    a = await Appel(casa).a_emporter()
    r = await a.ajouter("quatre fromages")
    assert r.statut == "AMBIGU", r
    assert a.p["lignes"] == []


# test_m120_l_homonyme_renvoye_avec_sa_taille_en_choix : supprimé au lot 4 (D49), la taille dite arrive dans ``variante`` ; sens repris par test_m120_une_taille_dite_departage_les_homonymes.
