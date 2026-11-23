"""[.mark] Module Restauration, lot 11 : le module au registre et son signal d'allumage.

| Test | Ce qu'il prouve |
|---|---|
| registre | le module « restauration » existe ; ses outils (réservation, service) lui appartiennent ; ceux de la commande restent au module ``commande`` |
| signal | un outil de commande, de réservation ou de service sur une étape l'allume ; aucun outil de ces trois : éteint ; la commande COUPÉE (son interrupteur) n'allume rien |
| outils | allumer le module ne retire ni n'ajoute jamais un outil à l'appel (réservation et service jamais filtrés, commande suit son interrupteur) |
| purge | de bout en bout : un agent qui porte le module est écrit dans la base du client (``mark.module_agent``), la purge de nuit le voit et vide ses copies d'appel |
"""

from __future__ import annotations

from datetime import timedelta

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.modules import ecrire_agents_des_modules, ecrire_catalogue
from api.db.bases_clients.restauration_purge import agents_du_module
from api.services.modules import registre
from api.services.modules.etat import actif_sur, modules_actifs, outil_d_un_module_coupe
from api.services.modules.lecture import catalogue_pour_la_base
from api.services.restauration.appel_et_memoire import conservation
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401
from api.tests.mark.test_conservation_appels import MAINTENANT, _relire, _run, monde, stockage  # noqa: F401


class _Outil:
    def __init__(self, connecteur):
        self.category = "integration"
        self.definition = {"config": {"connecteur": connecteur, "action": "x"}}


def test_le_module_restauration_est_au_registre_et_ses_outils_ont_un_seul_proprietaire():
    module = registre.PAR_CODE["restauration"]
    assert module.interrupteur is None and module.cles_de_l_agent() == ()
    assert registre.module_du_connecteur("reservation") is module
    assert registre.module_du_connecteur("service") is module
    # Les outils de la commande restent au module ``commande`` : son interrupteur les garde.
    assert registre.module_du_connecteur("commande") is registre.PAR_CODE["commande"]
    assert module.signal == ("commande",)
    assert len({m.code for m in registre.MODULES}) == len(registre.MODULES)


def test_un_outil_de_commande_reservation_ou_service_allume_le_module():
    module = registre.PAR_CODE["restauration"]
    # La commande est allumée par défaut chez un agent qui porte ses outils (``commande_sur_catalogue`` éteint par défaut : on l'allume).
    allume = {"commande_sur_catalogue": True}
    assert actif_sur(module, allume, [_Outil("commande")]) is True
    assert actif_sur(module, {}, [_Outil("reservation")]) is True
    assert actif_sur(module, {}, [_Outil("service")]) is True
    assert actif_sur(module, allume, [_Outil("equipe"), _Outil("planificateur")]) is False
    assert actif_sur(module, allume, []) is False
    assert "restauration" in modules_actifs(allume, [_Outil("commande")])
    assert "restauration" not in modules_actifs(allume, [_Outil("equipe")])


def test_la_commande_coupee_n_allume_pas_le_module_et_aucun_outil_n_est_filtre_en_plus():
    module = registre.PAR_CODE["restauration"]
    coupe = {"commande_sur_catalogue": False}
    assert actif_sur(module, coupe, [_Outil("commande")]) is False, "un module coupé n'allume rien"
    # Réservation et service n'ont pas d'interrupteur : jamais retirés de l'appel, comme avant le lot.
    assert outil_d_un_module_coupe(_Outil("reservation"), coupe) is False
    assert outil_d_un_module_coupe(_Outil("service"), {}) is False
    # La commande suit toujours SON interrupteur.
    assert outil_d_un_module_coupe(_Outil("commande"), coupe) is True
    assert outil_d_un_module_coupe(_Outil("commande"), {"commande_sur_catalogue": True}) is False


async def test_l_agent_qui_porte_le_module_est_vu_par_la_purge_de_nuit(monde, async_session, db_session, stockage, base_prete):
    """Avant le lot, aucune ligne « restauration » n'existait dans ``mark.module`` : la purge ne voyait aucun agent."""
    c = await schema.connecter(base_prete)
    proprietaire = await schema.connecter_proprietaire(base_prete)
    try:
        await ecrire_catalogue(c, catalogue_pour_la_base())
        assert await c.fetchval("SELECT count(*) FROM mark.module WHERE code = 'restauration'") == 1
        agent = await proprietaire.fetchval("INSERT INTO mark.agent (dograh_workflow_id, nom) VALUES ($1, 'Agent') RETURNING id", monde.agent_a.id)
        assert agent
        assert await agents_du_module(c) == []
        # Ce que ``synchroniser_modules`` écrit : « utilisé par », calculé d'après le registre.
        await ecrire_agents_des_modules(c, {"restauration": [monde.agent_a.id]})
        assert await agents_du_module(c) == [monde.agent_a.id]
        vieux = await _run(async_session, monde.agent_a, jours=40)
    finally:
        await c.close()
        await proprietaire.close()
    from api.db.bases_clients import horloge

    with horloge.remplacer(base_prete, MAINTENANT):
        sortie = await conservation.purger_une_organisation_du_module(monde.org_a.id, base_prete)
    assert sortie["agents"] == [monde.agent_a.id] and sortie["copies"]["texte"] == 1
    assert (await _relire(db_session, vieux.id)).gathered_context == {}
    assert timedelta(days=30)  # (la durée est celle de la règle E-10, lue par la tâche)
