"""[.mark] Module Restauration, lot 10, étape 1 : l'envoi d'une commande à HubRise en tâche de fond, la recherche avant renvoi et le secours.

Vraies bases de clients, vrai Redis, vraie base de Dograh ; la caisse est un transport ENREGISTRÉ (aucun appel réel).

| Test | Ce qu'il prouve |
|---|---|
| envoi | la commande part UNE fois avec NOTRE numéro en ``private_ref`` ; ``ref_fournisseur`` est écrit ; le statut avance par le chemin fermé et le flux le dit |
| réponse perdue | l'envoi est parti, la réponse s'est perdue : la reprise CHERCHE par notre numéro et ne renvoie pas (jamais deux commandes) |
| panne | l'envoi n'aboutit pas : la commande reste à reprendre, la reprise est espacée ; au dernier essai : ``echec`` et secours avec la commande jointe, UNE fois |
| refus | une caisse qui refuse (422) : ``refusee`` et secours tout de suite |
| jeton refusé | le 401 passe la liaison à « rompue » et laisse la commande à reprendre |
| cloisonnement | le numéro d'un autre établissement n'envoie rien |
| sans liaison | un établissement sans caisse : le classeur est maître, rien n'est envoyé nulle part |
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import httpx
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.db.bases_clients.horloge import horloge, remplacer
from api.services.restauration import envoi_caisse as ec
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import (  # noqa: F401
    _brancher,
    _caisse_enregistree,
    _corps,
    _etablissements_propres,
    _evenements,
    application_configuree,
)


async def _commande(base: str, etab: int, *, statut: str = "nouvelle", tentatives: int = 0) -> str:
    numero = uuid.uuid4()
    c = await schema.connecter(base)
    try:
        await c.execute(
            "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, telephone, tentatives) VALUES ($1, 'C7', $2, 'emporter', 1250, $3, '+33600000001', $4)",
            numero, etab, statut, tentatives,
        )
        await c.execute(
            "INSERT INTO mark.resto_commande_ligne (numero, site_id, rang, code_caisse, nom, prix_unitaire, quantite) VALUES ($1, $2, 1, 'REINE-S', 'Reine', 1250, 1)", numero, etab
        )
    finally:
        await c.close()
    return str(numero)


class CaisseQuiRegistre:
    """Une caisse avec une mémoire : elle garde les commandes reçues (par leur ``private_ref``) ; ``perd_la_reponse`` : elle enregistre PUIS la réponse se perd."""

    def __init__(self, *, mode: str = "ok"):
        self.mode, self.recues, self.demandes = mode, {}, []
        self.transport = httpx.MockTransport(self)

    def __call__(self, r: httpx.Request) -> httpx.Response:
        self.demandes.append(r)
        if r.url.path == "/v1/location/orders" and r.method == "POST":
            corps = json.loads(r.content)
            if self.mode == "panne":
                return httpx.Response(503, json={})
            if self.mode == "jeton_faux":
                return httpx.Response(401, json=_corps("18-erreur-jeton-faux.json"))
            if self.mode == "refus":
                return httpx.Response(422, json=_corps("17-erreur-formule-absente.json"))
            ordre = {**_corps("12-commande-simple.json"), "id": "caisse-" + corps["private_ref"][:8], "private_ref": corps["private_ref"], "status": "new"}
            self.recues[corps["private_ref"]] = ordre
            if self.mode == "perd_la_reponse":
                self.mode = "ok"  # la reprise, elle, passera
                raise httpx.ReadTimeout("la réponse s'est perdue")
            return httpx.Response(200, json=ordre)
        if r.url.path == "/v1/location/orders" and r.method == "GET":
            return httpx.Response(200, json=[o for p, o in self.recues.items() if p == r.url.params.get("private_ref")])
        return httpx.Response(404, json={})

    def posts(self) -> int:
        return len([r for r in self.demandes if r.method == "POST" and r.url.path == "/v1/location/orders"])


async def _etablissement_branche(db_session, seconde_base):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    await _brancher(cas, etab, cas.a, cas.base_a, _caisse_enregistree(pdv="pdv-envoi-" + uuid.uuid4().hex[:6]), cas.admin.id)
    return cas, etab


async def _etat(base: str, numero: str) -> dict:
    c = await schema.connecter(base)
    try:
        return dict(await c.fetchrow("SELECT statut, ref_fournisseur, tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)))
    finally:
        await c.close()


class Secours:
    def __init__(self):
        self.messages: list[tuple[int | None, str, str]] = []

    async def __call__(self, organisation, sujet, texte):
        self.messages.append((organisation, sujet, texte))


async def test_la_commande_part_une_fois_avec_notre_numero_et_la_caisse_lui_donne_une_ref(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    caisse = CaisseQuiRegistre()
    secours = Secours()
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert issue.issue == "envoyee" and issue.pour_l_outil == "TRANSMISE" and caisse.posts() == 1
    corps = json.loads([r for r in caisse.demandes if r.method == "POST"][0].content)
    assert corps["private_ref"] == numero and corps["items"][0]["sku_ref"] == "REINE-S"
    etat = await _etat(cas.base_a, numero)
    assert (etat["statut"], etat["ref_fournisseur"], etat["tentatives"]) == ("envoyee", "caisse-" + numero[:8], 1)
    assert ("commande.statut", {"numero": numero, "de": "nouvelle", "vers": "envoyee", "source": "agent"}) in await _evenements(cas.a, etab)
    assert secours.messages == []
    # un second geste sur la même commande ne renvoie rien (la commande a déjà une ref ; la recherche la retrouve)
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert caisse.posts() == 1


async def test_une_reponse_perdue_n_envoie_pas_deux_fois_la_commande(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    caisse = CaisseQuiRegistre(mode="perd_la_reponse")
    secours = Secours()
    premier = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert premier.issue == "a_reprendre" and numero in caisse.recues and caisse.posts() == 1  # la caisse l'a, nous ne le savons pas
    assert (await _etat(cas.base_a, numero))["statut"] == "envoyee" and (await _etat(cas.base_a, numero))["ref_fournisseur"] is None
    reprise = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert reprise.issue == "envoyee" and reprise.renvoi_evite is True
    assert caisse.posts() == 1  # JAMAIS deux commandes : la recherche par notre numéro l'a retrouvée
    assert (await _etat(cas.base_a, numero))["ref_fournisseur"] == "caisse-" + numero[:8] and secours.messages == []


async def test_une_caisse_en_panne_laisse_a_reprendre_puis_echec_et_un_seul_secours_avec_la_commande(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    caisse = CaisseQuiRegistre(mode="panne")
    secours = Secours()
    for essai in range(1, ec.TENTATIVES_MAX):
        issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
        assert issue.issue == "a_reprendre"
        assert (await _etat(cas.base_a, numero))["statut"] == "envoyee" and secours.messages == [], essai  # à reprendre, personne n'est dérangé
    dernier = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert dernier.issue == "a_reprendre"
    assert (await _etat(cas.base_a, numero))["statut"] == "echec"
    assert len(secours.messages) == 1  # UNE alerte, commande jointe
    organisation, sujet, texte = secours.messages[0]
    assert organisation == cas.a and "C7" in sujet and "1 x Reine" in texte and "+33600000001" in texte and "12,50 €" in texte
    # une commande en échec n'est plus envoyée : plus d'appel, plus d'alerte
    apres = caisse.posts()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert caisse.posts() == apres and len(secours.messages) == 1
    assert ("commande.statut", {"numero": numero, "de": "envoyee", "vers": "echec", "source": "agent"}) in await _evenements(cas.a, etab)


async def test_un_refus_de_la_caisse_est_refusee_et_le_secours_part_tout_de_suite(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=CaisseQuiRegistre(mode="refus").transport, secours=secours)
    assert issue.issue == "refusee" and (await _etat(cas.base_a, numero))["statut"] == "refusee"
    assert len(secours.messages) == 1 and "refus de la caisse" in secours.messages[0][2]


async def test_un_jeton_refuse_rompt_la_liaison_et_laisse_la_commande_a_reprendre(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=CaisseQuiRegistre(mode="jeton_faux").transport, secours=Secours())
    assert issue.issue == "a_reprendre"
    c = await schema.connecter(cas.base_a)
    try:
        assert (await lia.liaison(c, etab))["etat"] == "rompue"
    finally:
        await c.close()
    assert ("caisse.liaison", {"etat": "rompue"}) in await _evenements(cas.a, etab)


async def test_le_numero_d_un_autre_etablissement_n_envoie_rien_et_sans_liaison_rien_ne_part(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    voisin = cas.sites_a[1]  # sans liaison
    numero_du_voisin = await _commande(cas.base_a, voisin)
    caisse = CaisseQuiRegistre()
    assert await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero_du_voisin, transport=caisse.transport, secours=Secours()) is None
    assert caisse.demandes == []
    # l'établissement voisin n'a pas de caisse : le classeur est maître, la prise « portail » ne contacte personne
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, voisin, numero_du_voisin, transport=caisse.transport, secours=Secours())
    assert issue.issue == "envoyee" and caisse.demandes == []


async def test_la_reprise_est_espacee_selon_le_nombre_d_essais(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    uns = await _commande(cas.base_a, etab, statut="envoyee", tentatives=1)
    trois = await _commande(cas.base_a, etab, statut="envoyee", tentatives=3)
    c = await schema.connecter(cas.base_a)
    try:
        base = horloge(cas.base_a).maintenant()
        for numero in (uns, trois):  # le dernier essai remonte à 5 minutes
            await c.execute("UPDATE mark.resto_commande SET maj_le = $2 WHERE numero = $1", uuid.UUID(numero), base - timedelta(minutes=5))
        with remplacer(cas.base_a, base):
            a_reprendre = await lia.commandes_a_reprendre(c, etab)
        assert a_reprendre == [uns]  # 1 essai : reprise après 2 min ; 3 essais : après 8 min, pas encore
        with remplacer(cas.base_a, base + timedelta(minutes=4)):
            assert set(await lia.commandes_a_reprendre(c, etab)) == {uns, trois}
        autre = await _commande(cas.base_a, cas.sites_a[1], statut="envoyee")
        await c.execute("UPDATE mark.resto_commande SET maj_le = $2 WHERE numero = $1", uuid.UUID(autre), base - timedelta(hours=1))
        with remplacer(cas.base_a, base):
            assert autre not in await lia.commandes_a_reprendre(c, etab)  # une commande d'un autre établissement n'est jamais reprise ici
    finally:
        await c.close()
