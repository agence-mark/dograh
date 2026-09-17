"""[.mark] Where the trade vocabulary of an organization is read and written.

One row of ``organization_configurations``, key ``LEXIQUE_METIER`` (decision L1
of 2026-09-16: in the database, no migration). Format and bounds:
``api/schemas/lexique_metier.py``.

⛔ ``lire_lexique`` never raises: it is read when a call is set up, and a
missing or unreadable vocabulary must leave the call exactly as it is without
one (an empty vocabulary), never stop it.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.lexique_metier import LexiqueMetier

CLE = OrganizationConfigurationKey.LEXIQUE_METIER.value


async def lire_lexique(organization_id: int | None) -> LexiqueMetier:
    """The organization's vocabulary; empty when absent, unreadable or on any error."""
    if organization_id is None:
        return LexiqueMetier()
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return LexiqueMetier()
        return LexiqueMetier.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- a vocabulary problem never costs a call
        logger.warning(
            f"[.mark] Trade vocabulary of organization {organization_id} unreadable, "
            f"used as empty: {erreur!r}"
        )
        return LexiqueMetier()


async def lire_lexique_strict(organization_id: int | None) -> LexiqueMetier:
    """Le lexique, ou une exception si la ligne existe et n'est pas lisible.

    ⛔ Pour l'ÉCRAN seulement. La règle « ne jamais lever » est faite pour l'appel :
    sur l'écran, elle ferait afficher un lexique vide, et l'enregistrement qui
    suit (un remplacement complet) écraserait un lexique bien présent en base
    (relecture indépendante du 17/09).
    """
    if organization_id is None:
        return LexiqueMetier()
    ligne = await db_client.get_configuration(organization_id, CLE)
    if ligne is None or not ligne.value:
        return LexiqueMetier()
    return LexiqueMetier.model_validate(ligne.value)


async def enregistrer_lexique(organization_id: int, lexique: LexiqueMetier) -> LexiqueMetier:
    await db_client.upsert_configuration(organization_id, CLE, lexique.model_dump(mode="json"))
    return lexique


def fusionner_import(existant: LexiqueMetier, importe: LexiqueMetier) -> tuple[LexiqueMetier, int, int]:
    """Add the imported terms that are absent; never change a term already there (T13).

    A term is "already there" when ANY of its spellings (normalised) is already
    carried by the vocabulary: its pronunciation and its « listen for » box, set
    by the organization, stay as they are. Imported terms arrive unticked.

    Returns (merged vocabulary, added, already there). The merged vocabulary is
    validated again: past the bounds, ``pydantic.ValidationError``.
    """
    formes_presentes: set[str] = set()
    for terme in existant.termes:
        formes_presentes |= terme.formes_normalisees()

    ajoutes, deja_presents = [], 0
    for terme in importe.termes:
        formes = terme.formes_normalisees()
        if formes & formes_presentes:
            deja_presents += 1
            continue
        ajoutes.append(terme.model_copy(update={"a_ecouter": False}))
        formes_presentes |= formes

    modeles = list(existant.modeles_importes)
    connus = {(m.nom, m.date) for m in modeles}
    for modele in importe.modeles_importes:
        if (modele.nom, modele.date) not in connus:
            modeles.append(modele)
            connus.add((modele.nom, modele.date))

    fusion = LexiqueMetier.model_validate(
        {
            "modeles_importes": [m.model_dump() for m in modeles],
            "termes": [t.model_dump() for t in [*existant.termes, *ajoutes]],
        }
    )
    return fusion, len(ajoutes), deja_presents
