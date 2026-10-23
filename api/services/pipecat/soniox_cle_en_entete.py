"""[.mark] Chantier voix-soniox, D19 : la clé Soniox part dans l'en-tête de connexion.

Soniox refuse, à partir du 15/01/2027, toute connexion WebSocket qui ne porte pas
sa clé dans l'en-tête ``Authorization: Bearer`` (transcription et voix). Le
Pipecat que Dograh épingle (1.10) n'envoie la clé que dans le premier message de
configuration ; Pipecat 1.13 ajoute l'en-tête lui-même (PR #6096).

⛔ Le sous-module Pipecat n'est jamais modifié (R2) : deux sous-classes, une par
connecteur, qui complètent ``_websocket_connect`` (le point par où chaque
connexion passe, y compris les reconnexions). Le message de configuration reste
tel quel : Soniox accepte de le voir répéter la même clé.

🔑 ``setdefault`` : un appelant qui passe son propre en-tête garde la main, et
après une montée en 1.13 (qui pose le même en-tête) la surcharge devient sans
effet et peut être retirée avec sa ligne du registre.

Les deux classes partagent UNE mécanique (``CleSonioxEnEnteteMixin``) : un
connecteur Soniox de plus en hérite sans la réécrire.
"""

from api.services.pipecat.soniox_voix_correctifs import CorrectifsVoixSonioxMixin
from pipecat.services.soniox.stt import SonioxSTTService
from pipecat.services.soniox.tts import SonioxTTSService


def en_tete_de_cle_soniox(cle: str) -> dict[str, str]:
    """L'en-tête que Soniox exige. Partagé avec la sonde du lexique."""
    return {"Authorization": f"Bearer {cle}"}


class CleSonioxEnEnteteMixin:
    """Ajoute la clé du service à chaque connexion, sans écraser un en-tête donné."""

    async def _websocket_connect(self, uri: str, **kwargs):
        kwargs.setdefault("additional_headers", en_tete_de_cle_soniox(self._api_key))
        return await super()._websocket_connect(uri, **kwargs)


class MarkSonioxSTTService(CleSonioxEnEnteteMixin, SonioxSTTService):
    """Transcription Soniox, clé dans l'en-tête (construite par la fabrique)."""


class MarkSonioxTTSService(CorrectifsVoixSonioxMixin, CleSonioxEnEnteteMixin, SonioxTTSService):
    """Voix Soniox, clé dans l'en-tête (branchée par la fabrique au lot 3).

    Lot V de correctifs-apres-banc-commun : y ajoute les correctifs officiels de Pipecat 1.13
    (keepalive, flux configuré avant son texte, contextes fermés à une reconnexion, erreurs classées
    par code) et la connexion empruntée par la fabrique des sons. Voir ``soniox_voix_correctifs.py``."""
