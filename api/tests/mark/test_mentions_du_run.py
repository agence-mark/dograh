"""[.mark] Non-regression test of the sub-part « Mentions » of the run window (chantier l-agent-collegue, L8).

The question this file answers (R1):

    After a REAL after-call that wrote the mentions of a call, does the route of the run's
    section « After the call » return them (the person's name, the source, the certainty), with
    what the agent did for the team and the record's verdict -- read for its own organization
    only, nothing for another one?
"""

from __future__ import annotations

from unittest.mock import patch

from api.schemas.base_client import Equipe, Personne
from api.services.equipe.vue_du_run import actions_pour_lequipe


def test_les_actions_pour_l_equipe_se_lisent_dans_la_fiche():
    contexte = {
        "equipe_gestes": [
            {"geste": "transfert", "personne": "camille", "decroche": False, "duree_s": 30, "le": "2026-10-07T09:00:00+00:00"},
            {"geste": "transmission", "personne": "camille", "motif": "facture", "rappel": True},
        ],
        "planificateur_rappel": [{"origine": "equipe", "personne": "camille", "objet": "facture", "souhait": "lundi"}],
        "hub_rendez_vous": [{"personne": "sacha", "type": "visite", "debut": "2026-10-08T14:00:00+02:00"}],
        "verification_appelant": [{"resultat": "verifie", "facteurs_reussis": ["numero", "question"]}],
        "dossier_lu": [{"quoi": "demandes", "nombre": 1}],
    }
    actions = actions_pour_lequipe(contexte, {"camille": "Camille Martin"})
    assert [(a.type, a.personne) for a in actions] == [
        ("transfert", "Camille Martin"), ("transmission", "Camille Martin"), ("rappel", "Camille Martin"),
        ("rendez_vous", "sacha"), ("verification", None), ("dossier_lu", None),
    ]
    assert actions[0].detail == "pas de réponse, 30 s"
    assert actions[2].detail == "facture ; souhaité : « lundi »"
    assert actions_pour_lequipe({}) == []  # an agent of before: nothing


async def test_la_route_rend_les_mentions_de_l_appel_a_son_organisation_seulement(
    base_v4, smtp, modele, db_session, async_session
):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe
    from api.tasks.workflow_completion import process_workflow_completion
    from api.tests.mark import test_apres_appel as t

    a = await t._organisation(async_session, db_session)
    b = await t._organisation(async_session, db_session)
    await t._regler(db_session, a, base_v4, smtp)
    await t._equipe(base_v4)
    connexion = await schema.connecter(base_v4)
    try:
        await ecrire_equipe(connexion, Equipe(personnes=[
            Personne(cle="accueil", prenom="Accueil", mail="accueil@example.org", destinataire_defaut=True),
            Personne(cle="camille", prenom="Camille", nom="Martin", mail="camille@example.org",
                     telephone="+33611111111", joignable_par_transfert=True),
        ]), "test")
    finally:
        await connexion.close()
    run = await t._run(db_session, a)
    await db_session.update_workflow_run(run.id, gathered_context={
        **run.gathered_context,
        "equipe_assignation": "camille",
        "equipe_gestes": [
            {"geste": "transfert", "personne": "camille", "numero": "+33611111111",
             "le": "2026-10-07T09:00:05+00:00", "decroche": False, "duree_s": 30, "motif": "facture"},
            {"geste": "transmission", "personne": "camille", "motif": "facture", "rappel": True},
        ],
        "planificateur_rappel": [{"origine": "equipe", "personne": "camille", "prenom": "Camille", "objet": "facture"}],
    })
    with patch("api.tasks.arq.enqueue_job", await t._executer_tout_de_suite([])):
        await process_workflow_completion(None, run.id)

    chemin = f"/workflow/{a.agent.id}/runs/{run.id}/apres-appel"
    vue = (await t._app(a.utilisateur).get(chemin)).json()
    assert vue["actif"] is True and vue["mentions_illisibles"] is False
    assert sorted((m["personne"], m["source"], m["certitude"]) for m in vue["mentions"]) == [
        ("Camille Martin", "transfert", "certaine"), ("Camille Martin", "transmission", "certaine")]
    assert {m["extrait"] for m in vue["mentions"]} == {"facture", "À rappeler : facture"}
    assert [x["type"] for x in vue["actions_equipe"]] == ["transfert", "transmission", "rappel"]
    assert vue["actions_equipe"][0]["personne"] == "Camille Martin"
    assert vue["qualite_fiche"] is None  # « Check the data » off: no verdict
    assert (await t._app(b.utilisateur).get(chemin)).status_code == 404


# Fixtures of the after-call's tests (a real client database, an SMTP stand-in, a model stand-in).
from api.tests.mark.test_apres_appel import base_v4, modele, smtp  # noqa: E402, F401
from api.tests.mark.test_base_client import base_essai  # noqa: E402, F401
