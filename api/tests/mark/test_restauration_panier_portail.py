"""[.mark] Module Restauration, lot 15 : la commande qui se remplit pendant un appel, lue par le portail.

Vraie route, vraie authentification (clé d'API de l'organisation), vrai Redis.

| Test | Ce qu'il prouve |
|---|---|
| le geste | un geste qui change le panier le garde (mode, lignes nom et quantité, prix de chaque ligne et total en centimes quand ils sont chiffrés) avant d'émettre ``commande.panier`` ; un geste qui ne le change pas ne le touche pas |
| la lecture | la route rend le panier de l'appel ; jamais le nom ni l'adresse de l'appelant (aucun autre champ) |
| cloisonnement | la clé d'une autre organisation, un autre établissement de la même organisation, un établissement inconnu : 404 ; un appel inconnu : 404 |
| permission | ``conversations.voir`` au registre ; la route est gelée dans le contrat avec le portail |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.equipe_mark import registre_routes as registre
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements, organisations  # noqa: F401

PANIER = {
    "version": 3, "mode": "emporter", "client": {"prenom": "Sophie", "telephone": "0600000000"}, "adresse": "1 rue des Lilas",
    "lignes": [{"n": 1, "nom": "Regina", "quantite": 2, "code": "R1", "choix": ["grande"], "note": "sans champignons"}, {"n": 2, "nom": "Tiramisu", "quantite": 1}],
}


def _url(etablissement: int, appel: int | str) -> str:
    return f"/api/v1/restauration/etablissements/{etablissement}/appels/{appel}/panier"


async def test_la_route_rend_le_panier_de_l_appel_sans_rien_de_l_appelant(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    await flux.poser_le_panier(cas.a, etab, 4242, PANIER)
    async with client_http() as c:
        r = await c.get(_url(etab, 4242), headers=_cle(cas.cle_a))
    assert r.status_code == 200
    assert r.json() == {"version": 3, "mode": "emporter", "lignes": [{"nom": "Regina", "quantite": 2, "prix": None, "sous_ligne": None}, {"nom": "Tiramisu", "quantite": 1, "prix": None, "sous_ligne": None}], "total": None, "zone": None}
    assert "Sophie" not in r.text and "0600000000" not in r.text and "Lilas" not in r.text and "champignons" not in r.text


async def test_cloisonnement_autre_organisation_autre_etablissement_inconnu(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    un, deux = cas.sites_a
    await flux.poser_le_panier(cas.a, un, 77, PANIER)
    inconnu = max(cas.sites_a + cas.sites_b) + 1000
    async with client_http() as c:
        autre_organisation = await c.get(_url(un, 77), headers=_cle(cas.cle_b))
        autre_etablissement = await c.get(_url(deux, 77), headers=_cle(cas.cle_a))
        etablissement_inconnu = await c.get(_url(inconnu, 77), headers=_cle(cas.cle_a))
        appel_inconnu = await c.get(_url(un, 78), headers=_cle(cas.cle_a))
        sans_cle = await c.get(_url(un, 77))
        mal_forme = await c.get(_url(un, "abc"), headers=_cle(cas.cle_a))
    assert [r.status_code for r in (autre_organisation, autre_etablissement, etablissement_inconnu, appel_inconnu)] == [404, 404, 404, 404]
    assert sans_cle.status_code == 401 and mal_forme.status_code == 422


async def test_un_geste_qui_change_le_panier_le_garde_puis_emet_un_geste_sans_effet_ne_touche_a_rien(organisations):  # noqa: F811
    org, etab = organisations[0], 5
    async def sans_prix(p, ctx):
        return p

    source = SimpleNamespace(lieu=SimpleNamespace(etablissement_id=etab), _panier_chiffre=sans_prix)
    ctx = SimpleNamespace(organization_id=org, run_id=9001)
    await SourceClasseur.apres_le_geste(source, "ajouter", 2, PANIER, SimpleNamespace(statut="OK", faits={}), ctx)
    assert (await flux.lire_le_panier(org, etab, 9001))["lignes"][0] == {"nom": "Regina", "quantite": 2, "prix": None}
    await SourceClasseur.apres_le_geste(source, "ajouter", 2, {**PANIER, "version": 2, "lignes": []}, SimpleNamespace(statut="OK", faits={}), ctx)  # version inchangée
    assert (await flux.lire_le_panier(org, etab, 9001))["lignes"]  # rien n'a été réécrit


def test_la_route_est_au_registre_avec_sa_permission():
    decision = registre.decision_de("GET", "/restauration/etablissements/{etablissement_id}/appels/{appel_id}/panier")
    assert decision is not None and decision[1] is False


def _ligne(n: int, nom: str, quantite: int, code: str) -> dict:
    return {"n": n, "nom": nom, "quantite": quantite, "code": code, "choix": [], "retires": [], "note": None, "attente": None}


def _panier_a_chiffrer(*lignes: dict) -> dict:
    return {"version": 4, "mode": "emporter", "zone": None, "client": {"telephone": "0600000000", "prenom": "Sophie"}, "adresse": "1 rue des Lilas", "lignes": list(lignes), "heure_voulue": None}


class _SourceChiffree:
    """Une source dont le chiffrage est rendu tel que le classeur le rend (réponse écrite, aucun appel) ; ``panne`` : elle lève."""

    def __init__(self, panne: bool = False):
        self.panne = panne
        self.regles_vues: list[dict] = []

    async def chiffrer(self, mode, lignes, zone_id, regles):
        from api.services.commande.resultat import Resultat

        if self.panne:
            raise RuntimeError("classeur indisponible")
        self.regles_vues.append(regles)
        return Resultat("OK", {"lignes": [{"prix_unitaire": 1250}, {"prix_unitaire": 450}], "sous_total": 2950, "frais": 0, "total": 2950})


async def test_le_panier_du_direct_porte_le_prix_de_chaque_ligne_et_le_total_en_centimes_sans_rien_de_l_appelant(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    panier = _panier_a_chiffrer(_ligne(1, "Reine", 2, "R1"), _ligne(2, "Tiramisu", 1, "T1"))
    source = _SourceChiffree()
    chiffre = await SourceClasseur._panier_chiffre(source, panier, SimpleNamespace(configurations=None))
    assert [l["prix"] for l in chiffre["lignes"]] == [2500, 450] and chiffre["total"] == 2950  # le prix d'une ligne : prix unitaire x quantité
    await flux.poser_le_panier(cas.a, etab, 5150, chiffre)
    async with client_http() as c:
        r = await c.get(_url(etab, 5150), headers=_cle(cas.cle_a))
    assert r.status_code == 200
    assert r.json() == {"version": 4, "mode": "emporter", "lignes": [{"nom": "Reine", "quantite": 2, "prix": 2500, "sous_ligne": None}, {"nom": "Tiramisu", "quantite": 1, "prix": 450, "sous_ligne": None}], "total": 2950, "zone": None}
    assert "Sophie" not in r.text and "0600000000" not in r.text and "Lilas" not in r.text  # le numéro ne sert qu'au chiffrage (remise qui le reconnaît), jamais rendu


async def test_un_panier_qui_ne_se_chiffre_pas_garde_ses_lignes_sans_prix_et_un_panier_incomplet_n_a_pas_de_total(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    en_panne = await SourceClasseur._panier_chiffre(_SourceChiffree(panne=True), _panier_a_chiffrer(_ligne(1, "Reine", 2, "R1")), SimpleNamespace(configurations=None))
    assert "total" not in en_panne and all("prix" not in l for l in en_panne["lignes"])  # comme avant : jamais un direct qui casse
    incomplet = _panier_a_chiffrer(_ligne(1, "Reine", 2, "R1"), {**_ligne(2, "Pizza", 1, ""), "attente": {"nom": "taille"}})
    resultat = await SourceClasseur._panier_chiffre(_SourceChiffree(), incomplet, SimpleNamespace(configurations=None))
    assert resultat["total"] is None  # une question reste ouverte : pas de total annoncé
    org_flux = flux._centimes
    assert [org_flux(x) for x in (250, None, -1, 2.5, "250", True)] == [250, None, None, None, None, None]


async def test_le_panier_du_direct_porte_la_taille_les_options_et_la_zone_sans_donnee_personnelle(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    """Lot 26, M18 : la sous-ligne (taille, choix, retraits) et le nom de la zone de livraison ; jamais la note libre, ni l'adresse, ni le nom."""
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    ligne = {**_ligne(1, "Regina Mega", 1, "R1"), "taille": "Mega", "choix": [{"nom": "Sauce barbecue", "option_code": "S1", "quantite": 1}], "retires": ["oignons"], "note": "digicode 4521"}
    panier = {**_panier_a_chiffrer(ligne), "zone": {"id": 3, "nom": "Chantilly"}}
    await flux.poser_le_panier(cas.a, etab, 6161, panier)
    async with client_http() as c:
        r = await c.get(_url(etab, 6161), headers=_cle(cas.cle_a))
    assert r.status_code == 200
    assert r.json()["lignes"] == [{"nom": "Regina Mega", "quantite": 1, "prix": None, "sous_ligne": "Mega, Sauce barbecue, sans oignons"}]
    assert r.json()["zone"] == "Chantilly"
    for personnel in ("Sophie", "0600000000", "Lilas", "digicode", "4521"):
        assert personnel not in r.text
