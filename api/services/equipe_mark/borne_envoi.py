"""[.mark] Correctifs d'écran, revue : une borne de taille par route qui reçoit un fichier ou un gros corps.

Intergiciel ASGI : il refuse avec **413** un corps plus gros que la borne de sa route, **avant** que FastAPI lise le formulaire
(donc avant que la route, ses dépendances ou le disque temporaire du multipart soient touchés). Il regarde le
``Content-Length`` annoncé et, quand le corps est découpé (chunked) ou que l'annonce ment, compte les octets reçus.

Une route absente du tableau n'a aucune borne ici : ce module ne durcit que ce qu'il liste. Chaque borne est **au moins égale** à
ce que la route accepte déjà (sa limite écrite dans le code, plus la marge des entêtes multipart), jamais en dessous.
Format d'erreur unique : ``413`` et ``{"detail": "envoi_trop_lourd"}``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from api.services.builder.constantes import DEPOT_MAX_OCTETS
from api.services.builder.dossiers.extraction import (
    OCTETS_MAX as DEPOT_FICHIER_MAX_OCTETS,
)
from api.services.equipe_mark.image_logo import OCTETS_MAX as LOGO_OCTETS_MAX

CODE_ENVOI_TROP_LOURD = "envoi_trop_lourd"
MARGE_MULTIPART = 65_536  # entêtes et séparateurs d'un formulaire multipart autour du fichier
MO = 1024 * 1024


@dataclass(frozen=True)
class Borne:
    methode: str
    chemin: re.Pattern[str]
    octets: int
    raison: str


def _b(methode: str, motif: str, octets: int, raison: str) -> Borne:
    return Borne(methode, re.compile(rf"^/api/v1{motif}/?$"), octets, raison)


# Tableau des routes à corps lourd (copié dans le journal du chantier). JSON : la borne couvre le pire cas d'échappement
# (un texte de n octets peut peser jusqu'à 6 n en JSON) au-dessus de la limite de contenu déjà écrite dans la route.
BORNES: tuple[Borne, ...] = (
    _b("PUT", r"/espaces/\d+/logo", LOGO_OCTETS_MAX + MARGE_MULTIPART, "logo : 1 Mo + entêtes"),
    _b("POST", r"/builder/bibliotheque/depot", DEPOT_MAX_OCTETS + MARGE_MULTIPART, "dépôt de la bibliothèque : 15 Mo + entêtes"),
    _b("POST", r"/builder/depot/\d+", DEPOT_FICHIER_MAX_OCTETS + MARGE_MULTIPART, "dépôt d'un fichier de contexte : 15 Mo + entêtes"),
    _b("POST", r"/workflow-recordings/transcribe", 50 * MO, "audio à transcrire : aucune limite avant, 50 Mo écrits"),
    _b("POST", r"/agent-fichiers/\d+/import", 64 * MO, "import de fichiers d'agent : 8 Mo de texte, ×6 d'échappement JSON, 64 Mo"),
    _b("POST", r"/builder/bibliotheque/import", 32 * MO, "import d'un élément : contenu sans borne avant, 32 Mo écrits"),
    _b("POST", r"/builder/attaques/jeu-public/importer", 64 * MO, "jeu public : 12 M de caractères, 64 Mo"),
    _b("POST", r"/organizations/modeles-de-reglages/import", 32 * MO, "fichier de modèle de réglages : 32 Mo écrits"),
    _b("POST", r"/organizations/lexique/import", 32 * MO, "lexique métier : 2000 termes, 32 Mo écrits"),
)


def borne_de(methode: str, chemin: str) -> Borne | None:
    for borne in BORNES:
        if borne.methode == methode and borne.chemin.match(chemin):
            return borne
    return None


class _EnvoiTropLourd(Exception):
    pass


class BorneEnvoi:
    """Intergiciel ASGI : refuse un corps au-dessus de la borne de sa route, avant que la route le lise."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        borne = borne_de(scope.get("method", ""), scope.get("path", "")) if scope.get("type") == "http" else None
        if borne is None:
            await self.app(scope, receive, send)
            return
        annonce = dict(scope.get("headers") or []).get(b"content-length", b"")
        if annonce.isdigit() and int(annonce) > borne.octets:
            await self._refuser(send)
            return
        recus = 0
        depasse = False
        commence = False

        async def compter(*args, **kwargs):
            nonlocal recus, depasse
            message = await receive(*args, **kwargs)
            if message.get("type") == "http.request":
                recus += len(message.get("body", b""))
                if recus > borne.octets:
                    depasse = True
                    raise _EnvoiTropLourd()
            return message

        async def observer(message):
            # FastAPI transforme une exception levée pendant la lecture du corps en 400 : tant que la réponse n'est pas partie,
            # un dépassement constaté la remplace par le 413.
            nonlocal commence
            if depasse and not commence:
                if message.get("type") == "http.response.start":
                    commence = True
                    await self._refuser(send)
                return
            if message.get("type") == "http.response.start":
                commence = True
            if depasse:
                return
            await send(message)

        try:
            await self.app(scope, compter, observer)
        except _EnvoiTropLourd:
            if not commence:
                await self._refuser(send)

    @staticmethod
    async def _refuser(send) -> None:
        corps = json.dumps({"detail": CODE_ENVOI_TROP_LOURD}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(corps)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": corps})
