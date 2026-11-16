"""[.mark] Lot 11 (M1) : les mesures des outils arrivent à l'après-appel, dans ``mark.appel.mesures``.

| Test | Ce qu'il prouve |
|---|---|
| bout en bout | une mesure écrite par un outil PENDANT l'appel (la fonction que le comptoir appelle, sur la fiche de l'appel) se retrouve, après la tâche de fin d'appel, dans ``mark.appel.mesures`` sous la clé ``mesures_des_outils`` (celle que le portail lit), à côté de ``analyse_version`` |
| liste fermée | une mesure hors liste (faute de frappe) n'est jamais versée |
| rien | un appel sans mesure ne porte pas la clé : le portail lit « aucune mesure », jamais une liste vide inventée |
"""

from __future__ import annotations

import json
from unittest.mock import patch

from api.db.bases_clients import connexion as schema
from api.tests.mark.test_base_client import base_essai  # noqa: F401  (fixture de base_v4)
from api.services.apres_appel.envoi import construire_envoi
from api.services.integrations.connectors import mesures
from api.services.restauration import mesures as mesures_du_module
from api.tests.mark.test_apres_appel import (  # noqa: F401  (fixtures et assistants)
    _equipe,
    _executer_tout_de_suite,
    _organisation,
    _regler,
    _run,
    base_v4,
    modele,
    smtp,
)


async def test_une_mesure_ecrite_par_un_outil_pendant_l_appel_arrive_dans_mark_appel(base_v4, smtp, modele, db_session, async_session):
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    run = await _run(db_session, org)
    run_id = run.id

    # Pendant l'appel : les outils écrivent dans la fiche (``_gathered_context`` du moteur), comme le comptoir le fait à chaque retour.
    fiche = dict(run.gathered_context)
    mesures_du_module.de_la_commande(fiche, "verifier_adresse", {"statut": "HORS_ZONE", "faits": {}})
    mesures_du_module.de_la_commande(fiche, "finaliser", {"statut": "ENREGISTREE", "faits": {"mode": "livraison", "total_remises": 150}})
    mesures.ecrire(fiche, "mesure_inventee", "commande.ajouter")  # hors liste fermée : jamais écrite
    assert [m["mesure"] for m in fiche[mesures.CLE]] == ["commande.hors_zone", "commande.enregistree", "commande.remise_appliquee"]
    # Ce que le moteur range dans la ligne de l'appel à la fin (``gathered_context``).
    await db_session.update_workflow_run(run_id, gathered_context=fiche)

    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run_id)

    connexion = await schema.connecter(base_v4)
    try:
        brut = await connexion.fetchval("SELECT mesures FROM mark.appel WHERE dograh_run_id = $1", run_id)
    finally:
        await connexion.close()
    versees = json.loads(brut) if isinstance(brut, str) else brut
    assert "analyse_version" in versees, "ce qui y était déjà y est toujours"
    assert [(m["mesure"], m["outil"], m["detail"]) for m in versees["mesures_des_outils"]] == [
        ("commande.hors_zone", "commande.verifier_adresse", None),
        ("commande.enregistree", "commande.finaliser", "livraison"),
        ("commande.remise_appliquee", "commande.finaliser", None),
    ]
    assert set(versees["mesures_des_outils"][0]) == {"mesure", "outil", "tache", "detail"}


async def test_sans_mesure_la_cle_n_existe_pas_et_une_mesure_hors_liste_n_est_jamais_versee(db_session, async_session):
    org = await _organisation(async_session, db_session)
    run = await _run(db_session, org)
    from api.schemas.apres_appel import ApresAppelAgent

    agent = ApresAppelAgent()
    assert "mesures_des_outils" not in construire_envoi(run, {}, agent)["mesures"]
    # Une liste abîmée ou une entrée hors liste fermée : lue comme absente, jamais versée telle quelle.
    run.gathered_context = {**run.gathered_context, mesures.CLE: [{"mesure": "mesure_inventee"}, "texte", None]}
    assert "mesures_des_outils" not in construire_envoi(run, {}, agent)["mesures"]
    run.gathered_context = {**run.gathered_context, mesures.CLE: [{"mesure": "commande.rupture", "outil": "commande.ajouter", "tache": None, "detail": None}]}
    assert construire_envoi(run, {}, agent)["mesures"]["mesures_des_outils"][0]["mesure"] == "commande.rupture"
