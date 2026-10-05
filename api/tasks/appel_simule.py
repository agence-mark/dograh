"""[.mark] La tâche de fond d'une série de l'appelant simulé (langwatch-et-fenetre-du-run, lot 3, L19).

Le travail est dans ``services/appel_simule/serie.py`` ; ici, seulement l'entrée ARQ.
"""

from api.services.appel_simule.serie import jouer_serie


async def jouer_serie_simulee(ctx, organization_id: int, serie_id: str) -> None:
    await jouer_serie(organization_id, serie_id)
