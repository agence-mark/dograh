"""[.mark] Clôture, SA-2 : le journal de l'équipe ne dit que ce qui a eu lieu.

``appliquer_acces`` (avant la route) retient la ligne du geste dans la portée de la requête ; ce module l'écrit
**après** la réponse, et seulement si elle est réussie (statut inférieur à 400). Un geste en échec (4xx, 500, exception) n'écrit
rien ; une tentative refusée faute de droit non plus (la ligne n'est retenue qu'une fois la permission accordée).
Une panne d'écriture se consigne sans bloquer ni changer la réponse, déjà partie.
"""

from __future__ import annotations

from loguru import logger

from api.services.equipe_mark.acces import CLE_JOURNAL_DIFFERE, journaliser


async def ecrire_le_journal_differe(scope: dict, statut: int | None) -> bool:
    """Écrit la ligne retenue si la réponse est réussie. Rend ``True`` quand une ligne a été confiée au journal."""
    retenue = scope.pop(CLE_JOURNAL_DIFFERE, None)
    if retenue is None or statut is None or statut >= 400:
        return False
    compte, action, organisation, detail = retenue
    try:
        await journaliser(compte, action, organisation, detail)
    except Exception:  # ``journaliser`` se protège déjà ; ceci protège la réponse contre tout le reste
        logger.warning("Journal write failed")
        return False
    return True


class JournalApresSucces:
    """Intergiciel ASGI : observe le statut de la réponse, puis écrit la ligne retenue par ``appliquer_acces``."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        statut: list[int] = []

        async def observer(message):
            if message.get("type") == "http.response.start":
                statut.append(int(message.get("status", 0)))
            await send(message)

        await self.app(scope, receive, observer)  # une exception remonte : aucun statut, aucune ligne
        await ecrire_le_journal_differe(scope, statut[0] if statut else None)
