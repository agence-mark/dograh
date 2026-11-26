"""[.mark] SA-55, lot 2 : défauts de l'agent Lusitalia (appels 2606 à 2609), avec la vraie carte de Lusitalia.

| Test | Ce qu'il prouve |
|---|---|
| supplément après la taille | « sénior, avec un œuf en plus » pose la taille ET le supplément (2606, 2609 : le supplément était jeté sans rien dire) ; un supplément qui n'existe pas est refusé, jamais tu |
| taille seule | « sénior » seul répond toujours à la taille, comme avant (C3, M120) |
| rangement dit | « deux pizzas » renvoie à ses rangements (« nous avons… : qu'est-ce que je vous mets ? »), jamais « je ne trouve pas » ; un rangement seul donne quelques noms, jamais toute la liste |

Lot 4 de la partie 1 (D49) : réécrit sur la fiche ; la taille et le supplément arrivent dans leurs cases (``variante``, ``supplements``), les
tournures (« sénior, avec un œuf en plus ») sont lues par le modèle (D1).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte
from api.services.commande import moteur, panier
from api.services.commande.moteur import Reglages
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.caisse.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark import commande_sur_la_fiche as F
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

CARTE = json.loads((Path(__file__).parent / "cartes_essai" / "carte-lusitalia.json").read_text(encoding="utf-8"))


@pytest.fixture
async def lusitalia(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Lusitalia')")
        site = await c.fetchval(
            "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'lusi', 'Lusitalia', 'Europe/Paris' FROM mark.entreprise RETURNING id"
        )
        for jour in range(1, 8):
            for ouverture, fermeture in (("11:00", "14:00"), ("18:00", "22:30")):
                await c.execute(
                    "INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, $3::text::time, $4::text::time)", site, jour, ouverture, fermeture
                )
        await c.execute("INSERT INTO mark.resto_reglage (site_id, prefixe_numero_court, moyens_paiement) VALUES ($1, 'L', '{carte,especes}')", site)
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, delai_annonce) VALUES ($1, 'emporter', 20)", site)
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            await importer_carte(c, site, CARTE, "caisse")
            yield SimpleNamespace(c=c, a=site, base=base_prete)
    finally:
        await c.close()


class Appel:
    def __init__(self, lieu):
        self.source = SourceClasseur(lieu.c, Lieu(lieu.base, lieu.a, 1), nom_prise="test", prise=PriseTest())
        self.p = panier.nouveau()
        self.regles = Reglages(vente_en_plus=False)

    async def a_emporter(self):
        await moteur.choisir_mode(self.source, self.p, self.regles, "emporter")
        return self

    async def ajouter(self, *articles):
        return await F.ajouter(self.source, self.p, self.regles, *articles)

    def lignes(self):
        return [(l["nom"], [c["nom"] for c in l["choix"]]) for l in self.p["lignes"]]


@pytest.mark.parametrize("oeuf", ["œuf", "oeuf"])
async def test_le_supplement_dit_apres_la_taille_est_pose(lusitalia, oeuf):
    a = await Appel(lusitalia).a_emporter()
    r = await a.ajouter(A("Carbonara", variante="sénior", supplements=[oeuf]))
    assert r.statut == "OK", r
    assert a.lignes() == [("Carbonara Sénior", ["Oeuf"])]
    assert r.faits["total"] == 950 + 100


async def test_un_supplement_qui_n_existe_pas_apres_la_taille_est_refuse_jamais_tu(lusitalia):
    a = await Appel(lusitalia).a_emporter()
    r = await a.ajouter(A("Carbonara", variante="sénior", supplements=["caviar"]))
    assert r.statut == "HORS_CARTE", r
    assert a.p["lignes"] == []


async def test_la_taille_seule_repond_toujours_a_la_taille(lusitalia):
    a = await Appel(lusitalia).a_emporter()
    r = await a.ajouter(A("Reine", variante="sénior"))
    assert r.statut == "OK", r
    assert a.lignes() == [("Reine Sénior", [])]


@pytest.mark.parametrize("articles", [A("pizzas", 2), A("pizzas")])
async def test_un_rangement_dit_renvoie_a_ses_rangements_jamais_je_ne_trouve_pas(lusitalia, articles):
    a = await Appel(lusitalia).a_emporter()
    r = await a.ajouter(articles)
    assert (r.statut, r.manque) == ("INCOMPLETE", "articles"), r
    # C7 B12 (T9, rouge depuis 9cd42f70, C7a) : « Nous avons… : qu'est-ce que je vous mets ? » est sorti du retour (décision d'Evan 25/11 8 h 45, le modèle parle) ;
    # les rangements sont dans les faits, d'où le texte d'avant se refait (« pas juste une suppression ») ; C7 B9 : le catalogue parti, les rangements suffisent (« Nous avons » + rangements)
    rangements = r.faits.get("rangements") or []
    assert r.suggestion == "" and "Pizzas Classiques" in rangements and "Salades" not in rangements, r.faits
    assert "Bambino" not in rangements                                      # les rangements, pas leurs articles un par un
    assert a.p["lignes"] == []


async def test_un_seul_rangement_donne_quelques_noms_jamais_toute_la_liste(lusitalia):
    a = await Appel(lusitalia).a_emporter()
    r = await a.ajouter("salade")
    assert (r.statut, r.manque) == ("INCOMPLETE", "articles"), r
    salades = [p["nom"] for p in CARTE["produits"] if p["categorie_id"] == "salades"]
    dites = [s for s in salades if s in (r.faits.get("exemples") or [])]  # C7 B12 (T9, C7a 9cd42f70) : les exemples en faits, le modèle les dit (Evan 25/11 8 h 45)
    assert r.suggestion == "" and 1 <= len(dites) <= 3 and len(salades) > 3, (r.faits, salades)
