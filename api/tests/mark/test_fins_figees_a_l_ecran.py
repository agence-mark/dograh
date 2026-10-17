"""[.mark] Après le banc du 16/10 (C6, Evan) : un agent spécialisé peut porter la fin d'appel par la
seule configuration à l'écran. Les phrases de fin figées (A17) se règlent dans la fenêtre du nœud de
fin, en lignes répétées, comme les variables d'extraction.

| Test | Ce qu'il prouve |
|---|---|
| catalogue | le nœud de fin expose « Fixed closing sentences » en lignes (champ, valeur, phrase), la phrase requise |
| lecture | une ligne écrite par l'écran est relue par le moteur (``FinFigeeDTO``) |
"""

from api.services.workflow.dto import FinFigeeDTO
from api.services.workflow.node_specs import get_spec
from api.services.workflow.node_specs._base import PropertyType


def test_le_noeud_de_fin_expose_les_phrases_figees_en_lignes():
    spec = get_spec("endCall")
    [fins] = [p for p in spec.properties if p.name == "fins"]
    assert fins.type == PropertyType.fixed_collection
    assert fins.display_name == "Fixed closing sentences"
    sous = {p.name: p for p in fins.properties}
    assert set(sous) == {"champ", "vaut", "phrase"}
    assert sous["phrase"].required is True


def test_une_ligne_ecrite_par_l_ecran_est_relue():
    ligne = FinFigeeDTO.model_validate({"champ": "objet", "vaut": "", "phrase": "Au revoir."})
    assert ligne.phrase == "Au revoir." and ligne.champ == "objet"
    assert FinFigeeDTO.model_validate({"phrase": "Bonne journée."}).champ is None
