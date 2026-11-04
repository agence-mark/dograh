"""[.mark] RA-B, R5 : le délai caché de la panne est retiré (script idempotent, sauvegarde avant d'écrire)."""

import json

import pytest

from api.db import db_client
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.equipe_commun import (  # noqa: F401
    creer_compte,
    creer_organisation,
    sans_preparation_des_organisations,
)
from api.schemas.panne import PanneAgent
from api.services.panne.garde_modele import delai_de_garde
from scripts.mark.retirer_delai_modele_panne import executer, migrer


def test_le_schema_de_la_panne_n_a_plus_de_delai_modele():
    assert "delai_modele_s" not in PanneAgent.model_fields


def test_le_delai_de_garde_ne_lit_plus_l_ancien_reglage():
    assert delai_de_garde({"panne": {"actif": False, "delai_modele_s": 6}}) == 4.0
    assert delai_de_garde({"delai_garde_modele_s": 2.5}) == 2.5


def test_migrer_reporte_la_valeur_dans_le_reglage_visible_sans_rien_perdre():
    neuve, change = migrer({"panne": {"actif": True, "delai_modele_s": 6, "sonnerie_s": 20}})
    assert change and neuve == {"panne": {"actif": True, "sonnerie_s": 20}, "delai_garde_modele_s": 6.0}


def test_migrer_garde_le_reglage_visible_deja_pose_et_borne_l_ancien():
    neuve, _ = migrer({"panne": {"delai_modele_s": 6}, "delai_garde_modele_s": 2.5})
    assert neuve["delai_garde_modele_s"] == 2.5
    assert migrer({"panne": {"delai_modele_s": 0.2}})[0]["delai_garde_modele_s"] == 1.0


def test_migrer_est_idempotent_et_ne_touche_pas_l_argument():
    origine = {"panne": {"delai_modele_s": 6}}
    neuve, _ = migrer(origine)
    assert origine == {"panne": {"delai_modele_s": 6}}
    assert migrer(neuve) == (neuve, False)


@pytest.mark.asyncio
async def test_le_script_sur_la_base_sauvegarde_puis_ecrit_une_seule_fois(tmp_path, db_session, sans_preparation_des_organisations):
    org = await creer_organisation(db_session, "org-ra-b-r5")
    user, _ = await creer_compte(db_session, "ra-b-r5@example.test", role="Administrateur", organisations=[org])
    agent = await db_client.create_workflow(
        "Agent R5", graphe_depart(), user.id, org, workflow_configurations={"panne": {"actif": True, "delai_modele_s": 7}}
    )
    async with db_client.async_session() as session:
        copie = tmp_path / "copie.json"
        a_blanc = await executer(session, False, None)
        assert any(t["table"] == "workflows" and t["id"] == agent.id for t in a_blanc)
        assert not copie.exists()  # à blanc : rien écrit
        with pytest.raises(ValueError):
            await executer(session, True, None)  # jamais d'écriture sans sauvegarde
        fait = await executer(session, True, copie)
        sauve = json.loads(copie.read_text(encoding="utf-8"))
        assert {(s["table"], s["id"]) for s in sauve} == {(t["table"], t["id"]) for t in fait}
        assert any(s["avant"].get("panne", {}).get("delai_modele_s") == 7 for s in sauve)
        assert await executer(session, True, copie) == []  # seconde passe : plus rien
