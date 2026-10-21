"""[.mark] Chantier correctifs-apres-banc-v4, lot 3 : les essais d'un outil HTTP (plan § 5.1).

Chaque cas du tableau passe par la vraie ``execute_http_tool``, devant un faux service (la couche
``httpx.AsyncClient``), et compte les requêtes qui partent réellement.

| Test | La garantie |
|---|---|
| défaut | 0 essai : une seule requête, comme avant, quelle que soit la panne |
| requête pas partie | connexion refusée, nom introuvable : relancée, case « sans risque » cochée ou non |
| délai | pas de réponse dans le délai : relancée seulement si « sans risque de doublon » |
| erreur du service | 5xx : relancée seulement si « sans risque de doublon » ; le dernier résultat est rendu quand les essais sont épuisés |
| jamais | 4xx, réponse 2xx qui dit un échec, erreur d'exécution : une seule requête, même case cochée |
| attente | l'attente réglée sépare les essais ; au plus 2 essais de plus quoi qu'on écrive |
| délai total | (1 + essais) délais + attentes ; l'appel de fonction du moteur l'attend (sinon il coupait l'outil au premier délai) |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.services.workflow.tools.custom_tool import (
    delai_total_s,
    execute_http_tool,
    reglages_des_essais,
)

MODULE = "api.services.workflow.tools.custom_tool"


def _outil(**config):
    return SimpleNamespace(
        tool_uuid="essais-test",
        name="Chercher",
        description="Cherche.",
        category="http_api",
        definition={
            "schema_version": 1,
            "type": "http_api",
            "config": {
                "method": "POST",
                "url": "https://agenda.example.test/chercher",
                "timeout_ms": 5000,
                "attente_entre_essais_s": 0,
                **config,
            },
        },
    )


def _reponse(code, corps=None):
    r = Mock(status_code=code, text="")
    r.json.return_value = corps if corps is not None else {"ok": code < 400}
    return r


async def _jouer(sorties, **config):
    """Rejoue ``execute_http_tool`` ; ``sorties`` : ce que le faux service fait à chaque requête
    (une exception levée, ou une réponse). Rend (résultat, nombre de requêtes parties, pauses)."""
    pauses = []

    async def pause(secondes):
        pauses.append(secondes)

    with patch(f"{MODULE}.httpx.AsyncClient") as client, patch(f"{MODULE}.asyncio.sleep", pause):
        session = AsyncMock()
        session.request.side_effect = sorties
        client.return_value.__aenter__.return_value = session
        resultat = await execute_http_tool(_outil(**config), {"jour": "demain"})
    return resultat, session.request.call_count, pauses


REFUSEE = httpx.ConnectError("connexion refusée")
INTROUVABLE = httpx.ConnectError("[Errno -2] Name or service not known")
DELAI = httpx.ReadTimeout("pas de réponse")


@pytest.mark.asyncio
@pytest.mark.parametrize("panne", [REFUSEE, DELAI, _reponse(503)])
async def test_par_defaut_une_seule_requete_comme_avant(panne):
    resultat, requetes, pauses = await _jouer([panne, _reponse(200)])
    assert requetes == 1 and pauses == []
    assert resultat["status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("sans_risque", [False, True])
@pytest.mark.parametrize("panne", [REFUSEE, INTROUVABLE, httpx.ConnectTimeout("connexion trop lente")])
async def test_une_requete_pas_partie_est_relancee(panne, sans_risque):
    resultat, requetes, _ = await _jouer(
        [panne, panne, _reponse(200, {"dates": ["jeudi"]})], essais=2, sans_risque_de_doublon=sans_risque
    )
    assert requetes == 3
    assert resultat["status"] == "success" and resultat["data"] == {"dates": ["jeudi"]}


@pytest.mark.asyncio
async def test_un_delai_n_est_relance_que_sans_risque_de_doublon():
    resultat, requetes, _ = await _jouer([DELAI, _reponse(200)], essais=2)
    assert requetes == 1 and resultat["status"] == "error" and "timed out" in resultat["error"]
    resultat, requetes, _ = await _jouer([DELAI, _reponse(200)], essais=2, sans_risque_de_doublon=True)
    assert requetes == 2 and resultat["status"] == "success"


@pytest.mark.asyncio
async def test_une_erreur_du_service_n_est_relancee_que_sans_risque_de_doublon():
    resultat, requetes, _ = await _jouer([_reponse(503), _reponse(200)], essais=2)
    assert requetes == 1 and resultat["status_code"] == 503
    resultat, requetes, _ = await _jouer([_reponse(503), _reponse(200)], essais=2, sans_risque_de_doublon=True)
    assert requetes == 2 and resultat["status"] == "success"
    # Essais épuisés : le dernier résultat est rendu tel quel (c'est lui qui passe par la règle « un outil échoue »).
    resultat, requetes, _ = await _jouer(
        [_reponse(502), _reponse(503), _reponse(504)], essais=2, sans_risque_de_doublon=True
    )
    assert requetes == 3 and resultat["status"] == "error" and resultat["status_code"] == 504


@pytest.mark.asyncio
@pytest.mark.parametrize("sortie", [_reponse(400), _reponse(404), _reponse(422), _reponse(200, {"statut": "echec"}), ValueError("boum")])
async def test_un_refus_un_echec_dit_ou_une_erreur_d_execution_ne_sont_jamais_relances(sortie):
    """Même avec la case cochée et 2 essais : ce n'est pas une panne, relancer ne changerait rien (ou doublerait)."""
    _, requetes, _ = await _jouer([sortie, _reponse(200)], essais=2, sans_risque_de_doublon=True)
    assert requetes == 1


@pytest.mark.asyncio
async def test_l_attente_separe_les_essais_et_les_essais_sont_bornes():
    _, requetes, pauses = await _jouer(
        [REFUSEE] * 5, essais=9, attente_entre_essais_s=2.5
    )
    assert requetes == 3  # 2 essais de plus au plus, quoi qu'on écrive
    assert pauses == [2.5, 2.5]


def test_les_reglages_illisibles_valent_le_defaut():
    assert reglages_des_essais({}) == (0, 1.0, False)
    assert reglages_des_essais({"essais": "deux", "attente_entre_essais_s": "x", "sans_risque_de_doublon": "oui"}) == (
        0,
        1.0,
        False,
    )
    assert reglages_des_essais({"essais": -3, "attente_entre_essais_s": 999, "sans_risque_de_doublon": True}) == (0, 30.0, True)


def test_le_delai_total_compte_les_essais_et_les_attentes():
    assert delai_total_s({"timeout_ms": 5000}) == 5.0  # défaut : comme avant
    assert delai_total_s({"timeout_ms": 5000, "essais": 1, "attente_entre_essais_s": 1}) == 11.0
    assert delai_total_s({"timeout_ms": 5000, "essais": 2, "attente_entre_essais_s": 1}) == 17.0
    assert delai_total_s({"essais": 2, "attente_entre_essais_s": 0}) == 15.0  # délai absent : 5 s


def test_l_appel_de_fonction_du_moteur_attend_les_essais():
    """Sans cela le moteur coupait l'outil au premier délai (timeout de l'appel de fonction = timeout_ms)."""
    gestionnaire = CustomToolManager.__new__(CustomToolManager)
    gestionnaire._engine = SimpleNamespace()
    gestionnaire._agent = None
    for essais, attendu in ((0, 5.0), (2, 17.0)):
        outil = _outil(essais=essais, attente_entre_essais_s=1)
        _, delai = gestionnaire._create_handler(outil, "chercher")
        assert delai == attendu
