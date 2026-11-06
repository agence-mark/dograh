"""[.mark] builder-agent-vocal, lot 1 : la couche d'appel unique (deux formats de fil, mêmes événements, mêmes erreurs).

Aucun appel réel : ``httpx.MockTransport`` joue le fournisseur. Ce qui doit tenir : la requête respecte le format du
fil (OpenAI compatible / Anthropic Messages, avec le cache des consignes pour Anthropic) ; le flux de réponse donne
les MÊMES événements (texte, appel d'action, usage, fin) ; les erreurs sont normalisées et la clé n'y figure jamais ;
une panne passagère est retentée AVANT le premier événement, jamais après.
"""

from __future__ import annotations

import json

import httpx
import pytest

from api.services.builder.cerveau import appel
from api.services.builder.cerveau.appel import CODE_CLE, CODE_INDISPONIBLE, CODE_LIMITE, CODE_REQUETE, ErreurCerveau, fabriquer
from api.services.builder.cerveau.reglages import ReglagesCerveau

CLE = "cle-factice-VALEUR-1234567890"
OUTILS = [{"name": "fiche_lire", "description": "Lire la fiche", "parameters": {"type": "object", "properties": {}}}]
MESSAGES = [
    {"role": "user", "content": "Bonjour"},
    {"role": "assistant", "content": "Je lis.", "appels": [{"id": "a1", "nom": "fiche_lire", "arguments": {"x": 1}}]},
    {"role": "outil", "appel_id": "a1", "nom": "fiche_lire", "content": '{"ok": true}'},
    {"role": "outil", "appel_id": "a2", "nom": "autre", "content": "{}"},
    {"role": "user", "content": "Merci"},
]


def sse(*blocs: tuple[str | None, dict | str]) -> bytes:
    morceaux = []
    for nom, donnees in blocs:
        ligne = donnees if isinstance(donnees, str) else json.dumps(donnees)
        morceaux.append((f"event: {nom}\n" if nom else "") + f"data: {ligne}\n\n")
    return "".join(morceaux).encode()


def flux_anthropic(texte=True, appel_outil=True) -> bytes:
    blocs = [(
        "message_start",
        {"type": "message_start", "message": {"usage": {"input_tokens": 120, "output_tokens": 1, "cache_read_input_tokens": 80, "cache_creation_input_tokens": 5}}},
    )]
    if texte:
        blocs += [
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Je "}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "regarde."}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ]
    if appel_outil:
        blocs += [
            ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "tu1", "name": "fiche_lire", "input": {}}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"workflow'}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '_id": 42}'}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ]
    blocs += [
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use" if appel_outil else "end_turn"}, "usage": {"output_tokens": 33}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return sse(*blocs)


def flux_openai() -> bytes:
    def morceau(delta, fin=None):
        return (None, {"choices": [{"index": 0, "delta": delta, "finish_reason": fin}]})

    return sse(
        morceau({"role": "assistant", "content": "Je "}),
        morceau({"content": "regarde."}),
        morceau({"tool_calls": [{"index": 0, "id": "call1", "function": {"name": "fiche_lire", "arguments": '{"workflow'}}]}),
        morceau({"tool_calls": [{"index": 0, "function": {"arguments": '_id": 42}'}}]}),
        morceau({}, "tool_calls"),
        (None, {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 33, "prompt_tokens_details": {"cached_tokens": 80}}}),
        (None, "[DONE]"),
    )


async def jouer(cerveau, messages=MESSAGES, outils=OUTILS) -> list[dict]:
    return [e async for e in cerveau.tour(systeme="Consigne", messages=messages, outils=outils)]


def normalise(evenements: list[dict]) -> dict:
    return {
        "texte": "".join(e["texte"] for e in evenements if e["type"] == "texte"),
        "appels": [(e["nom"], e["arguments"]) for e in evenements if e["type"] == "appel"],
        "usage": next(e for e in evenements if e["type"] == "usage"),
        "fin": evenements[-1],
    }


async def test_anthropic_requete_au_format_messages_avec_cache_des_consignes():
    vu = {}

    def repondre(requete: httpx.Request) -> httpx.Response:
        vu["url"], vu["entetes"], vu["corps"] = str(requete.url), requete.headers, json.loads(requete.content)
        return httpx.Response(200, content=flux_anthropic())

    cerveau = fabriquer(ReglagesCerveau(format="anthropic", modele="m-1"), CLE, httpx.MockTransport(repondre))
    await jouer(cerveau)
    assert vu["url"] == "https://api.anthropic.com/v1/messages"
    assert vu["entetes"]["x-api-key"] == CLE and vu["entetes"]["anthropic-version"]
    corps = vu["corps"]
    assert corps["stream"] is True and corps["model"] == "m-1"
    assert corps["system"][0]["cache_control"] == {"type": "ephemeral"}  # consignes en cache
    assert corps["tools"][-1]["cache_control"] == {"type": "ephemeral"} and corps["tools"][0]["input_schema"]
    # Deux résultats d'outils de suite = UN message utilisateur à deux blocs (le format l'exige).
    resultats = [m for m in corps["messages"] if m["role"] == "user" and m["content"][0]["type"] == "tool_result"]
    assert len(resultats) == 1 and len(resultats[0]["content"]) == 2
    assistant = next(m for m in corps["messages"] if m["role"] == "assistant")
    assert assistant["content"][1] == {"type": "tool_use", "id": "a1", "name": "fiche_lire", "input": {"x": 1}}


async def test_openai_requete_au_format_compatible_et_adresse_libre():
    vu = {}

    def repondre(requete: httpx.Request) -> httpx.Response:
        vu["url"], vu["entetes"], vu["corps"] = str(requete.url), requete.headers, json.loads(requete.content)
        return httpx.Response(200, content=flux_openai())

    reglages = ReglagesCerveau(format="openai", modele="gpt-x", adresse="https://api.exemple-compatible.test/v1/")
    await jouer(fabriquer(reglages, CLE, httpx.MockTransport(repondre)))
    assert vu["url"] == "https://api.exemple-compatible.test/v1/chat/completions"
    assert vu["entetes"]["authorization"] == f"Bearer {CLE}"
    corps = vu["corps"]
    assert corps["messages"][0] == {"role": "system", "content": "Consigne"}
    assert corps["tools"][0]["function"]["name"] == "fiche_lire"
    appel_assistant = next(m for m in corps["messages"] if m["role"] == "assistant")
    assert json.loads(appel_assistant["tool_calls"][0]["function"]["arguments"]) == {"x": 1}
    assert [m["tool_call_id"] for m in corps["messages"] if m["role"] == "tool"] == ["a1", "a2"]


async def test_les_deux_formats_donnent_les_memes_evenements():
    anthropic = fabriquer(ReglagesCerveau(format="anthropic", modele="m"), CLE, httpx.MockTransport(lambda r: httpx.Response(200, content=flux_anthropic())))
    openai = fabriquer(ReglagesCerveau(format="openai", modele="m"), CLE, httpx.MockTransport(lambda r: httpx.Response(200, content=flux_openai())))
    a, o = normalise(await jouer(anthropic)), normalise(await jouer(openai))
    assert a["texte"] == o["texte"] == "Je regarde."
    assert a["appels"] == o["appels"] == [("fiche_lire", {"workflow_id": 42})]
    assert (a["usage"]["entree"], a["usage"]["sortie"], a["usage"]["cache_lu"]) == (120, 33, 80)
    assert (o["usage"]["entree"], o["usage"]["sortie"], o["usage"]["cache_lu"]) == (120, 33, 80)
    assert a["fin"] == o["fin"] == {"type": "fin", "raison": "outils"}


@pytest.mark.parametrize("format_", ["anthropic", "openai"])
@pytest.mark.parametrize(
    ("statut", "code"), [(401, CODE_CLE), (403, CODE_CLE), (400, CODE_REQUETE), (404, CODE_REQUETE)]
)
async def test_les_erreurs_sont_normalisees_et_la_cle_ne_sort_jamais(format_, statut, code):
    corps = {"error": {"message": f"Invalid key {CLE} for the request"}}
    cerveau = fabriquer(ReglagesCerveau(format=format_, modele="m"), CLE, httpx.MockTransport(lambda r: httpx.Response(statut, json=corps)))
    with pytest.raises(ErreurCerveau) as erreur:
        await jouer(cerveau)
    assert erreur.value.code == code and not erreur.value.reessayable
    assert CLE not in erreur.value.message and CLE not in repr(erreur.value)


@pytest.mark.parametrize("format_", ["anthropic", "openai"])
async def test_une_panne_passagere_est_retentee_avant_le_premier_evenement(format_, monkeypatch):
    attentes = []

    async def sans_attendre(secondes):
        attentes.append(secondes)

    monkeypatch.setattr(appel, "_dormir", sans_attendre)
    reponses = [httpx.Response(429, json={"error": {"message": "slow down"}}), httpx.Response(529, json={}), httpx.Response(
        200, content=flux_anthropic() if format_ == "anthropic" else flux_openai()
    )]
    cerveau = fabriquer(ReglagesCerveau(format=format_, modele="m"), CLE, httpx.MockTransport(lambda r: reponses.pop(0)))
    assert normalise(await jouer(cerveau))["texte"] == "Je regarde."
    assert len(attentes) == 2 and not reponses


async def test_une_panne_qui_dure_leve_une_erreur_reessayable_normalisee(monkeypatch):
    async def sans_attendre(secondes):
        return None

    monkeypatch.setattr(appel, "_dormir", sans_attendre)
    cerveau = fabriquer(ReglagesCerveau(format="openai", modele="m"), CLE, httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    with pytest.raises(ErreurCerveau) as erreur:
        await jouer(cerveau)
    assert erreur.value.code == CODE_LIMITE and erreur.value.reessayable
    cerveau = fabriquer(ReglagesCerveau(format="anthropic", modele="m"), CLE, httpx.MockTransport(lambda r: httpx.Response(503, json={})))
    with pytest.raises(ErreurCerveau) as erreur:
        await jouer(cerveau)
    assert erreur.value.code == CODE_INDISPONIBLE


async def test_une_erreur_en_cours_de_flux_n_est_pas_rejouee(monkeypatch):
    """Après un événement rendu, on ne recommence pas : le moteur aurait le début en double."""
    appels = []

    def repondre(requete):
        appels.append(1)
        flux = sse(
            ("message_start", {"type": "message_start", "message": {"usage": {}}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "début"}}),
            ("error", {"type": "error", "error": {"type": "overloaded_error", "message": "coupé"}}),
        )
        return httpx.Response(200, content=flux)

    cerveau = fabriquer(ReglagesCerveau(format="anthropic", modele="m"), CLE, httpx.MockTransport(repondre))
    recus = []
    with pytest.raises(ErreurCerveau):
        async for evenement in cerveau.tour(systeme="s", messages=MESSAGES, outils=OUTILS):
            recus.append(evenement)
    assert [e["texte"] for e in recus] == ["début"] and len(appels) == 1


async def test_des_arguments_illisibles_sont_signales_au_moteur():
    flux = sse(
        (None, {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "fiche_lire", "arguments": "{pas du json"}}]}, "finish_reason": "tool_calls"}]}),
        (None, "[DONE]"),
    )
    cerveau = fabriquer(ReglagesCerveau(format="openai", modele="m"), CLE, httpx.MockTransport(lambda r: httpx.Response(200, content=flux)))
    appels = [e for e in await jouer(cerveau) if e["type"] == "appel"]
    assert appels[0]["illisible"] is True and appels[0]["arguments"] == {}


def test_sans_cle_ou_sans_modele_le_cerveau_ne_se_construit_pas():
    with pytest.raises(ErreurCerveau) as erreur:
        fabriquer(ReglagesCerveau(format="openai", modele="m"), None)
    assert erreur.value.code == "cle_absente"
    with pytest.raises(ErreurCerveau):
        fabriquer(ReglagesCerveau(format="openai", modele=""), CLE)
