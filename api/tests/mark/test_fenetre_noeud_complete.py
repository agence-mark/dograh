"""[.mark] builder partie 2, D1 (U4, E39) : la fenêtre d'un nœud montre toutes les propriétés du fork.

La fenêtre est dessinée depuis les spécifications que le serveur sert (``all_specs()``), rangées par onglet
(``sections-noeud.ts``, une propriété inconnue va dans « Général » : rien ne se perd). Le test de l'écran
(``sections-noeud.test.tsx``) joue la liste relevée des propriétés de chaque type ; CE test compare ce relevé au serveur :
une propriété qu'une montée de version ajoute et que le relevé ignore fait échouer ici, avant qu'elle n'arrive à l'écran
sans qu'on l'ait regardée.
"""

import json
import re
from pathlib import Path

from api.services.workflow.node_specs import all_specs

RACINE = Path(__file__).resolve().parents[3]
TEST_ECRAN = RACINE / "ui/src/components/mark/graphe/sections-noeud.test.tsx"


def _releve_de_l_ecran() -> dict[str, list[str]]:
    source = TEST_ECRAN.read_text(encoding="utf-8")
    bloc = source.split("const SPECS: Record<string, string[]> = {", 1)[1].split("\n};", 1)[0]
    releve: dict[str, list[str]] = {}
    for ligne in bloc.splitlines():
        m = re.match(r"\s*(\w+):\s*(\[.*\]),?\s*$", ligne)
        if m:
            releve[m.group(1)] = json.loads(m.group(2))
    return releve


def test_le_releve_de_l_ecran_est_celui_du_serveur():
    releve = _releve_de_l_ecran()
    serveur = {s.name: [p.name for p in s.properties] for s in all_specs()}
    # Chaque type que le serveur sert est relevé, avec exactement ses propriétés.
    assert set(serveur) <= set(releve), f"type de nœud absent du relevé de l'écran : {sorted(set(serveur) - set(releve))}"
    for type_, proprietes in serveur.items():
        assert sorted(releve[type_]) == sorted(proprietes), type_


def test_les_proprietes_e39_existent_au_fork():
    """Le relevé d'E39 (nom, accueil différé, avant l'appel, extraction, filtres MCP, étape de retour, webhook...)."""
    serveur = {s.name: {p.name for p in s.properties} for s in all_specs()}
    for type_, attendues in {
        "startCall": {"name", "greeting", "prompt", "extraction_variables"},
        "endCall": {"name", "prompt", "premiere_replique", "extraction_variables"},
        "webhook": {"enabled", "http_method", "credential_uuid", "custom_headers"},
        "trigger": {"enabled"},
        "qa": {"qa_enabled", "qa_system_prompt"},
    }.items():
        assert attendues <= serveur[type_], (type_, attendues - serveur[type_])
