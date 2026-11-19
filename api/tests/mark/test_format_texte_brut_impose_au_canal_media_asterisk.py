"""[.mark] Le fork demande lui-même à Asterisk le format texte brut des messages de contrôle du canal média.

| Cas | Ce qu'il prouve |
|---|---|
| sans jeton | la demande de canal média porte exactement ``f(plain-text)`` devant ``v(...)``, les trois paramètres de routage étant intacts : valeur entière comparée à un littéral |
| avec jeton | quand un secret est configuré, le jeton du flux audio voyage toujours dans ``v(...)``, derrière le format, et la route du flux audio l'accepterait (``verify_ws_token``) : le format n'a ni perdu le jeton ni été collé à lui |

Pourquoi : à la coupure de parole, le fork envoie à Asterisk sa commande de vidage en texte brut. Un
Asterisk réglé pour des messages de contrôle en JSON la refuse, et sa file audio ne se vide pas. Demandé
par l'appel lui-même, le format ne dépend plus du réglage de l'Asterisk d'en face.

La valeur est lue dans la requête que le faux Asterisk reçoit, à la couche réseau : c'est celle que
``_ari_request`` émet réellement.
"""

from collections.abc import Callable

import pytest

from api import constants
from api.services.telephony import ws_auth
from api.tests.mark.telephonie_commun import (
    AGENT,
    CREATION_DU_CANAL_MEDIA,
    RUN,
    canal_media_demande,
    monter_une_connexion,
)

CANAL_MEDIA = "canal-media"
SECRET_DU_FLUX_AUDIO = "secret-de-test"

# Ce qu'Asterisk reçoit, écrit en dur : le test ne lit aucune constante du code.
SANS_JETON = "f(plain-text)v(workflow_id=42,organization_id=1,workflow_run_id=123)"
DEBUT_AVEC_FORMAT = "f(plain-text)v("
PARAMETRES_AVEC_JETON = {"workflow_id", "organization_id", "workflow_run_id", "token"}


def _vaut_exactement_la_forme_sans_jeton(transport_data: str) -> None:
    assert transport_data == SANS_JETON


def _porte_un_jeton_valide_derriere_le_format(transport_data: str) -> None:
    assert transport_data.startswith(DEBUT_AVEC_FORMAT) and transport_data.endswith(")")
    # Relu comme Asterisk le remet à la route du flux audio : des paires clé=valeur.
    paires = transport_data[len(DEBUT_AVEC_FORMAT) : -1].split(",")
    parametres = dict(paire.split("=", 1) for paire in paires)
    assert set(parametres) == PARAMETRES_AVEC_JETON
    assert ws_auth.verify_ws_token(
        int(parametres["workflow_id"]),
        int(parametres["organization_id"]),
        int(parametres["workflow_run_id"]),
        parametres["token"],
    )


@pytest.mark.parametrize(
    ("secret", "verifier"),
    [
        pytest.param(None, _vaut_exactement_la_forme_sans_jeton, id="sans jeton"),
        pytest.param(
            SECRET_DU_FLUX_AUDIO,
            _porte_un_jeton_valide_derriere_le_format,
            id="avec jeton",
        ),
    ],
)
async def test_le_canal_media_est_demande_en_texte_brut_devant_les_parametres_de_routage(
    monkeypatch, secret: str | None, verifier: Callable[[str], None]
):
    monkeypatch.setattr(constants, "TELEPHONY_WS_TOKEN_SECRET", secret)
    montage = monter_une_connexion(monkeypatch)

    await montage.connexion._create_external_media(
        AGENT, str(RUN), channel_id=CANAL_MEDIA
    )

    assert canal_media_demande(montage.asterisk) == CANAL_MEDIA
    [demande] = montage.asterisk.parametres_recus(*CREATION_DU_CANAL_MEDIA)
    verifier(demande["transport_data"])
