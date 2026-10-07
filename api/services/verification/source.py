"""[.mark] Where a caller's record is read (L6, V3, V4), in the hub's common format.

- ``hub`` (default): the client's database (``db/bases_clients/dossier.py``).
- a translator of the domain « dossier » (``logiciel`` of the settings): ``chercher`` with
  ``telephone`` or ``reference``, ``lire`` with ``id_externe`` (``OBJETS["dossier"]``). A new
  software is a new translator; nothing here changes.

Read on demand, nothing copied (H5). Never raises a detail to the model: the action stamps it.
"""

from __future__ import annotations

from api.schemas.apres_appel import numero_e164
from api.schemas.verification import ReglagesVerification

HUB = "hub"


def source_de(reglages: ReglagesVerification) -> str:
    return reglages.logiciel or HUB


async def _connexion(organization_id: int):
    from api.db.bases_clients.connexion import connecter
    from api.services.base_client.rattachement import nom_de_la_base

    nom = await nom_de_la_base(organization_id)
    if not nom:
        raise LookupError("no client database attached")
    return await connecter(nom)


async def trouver(
    organization_id: int, source: str, *, telephone: str | None = None,
    reference: str | None = None, delai: float = 3.0,
) -> dict | None:
    """The ONE record of this number (or reference), else None (none, or several: never guessed)."""
    numero = numero_e164(telephone) if telephone else None
    if source == HUB:
        from api.db.bases_clients import dossier as sql

        connexion = await _connexion(organization_id)
        try:
            contact = (
                await sql.contact_par_telephone(connexion, numero) if numero
                else await sql.contact_par_reference(connexion, reference)
            )
            return await sql.lire_dossier(connexion, contact) if contact else None
        finally:
            await connexion.close()
    from api.services.hub.traducteurs import operer

    arguments = {"telephone": numero} if numero else {"reference": str(reference or "")}
    trouves = await operer(organization_id, source, "dossier", "chercher", arguments, delai=delai)
    trouves = [t for t in trouves or [] if isinstance(t, dict) and t.get("id_externe")]
    return trouves[0] if len(trouves) == 1 else None


async def lire(organization_id: int, source: str, identifiant: str, *, delai: float = 3.0) -> dict | None:
    if source == HUB:
        from api.db.bases_clients import dossier as sql

        if not str(identifiant).isdigit():
            return None
        connexion = await _connexion(organization_id)
        try:
            return await sql.lire_dossier(connexion, int(identifiant))
        finally:
            await connexion.close()
    from api.services.hub.traducteurs import operer

    lu = await operer(organization_id, source, "dossier", "lire", {"id_externe": identifiant}, delai=delai)
    return lu if isinstance(lu, dict) and lu.get("id_externe") else None
