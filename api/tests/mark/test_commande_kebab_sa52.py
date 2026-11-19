"""[.mark] SA-52 (appels 2602, 2604) : la commande d'un kebab prise en entier, avec la vraie carte du Kebab de démo.

Mécanismes COMMUNS (aucun mot de la carte dans le code), prouvés sur une carte à choix multiples (C5 : un tacos à n viandes) :

| Test | Ce qu'il prouve |
|---|---|
| D1 | les mots qui sont des OPTIONS du produit cité juste avant (« tacos 2 viandes kebab et chicken, sauce algérienne ») ne deviennent pas des articles |
| D2 | une option se trouve par ses synonymes (surcouche, comme les produits) : « poulet » pour « Chicken » |
| D3 | les nombres dits en lettres se lisent des deux côtés (« tacos deux viandes » = « Tacos 2 viandes ») ; ``modifier`` retrouve la ligne |
| D4 | un choix dit avec un article encore en doute est gardé, et posé quand l'article est trouvé |
| D5 | un mode refusé ne fait pas perdre les articles dits ; une adresse vérifiée sans mode pose le mode qui en exige une |
| D6 | « c'est noté pour X, mais … ? » est une affirmation (retenue quand rien n'est fait) ; « introuvable » dit « pas fait » |
| D7 | la question d'un choix est une phrase dite (« Quelle taille pour votre Oasis : 33 centilitres… ? »), pas une étiquette |
| — | ce que l'article contient déjà (« assiette chicken frites salade ») n'est pas refusé comme un choix |

Lot 4 de la partie 1 (D49) : réécrit sur la fiche. Le modèle range chaque article et ses choix dans la case ``ajouter`` (D1) ; le code
retrouve les noms (nombres en lettres, synonymes) et applique les règles. D1 (les options ne deviennent pas des articles) et D4 (le choix
gardé en suspens) n'existent plus côté code : un article et ses choix voyagent ensemble dans la même case.
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
from api.services.commande import moteur, panier
from api.services.commande.moteur import Reglages
from api.services.restauration.appel import Lieu
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.services.workflow.verite_des_actions import affirmation_sans_outil_fait
from api.tests.mark import commande_sur_la_fiche as F
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

DOSSIER = Path(__file__).parent / "cartes_essai"
CARTE = json.loads((DOSSIER / "carte-kebab-demo.json").read_text(encoding="utf-8"))
SYNONYMES = {k: v for k, v in json.loads((DOSSIER / "synonymes-kebab-demo.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
ADRESSE = "5 rue Louis Boilet, 60700 Pont-Sainte-Maxence"


@pytest.fixture
async def kebab(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Kebab')")
        site = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'kebab', 'Kebab', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        for jour in range(1, 8):
            await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, '11:00'::time, '22:30'::time)", site, jour)
        await c.execute("INSERT INTO mark.resto_reglage (site_id, prefixe_numero_court, moyens_paiement) VALUES ($1, 'K', '{carte,especes,titre_restaurant}')", site)
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, delai_annonce) VALUES ($1, 'emporter', 15)", site)
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type) VALUES ($1, 'livraison')", site)
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, ouvert) VALUES ($1, 'sur_place', false)", site)
        await c.execute(
            "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, minimum, frais, delai) VALUES ($1, 'Pont', 'communes', '{60509,60508,60587}', 0, 0, 30)", site
        )
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            await importer_carte(c, site, CARTE, "caisse")
            for ref, synonymes in SYNONYMES.items():
                assert await poser_les_synonymes(c, site, ref, synonymes, "essai"), ref
            yield SimpleNamespace(c=c, a=site, base=base_prete)
    finally:
        await c.close()


class Appel:
    def __init__(self, kebab):
        self.kebab = kebab
        self.source = SourceClasseur(kebab.c, Lieu(kebab.base, kebab.a, 1), nom_prise="test", prise=PriseTest())
        self.p = panier.nouveau()
        self.regles = Reglages(vente_en_plus=False)

    async def charger(self):
        await self.source.charger_les_modes()
        return self

    async def a_emporter(self):
        await self.charger()
        await moteur.choisir_mode(self.source, self.p, self.regles, "emporter")
        return self

    async def ajouter(self, *articles):
        return await F.ajouter(self.source, self.p, self.regles, *articles)

    async def repondre(self, choix):
        return await F.repondre(self.source, self.p, self.regles, choix)

    def lignes(self):
        return sorted(
            (l["nom"], l["quantite"], tuple(sorted(c["nom"] for c in l["choix"])), tuple(sorted(l["retires"])))
            for l in self.p["lignes"]
        )


TACOS_2598 = ("Tacos 2 viandes", 1, ("Algérienne", "Chicken", "Gratiné au fromage", "Kebab"), ())


# --------------------------------------------------------------------------- #
# D3 : les nombres dits en lettres
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "dit,article",
    [("tacos deux viandes", "Tacos 2 viandes"), ("tacos une viande", "Tacos 1 viande"), ("tacos trois viandes", "Tacos 3 viandes")],
)
async def test_d3_le_nombre_en_lettres_dans_un_nom(kebab, dit, article):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(dit)
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.faits["article"] == article, r


@pytest.mark.parametrize("dit,article", [("panini trois fromages", "Panini 3 fromages"), ("hummer h un", "Hummer H1"), ("sept up", "7Up"), ("le cent quatre-vingt", "Le 180")])
async def test_d3_nombres_colles_et_composes(kebab, dit, article):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(dit)
    assert r.statut in ("OK", "CHOIX_OBLIGATOIRE"), r
    assert any(l["nom"].startswith(article) for l in a.p["lignes"]), a.p["lignes"]


async def test_d3_modifier_retrouve_la_ligne_dite_en_lettres(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(A("tacos 2 viandes", supplements=["kebab", "chicken"]))
    assert r.statut == "OK", r
    r = await moteur.modifier(a.source, a.p, a.regles, ligne="tacos deux viandes", choix="sauce algérienne et samouraï")
    assert r.statut == "OK", r
    assert a.lignes() == [("Tacos 2 viandes", 1, ("Algérienne", "Chicken", "Kebab", "Samouraï"), ())]


# --------------------------------------------------------------------------- #
# D1, D2 : les options du produit cité dans la même phrase
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "plus",
    [
        A("tacos deux viandes", supplements=["kebab", "poulet", "sauce algérienne", "gratiné"]),
        A("tacos 2 viandes", supplements=["kebab", "chicken", "algérienne", "gratiné"]),
    ],
    ids=["lettres_et_synonyme", "chiffres"],
)
async def test_d1_d2_le_tacos_et_ses_choix_dans_la_meme_phrase(kebab, plus):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(plus)
    assert r.statut == "OK", r
    assert a.lignes() == [TACOS_2598], a.p["lignes"]


async def test_d1_un_article_avec_sa_quantite_reste_un_article(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(A("tacos deux viandes", supplements=["kebab", "chicken"]), A("kebab", variante="normal"))
    assert r.statut == "OK", r
    assert a.lignes() == [("Kebab Normal", 1, (), ()), ("Tacos 2 viandes", 1, ("Chicken", "Kebab"), ())]


async def test_d2_poulet_repond_a_la_question_des_viandes(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter("tacos deux viandes")
    assert r.manque == "Viandes (2)", r
    r = await a.repondre("kebab et poulet")
    assert r.statut == "OK", r
    assert a.lignes() == [("Tacos 2 viandes", 1, ("Chicken", "Kebab"), ())]


async def test_deux_kebabs_sandwich_sauce_blanche_dont_un_sans_oignons(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(A("kebab sandwich", supplements=["sauce blanche"]), A("kebab sandwich", supplements=["sauce blanche"], sans=["oignons"]))
    assert r.manque == "taille", r  # Normal ou Maxi : demandé, jamais deviné
    r = await a.repondre("normal")
    assert r.statut == "OK", r
    assert a.lignes() == [("Kebab Normal", 1, ("Blanche",), ()), ("Kebab Normal", 1, ("Blanche",), ("oignon",))], a.p["lignes"]


async def test_ce_que_l_article_contient_deja_n_est_pas_refuse(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(A("assiette chicken", supplements=["frites", "salade"]))
    assert r.statut == "OK", r
    assert a.lignes() == [("Assiette chicken", 1, (), ())]


# --------------------------------------------------------------------------- #
# D4 : le choix dit avant que l'article soit sûr
# --------------------------------------------------------------------------- #


# test_d4_le_choix_dit_avec_un_article_en_doute_est_garde : supprimé au lot 4 (D49), le choix en suspens n'existe plus : un article et ses choix voyagent dans la même case, et un doute rend ses choix ; sens repris par partie_1/test_l03_porte.py::test_doute_rend_les_choix.


# --------------------------------------------------------------------------- #
# D5 : le mode et la livraison
# --------------------------------------------------------------------------- #






async def test_d5_l_adresse_verifiee_sans_mode_pose_la_livraison(kebab):
    a = await Appel(kebab).charger()
    r = await a.ajouter("assiette chicken")
    assert "garde" in r.faits, r  # lot 4 (M28) : gardé tant que le mode manque
    r = await moteur.verifier_adresse(a.source, a.p, a.regles, ADRESSE)
    assert r.statut == "RETENU", r
    assert a.p["mode"] == "livraison" and a.lignes() == [("Assiette chicken", 1, (), ())], a.p


# --------------------------------------------------------------------------- #
# D7 : la question d'un choix est une phrase
# --------------------------------------------------------------------------- #


async def test_d7_la_question_de_la_taille_est_une_phrase_dite(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter("Oasis")
    assert r.suggestion == "Quelle taille pour votre Oasis : 33 centilitres, 1,5 litre ou 2 litres ?", r


async def test_d7_la_question_d_un_groupe_est_une_phrase_dite(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter("tacos deux viandes")
    assert r.suggestion.startswith("Pour votre Tacos 2 viandes, qu'est-ce que vous prenez comme viandes, deux au choix : Kebab, Merguez"), r
    assert "(" not in r.suggestion, r


# --------------------------------------------------------------------------- #
# D6 : « c'est noté » quand rien n'est fait
# --------------------------------------------------------------------------- #


def _tour(*resultats):
    return [{"role": "user", "content": "un tacos"}] + [{"role": "tool", "content": json.dumps(r)} for r in resultats]


REFUS_DU_MODE = {"statut": "ARGUMENT_INVALIDE", "faits": {"modes": ["emporter"]}, "suggestion": "À emporter ?", "manque": "mode"}


@pytest.mark.parametrize(
    "replique",
    [
        "C'est noté pour votre tacos deux viandes avec poulet, kebab, sauce algérienne et samouraï, mais est-ce que ce serait finalement pour venir le chercher ?",
        "C'est bien noté pour le tacos deux viandes avec le kebab et le chicken et vos deux sauces, alors pour le menu étudiant, vous le voulez avec quoi ?",
        "Votre tacos deux viandes est bien pris en compte.",
    ],
)
def test_d6_l_affirmation_suivie_d_une_question_est_retenue(replique):
    assert affirmation_sans_outil_fait(replique, _tour(REFUS_DU_MODE)) is not None


def test_d6_une_vraie_question_passe():
    assert affirmation_sans_outil_fait("Est-ce que c'est noté pour vous ?", _tour(REFUS_DU_MODE)) is None
    assert affirmation_sans_outil_fait("Vous voulez que je l'ajoute, ou c'est noté comme ça ?", _tour(REFUS_DU_MODE)) is None


@pytest.mark.parametrize("statut", ["INTROUVABLE", "HORS_CARTE", "ECHEC_REPETE"])
def test_d6_un_introuvable_dit_pas_fait(statut):
    assert affirmation_sans_outil_fait("C'est noté pour les sauces.", _tour({"statut": statut, "faits": {}, "suggestion": "Je ne trouve pas."})) is not None

