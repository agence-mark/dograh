"""[.mark] Module Restauration, lot 4 : le module « Recherche dans une liste » au registre, ses réglages, les noms ambigus calculés,
les synonymes proposés à relire et le lexique rempli depuis la carte.

| Test | Ce qu'il prouve |
|---|---|
| registre | le module est au registre : interrupteur, besoin « liste », 4 réglages de construction, réglage terrain « synonymes » ; ses clés existent au schéma, par défaut : allumé, son oui, sens NON |
| réglages de l'agent | lus de la configuration de l'appel ; une valeur hors bornes retombe sur le défaut (au journal) ; module coupé : ``None`` ; des seuils plus durs posent plus de questions (par la vraie fonction) |
| la couche sens | éteinte par défaut ; une fois allumée et fournie, elle propose seulement |
| noms ambigus | calculés depuis la carte (un même nom dans deux rangements), jamais tapés |
| synonymes proposés | tirés du nom ; jamais le nom d'un autre produit ; un synonyme que deux produits proposent n'est donné à aucun |
| à relire | proposés « à relire » : la recherche ne s'en sert pas ; après relecture elle s'en sert ; rejouable ; une relecture n'est jamais écrasée |
| lexique | les noms de la carte entrent au lexique ; le lexique existant n'est jamais modifié ; seuls ceux qui tiennent dans le plafond du fournisseur sont cochés |
"""

from __future__ import annotations

import copy
import uuid

import pytest

from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_index import GESTIONNAIRE
from api.db.bases_clients.recherche_liste_moteur import (
    Reglages,
    chercher_dans_l_index,
    construire_index,
    noms_ambigus,
    poser_couche_sens,
    proposer_synonymes,
)
from api.db.bases_clients.restauration_carte import carte_du_restaurant, importer_carte
from api.db.bases_clients.restauration_client import chercher_dans_la_liste, elements_de_la_carte
from api.db.bases_clients.restauration_synonymes import marquer_relus, proposer_les_synonymes
from api.schemas.lexique_metier import LexiqueMetier, TermeLexique
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.configuration.plafond_lexique import PlafondLexique
from api.services.modules import registre
from api.services.restauration.lexique_liste import construire_lexique, remplir_le_lexique, termes_de_la_liste
from api.services.restauration.recherche_reglages import module_allume, reglages_de_la_recherche
from api.tests.mark.equipe_commun import creer_organisation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, resto  # noqa: F401

# --------------------------------------------------------------------------- le registre


def test_le_module_est_au_registre_avec_ses_reglages():
    module = registre.PAR_CODE["recherche_liste"]
    assert module.interrupteur == "recherche_dans_une_liste"
    assert [b.code for b in module.besoins] == ["liste"] and module.besoins[0].domaine is None and module.besoins[0].source_interne
    assert [r.cle for r in module.construction] == ["recherche_liste_seuil_retenu", "recherche_liste_seuil_ambigu", "recherche_liste_son", "recherche_liste_sens"]
    assert [(r.cle, r.lieu) for r in module.terrain] == [("synonymes", registre.CLASSEUR)]
    champs = WorkflowConfigurationDefaults.model_fields
    for cle in module.cles_de_l_agent():
        assert cle in champs, cle
    defauts = WorkflowConfigurationDefaults()
    assert defauts.recherche_dans_une_liste is True and defauts.recherche_liste_son is True and defauts.recherche_liste_sens is False
    assert (defauts.recherche_liste_seuil_retenu, defauts.recherche_liste_seuil_ambigu) == (0.90, 0.72)
    with pytest.raises(ValueError):
        WorkflowConfigurationDefaults(recherche_liste_seuil_retenu=0.2)
    # aucun mot de métier dans l'entrée du registre (M1)
    assert not any(m in str(module).lower() for m in ("restaura", "pizza", "menu", "carte"))


# --------------------------------------------------------------------------- les réglages de l'agent


def test_les_reglages_de_l_agent_viennent_de_la_configuration_de_l_appel():
    assert reglages_de_la_recherche({}) == Reglages() and reglages_de_la_recherche(None) == Reglages()
    r = reglages_de_la_recherche({"recherche_liste_seuil_retenu": 0.95, "recherche_liste_seuil_ambigu": 0.6, "recherche_liste_son": False, "recherche_liste_sens": True}, ("Pizzas",))
    assert (r.seuil_retenu, r.seuil_ambigu, r.couche_son, r.couche_sens, r.mots_de_categorie) == (0.95, 0.6, False, True, ("Pizzas",))
    assert reglages_de_la_recherche({"recherche_dans_une_liste": False}) is None and not module_allume({"recherche_dans_une_liste": False})
    # une valeur hors bornes, d'un mauvais type, ou incohérente : le défaut, jamais une erreur d'appel
    for faux in ({"recherche_liste_seuil_retenu": 3}, {"recherche_liste_seuil_retenu": "haut"}, {"recherche_liste_seuil_retenu": True}, {"recherche_liste_seuil_ambigu": 0.1}):
        assert reglages_de_la_recherche(faux) == Reglages(), faux
    assert reglages_de_la_recherche({"recherche_liste_seuil_retenu": 0.7, "recherche_liste_seuil_ambigu": 0.8}) == Reglages()  # ambigu au-dessus de retenu
    assert reglages_de_la_recherche({"recherche_liste_son": "oui"}).couche_son is True


async def test_des_seuils_plus_durs_posent_plus_de_questions_par_la_vraie_fonction(resto):  # noqa: F811
    GESTIONNAIRE.oublier()
    await importer_carte(resto.c, resto.a, CARTE, "caisse")
    normal = await chercher_dans_la_liste(resto.c, "carte", "une canette de coca", resto.a, reglages=reglages_de_la_recherche({}))
    dur = await chercher_dans_la_liste(resto.c, "carte", "une canette de coca", resto.a, reglages=reglages_de_la_recherche({"recherche_liste_seuil_retenu": 1.0}))
    assert normal.statut == "RETENU" and dur.statut == "AMBIGU" and dur.faits["retenu"] is None
    assert (await chercher_dans_la_liste(resto.c, "carte", "une canette de coca", resto.a)).statut == "RETENU"  # sans réglage : ceux du module


def test_la_couche_sens_est_eteinte_par_defaut_et_ne_fait_que_proposer():
    liste = [Element("a", "Tiramisu"), Element("b", "Orangina")]
    index = construire_index(liste)
    poser_couche_sens(lambda texte, elements: [("a", 1.0)])
    try:
        assert chercher_dans_l_index(index, "le dessert au café", Reglages())["statut"] == "INTROUVABLE"  # éteinte : jamais appelée
        r = chercher_dans_l_index(index, "le dessert au café", Reglages(couche_sens=True))
        assert (r["statut"], r["retenu"], r["candidats"][0]["id"]) == ("AMBIGU", None, "a")
    finally:
        poser_couche_sens(None)
    assert chercher_dans_l_index(index, "le dessert au café", Reglages(couche_sens=True))["statut"] == "INTROUVABLE"  # aucune couche fournie : rien


# --------------------------------------------------------------------------- noms ambigus, synonymes proposés


def test_les_noms_ambigus_sont_calcules_depuis_la_liste():
    liste = [
        Element("p", "Calabrese", (), "Pizzas"), Element("b", "Calabrese", (), "Bruschettas"), Element("t", "Tiramisu", (), "Desserts"),
        Element("x", "Capre e Miel", (), "Pizzas"), Element("y", "Capre e Miel", (), "Bruschettas"), Element("z", "capre e miel", (), "Salades"),
    ]
    ambigus = noms_ambigus(liste)
    assert set(ambigus) == {"calabrese", "capre e miel"} and [x["id"] for x in ambigus["calabrese"]] == ["p", "b"]
    assert [x["categorie"] for x in ambigus["capre e miel"]] == ["Pizzas", "Bruschettas", "Salades"]
    assert noms_ambigus([Element("t", "Tiramisu")]) == {}


def test_les_synonymes_sont_tires_du_nom_jamais_du_nom_d_un_autre():
    assert proposer_synonymes("Pizza Reine (maison)", ["Pizzas"]) == ["Pizza Reine", "Reine"]
    assert proposer_synonymes("Jus de pomme-poire", []) == ["Jus de pomme"]
    assert proposer_synonymes("Coca-Cola", []) == ["Coca"]
    assert proposer_synonymes("Eau", ["Boissons"]) == [] and proposer_synonymes("Tiramisu", []) == []
    assert proposer_synonymes("Pizza Reine", ["Pizzas"], autres_noms=frozenset({"reine"})) == []  # « reine » est déjà un autre produit
    assert proposer_synonymes("Canette-Cola", []) == [] or "Canette" not in proposer_synonymes("Canette-Cola", [])  # un contenant n'est pas un nom


CARTE_SYNONYMES = {
    "format": "mark-carte-commune/1",
    "categories": [{"id": "c1", "nom": "Pizzas"}],
    "produits": [
        {"id": "p-reine", "nom": "Pizza Reine (maison)", "categorie_id": "c1", "declinaisons": [{"id": "d1", "nom": "Normale", "code_caisse": "REINE", "prix": 1000}]},
        {"id": "p-jus", "nom": "Jus de pomme-poire", "categorie_id": "c1", "declinaisons": [{"id": "d2", "nom": "33 cl", "code_caisse": "JUS", "prix": 300}]},
        {"id": "p-cola", "nom": "Coca-Cola", "categorie_id": "c1", "declinaisons": [{"id": "d3", "nom": "33 cl", "code_caisse": "COLA", "prix": 250}]},
        {"id": "p-cola0", "nom": "Coca-Cola Zéro", "categorie_id": "c1", "declinaisons": [{"id": "d4", "nom": "33 cl", "code_caisse": "COLA0", "prix": 250}]},
        {"id": "p-tira", "nom": "Tiramisu", "categorie_id": "c1", "declinaisons": [{"id": "d5", "nom": "Part", "code_caisse": "TIRA", "prix": 450}]},
    ],
    "groupes": [], "formules": [],
}


async def _synonymes(c, site):
    return {r["ref"]: (list(r["synonymes"]), r["synonymes_a_relire"]) for r in await c.fetch("SELECT ref, synonymes, synonymes_a_relire FROM mark.resto_surcouche WHERE site_id = $1 AND objet = 'produit'", site)}


async def test_les_synonymes_proposes_sont_a_relire_la_recherche_ne_s_en_sert_qu_apres_relecture(resto):  # noqa: F811
    c, a = resto.c, resto.a
    GESTIONNAIRE.oublier()
    await importer_carte(c, a, CARTE_SYNONYMES, "caisse")
    bilan = await proposer_les_synonymes(c, a)
    assert bilan == {"proposes": 2, "ignores": 3}
    ecrits = await _synonymes(c, a)
    # « Coca » est proposé aux deux boissons : donné à aucune ; « Reine » et « Jus de pomme » sont propres à un seul produit
    assert ecrits == {"p-reine": (["Pizza Reine", "Reine"], True), "p-jus": (["Jus de pomme"], True)}
    carte = await carte_du_restaurant(c, a)
    reine = next(p for p in carte["produits"] if p["id"] == "p-reine")
    assert reine["synonymes"] == [] and reine["synonymes_a_relire"] == ["Pizza Reine", "Reine"]  # pas encore actifs
    # la recherche ne s'en sert pas
    avant = await chercher_dans_la_liste(c, "carte", "reine", a)
    assert avant.faits["retenu"] != "p-reine" or avant.faits["candidats"][0]["couche"] != "exact"
    assert not await marquer_relus(c, a, "p-tira")  # rien à relire : rien de changé
    # la relecture : ils deviennent actifs ; la carte change de version, l'index se refait seul
    assert await marquer_relus(c, a, "p-reine")
    carte = await carte_du_restaurant(c, a)
    assert next(p for p in carte["produits"] if p["id"] == "p-reine")["synonymes"] == ["Pizza Reine", "Reine"]
    apres = await chercher_dans_la_liste(c, "carte", "une reine", a)
    assert (apres.statut, apres.faits["retenu"]) == ("RETENU", "p-reine")
    # rejouable : un produit proposé ou relu n'est jamais retouché
    assert await proposer_les_synonymes(c, a) == {"proposes": 0, "ignores": 5}
    assert (await _synonymes(c, a))["p-reine"] == (["Pizza Reine", "Reine"], False)
    # une relecture corrigée remplace la proposition
    assert await marquer_relus(c, a, "p-jus", ["Jus de pommes"])
    assert (await _synonymes(c, a))["p-jus"] == (["Jus de pommes"], False)
    assert not await marquer_relus(c, a, "p-jus", ["autre"])  # déjà relu : on n'y revient pas par cette voie
    # un import ne les écrase pas
    await importer_carte(c, a, CARTE_SYNONYMES, "caisse")
    assert (await _synonymes(c, a))["p-reine"] == (["Pizza Reine", "Reine"], False)


async def test_les_propositions_ne_touchent_pas_une_fiche_qui_a_deja_ses_synonymes(resto):  # noqa: F811
    c, a = resto.c, resto.a
    await importer_carte(c, a, CARTE_SYNONYMES, "caisse")
    await c.execute("INSERT INTO mark.resto_surcouche (site_id, objet, ref, synonymes, synonymes_a_relire) VALUES ($1, 'produit', 'p-reine', '{ma reine}', false)", a)
    await c.execute("INSERT INTO mark.resto_surcouche (site_id, objet, ref, etoile) VALUES ($1, 'produit', 'p-jus', true)", a)
    await proposer_les_synonymes(c, a)
    ecrits = await _synonymes(c, a)
    assert ecrits["p-reine"] == (["ma reine"], False)  # relu à la main : intact
    assert ecrits["p-jus"] == (["Jus de pomme"], True)  # une surcouche sans synonyme (l'étoile) reçoit la proposition
    assert await c.fetchval("SELECT etoile FROM mark.resto_surcouche WHERE site_id = $1 AND ref = 'p-jus'", a) is True  # l'étoile reste


# --------------------------------------------------------------------------- le lexique


PLAFOND_TROIS = PlafondLexique(fournisseur="Essai", jetons=None, termes=3, octets_par_jeton=3.0, jetons_par_terme=1, source="essai du test")
LISTE = [Element(f"e{i}", nom) for i, nom in enumerate(["Margherita", "Capre e Miel", "Calzone", "Pepperoni", "Napoli"])]


def test_les_noms_de_la_carte_entrent_au_lexique_dans_la_limite_du_fournisseur():
    resultat = construire_lexique(LexiqueMetier(), LISTE, PLAFOND_TROIS)
    assert (resultat.ajoutes, resultat.deja_presents, resultat.a_ecouter, resultat.non_ecoutes) == (5, 0, 3, 2)
    assert [t.terme for t in resultat.lexique.termes if t.a_ecouter] == ["Margherita", "Capre e Miel", "Calzone"]  # l'ordre de la carte
    assert len(resultat.lexique.termes) == 5 and all(t.categorie == "Carte" and t.nature == "nom_propre" for t in resultat.lexique.termes)
    # les prioritaires (l'étoile) passent d'abord
    prio = construire_lexique(LexiqueMetier(), LISTE, PLAFOND_TROIS, prioritaires=["e4", "e3"])
    assert {t.terme for t in prio.lexique.termes if t.a_ecouter} == {"Napoli", "Pepperoni", "Margherita"}  # les deux étoiles, puis le premier de la carte
    # sans plafond déclaré : rien n'est coché (comme à l'appel), tout est gardé pour la correction et la prononciation
    sans = construire_lexique(LexiqueMetier(), LISTE, None)
    assert (sans.ajoutes, sans.a_ecouter, sans.non_ecoutes) == (5, 0, 5)


def test_le_lexique_existant_n_est_jamais_modifie_et_ce_qu_il_ecoute_deja_prend_du_plafond():
    existant = LexiqueMetier(termes=[
        TermeLexique(terme="Margherita", variantes=["Margarita"], prononciation="margueri-ta", a_ecouter=False),  # déjà là, sous une graphie
        TermeLexique(terme="Edilkamin", a_ecouter=True),
        TermeLexique(terme="Godin", a_ecouter=True),
    ])
    resultat = construire_lexique(existant, LISTE, PLAFOND_TROIS)
    assert (resultat.ajoutes, resultat.deja_presents) == (4, 1)
    avant = {t.terme: t for t in existant.termes}
    apres = {t.terme: t for t in resultat.lexique.termes}
    assert apres["Margherita"] == avant["Margherita"] and apres["Edilkamin"] == avant["Edilkamin"] and apres["Godin"] == avant["Godin"]
    assert resultat.a_ecouter == 1 and resultat.non_ecoutes == 3  # trois places dont deux déjà prises
    assert sum(1 for t in resultat.lexique.termes if t.a_ecouter) == 3


def test_un_nom_trop_long_ou_sans_lettre_n_est_pas_ecrit():
    liste = [Element("a", "x" * 200), Element("b", "---"), Element("c", "Calzone")]
    assert [t.terme for t in termes_de_la_liste(liste)] == ["Calzone"]
    assert construire_lexique(LexiqueMetier(), liste, PLAFOND_TROIS).ecartes == 2


async def test_le_lexique_de_l_organisation_se_remplit_et_se_rejoue_sans_doublon(db_session):
    org = await creer_organisation(db_session, f"lex-{uuid.uuid4().hex[:8]}")
    premier = await remplir_le_lexique(org, LISTE, PLAFOND_TROIS)
    from api.services.lexique.stockage import lire_lexique

    lu = await lire_lexique(org)
    assert (premier.ajoutes, premier.a_ecouter) == (5, 3) and len(lu.termes) == 5 and sum(1 for t in lu.termes if t.a_ecouter) == 3
    second = await remplir_le_lexique(org, LISTE, PLAFOND_TROIS)
    assert (second.ajoutes, second.deja_presents) == (0, 5) and (await lire_lexique(org)).termes == lu.termes
    # par la carte : les éléments de la vraie fonction de lecture
    elements, _ = elements_de_la_carte(copy.deepcopy({"categories": [], "produits": [], "formules": []}))
    assert elements == []
