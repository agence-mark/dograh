"""[.mark] Après le banc du 16/10 (C6, Evan) : un agent spécialisé peut porter la fin d'appel par la
seule configuration à l'écran. Les phrases de fin figées (A17) se règlent dans la fenêtre du nœud de
fin, en lignes répétées, comme les variables d'extraction.

| Test | Ce qu'il prouve |
|---|---|
| catalogue | lot 2 d'orchestrateur-trois-cerveaux (D5) : le formulaire généré du nœud de fin n'expose plus la liste (``PhrasesDeFin`` seul l'affiche, sur tout nœud de fin) : plus de doublon |
| lecture | une ligne écrite par l'écran est relue par le moteur (``FinFigeeDTO``) |
"""

from api.services.workflow.dto import FinFigeeDTO
from api.services.workflow.node_specs import get_spec


def test_le_formulaire_du_noeud_de_fin_n_expose_plus_les_phrases_figees():
    """Plus de doublon chez le principal : la liste n'est dans le formulaire généré d'aucun nœud,
    son composant dédié l'affiche sur tout nœud de fin. Les données, elles, restent lues."""
    spec = get_spec("endCall")
    assert not [p for p in spec.properties if p.name == "fins"]
    assert "fins" not in {p.name for p in get_spec("agentNode").properties}


def test_la_liste_reste_lue_et_ecrite_par_les_donnees_du_noeud():
    from api.services.workflow.dto import EndCallNodeData

    donnees = EndCallNodeData.model_validate(
        {"name": "Fin", "prompt": "x", "fins": [{"champ": "objet", "phrase": "Au revoir."}]}
    )
    assert donnees.fins and donnees.fins[0].phrase == "Au revoir."
    assert donnees.model_dump(mode="json")["fins"][0]["champ"] == "objet"


def test_une_ligne_ecrite_par_l_ecran_est_relue():
    ligne = FinFigeeDTO.model_validate({"champ": "objet", "vaut": "", "phrase": "Au revoir."})
    assert ligne.phrase == "Au revoir." and ligne.champ == "objet"
    assert FinFigeeDTO.model_validate({"phrase": "Bonne journée."}).champ is None
