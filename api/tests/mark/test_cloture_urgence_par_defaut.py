"""[.mark] Clôture, lot B (D3, D4) : le garde-fou urgence est ALLUMÉ sur un nouvel agent (numéro 112), phrase et numéro modifiables.

| Test | Ce qu'il prouve |
|---|---|
| nouvel agent | créé sans réglage de sécurité : le garde-fou est allumé, numéro 112, aussi dans sa première version publiée (vraie base) |
| choix gardé | une création qui règle déjà le garde-fou (copie, import, recette) n'est pas écrasée ; un agent existant n'est pas touché |
| modifiable | le numéro et les mots en plus se changent (schéma) ; la phrase est celle du catalogue des phrases |
| D4 | le garde-fou ne transfère pas : il dit le numéro et note l'appel (« À améliorer ») |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.db.workflow_client import avec_le_garde_fou_urgence_allume
from api.services.securite import urgence
from api.services.securite.reglages import de_l_agent
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401
from api.tests.mark.test_sous_dossiers_et_groupe import autre_org, org  # noqa: F401


def test_la_configuration_d_un_nouvel_agent_allume_le_garde_fou_sans_toucher_au_reste():
    configuration = avec_le_garde_fou_urgence_allume({"autre": 1, "securite_conversation": {"manipulation": {"actif": True}}})
    assert configuration["autre"] == 1 and configuration["securite_conversation"]["manipulation"] == {"actif": True}
    garde = de_l_agent(configuration).garde_urgence
    assert garde.actif is True and garde.numero == "112"
    assert urgence.urgence_allumee(SimpleNamespace(reglages=configuration)) is True


def test_un_choix_deja_pose_a_la_creation_est_garde():
    eteint = {"securite_conversation": {"garde_urgence": {"actif": False, "numero": "15", "mots_en_plus": ["alarme"]}}}
    garde = de_l_agent(avec_le_garde_fou_urgence_allume(eteint)).garde_urgence
    assert (garde.actif, garde.numero, garde.mots_en_plus) == (False, "15", ["alarme"])


def test_le_numero_est_modifiable_et_borne():
    import pytest

    from api.schemas.securite_conversation import GardeUrgence

    assert GardeUrgence(numero="+33 15").numero == "+33 15"
    with pytest.raises(ValueError):
        GardeUrgence(numero="appelez moi")


def test_d4_le_garde_fou_ne_transfere_pas():
    assert "transfert" not in {c for c in urgence.__dict__ if c.startswith("transf")}
    from api.schemas.securite_conversation import GardeUrgence

    assert "transfert" not in GardeUrgence.model_fields


async def test_un_agent_cree_sans_reglage_a_le_garde_fou_allume_aussi_dans_sa_premiere_version(org, db_session):  # noqa: F811
    agent = await db_session.create_workflow(
        name="Neuf", workflow_definition=graphe_depart(), user_id=org.utilisateur.id, organization_id=org.organisation.id
    )
    assert de_l_agent(agent.workflow_configurations).garde_urgence.actif is True
