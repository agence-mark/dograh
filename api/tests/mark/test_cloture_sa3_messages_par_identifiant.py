"""[.mark] Clôture, SA-3 : les messages du contrôle avant publication partent avec un identifiant, l'écran les traduit.

| Test | Ce qu'il prouve |
|---|---|
| parametres | une règle du contrôle du prompt rend son code ET ses paramètres (longueur, genre de valeur) |
| problème structuré | un problème reste une phrase (API, MCP) et porte son code et ses paramètres |
| tests obligatoires | chaque raison de test à rejouer a un code |
| dictionnaire complet | TOUT code que le serveur peut envoyer a sa phrase française et anglaise dans le dictionnaire de l'écran |
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from api.services.builder.controle import regles
from api.services.builder.controle.service import rendre_le_resultat
from api.services.publication import controles, sans_effet
from api.services.publication.probleme import Probleme, detail_de

RACINE = Path(__file__).resolve().parents[3]
DICTIONNAIRE = RACINE / "ui" / "src" / "components" / "mark" / "langue" / "messages-serveur.ts"


def _graphe(prompt: str) -> dict:
    return {
        "nodes": [
            {"id": "1", "type": "startCall", "data": {"name": "Accueil", "prompt": prompt}},
            {"id": "2", "type": "endCall", "data": {"name": "Fin", "prompt": "Au revoir."}},
        ],
        "edges": [{"id": "e", "source": "1", "target": "2", "data": {"label": "fin", "condition": "fin"}}],
    }


def test_une_regle_rend_son_code_et_ses_parametres():
    e = regles.Entree(graphe=_graphe("Réponds poliment. " * 40), plafond=100)
    defauts = regles.longueur(e)
    assert defauts and defauts[0].code == "longueur"
    assert defauts[0].parametres["plafond"] == 100 and defauts[0].parametres["longueur"] > 100
    rendu = rendre_le_resultat(defauts)
    assert rendu["elements"][0]["parametres"]["plafond"] == 100
    assert rendu["avertissements"][0]["parametres"]["plafond"] == 100

    valeur = regles.exemple_de_valeur(regles.Entree(graphe=_graphe("Écris à jean.dupont@example.com pour confirmer.")))
    assert valeur and valeur[0].parametres == {"genre": "an e-mail address"}


def test_un_probleme_reste_une_phrase_et_porte_son_code():
    p = Probleme("3 attack(s) got through.", "attaque_a_cede", nombre=3)
    assert isinstance(p, str) and p == "3 attack(s) got through."
    assert detail_de(p)["code"] == "attaque_a_cede" and detail_de(p)["parametres"] == {"nombre": 3}
    assert detail_de("une phrase seule")["code"] is None  # sans code : l'écran garde la phrase


async def test_chaque_raison_de_test_a_rejouer_a_un_code():
    lignes = [
        {"slug": "a", "nom": "Test A", "raison": "never replayed", "code": "test_jamais_rejoue", "parametres": {}},
        {"slug": "b", "nom": "Test B", "raison": "failed (1/3)", "code": "test_echoue", "parametres": {"reussis": 1, "total": 3}},
    ]
    brouillon = type("B", (), {"version_number": 2, "workflow_json": {}, "workflow_configurations": {}})()
    agent = type("W", (), {"id": 7})()
    with patch("api.services.builder.tests_agent.publication.problemes_des_tests_obligatoires", new=AsyncMock(return_value=lignes)):
        problemes = await controles._tests(agent, brouillon, 1)
    details = [detail_de(p) for p in problemes]
    assert [d["code"] for d in details] == ["test_jamais_rejoue", "test_echoue"]
    assert details[1]["parametres"] == {"nom": "Test B", "reussis": 1, "total": 3}


def _codes_du_serveur() -> set[str]:
    sources = {
        "regles": Path(regles.__file__).read_text(encoding="utf8"),
        "controles": Path(controles.__file__).read_text(encoding="utf8"),
        "garde": (RACINE / "api" / "services" / "builder" / "tests_agent" / "publication.py").read_text(encoding="utf8"),
    }
    codes = set(re.findall(r'Defaut\(\s*"(\w+)"', sources["regles"]))
    codes |= set(re.findall(r"^K\d, ?.*= ?\"(\w+)\"", sources["regles"], re.M))
    codes |= set(re.findall(r'(?:K\d, ?)+K\d = ("[^\n]+)', sources["regles"]))  # la ligne K1, K2... = "a", "b", ...
    codes = {c for c in codes if re.fullmatch(r"\w+", c)}
    codes |= {c for ligne in re.findall(r'^K1, K2, K3, K4, K5 = (.*)$', sources["regles"], re.M) for c in re.findall(r'"(\w+)"', ligne)}
    codes |= set(re.findall(r'Probleme\(.*?,\s*"(\w+)"', sources["controles"]))
    codes |= set(re.findall(r'code = "(\w+)"', sources["garde"]))
    codes |= {f"effet_{cle}" for cle in sans_effet.MESSAGES}
    return codes


def test_tout_code_du_serveur_est_traduit_dans_les_deux_langues():
    dictionnaire = DICTIONNAIRE.read_text(encoding="utf8")
    codes = _codes_du_serveur()
    assert len(codes) > 40, codes  # le relevé lui-même doit trouver ce qu'il faut
    manquants = []
    for code in sorted(codes):
        # une entrée `code:` ou `"code:..."` (cas à plusieurs phrases), avec ses deux langues
        entree = re.search(rf'^\s*"?{re.escape(code)}(?::\w+)?"?: \{{', dictionnaire, re.M)
        if not entree:
            manquants.append(code)
    assert not manquants, f"codes sans phrase dans messages-serveur.ts : {manquants}"
    # chaque entrée a ses deux langues
    for bloc in re.findall(r"\{\s*en: (?:\"(?:[^\"\\]|\\.)*\"),\s*fr: (?:\"(?:[^\"\\]|\\.)*\"),?\s*\}", dictionnaire):
        assert "en:" in bloc and "fr:" in bloc
    assert dictionnaire.count("en: ") >= dictionnaire.count("fr: ") - 1
