"""[.mark] Un spécialiste aux réglages propres ne cache jamais les interrupteurs posés sur le principal (SA-31, lot 2).

Avant : ``agent.reglages or moteur.reglages_appel`` rendait les réglages du spécialiste dès qu'ils n'étaient pas vides, et l'interrupteur posé sur le principal
restait éteint pour lui. Maintenant : réglages du principal, complétés puis surchargés par ceux de l'agent (``reglages_de_l_agent``, repris de la garde de SA-30).

| Test | Ce qu'il prouve |
|---|---|
| chaque lecture | les lectures (option « action non aboutie », intervention du moteur, case outil écrit, fiche dans le système, laisser la parole) voient l'interrupteur du principal |
| l'agent gagne | une valeur posée sur l'agent prime sur celle du principal |
| sans principal | l'agent seul, ou l'appel seul, se lisent comme avant |
| plus de motif | aucun fichier de ``api/services`` ne reprend ``agent.reglages or reglages_appel`` |
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from api.services import interventions_du_moteur as iv
from api.services.groupe.reglages_effectifs import reglages_de_l_agent
from api.services.pipecat import texte_du_cerveau as tc
from api.services.workflow import action_non_aboutie as ana
from api.services.workflow import fiche_dans_le_systeme as fiche
from api.services.workflow import laisser_la_parole as parole

SERVICES = Path(__file__).resolve().parents[2] / "services"


def _moteur(principal: dict, specialiste: dict):
    agent = SimpleNamespace(reglages=specialiste)
    return SimpleNamespace(reglages_appel=principal, active_agent=agent), agent


def test_les_cinq_lectures_voient_l_interrupteur_du_principal():
    moteur, agent = _moteur(
        {ana.CLE_PREVENIR: True, tc.CLE_OUTIL_ECRIT: True, fiche.CLE_FICHE_DANS_LE_SYSTEME: True, parole.CLE_LAISSER_LA_PAROLE: True, iv.CLE_FIN_APRES_ACTION_NON_ABOUTIE: False},
        {"un_reglage_du_specialiste": 1},
    )
    assert ana._option_posee(moteur, ana.CLE_PREVENIR) is True
    assert tc.case_outil_ecrit(agent, moteur) is True
    assert fiche.case_allumee(agent, moteur) is True
    assert parole.case_allumee(agent, moteur) is True
    assert iv.intervention_du_moteur(moteur, iv.CLE_FIN_APRES_ACTION_NON_ABOUTIE) is False  # éteint sur le principal, allumé par défaut sinon


def test_l_agent_gagne_sur_le_principal_et_les_cas_simples_restent():
    moteur, agent = _moteur({tc.CLE_OUTIL_ECRIT: True}, {tc.CLE_OUTIL_ECRIT: False})
    assert tc.case_outil_ecrit(agent, moteur) is False
    assert reglages_de_l_agent(SimpleNamespace(reglages_appel=None), SimpleNamespace(reglages={"a": 1})) == {"a": 1}
    assert reglages_de_l_agent(SimpleNamespace(reglages_appel={"b": 2}), None) == {"b": 2}
    assert reglages_de_l_agent(object(), object()) == {}


def test_aucun_fichier_ne_cache_les_reglages_du_principal():
    motif = re.compile(r"""["']reglages["'],\s*None\)\s*or\s*(?:getattr\([^)]*|[\w.]*get\()["']reglages_appel["']""")
    fautes = [f"{f.relative_to(SERVICES)}" for f in SERVICES.rglob("*.py") if motif.search(f.read_text(encoding="utf-8"))]
    assert not fautes, fautes
