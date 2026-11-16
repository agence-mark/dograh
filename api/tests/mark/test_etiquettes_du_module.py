"""[.mark] Module Restauration, lot 11 (§ 3.3) : les étiquettes que le module pose au décroché.

| Test | Ce qu'il prouve |
|---|---|
| déclaration | chaque étiquette est déclarée au registre, une seule fois, sans collision avec une clé posée par le code ; elles arrivent au catalogue de l'éditeur sous la source « module » avec le nom du module |
| aucune carte | aucune étiquette ne porte un article, un prix d'article, un ingrédient ou un allergène : l'inventaire est fermé, chaque valeur est courte |
| poser | une clé déclarée et non vide n'est jamais écrasée ; une clé non déclarée n'est jamais posée ; un texte long est coupé |
| allumage | module coupé (commande éteinte) : rien n'est lu ni posé ; une lecture qui échoue : le contexte de l'appel reste tel quel |
| valeurs | phrase des zones, minimum, types ouverts, paiements et prénom lus dans le classeur de l'établissement servi ; une organisation sans base : aucune étiquette |
| deux chemins | le téléphone et le clavier appellent le même ``injecter_etiquettes_du_module`` |
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.services.modules import etiquettes
from api.services.modules.registre import PAR_CODE
from api.services.objets_agent.noms_poses_par_le_code import INJECTIONS_DU_CODE, VARIABLES_POSEES_PAR_LE_CODE
from api.services.restauration import etiquettes as valeurs_resto
from api.services.variables_agent.catalogue import SOURCES, construire
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401  (fixtures)

RACINE = Path(__file__).resolve().parents[2] / "services"
CLES = frozenset(etiquettes.cles_des_etiquettes())


def test_les_etiquettes_sont_declarees_une_fois_et_arrivent_au_catalogue_de_l_editeur():
    module = PAR_CODE["restauration"]
    assert len(CLES) == len(module.etiquettes) == 6
    assert INJECTIONS_DU_CODE["injecter_etiquettes_du_module"] == CLES
    assert "module" in SOURCES
    catalogue = {v.cle: v for v in construire()}
    for e in module.etiquettes:
        v = catalogue[e.cle]
        assert (v.source, v.libelle, v.groupe_fr, v.groupe_en) == ("module", e.libelle.fr, "Restauration", "Restaurant")
    # Aucune clé n'est déjà posée par ailleurs (une seule source par clé).
    autres = set().union(*(c for nom, c in INJECTIONS_DU_CODE.items() if nom != "injecter_etiquettes_du_module"))
    assert not CLES & autres and CLES <= VARIABLES_POSEES_PAR_LE_CODE
    from api.schemas.noms_reserves import NOMS_RESERVES

    assert CLES <= NOMS_RESERVES, "une phrase, un champ de fiche ou un objet ne peut pas prendre le nom d'une étiquette"


def test_aucune_donnee_de_carte_dans_les_etiquettes():
    interdits = ("article", "plat", "ingredient", "allergene", "prix", "produit", "carte")
    for cle in CLES:
        assert not any(mot in cle for mot in interdits), cle
    # Chaque valeur d'exemple tient en une ligne courte.
    assert all(len(e.exemple) < 100 and "\n" not in e.exemple for m in etiquettes.modules_a_etiquettes() for e in m.etiquettes)
    # Le lecteur ne sait lire que des étiquettes de l'inventaire : zones (noms), minimum, types, paiements, prénom, motifs.
    source = (RACINE / "restauration" / "etiquettes.py").read_text(encoding="utf-8")
    for requete in ("resto_produit", "resto_ingredient", "allergene", "carte_du_restaurant", "article_de_la_carte"):
        assert requete not in source, requete


def test_poser_ne_depasse_pas_les_cles_declarees_et_n_ecrase_rien():
    base = {"commande_minimum": "10 euros", "autre": "x", "equipe_motifs": "  "}
    sortie = etiquettes.poser(
        base,
        {"commande_minimum": "99 euros", "equipe_motifs": "deux motifs", "commande_types_ouverts": "x" * 900, "inconnue": "oups", "livraison_phrase_des_zones": ""},
        CLES,
    )
    assert sortie["commande_minimum"] == "10 euros", "une valeur déjà posée n'est jamais écrasée"
    assert sortie["equipe_motifs"] == "deux motifs", "une valeur vide est remplacée"
    assert len(sortie["commande_types_ouverts"]) == etiquettes.MAX_ETIQUETTE
    assert "inconnue" not in sortie and "livraison_phrase_des_zones" not in sortie
    assert base["commande_minimum"] == "10 euros", "le contexte d'entrée n'est pas modifié"


async def test_module_coupe_rien_n_est_lu_et_une_lecture_qui_echoue_laisse_le_contexte(monkeypatch):
    appels = []

    async def lecteur(organization_id, workflow_id, appel):
        appels.append(organization_id)
        return {"commande_minimum": "15 euros en livraison"}

    monkeypatch.setattr(etiquettes, "_fournisseur", lambda module: lecteur)
    contexte = {"caller_number": "+33612345678"}
    coupe = await etiquettes.injecter_etiquettes_du_module(contexte, {"commande_sur_catalogue": False}, 1, 2)
    assert coupe == contexte and appels == []
    allume = await etiquettes.injecter_etiquettes_du_module(contexte, {"commande_sur_catalogue": True}, 1, 2)
    assert allume["commande_minimum"] == "15 euros en livraison" and appels == [1]
    assert await etiquettes.injecter_etiquettes_du_module(contexte, {"commande_sur_catalogue": True}, None, 2) == contexte

    async def casse(*_):
        raise RuntimeError("base muette")

    monkeypatch.setattr(etiquettes, "_fournisseur", lambda module: casse)
    assert await etiquettes.injecter_etiquettes_du_module(contexte, {"commande_sur_catalogue": True}, 1, 2) == contexte


def test_phrase_des_zones_et_minimum_ne_disent_que_des_noms_et_un_chiffre():
    zones = [{"nom": "Centre", "minimum": 1500}, {"nom": "Alentours", "minimum": 2500}, {"nom": "  ", "minimum": 0}]
    assert valeurs_resto.phrase_des_zones(zones) == "Nous livrons Centre et Alentours."
    assert valeurs_resto.phrase_des_zones([]) == ""
    assert valeurs_resto.minimum_dit(zones) == "quinze euros en livraison"
    assert valeurs_resto.minimum_dit([{"nom": "A", "minimum": 0}]) == ""
    assert valeurs_resto._euros(1250) == "douze euros cinquante"


async def test_une_organisation_sans_base_n_a_aucune_etiquette(monkeypatch):
    from api.services.base_client import rattachement

    async def aucune(_organisation):
        return None

    monkeypatch.setattr(rattachement, "nom_de_la_base", aucune)
    assert await valeurs_resto.valeurs(1, 2, {}) == {}


def test_le_telephone_et_le_clavier_appellent_le_meme_branchement():
    for fichier in ("pipecat/run_pipeline.py", "workflow/text_chat_runner.py"):
        source = (RACINE / fichier).read_text(encoding="utf-8")
        assert "await injecter_etiquettes_du_module(" in source, fichier


@pytest.mark.parametrize("motif", ["Restauration", "restaurant"])
def test_le_moteur_commun_ne_dit_aucun_mot_de_metier(motif):
    assert motif.lower() not in (RACINE / "modules" / "etiquettes.py").read_text(encoding="utf-8").lower()


def test_une_etiquette_d_un_module_eteint_est_refusee_a_la_publication():
    from api.services.variables_agent import citations as cit
    from api.services.variables_agent.catalogue import cles_connues

    graphe = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "Accueil", "prompt": "Minimum : {{commande_minimum}}. Nom : {{etablissement}}."}}]}
    citations = cit.citations_de(graphe, {})
    # Module éteint (interrupteur de la commande) : l'étiquette n'est pas au catalogue de l'agent, la publication la refuse comme une clé inconnue.
    eteint = construire(configurations={"commande_sur_catalogue": False})
    assert not [v for v in eteint if v.source == "module"]
    assert [c.cle for c in cit.inconnues(citations, cles_connues(eteint))] == ["commande_minimum"]
    # Allumé : connue.
    allume = construire(configurations={"commande_sur_catalogue": True})
    assert {v.cle for v in allume if v.source == "module"} == CLES
    assert cit.inconnues(citations, cles_connues(allume)) == []
    # Vue de l'organisation (aucun agent) : toutes les étiquettes de modules, pour les montrer.
    assert {v.cle for v in construire() if v.source == "module"} == CLES


async def test_les_valeurs_sont_lues_dans_le_classeur_de_l_etablissement_servi(base_prete, monkeypatch):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.restauration_ecran import poser_le_module
    from api.services.base_client import rattachement
    from api.services.etablissements import appel as appel_etablissement

    async def la_base(_organisation):
        return base_prete

    async def aucun_choix(*_args, **_kwargs):
        return None  # un seul établissement : celui-là

    monkeypatch.setattr(rattachement, "nom_de_la_base", la_base)
    monkeypatch.setattr(appel_etablissement, "etablissement_de_lappel", aucun_choix)
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        site = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'a', 'a', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        # Module pas ouvert chez ce client : aucune étiquette, aucune autre lecture.
        assert await valeurs_resto.valeurs(1, 2, {"caller_number": "+33612345678"}) == {}
        await poser_le_module(c, True, "test")
        await c.execute("INSERT INTO mark.resto_zone (site_id, nom, forme, communes, minimum, delai) VALUES ($1, 'Beauvais', 'communes', '{60057}', 1500, 30)", site)
        await c.execute("INSERT INTO mark.resto_zone (site_id, nom, forme, communes, minimum, delai) VALUES ($1, 'Auneuil', 'communes', '{60022}', 2500, 40)", site)
        await c.execute("INSERT INTO mark.resto_client (site_id, telephone, prenom) VALUES ($1, '+33612345678', 'Karim')", site)
    finally:
        await c.close()
    sortie = await valeurs_resto.valeurs(1, 2, {"caller_number": "+33612345678"})
    assert sortie["livraison_phrase_des_zones"] == "Nous livrons Beauvais et Auneuil."
    assert sortie["commande_minimum"] == "quinze euros en livraison"
    assert sortie["appel_client_reconnu"] == "Karim"
    assert sortie["commande_paiements_acceptes"] == "par carte et en espèces"
    assert sortie["equipe_motifs"] == valeurs_resto.MOTIFS_DE_PASSAGE
    assert set(sortie) <= CLES, "rien d'autre que les étiquettes déclarées"
    # Un numéro inconnu : pas de prénom ; numéro masqué : pas de prénom non plus.
    assert "appel_client_reconnu" not in {k for k, v in (await valeurs_resto.valeurs(1, 2, {"caller_number": "+33699999999"})).items() if v}
    assert not (await valeurs_resto.valeurs(1, 2, {})).get("appel_client_reconnu")


async def test_le_vrai_catalogue_n_offre_pas_une_etiquette_d_un_module_eteint(monkeypatch):
    """Les noms réservés (NOMS_RESERVES) ne doivent pas faire entrer par la porte de derrière une étiquette d'un module éteint."""
    from api.services.variables_agent import catalogue as cat

    async def rien(_organisation):
        return []

    monkeypatch.setattr(cat, "_objets", rien)
    monkeypatch.setattr(cat, "_phrases", rien)
    eteint = {v.cle for v in await cat.catalogue_de(1, None, {"commande_sur_catalogue": False})}
    assert not CLES & eteint
    allume = {v.cle: v for v in await cat.catalogue_de(1, None, {"commande_sur_catalogue": True})}
    assert CLES <= set(allume) and all(allume[c].source == "module" for c in CLES)
