"""[.mark] Le contrat du lanceur de l'appelant simulé (chantier langwatch-et-fenetre-du-run, lot 3, L19).

``simulateur/jouer.py`` tourne dans un autre environnement Python que l'API : on ne peut pas y
importer Scenario ici. On teste ce qui ne dépend pas de Scenario, et qui fait le contrat avec la
tâche de fond : l'entrée validée, le verdict lisible, la ligne marquée, et l'absence de tout import
de l'API (sinon le lanceur casserait dans son environnement).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

LANCEUR = Path(__file__).resolve().parents[3] / "simulateur" / "jouer.py"


@pytest.fixture(scope="module")
def jouer():
    spec = importlib.util.spec_from_file_location("simulateur_jouer", LANCEUR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entree(**surcharges):
    entree = {
        "adresse": "wss://api.exemple.fr/api/v1/appel-simule/ws/12/jeton",
        "scenario": {
            "nom": "Panne de chaudière",
            "description": "Un particulier appelle pour une panne.",
            "criteres": ["L'agent prend le nom", "  ", "L'agent propose un rappel"],
            "tours_max": 8,
        },
        "appelant": {
            "modele": "mistral/mistral-small-latest",
            "consigne": "Tu es un particulier pressé.",
            "voix": "elevenlabs/voix-fr",
        },
        "juge": {"modele": "mistral/mistral-small-latest"},
    }
    entree.update(surcharges)
    return json.dumps(entree)


def test_l_entree_valide_est_nettoyee(jouer):
    lue = jouer.lire_l_entree(_entree())
    assert lue["criteres"] == ["L'agent prend le nom", "L'agent propose un rappel"]
    assert lue["tours_max"] == 8
    assert lue["appelant"]["coupe_la_parole"] == 0.0
    assert lue["juge"]["consigne"] is None


@pytest.mark.parametrize(
    "surcharge",
    [
        {"adresse": ""},
        {"scenario": {"nom": "x", "description": "y", "criteres": []}},
        {"appelant": {"modele": "m", "consigne": "c"}},
        {"juge": {}},
    ],
)
def test_une_entree_incomplete_est_refusee(jouer, surcharge):
    with pytest.raises(jouer.EntreeInvalide):
        jouer.lire_l_entree(_entree(**surcharge))


def test_le_verdict_ne_garde_que_la_conversation_en_texte(jouer):
    resultat = SimpleNamespace(
        success=False,
        reasoning="Le nom n'a pas été demandé.",
        passed_criteria=["L'agent propose un rappel"],
        failed_criteria=["L'agent prend le nom"],
        total_time=41.2,
        agent_time=12.5,
        messages=[
            {"role": "system", "content": "consigne"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Bonjour"},
                    {"type": "input_audio"},
                ],
            },
            {"role": "assistant", "content": "Bonjour, que puis-je pour vous ?"},
        ],
    )
    assert jouer.verdict(resultat) == {
        "success": False,
        "reasoning": "Le nom n'a pas été demandé.",
        "passed_criteria": ["L'agent propose un rappel"],
        "failed_criteria": ["L'agent prend le nom"],
        "total_time": 41.2,
        "agent_time": 12.5,
        "messages": [
            {"role": "user", "content": "Bonjour"},
            {"role": "assistant", "content": "Bonjour, que puis-je pour vous ?"},
        ],
    }


def test_une_entree_illisible_rend_quand_meme_une_ligne_marquee():
    sortie = subprocess.run(
        [sys.executable, str(LANCEUR)],
        input="pas du json",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert sortie.returncode == 2
    ligne = [lg for lg in sortie.stdout.splitlines() if lg.startswith("MARK_VERDICT ")]
    assert len(ligne) == 1
    assert json.loads(ligne[0].removeprefix("MARK_VERDICT "))["error"].startswith(
        "invalid input"
    )


def test_le_lanceur_n_importe_rien_de_l_api():
    arbre = ast.parse(LANCEUR.read_text(encoding="utf-8"))
    modules = {
        n.module if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(arbre)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert not any(m and (m == "api" or m.startswith("api.")) for m in modules)


def test_l_appelant_simule_part_sans_liste_d_outils_vide(jouer):
    # 06/10 : Scenario appelle toujours l'appelant simulé avec ``tools=[]`` et Mistral refuse une
    # liste vide. Le juge, qui a des outils, les garde.
    recus = []
    appeler = jouer.pour_le_fournisseur(lambda *a, **k: recus.append(k) or "ok")
    assert appeler(model="m", messages=[], tools=[]) == "ok"
    appeler(model="m", messages=[], tools=[{"type": "function"}])
    appeler(model="m", messages=[])
    assert recus == [
        {"model": "m", "messages": []},
        {"model": "m", "messages": [], "tools": [{"type": "function"}]},
        {"model": "m", "messages": []},
    ]


def test_les_messages_partent_sans_les_champs_de_suivi_de_scenario(jouer):
    # Run 1026 : Mistral refuse le ``trace_id`` que Scenario pose sur chaque message.
    recus = []
    appeler = jouer.pour_le_fournisseur(lambda *a, **k: recus.append(k))
    messages = [
        {"role": "system", "content": "consigne"},
        {"role": "assistant", "content": "Bonjour", "trace_id": "t1"},
        {"role": "user", "content": "J'ai une panne", "trace_id": "t1"},
    ]
    appeler(model="m", messages=messages)
    assert recus[0]["messages"] == [
        {"role": "system", "content": "consigne"},
        {"role": "assistant", "content": "Bonjour"},
        {"role": "user", "content": "J'ai une panne"},
    ]
    assert messages[1]["trace_id"] == "t1"  # La conversation de Scenario reste intacte.


def test_l_erreur_garde_le_message_du_fournisseur(jouer):
    class ErreurFournisseur(Exception):
        message = "MistralException - List should have at least 1 item"

        def __str__(self):
            return "Headers({'content-type': 'application/json', ...})"

    assert jouer.message_d_erreur(ErreurFournisseur()) == (
        "ErreurFournisseur: MistralException - List should have at least 1 item"
    )
    assert jouer.message_d_erreur(ValueError("simple")) == "ValueError: simple"
