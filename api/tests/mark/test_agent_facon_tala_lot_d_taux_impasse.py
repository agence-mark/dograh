"""[.mark] agent-facon-tala, suite des résultats fermés, lot D : surveiller la sortie d'impasse.

Le garde-fou d'impasse (``sortie_d_impasse.py``) reprend le modèle deux fois (temps 1 et 2) avant de changer l'étape.
Un modèle repris qui se corrige seul ne laissait aucune trace durable : on ne savait pas si la sortie d'impasse servait ou
masquait un défaut. D1 compte ces reprises dans la fiche ; D2 les lit par agent (``GET /tri/taux``), cloisonné à l'organisation.

| Test | Ce qu'il prouve |
|---|---|
| D1 temps | le compteur monte aux temps 1 et 2, pas au temps 3, et vaut zéro dans un état neuf |
| D1 mémoire | il n'est remis à zéro ni par le changement d'étape ni par le temps 3 |
| D1 clavier | une vraie session clavier où l'agent se redit : le compteur est dans la fiche du run |
| D2 pures | une part n'existe pas sans dénominateur (jamais un zéro qui ferait croire à un taux nul) ; 7 ou 30 jours |
| D2 route | taux justes sur un jeu connu, période respectée, runs sans compteur hors de la part des reprises |
| D2 cloisonnement | un run d'une autre organisation n'est jamais compté, et ne donne aucune ligne à l'autre |
"""

import pytest

from api.services.tri import donnees
from api.services.workflow.sortie_d_impasse import CLE_IMPASSE
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_passages_fiables_signalements_et_alertes import _run
from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide
from api.tests.mark.test_sortie_d_impasse import (
    AUTRE,
    REPLIQUE,
    Banc,
    _entrer,
    _noeud,
    _repliques,
)

# --------------------------------------------------------------------------- #
# D1 : le compteur de reprises
# --------------------------------------------------------------------------- #


async def test_d1_le_compteur_monte_aux_temps_1_et_2_pas_au_temps_3():
    banc = Banc()
    _entrer(banc)
    await _repliques(banc, REPLIQUE)
    assert banc.etat()["reprises"] == 0  # un état neuf porte le compteur : l'appel date d'après lui
    await _repliques(banc, REPLIQUE)  # un seul signe : aucune consigne
    assert banc.etat()["reprises"] == 0
    await _repliques(banc, REPLIQUE)  # temps 1
    assert banc.etat()["temps"] == 1 and banc.etat()["reprises"] == 1
    await _repliques(banc, REPLIQUE)  # temps 2
    assert banc.etat()["temps"] == 2 and banc.etat()["reprises"] == 2
    await _repliques(banc, REPLIQUE)  # temps 3 : le code change l'étape, ce n'est plus une reprise
    assert banc.etat()["impasses"] == 1 and banc.etat()["reprises"] == 2


async def test_d1_jamais_remis_a_zero_ni_par_le_temps_3_ni_par_le_changement_d_etape():
    banc = Banc()
    _entrer(banc)
    for _ in range(5):  # jusqu'au temps 3
        await _repliques(banc, REPLIQUE)
    assert banc.etat()["reprises"] == 2 and banc.etat()["signes"] == 0 and banc.etat()["temps"] == 0
    # une autre étape : les signes repartent, les reprises restent
    banc.noeud = _noeud("n2")
    banc.active_agent.current_node = banc.noeud
    _entrer(banc)
    assert banc.etat()["signes"] == 0 and banc.etat()["reprises"] == 2
    for _ in range(3):
        await _repliques(banc, AUTRE)  # le 2e signe pose le temps 1 dans la seconde étape
    assert banc.etat()["reprises"] == 3


@pytest.mark.asyncio
async def test_d1_au_clavier_le_compteur_est_dans_la_fiche_du_run(db_session, async_session, test_client_factory):
    user, workflow = await _monter(db_session, async_session, FICHE)
    redite = "Je cherche les disponibilités pour vous."
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), *(_dit(_texte(redite)) for _ in range(4))],
        ["bonjour", "alors ?", "toujours rien ?", "vous êtes là ?"],
    )
    etat = reponses[-1]["checkpoint"]["gathered_context"].get(CLE_IMPASSE) or {}
    assert etat.get("temps", 0) >= 2 and etat.get("reprises") == etat.get("temps"), etat


# --------------------------------------------------------------------------- #
# D2 : la lecture par agent
# --------------------------------------------------------------------------- #


def test_d2_une_part_n_existe_pas_sans_denominateur():
    assert donnees.part(1, 4) == 0.25 and donnees.part(0, 4) == 0.0
    assert donnees.part(0, 0) is None  # aucun appel qui porte le compteur : pas de taux, jamais « 0 % »
    ligne = donnees.ligne_de_taux(1, "A", 3, 0, 0, 0)
    assert ligne["part_impasse"] == 0.0 and ligne["part_reprise"] is None and ligne["appels_avec_compteur"] == 0


def test_d2_les_periodes_permises_sont_7_et_30_jours():
    assert [donnees.jours_des_taux(j) for j in (7, 30, 1, 10, 20, 29)] == [7, 30, 7, 7, 30, 30]


async def _jeu(db_session, async_session, user, workflow):
    def impasse(**champs):
        return {CLE_IMPASSE: champs}

    return [
        await _run(db_session, async_session, user, workflow, impasse(impasses=1, reprises=2)),
        await _run(db_session, async_session, user, workflow, impasse(impasses=0, reprises=1)),
        await _run(db_session, async_session, user, workflow, impasse(impasses=0, reprises=0)),
        await _run(db_session, async_session, user, workflow, {"extracted_variables": {"a": 1}}),
        await _run(db_session, async_session, user, workflow, impasse(impasses=0)),  # d'avant le compteur
        await _run(db_session, async_session, user, workflow, impasse(impasses=1, reprises=1), jours=10),
        await _run(db_session, async_session, user, workflow, impasse(impasses=1, reprises=1), jours=31),
    ]


async def test_d2_taux_justes_sur_un_jeu_connu_et_periode_respectee(db_session, async_session, test_client_factory):
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    await _jeu(db_session, async_session, user, workflow)
    async with test_client_factory(user) as client:
        sept = (await client.get("/api/v1/tri/taux", params={"jours": 7})).json()
        trente = (await client.get("/api/v1/tri/taux", params={"jours": 30})).json()
        autre = (await client.get("/api/v1/tri/taux", params={"jours": 10})).json()
    (ligne7,) = sept["lignes"]
    assert sept["jours"] == 7 and ligne7["workflow_id"] == workflow.id
    # 5 appels sur 7 jours ; 1 avec impasse ; 3 portent le compteur ; 1 reprise sans impasse (les runs d'avant le compteur
    # et celui sans impasse ne comptent jamais comme « zéro reprise »)
    assert (ligne7["appels"], ligne7["avec_impasse"], ligne7["appels_avec_compteur"], ligne7["avec_reprise_sans_impasse"]) == (5, 1, 3, 1)
    assert ligne7["part_impasse"] == 0.2 and ligne7["part_reprise"] == round(1 / 3, 4)
    (ligne30,) = trente["lignes"]
    assert trente["jours"] == 30
    # le run de 10 jours s'ajoute ; celui de 31 jours reste hors de la borne
    assert (ligne30["appels"], ligne30["avec_impasse"], ligne30["appels_avec_compteur"], ligne30["avec_reprise_sans_impasse"]) == (6, 2, 4, 1)
    assert autre["jours"] == 7  # 10 jours : ramené à la période permise la plus proche


async def test_d2_un_run_d_une_autre_organisation_n_est_jamais_compte(db_session, async_session, test_client_factory):
    user_a, workflow_a = await _monter(db_session, async_session, dict(FICHE))
    user_b, workflow_b = await _monter(db_session, async_session, dict(FICHE))
    await _jeu(db_session, async_session, user_a, workflow_a)
    await _run(db_session, async_session, user_b, workflow_b, {CLE_IMPASSE: {"impasses": 1, "reprises": 3}})
    async with test_client_factory(user_b) as client:
        lignes_b = (await client.get("/api/v1/tri/taux", params={"jours": 30})).json()["lignes"]
    assert [(x["workflow_id"], x["appels"], x["avec_impasse"], x["appels_avec_compteur"]) for x in lignes_b] == [
        (workflow_b.id, 1, 1, 1)
    ]
    async with test_client_factory(user_a) as client:
        lignes_a = (await client.get("/api/v1/tri/taux", params={"jours": 30})).json()["lignes"]
    assert [x["workflow_id"] for x in lignes_a] == [workflow_a.id] and lignes_a[0]["appels"] == 6


async def test_d2_une_organisation_sans_appel_n_a_aucune_ligne(db_session, async_session, test_client_factory):
    user, _ = await _monter(db_session, async_session, dict(FICHE))
    async with test_client_factory(user) as client:
        corps = (await client.get("/api/v1/tri/taux")).json()
    assert corps == {"jours": 7, "lignes": []}
