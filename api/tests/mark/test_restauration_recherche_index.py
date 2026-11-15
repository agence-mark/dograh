"""[.mark] Module Restauration, lot 4 : l'index versionné d'une liste (D10) et son activation conditionnée au banc.

| Test | Ce qu'il prouve |
|---|---|
| même version | l'index n'est pas refait ; une nouvelle version le refait AVANT de chercher |
| banc propre | un index dont le banc rend zéro faux sûr devient actif |
| banc qui échoue | l'ancien index reste actif, les produits retirés sont marqués indisponibles, une alerte part avec le détail |
| pas de travail en double | la version refusée n'est pas re-mesurée à chaque recherche ; la suivante, bonne, active et lève les indisponibles |
| premier index | activé même non prouvé (sans index rien ne se cherche), avec l'alerte |
| deux processus | deux gestionnaires distincts lisant la même version font le même index |
| accès simultanés | deux préparations en même temps ne mesurent qu'une fois |
| par la vraie fonction | une carte changée en base se retrouve sans redémarrage ; un produit retiré n'est plus rendu |
"""

from __future__ import annotations

import asyncio

import pytest

from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_banc import Bilan
from api.db.bases_clients.recherche_liste_index import GESTIONNAIRE, GestionnaireDIndex
from api.db.bases_clients.recherche_liste_moteur import chercher_dans_l_index
from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_client import chercher_dans_la_liste
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, resto  # noqa: F401

V1 = [Element("a", "Tiramisu"), Element("b", "Orangina"), Element("c", "Fanta Citron")]
V2 = [Element("a", "Tiramisu"), Element("b", "Orangina"), Element("d", "Fanta Orange")]  # « c » retiré, « d » ajouté


def _banc_qui_repond(resultats):
    appels = []

    def banc(index, elements, reglages):
        appels.append([e.id for e in elements])
        faux = resultats.pop(0) if resultats else False
        return Bilan(total=4, bon=4 - (1 if faux else 0), faux_surs=[{"dit": "x", "attendu": "a", "obtenu": "RETENU", "retenu": "b", "origine": ""}] if faux else [])

    return banc, appels


def _gestionnaire(resultats):
    alertes = []
    banc, appels = _banc_qui_repond(resultats)
    return GestionnaireDIndex(alerte=lambda cle, evenement, details: alertes.append((cle, evenement, details)), banc=banc), appels, alertes


def test_la_meme_version_ne_refait_pas_l_index_une_nouvelle_version_le_refait():
    g, appels, alertes = _gestionnaire([False, False])
    e1 = g.preparer("liste", 1, V1)
    assert g.preparer("liste", 1, V1) is e1 and len(appels) == 1 and g.a_jour("liste", 1) and not g.a_jour("liste", 2)
    e2 = g.preparer("liste", 2, V2)
    assert len(appels) == 2 and e2.version == 2 and alertes == []
    assert chercher_dans_l_index(e2.index, "fanta orange", exclus=e2.exclus)["retenu"] == "d"
    assert chercher_dans_l_index(e2.index, "fanta citron", exclus=e2.exclus)["retenu"] is None  # retiré avec la nouvelle version


def test_un_index_qui_fait_un_faux_sur_n_est_pas_active_l_ancien_reste_les_retires_sont_indisponibles_et_une_alerte_part():
    g, appels, alertes = _gestionnaire([False, True])
    ancien = g.preparer("liste", 1, V1)
    refuse = g.preparer("liste", 2, V2)
    assert refuse is ancien and refuse.version == 1 and refuse.refusee and refuse.version_vue == 2
    # l'ancien index répond encore : « Fanta Orange » (nouveau) n'existe pas pour lui, « Fanta Citron » (retiré) est indisponible
    assert chercher_dans_l_index(refuse.index, "tiramisu", exclus=refuse.exclus)["retenu"] == "a"
    assert chercher_dans_l_index(refuse.index, "fanta orange", exclus=refuse.exclus)["retenu"] is None
    assert refuse.exclus == frozenset({"c"})
    r = chercher_dans_l_index(refuse.index, "fanta citron", exclus=refuse.exclus)
    assert r["retenu"] is None and "c" not in [x["id"] for x in r["candidats"]]
    assert [(c, ev) for c, ev, _ in alertes] == [("liste", "index_refuse")]
    details = alertes[0][2]
    assert details["version"] == 2 and details["version_active"] == 1 and details["faux_sur"] == 1 and details["indisponibles"] == 1
    assert details["exemples"][0]["retenu"] == "b"


def test_la_version_refusee_n_est_pas_mesuree_a_chaque_recherche_la_suivante_bonne_active():
    g, appels, alertes = _gestionnaire([False, True, False])
    g.preparer("liste", 1, V1)
    for _ in range(5):
        g.preparer("liste", 2, V2)
    assert len(appels) == 2 and len(alertes) == 1  # une mesure, une alerte
    e3 = g.preparer("liste", 3, V2)
    assert e3.version == 3 and e3.exclus == frozenset() and not e3.refusee and len(appels) == 3
    assert chercher_dans_l_index(e3.index, "fanta orange", exclus=e3.exclus)["retenu"] == "d"


def test_le_premier_index_est_active_meme_non_prouve_avec_l_alerte():
    g, _, alertes = _gestionnaire([True])
    e = g.preparer("liste", 1, V1)
    assert e.version == 1 and e.prouve is False and chercher_dans_l_index(e.index, "tiramisu")["retenu"] == "a"
    assert [ev for _, ev, _ in alertes] == ["premier_index_non_prouve"]


def test_deux_processus_qui_lisent_la_meme_version_font_le_meme_index():
    g1, _, _ = _gestionnaire([False])
    g2, _, _ = _gestionnaire([False])
    e1, e2 = g1.preparer("liste", 7, V2), g2.preparer("liste", 7, V2)
    assert e1 is not e2 and e1.version == e2.version == 7 and e1.index.signature == e2.index.signature
    assert chercher_dans_l_index(e1.index, "fanta orange")["retenu"] == chercher_dans_l_index(e2.index, "fanta orange")["retenu"] == "d"


async def test_deux_preparations_en_meme_temps_ne_mesurent_qu_une_fois():
    g, appels, _ = _gestionnaire([False])
    etats = await asyncio.gather(*(g.preparer_async("liste", 1, V1) for _ in range(5)))
    assert len(appels) == 1 and len({id(e) for e in etats}) == 1


def test_le_banc_par_defaut_est_tire_de_la_liste_et_un_vrai_moteur_est_sur():
    g = GestionnaireDIndex(alerte=lambda *a: pytest.fail("alerte inattendue"))
    e = g.preparer("liste", 1, V1 + [Element("e", "Tiramisu")])  # un même nom deux fois : attendu AMBIGU, jamais retenu
    assert e.prouve and e.bilan.faux_sur == 0 and e.bilan.total >= 6
    assert chercher_dans_l_index(e.index, "tiramisu")["statut"] == "AMBIGU"


# --------------------------------------------------------------------------- par la vraie fonction, sur une vraie base


async def test_une_carte_changee_en_base_se_retrouve_sans_redemarrage_un_produit_retire_n_est_plus_rendu(resto):  # noqa: F811
    c, a = resto.c, resto.a
    GESTIONNAIRE.oublier()
    await importer_carte(c, a, CARTE, "caisse")
    cle = (resto.base, "carte", a)
    avant = await chercher_dans_la_liste(c, "carte", "tiramisu", a)
    assert avant.statut == "RETENU"
    version = GESTIONNAIRE.etat(cle).version
    # même version : aucune reconstruction
    index_avant = GESTIONNAIRE.etat(cle).index
    await chercher_dans_la_liste(c, "carte", "tiramisu", a)
    assert GESTIONNAIRE.etat(cle).index is index_avant
    # un changement en base (déclencheur de version) : l'index est refait avant de chercher
    await c.execute("UPDATE mark.resto_produit SET nom = 'Tiramisu maison' WHERE site_id = $1 AND ref = $2", a, avant.faits["retenu"])
    apres = await chercher_dans_la_liste(c, "carte", "tiramisu maison", a)
    assert apres.statut == "RETENU" and apres.faits["retenu"] == avant.faits["retenu"] and apres.faits["version"] > version
    assert GESTIONNAIRE.etat(cle).index is not index_avant
    # un produit retiré : plus jamais rendu
    await c.execute("DELETE FROM mark.resto_produit WHERE site_id = $1 AND ref = $2", a, avant.faits["retenu"])
    retire = await chercher_dans_la_liste(c, "carte", "tiramisu maison", a)
    assert retire.faits["retenu"] is None and avant.faits["retenu"] not in [x["id"] for x in retire.faits["candidats"]]
    # une autre organisation ou un autre établissement a SON index
    assert GESTIONNAIRE.etat((resto.base, "carte", resto.b)) is None
