"""[.mark] Plan final Partie 1, lot 4 (caisse : n° 95, 96, 98, 99) : ce que la caisse dit et ce qu'elle ne perd pas en silence.

- 95 : les messages de secours citent le numéro court et le téléphone par UNE fonction (``identite_de_la_commande``).
- 96 : le client Redis est partagé par boucle (jamais une connexion par requête) ; ``alerter`` et ``secours_par_defaut`` sont publics.
- 98 : une réponse de la caisse que notre lecture ne sait pas lire laisse la commande « envoyée » (K2) mais une personne est prévenue que le total n'a pas été relu.
- 99 : une mesure perdue ou une panne de lecture part au journal d'erreur.
"""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

from api.services.restauration.caisse import annulation_caisse as AC
from api.services.restauration.caisse import envoi_caisse as EC
from api.services.restauration.caisse.prises import hubrise_liaison
from api.services.restauration.caisse.prises.envoi import EnvoiApplique, _avec_l_ecart_de_total
from api.services.restauration.caisse.prises.prise import ResultatEnvoi
from api.services.restauration.mesures import mesures as MESURES
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import application_configuree  # noqa: F401
from api.tests.mark.test_restauration_envoi_caisse import CaisseQuiRegistre, Secours, _commande, _etablissement_branche

SANS_NUMERO_COURT = {"numero": "8f0d6c64-6d62-4a42-9c0e-0c1c2c3c4c5c", "mode": "emporter", "total": 1250, "lignes": [], "client": {}}
AVEC = {**SANS_NUMERO_COURT, "numero_court": "C7", "client": {"telephone": "+33600000001"}}


def test_les_quatre_messages_citent_le_numero_court_et_le_telephone_par_la_meme_ecriture():
    textes = [
        EC.texte_du_secours(SANS_NUMERO_COURT, "x"), EC.texte_de_la_commande_restee_nouvelle(SANS_NUMERO_COURT, 5),
        EC.texte_de_l_ecart_de_total(SANS_NUMERO_COURT, 1250, 1300), AC.texte_de_l_annulation_perdue(SANS_NUMERO_COURT, 5),
        EC.texte_du_total_non_relu(SANS_NUMERO_COURT),
    ]
    for sujet, corps in textes:
        assert "8f0d6c64" in sujet and "Téléphone : -" in corps
    for sujet, corps in (EC.texte_du_secours(AVEC, "x"), AC.texte_de_l_annulation_perdue(AVEC, 5)):
        assert "C7" in sujet and "+33600000001" in corps


def test_le_secours_et_l_alerte_sont_publics_et_importes_sans_nom_prive():
    assert callable(EC.alerter) and callable(EC.secours_par_defaut)
    assert not hasattr(EC, "_alerter") and not hasattr(EC, "_secours_par_defaut")


async def test_le_client_redis_est_le_meme_pour_tous_les_appels_d_une_boucle():
    premier, second = await hubrise_liaison.redis_partage(), await hubrise_liaison.redis_partage()
    assert premier is second
    autre = await asyncio.get_running_loop().run_in_executor(None, lambda: asyncio.run(hubrise_liaison.redis_partage()))
    assert autre is not premier


def test_une_reponse_illisible_se_marque_total_non_relu_sans_changer_l_issue():
    applique = EnvoiApplique("envoyee", "envoyee", "TRANSMISE", ResultatEnvoi("ENVOYEE", lecture_impossible=True))
    marque = _avec_l_ecart_de_total(applique, 1250, applique.resultat)
    assert marque.total_non_relu and marque.issue == "envoyee"
    normal = _avec_l_ecart_de_total(applique, 1250, ResultatEnvoi("ENVOYEE", total_caisse=1250))
    assert not normal.total_non_relu


class CaisseQuiRepondAuHasard(CaisseQuiRegistre):
    """Une caisse qui prend la commande puis répond un corps que notre lecture ne sait pas lire."""

    def __call__(self, r: httpx.Request) -> httpx.Response:
        if r.url.path == "/v1/location/orders" and r.method == "POST":
            self.demandes.append(r)
            return httpx.Response(200, json={"id": "caisse-1", "status": "new", "total": ["pas", "un", "montant"], "items": 5})
        return super().__call__(r)


async def test_une_reponse_que_notre_lecture_ne_sait_pas_lire_garde_la_commande_envoyee_et_previent_une_personne(
    db_session, seconde_base, sans_preparation_des_organisations, application_configuree  # noqa: F811
):
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours, journal = Secours(), []
    sortie = logger.add(lambda m: journal.append(m.record), level="ERROR")
    try:
        issue = await EC.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=CaisseQuiRepondAuHasard().transport, secours=secours)
    finally:
        logger.remove(sortie)
    assert issue.issue == "envoyee" and issue.total_non_relu
    assert len(secours.messages) == 1 and "total non relu" in secours.messages[0][1]
    assert any("our reading of its answer failed" in r["message"] for r in journal)


def test_une_mesure_perdue_part_au_journal_d_erreur(monkeypatch):
    def casse(*_a, **_k):
        raise RuntimeError("fiche cassée")

    monkeypatch.setattr(MESURES.mesures, "ecrire", casse)
    journal = []
    sortie = logger.add(lambda m: journal.append(m.record), level="ERROR")
    try:
        MESURES.de_la_reservation(object(), "reserver", {"statut": "ENREGISTREE"})
        MESURES.de_la_commande(object(), "enregistrer", {"statut": "ENREGISTREE"})
    finally:
        logger.remove(sortie)
    assert len(journal) == 2


def test_le_resolveur_de_prise_d_un_essai_est_rendu_a_la_sortie_meme_sur_une_erreur():
    from api.services.restauration.caisse import statut

    async def un_resolveur(_o, _e):
        return None

    assert statut._resolveur is None
    try:
        with statut.remplacer_le_resolveur(un_resolveur):
            assert statut._resolveur is un_resolveur
            raise RuntimeError("l'essai échoue")
    except RuntimeError:
        pass
    assert statut._resolveur is None


async def test_le_lieu_et_l_instantane_d_un_appel_sont_poses_une_fois_et_donnes_aux_deux_connexions(monkeypatch):
    """N° 102 : un seul endroit pose le lieu et l'instantané (le geste d'outil et le chargement l'appellent)."""
    from types import SimpleNamespace

    from api.services.restauration.appel_et_memoire import memoire_de_l_appel as M

    lectures = []

    async def cle(_ctx):
        return "base", "cle"

    async def identifiant(_connexion, _cle):
        lectures.append(1)
        return 7

    monkeypatch.setattr(M, "base_et_cle_de_l_appel", cle)
    monkeypatch.setattr(M, "identifiant_de_l_etablissement", identifiant)
    appel = M.AppelOuvert("base")
    appel.connexion = SimpleNamespace(instantane=None)
    chargement = SimpleNamespace(instantane=None)
    ctx = SimpleNamespace(organization_id=3)
    await M._poser_le_lieu_et_l_instantane(appel, chargement, ctx)
    await M._poser_le_lieu_et_l_instantane(appel, appel.connexion, ctx)
    assert lectures == [1] and appel.lieu.etablissement_id == 7
    assert appel.connexion.instantane is chargement.instantane is appel.instantane
