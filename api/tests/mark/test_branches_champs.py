"""[.mark] Builder partie 3, SA-L3c, sous-lot 1 (05 § 12) : la fusion à trois, champ par champ (pure, sans base).

| Test | Ce qu'il prouve |
|---|---|
| statuts | un champ qui n'a bougé que d'un côté est repris ou gardé ; deux côtés qui ont bougé autrement sont un conflit ; deux côtés qui ont bougé pareil ne sont rien |
| jamais en silence | un conflit sans choix refuse la fusion ; un choix sur un champ inconnu aussi |
| déplacement | un déplacement sur le canevas n'est pas un changement |
| étape ajoutée / retirée | une étape qui n'existe pas partout est un seul champ (avec son prompt) ; un prompt ne survit pas à son étape |
| prompts | le prompt d'une étape présente partout se choisit à part de l'étape |
| réglages et variables | par clé ; ``phrases_regles`` est sa propre famille |
| cohérence | une liaison vers une étape retirée est signalée ; deux étapes de même identifiant aussi |
| secrets | un réglage au nom de clé n'est jamais rendu en clair |
"""

from __future__ import annotations

import copy

import pytest

from api.services.branches import champs
from api.services.branches.champs import Etat


def _graphe(prompt1="Bonjour", prompt2="Au revoir", label="Fini", extra_noeud=None, sans_2=False):
    noeuds = [
        {"id": "1", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Départ", "prompt": prompt1}},
        {"id": "2", "type": "endCall", "position": {"x": 0, "y": 100}, "data": {"name": "Fin", "prompt": prompt2}},
    ]
    liaisons = [{"id": "1-2", "source": "1", "target": "2", "data": {"label": label, "condition": "c"}}]
    if sans_2:
        noeuds, liaisons = noeuds[:1], []
    if extra_noeud:
        noeuds.append(extra_noeud)
    return {"nodes": noeuds, "edges": liaisons}


def _etat(graphe=None, reglages=None, variables=None):
    return Etat(graphe if graphe is not None else _graphe(), reglages or {}, variables or {})


def _par_cle(lignes):
    return {ligne["cle"]: ligne for ligne in lignes}


def test_un_champ_repris_un_champ_garde_un_conflit_et_deux_cotes_pareils():
    base = _etat(_graphe(), {"a": 1, "b": 1, "c": 1, "d": 1})
    source = _etat(_graphe(prompt1="Allô, cabinet"), {"a": 2, "b": 1, "c": 3, "d": 2})
    cible = _etat(_graphe(prompt2="À bientôt"), {"a": 1, "b": 5, "c": 4, "d": 2})
    lignes = _par_cle(champs.comparer(base, source, cible))
    assert lignes["prompt:1"]["statut"] == "reprise"  # seule la source a bougé
    assert lignes["prompt:2"]["statut"] == "gardee"  # seule la cible a bougé
    assert lignes["reglage:a"]["statut"] == "reprise" and lignes["reglage:b"]["statut"] == "gardee"
    assert lignes["reglage:c"]["statut"] == "conflit"
    assert "reglage:d" not in lignes  # bougé pareil des deux côtés : rien à dire
    assert lignes["prompt:1"]["avant"] == "Bonjour" and lignes["prompt:1"]["source"] == "Allô, cabinet" and lignes["prompt:1"]["cible"] == "Bonjour"
    assert lignes["prompt:1"]["libelle"] == "Départ" and lignes["prompt:1"]["famille"] == "prompts"


def test_sans_choix_un_conflit_refuse_la_fusion_et_jamais_le_plus_recent_ne_gagne():
    base, source, cible = _etat(_graphe()), _etat(_graphe(prompt1="Source")), _etat(_graphe(prompt1="Cible"))
    with pytest.raises(champs.ChoixIncomplet, match="Every conflict needs a choice"):
        champs.resoudre(base, source, cible, {})
    avec_source = champs.resoudre(base, source, cible, {"prompt:1": "source"})
    avec_cible = champs.resoudre(base, source, cible, {"prompt:1": "cible"})
    assert avec_source.graphe["nodes"][0]["data"]["prompt"] == "Source"
    assert avec_cible.graphe["nodes"][0]["data"]["prompt"] == "Cible"
    with pytest.raises(champs.ChoixIncomplet, match="Unknown field"):
        champs.resoudre(base, source, cible, {"prompt:1": "source", "prompt:99": "source"})
    with pytest.raises(champs.ChoixIncomplet):
        champs.resoudre(base, source, cible, {"prompt:1": "le_plus_recent"})


def test_sans_conflit_le_resultat_reprend_la_source_et_garde_la_cible():
    base = _etat(_graphe(), {"a": 1}, {"v": "x"})
    source = _etat(_graphe(prompt1="Allô"), {"a": 2}, {"v": "x"})
    cible = _etat(_graphe(prompt2="À bientôt"), {"a": 1}, {"v": "y"})
    fusionne = champs.resoudre(base, source, cible, {})
    assert [n["data"]["prompt"] for n in fusionne.graphe["nodes"]] == ["Allô", "À bientôt"]
    assert fusionne.reglages == {"a": 2} and fusionne.variables == {"v": "y"}


def test_un_deplacement_n_est_pas_un_changement_et_la_position_de_la_cible_est_gardee():
    base = _etat(_graphe())
    deplacee = _graphe()
    deplacee["nodes"][0]["position"] = {"x": 300, "y": 40}
    assert champs.comparer(base, _etat(deplacee), base) == []
    source = _etat(_graphe(prompt1="Allô"))
    fusionne = champs.resoudre(base, source, _etat(deplacee), {})
    assert fusionne.graphe["nodes"][0]["position"] == {"x": 300, "y": 40}
    assert fusionne.graphe["nodes"][0]["data"]["prompt"] == "Allô"


def test_une_etape_ajoutee_ou_retiree_est_un_seul_champ_avec_son_prompt():
    nouvelle = {"id": "3", "type": "agentNode", "position": {"x": 0, "y": 200}, "data": {"name": "Rendez-vous", "prompt": "On prend rendez-vous."}}
    base = _etat(_graphe())
    source = _etat(_graphe(extra_noeud=nouvelle))
    lignes = _par_cle(champs.comparer(base, source, base))
    assert lignes["etape:3"]["statut"] == "reprise" and "prompt:3" not in lignes
    assert "On prend rendez-vous." in lignes["etape:3"]["source"]
    fusionne = champs.resoudre(base, source, base, {})
    assert [n["id"] for n in fusionne.graphe["nodes"]] == ["1", "2", "3"]
    assert fusionne.graphe["nodes"][2]["data"]["prompt"] == "On prend rendez-vous."
    # retirée côté source alors que la cible a retouché son prompt : conflit sur l'étape entière, jamais un prompt orphelin
    source2 = _etat(_graphe(sans_2=True))
    cible2 = _etat(_graphe(prompt2="À bientôt"))
    lignes = _par_cle(champs.comparer(base, source2, cible2))
    assert lignes["etape:2"]["statut"] == "conflit" and "prompt:2" not in lignes
    assert [n["id"] for n in champs.resoudre(base, source2, cible2, {"etape:2": "cible", "liaison:1-2": "cible"}).graphe["nodes"]] == ["1", "2"]


def test_le_prompt_d_une_etape_presente_partout_se_choisit_a_part_de_l_etape():
    base = _etat(_graphe())
    source = _etat(_graphe(prompt1="Allô"))
    cible = _etat(_graphe())
    cible.graphe["nodes"][0]["data"]["name"] = "Accueil"
    lignes = _par_cle(champs.comparer(base, source, cible))
    assert lignes["prompt:1"]["statut"] == "reprise" and lignes["etape:1"]["statut"] == "gardee"


def test_les_reglages_sont_par_cle_et_les_phrases_forment_une_famille():
    base = _etat(_graphe(), {"phrases_regles": [1], "voix": "a"})
    source = _etat(_graphe(), {"phrases_regles": [1, 2], "voix": "a"})
    lignes = _par_cle(champs.comparer(base, source, base))
    assert lignes["phrases:phrases_regles"]["famille"] == "phrases"
    assert champs.resoudre(base, source, base, {}).reglages["phrases_regles"] == [1, 2]


def test_une_liaison_vers_une_etape_retiree_est_signalee_et_un_doublon_aussi():
    base = _etat(_graphe())
    source = _etat(_graphe(sans_2=True))
    cible = _etat(_graphe(label="Terminé"))
    fusionne = champs.resoudre(base, source, cible, {"liaison:1-2": "cible"})
    assert [p["code"] for p in champs.problemes(fusionne.graphe)] == ["liaison_orpheline"]
    assert champs.problemes(_graphe()) == []
    double = _graphe()
    double["nodes"].append(copy.deepcopy(double["nodes"][0]))
    assert champs.problemes(double)[0]["code"] == "etape_en_double"


def test_un_reglage_au_nom_de_cle_n_est_jamais_rendu_en_clair():
    base = _etat(_graphe(), {"travail_llm": {"api_key": "sk-secret-123", "model": "m1"}})
    source = _etat(_graphe(), {"travail_llm": {"api_key": "sk-autre-456", "model": "m2"}})
    corps = repr(champs.comparer(base, source, base))
    assert "sk-secret-123" not in corps and "sk-autre-456" not in corps and "••••" in corps
