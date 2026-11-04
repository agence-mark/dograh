"""RA-A, R2 (b) (audit du 04/11, rouge n° 5) : le builder ne lit jamais une clé en clair.

``reglages_agent.cles_reglables`` filtrait le NOM des réglages, pas leurs valeurs : ``travail_llm`` et
``greffier_llm`` rendaient leur ``api_key`` au modèle du builder. Maintenant : une référence à la place, à
tous les niveaux, et ``reglages_regler`` ne perd pas la clé quand il réécrit le bloc.
"""

from __future__ import annotations

import json

from api.services.builder.actions.registre import Contexte, executer
from api.tests.mark.builder_commun import AGENT, monde, utilisateur  # noqa: F401
from api.services.builder import reglages_agent

# Coupée en deux : la protection de push de GitHub refuse une clé d'essai d'un seul tenant.
CLE = "sk-" + "RAA-ESSAI-" + "0001"
CLE_V2 = "sk-" + "RAA-V2-ESSAI-" + "0002"
EQUIPE = Contexte(user=utilisateur(1), workflow_id=AGENT)


def _bloc(modele="gpt-4.1-mini", cle=CLE):
    return {"provider": "openai", "model": modele, "api_key": cle}


def _poser(monde):  # noqa: F811
    monde.workflows[AGENT].released_definition.workflow_configurations = {
        "greffier_llm": _bloc(),
        "travail_llm": _bloc("gpt-4.1", CLE),
        "relecture_des_numeros": True,
    }


def _ecrit(monde):  # noqa: F811
    return monde.ecritures_de_reglages[-1]["configurations"]


async def test_lire_tous_les_reglages_ne_rend_aucune_cle(monde):  # noqa: F811
    _poser(monde)
    lu = await executer("reglages_lire", {}, EQUIPE)
    assert lu["ok"] is True, lu
    texte = json.dumps(lu)
    assert CLE not in texte and CLE_V2 not in texte
    assert lu["reglages"]["relecture_des_numeros"] is True
    assert lu["reglages"]["greffier_llm"]["model"] == "gpt-4.1-mini"  # le reste du bloc se lit
    assert lu["reglages"]["greffier_llm"]["api_key"]  # une référence à la place, pas un vide


async def test_lire_un_bloc_par_son_nom_ne_rend_aucune_cle(monde):  # noqa: F811
    _poser(monde)
    lu = await executer("reglages_lire", {"cles": ["travail_llm", "greffier_llm"]}, EQUIPE)
    assert lu["ok"] is True, lu
    assert CLE not in json.dumps(lu) and CLE_V2 not in json.dumps(lu)


async def test_relire_puis_reecrire_le_bloc_garde_la_cle(monde):  # noqa: F811
    _poser(monde)
    lu = await executer("reglages_lire", {"cles": ["greffier_llm"]}, EQUIPE)
    bloc = lu["reglages"]["greffier_llm"]
    bloc["model"] = "gpt-4.1"
    ecrit = await executer("reglages_regler", {"valeurs": {"greffier_llm": bloc}}, EQUIPE)
    assert ecrit["ok"] is True, ecrit
    assert _ecrit(monde)["greffier_llm"] == _bloc("gpt-4.1", CLE)  # la clé d'origine, jamais la référence
    assert _ecrit(monde)["travail_llm"]["api_key"] == CLE  # les autres blocs intacts


async def test_reecrire_un_bloc_sans_cle_ne_perd_pas_la_cle(monde):  # noqa: F811
    _poser(monde)
    ecrit = await executer(
        "reglages_regler", {"valeurs": {"greffier_llm": {"provider": "openai", "model": "gpt-4.1-nano"}}}, EQUIPE
    )
    assert ecrit["ok"] is True, ecrit
    assert _ecrit(monde)["greffier_llm"] == _bloc("gpt-4.1-nano", CLE)


async def test_changer_de_fournisseur_ne_garde_pas_la_cle_de_l_ancien(monde):  # noqa: F811
    _poser(monde)
    ecrit = await executer(
        "reglages_regler", {"valeurs": {"greffier_llm": {"provider": "mistral", "model": "mistral-small-latest"}}}, EQUIPE
    )
    assert ecrit["ok"] is True, ecrit
    assert "api_key" not in _ecrit(monde)["greffier_llm"]


def test_le_masquage_va_a_tous_les_niveaux_et_dans_les_listes():
    imbrique = {"a": {"b": [{"api_key": CLE_V2, "token": "t-1", "model": "m"}, {"c": {"client_secret": "s-2"}}]}, "max_tokens": 5}
    masque = reglages_agent.masquer_les_cles(imbrique)
    texte = json.dumps(masque)
    assert CLE_V2 not in texte and "t-1" not in texte and "s-2" not in texte
    assert masque["a"]["b"][0]["model"] == "m" and masque["max_tokens"] == 5
    assert imbrique["a"]["b"][0]["api_key"] == CLE_V2  # la copie est masquée, pas l'original
