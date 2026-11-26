"""[.mark] Module Restauration, lot 3 : la prise de test branchée sur ``enregistrer_commande(declencher_envoi=)``, sur une vraie base.

| Test | Ce qu'il prouve |
|---|---|
| de bout en bout | une commande enregistrée est envoyée UNE fois à la prise, relue du classeur (lignes, choix) ; le statut avance par le chemin fermé |
| sans étape acceptée | la prise sans « acceptée » laisse la commande ``recue`` et l'outil rend ``TRANSMISE`` (jamais « acceptée ») |
| profils | pause, rupture, refus : commande ``refusee`` ; panne : reste ``envoyee`` à reprendre, puis reprise réussie ; débordé : heure repoussée |
| rejouable | un second déclenchement n'envoie rien de plus (aucun effet double) |
| anti-doublon | renvoi : la prise qui sait chercher par notre numéro n'est pas ré-envoyée ; la fiche ``notre_table`` l'est (la fiche décide) |
| cloisonnement | le numéro d'un autre établissement n'envoie rien |
| réponse calculée | le profil « refus » dit ``prix_different`` quand le total donné diffère du total recalculé |
| ne casse jamais | une prise qui lève ne casse pas l'enregistrement ; l'échec est au journal et la commande reste à reprendre |
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from api.db.bases_clients import restauration
from api.services.restauration.caisse.prises.envoi import declencheur_vers_la_prise, envoyer_une_commande
from api.services.restauration.caisse.prises.fiches import TEST, TEST_SANS_ACCEPTEE
from api.services.restauration.caisse.prises.prise_essai import MINUTES_DEBORDE, PriseTest, total_recalcule
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce  # noqa: F401


async def _statut(commerce, numero) -> str:
    return (await restauration.statut_commande(commerce.c, commerce.a, numero=numero)).faits["commandes"][0]["statut"]


async def _ecrite_par_l_agent_appel_fini(commerce, b) -> str:
    """Une commande de l'agent (sans envoi donné) est écrite ``retenue`` ; la fin de l'appel la fait passer ``nouvelle`` avant l'envoi (§ 17)."""
    numero = (await restauration.enregistrer_commande(commerce.c, commerce.a, b, f"relu-{b['appel_id']}")).faits["numero"]
    assert (await restauration.changer_statut(commerce.c, commerce.a, numero, "retenue", "nouvelle", "agent")).statut == "OK"
    return numero


async def _enregistrer(commerce, prise, **plus):
    r = await restauration.enregistrer_commande(
        commerce.c, commerce.a, brouillon(**plus), "relu", declencher_envoi=declencheur_vers_la_prise(commerce.c, commerce.a, prise)
    )
    assert r.statut == "ENREGISTREE", r
    return r.faits["numero"]


async def test_une_commande_enregistree_part_une_fois_vers_la_prise_et_avance_par_le_chemin_ferme(commerce):
    prise = PriseTest()
    numero = await _enregistrer(commerce, prise)
    assert await _statut(commerce, numero) == "acceptee"
    assert len(prise.recues) == 1
    envoyee = prise.recues[0]
    assert envoyee["numero"] == numero and envoyee["total"] == 2380 and total_recalcule(envoyee) == 2380
    assert [(l["code_caisse"], l["quantite"]) for l in envoyee["lignes"]] == [("PIZ-MARGHERITA-NORMALE", 2), ("BOI-COCA-COLA-33-CL", 1)]
    assert envoyee["client"]["telephone"] == "+33612345678" and envoyee["paiement"]["moyens"][0]["montant"] == 2380
    assert (await commerce.c.fetchval("SELECT tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero))) == 1


async def test_une_prise_sans_etape_acceptee_laisse_recue_et_l_outil_rend_transmise(commerce):
    prise = PriseTest(capacites=TEST_SANS_ACCEPTEE)
    numero = await _enregistrer(commerce, prise)
    assert await _statut(commerce, numero) == "recue"
    # un second geste identique ne change rien, et l'issue dit TRANSMISE, jamais « acceptée »
    suivante = await _ecrite_par_l_agent_appel_fini(commerce, brouillon(appel_id="appel-2"))
    envoi = await envoyer_une_commande(commerce.c, commerce.a, prise, suivante)
    assert envoi.issue == "envoyee" and envoi.statut == "recue" and envoi.pour_l_outil == "TRANSMISE"
    avec = await envoyer_une_commande(commerce.c, commerce.a, PriseTest(), await _ecrite_par_l_agent_appel_fini(commerce, brouillon(appel_id="appel-3")))
    assert avec.pour_l_outil == "OK" and avec.statut == "acceptee"


@pytest.mark.parametrize(
    "profil, ruptures, raison",
    [("pause", None, "restaurant_ferme"), ("rupture", {"BOI-COCA-COLA-33-CL"}, "autre"), ("rupture", None, "autre")],
)
async def test_pause_et_rupture_de_la_caisse_refusent_la_commande(commerce, profil, ruptures, raison):
    prise = PriseTest(profil, ruptures=ruptures)
    numero = await _enregistrer(commerce, prise)
    assert await _statut(commerce, numero) == "refusee" and prise.recues == []
    envoi = await envoyer_une_commande(commerce.c, commerce.a, prise, numero)
    assert envoi.issue == "fait" and envoi.statut == "refusee"  # rejoué : rien de plus
    assert raison  # la raison fermée est portée par le résultat d'envoi (cas direct ci-dessous)
    direct = await PriseTest(profil, ruptures=ruptures).envoyer_commande({"numero": numero, "lignes": [{"code_caisse": "BOI-COCA-COLA-33-CL", "prix_unitaire": 1}]})
    assert (direct.statut, direct.raison) == ("REFUSEE", raison)


async def test_une_rupture_d_un_autre_article_ne_refuse_pas(commerce):
    prise = PriseTest("rupture", ruptures={"DES-TIRAMISU"})
    numero = await _enregistrer(commerce, prise)
    assert await _statut(commerce, numero) == "acceptee"


async def test_une_panne_laisse_la_commande_a_reprendre_puis_la_reprise_passe(commerce):
    prise = PriseTest("panne")
    numero = await _enregistrer(commerce, prise)
    assert await _statut(commerce, numero) == "envoyee" and prise.recues == []
    prise.profil = "tout_va_bien"  # la caisse revient
    envoi = await envoyer_une_commande(commerce.c, commerce.a, prise, numero)
    assert envoi.issue == "envoyee" and await _statut(commerce, numero) == "acceptee"
    assert len(prise.recues) == 1  # envoyée une seule fois, malgré deux passages
    assert (await commerce.c.fetchval("SELECT tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero))) == 1


async def test_une_reponse_lente_passe_et_un_debord_repousse_l_heure(commerce):
    assert await _statut(commerce, await _enregistrer(commerce, PriseTest("lente"))) == "acceptee"
    prise = PriseTest("deborde")
    numero = await _enregistrer(commerce, prise, appel_id="appel-d")
    assert await _statut(commerce, numero) == "recue"
    commande = prise.recues[0]
    resultat = await prise.faire_envoyer(commande)
    assert resultat.heure_annoncee == commande["heure_annoncee"] + __import__("datetime").timedelta(minutes=MINUTES_DEBORDE)


async def test_un_second_declenchement_n_envoie_rien_de_plus(commerce):
    prise = PriseTest()
    numero = await _enregistrer(commerce, prise)
    for _ in range(3):
        assert (await envoyer_une_commande(commerce.c, commerce.a, prise, numero)).issue == "fait"
    assert len(prise.recues) == 1


async def test_un_renvoi_cherche_d_abord_par_notre_numero_quand_la_fiche_le_dit(commerce):
    prise = PriseTest("panne")
    numero = await _enregistrer(commerce, prise)  # envoyee, la caisse n'a rien répondu...
    commande = (await restauration.statut_commande(commerce.c, commerce.a, numero=numero)).faits["commandes"][0]
    assert commande["statut"] == "envoyee"
    # ... mais elle l'avait bien reçue (réponse perdue) : elle la connaît par notre numéro
    from api.db.bases_clients.restauration_commande import commande_complete

    prise.recues.append(await commande_complete(commerce.c, commerce.a, numero))
    envoi = await envoyer_une_commande(commerce.c, commerce.a, prise, numero)
    assert envoi.renvoi_evite is True and len(prise.recues) == 1 and await _statut(commerce, numero) == "acceptee"


async def test_la_fiche_decide_sans_recherche_le_renvoi_part_et_le_doublon_se_voit(commerce):
    sans_recherche = PriseTest("panne", capacites=dataclasses.replace(TEST, anti_doublon="notre_table"))
    numero = await _enregistrer(commerce, sans_recherche)
    from api.db.bases_clients.restauration_commande import commande_complete

    sans_recherche.recues.append(await commande_complete(commerce.c, commerce.a, numero))
    sans_recherche.profil = "tout_va_bien"
    envoi = await envoyer_une_commande(commerce.c, commerce.a, sans_recherche, numero)
    assert envoi.renvoi_evite is False and len(sans_recherche.recues) == 2  # le doublon est visible : c'est la règle de CETTE fiche


async def test_le_numero_d_un_autre_etablissement_n_envoie_rien(commerce):
    prise = PriseTest()
    numero = await _enregistrer(commerce, prise)
    autre = PriseTest()
    envoi = await envoyer_une_commande(commerce.c, commerce.b, autre, numero)
    assert envoi.issue == "fait" and envoi.statut is None and autre.recues == []
    assert (await envoyer_une_commande(commerce.c, commerce.a, autre, "pas-un-numero")).issue == "fait"


async def test_le_profil_refus_calcule_la_raison_depuis_la_demande():
    commande = {"numero": "n", "lignes": [{"code_caisse": "A", "prix_unitaire": 1000, "quantite": 2}], "frais": 200, "remises": [{"nom": "x", "montant": 100}], "total": 2100}
    assert total_recalcule(commande) == 2100
    assert (await PriseTest("refus").envoyer_commande(commande)).raison == "autre"  # total juste : refus de la caisse
    assert (await PriseTest("refus").envoyer_commande({**commande, "total": 999})).raison == "prix_different"
    avec_choix = {"lignes": [{"prix_unitaire": 1000, "quantite": 2, "choix": [{"prix": 150, "quantite": 1}]}]}
    assert total_recalcule(avec_choix) == 2300


async def test_une_prise_qui_leve_ne_casse_jamais_l_enregistrement(commerce):
    class Cassee(PriseTest):
        async def faire_envoyer(self, commande):
            raise RuntimeError("boum")

    numero = await _enregistrer(commerce, Cassee())
    assert await _statut(commerce, numero) == "envoyee"
    # une prise qui lève au rendu d'une commande inconnue n'est même pas appelée : le déclencheur ne lève jamais
    await declencheur_vers_la_prise(commerce.c, commerce.a, Cassee())(uuid.uuid4())


async def test_un_passage_deja_fait_par_un_autre_travail_n_envoie_jamais_une_seconde_fois(commerce, monkeypatch):
    """Revue de clôture (1) : deux travaux lisent la commande « nouvelle » ; celui dont le passage rend DEJA_FAIT (l'autre l'a fait et
    envoie) ne poste rien : jamais deux commandes en cuisine."""
    from types import SimpleNamespace

    prise = PriseTest()
    numero = await _ecrite_par_l_agent_appel_fini(commerce, brouillon())
    assert await _statut(commerce, numero) == "nouvelle"

    async def deja_fait(*a, **k):
        return SimpleNamespace(statut="DEJA_FAIT", faits={"statut_actuel": "envoyee"})

    monkeypatch.setattr(restauration, "changer_statut", deja_fait)
    resultat = await envoyer_une_commande(commerce.c, commerce.a, prise, numero)
    assert resultat.issue == "fait" and resultat.statut == "envoyee"
    assert prise.recues == []
