"""[.mark] Lot M : la recette d'un agent se fige à sa première VRAIE publication, sur la vraie base de test.

Tout agent naît avec un squelette v1 déjà « publié » : ce n'est pas une publication. Ce qui fige la recette, c'est une version
après le squelette qui n'est plus un brouillon.
"""

from __future__ import annotations

from api.db import db_client
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.equipe_commun import (  # noqa: F401
    creer_compte,
    creer_organisation,
    sans_preparation_des_organisations,
)


async def test_le_squelette_et_un_brouillon_ne_figent_pas_la_recette_une_publication_la_fige(db_session, sans_preparation_des_organisations):
    org = await creer_organisation(db_session, "org-m-publie")
    user, _jeton = await creer_compte(db_session, "m-publie@example.test", role="Administrateur", organisations=[org])
    agent = await db_client.create_workflow("Agent m", graphe_depart(), user.id, org)
    assert await db_client.workflow_a_ete_publie(agent.id) is False  # le squelette v1 est « publié » à la création
    await db_client.save_workflow_draft(workflow_id=agent.id, workflow_definition=graphe_depart())
    assert await db_client.workflow_a_ete_publie(agent.id) is False  # un brouillon n'est pas une publication
    await db_client.publish_workflow_draft(agent.id)
    assert await db_client.workflow_a_ete_publie(agent.id) is True
    assert await db_client.workflow_a_ete_publie(agent.id + 9999) is False
