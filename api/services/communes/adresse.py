"""[.mark] The business's address: checked on save, resolved and injected per call.

Decisions of 2026-09-16:

- D2: set on the organization, overridable per agent. An agent that leaves it
  empty uses the organization's address.
- D3: postal code (checked), commune chosen in that code's list (stored with
  its INSEE code), street (optional).
- D4: given to the agent in the variable ``adresse_etablissement``; the town
  recognition reads only postal code and commune.

⛔ Two sides, two rules, the same as the opening hours:

- SAVING refuses an address whose commune does not exist or does not carry
  that postal code (422 with a message). Checked against the national list.
- A CALL never fails because of the address: ``resoudre_adresse`` reads only
  its own key, ``lire_adresse_etablissement`` and ``injecter_adresse_etablissement``
  never raise. An address written by hand past a bound is logged and ignored.
"""

from __future__ import annotations

from loguru import logger
from pydantic import ValidationError

from api.schemas.organization_preferences import (
    AdresseEtablissement,
    OrganizationPreferences,
)
from api.services.communes.base import BaseCommunes, obtenir_base

CLE_ADRESSE = "adresse_etablissement"


class AdresseInvalide(ValueError):
    """The address refers to a commune that does not exist or not at that postal code."""


def verifier_adresse(adresse: AdresseEtablissement, base: BaseCommunes) -> AdresseEtablissement:
    """The address with the commune's official name, or ``AdresseInvalide``.

    The INSEE code is the reference: the name stored is the official one, so
    what the agent reads is never a name typed by hand.
    """
    commune = base.commune(adresse.code_insee)
    if commune is None:
        raise AdresseInvalide(f"Unknown commune (INSEE code {adresse.code_insee}).")
    if adresse.code_postal not in commune.cps:
        raise AdresseInvalide(
            f"{commune.nom} does not have the postal code {adresse.code_postal} "
            f"(its postal codes: {', '.join(commune.cps)})."
        )
    return adresse.model_copy(update={"commune": commune.nom})


async def valider_adresse_saisie(adresse: AdresseEtablissement | None) -> AdresseEtablissement | None:
    """Save-route check. The national list is read off the event loop."""
    if adresse is None:
        return None
    return verifier_adresse(adresse, await obtenir_base())


def _adresse_de(valeur, source: str) -> AdresseEtablissement | None:
    if valeur is None:
        return None
    if isinstance(valeur, AdresseEtablissement):
        return valeur
    try:
        return AdresseEtablissement.model_validate(valeur)
    except ValidationError as erreur:
        logger.warning(f"[.mark] {source} business address ignored, invalid: {erreur}")
        return None


def resoudre_adresse(
    run_configs: dict | None, preferences: OrganizationPreferences | None
) -> AdresseEtablissement | None:
    """Agent's address if set, else the organization's, else ``None``. Never raises."""
    try:
        agent = _adresse_de((run_configs or {}).get(CLE_ADRESSE), "Agent")
        if agent is not None:
            return agent
        return _adresse_de(getattr(preferences, CLE_ADRESSE, None), "Organization")
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Business address not resolved, the call goes on without it: {erreur!r}")
        return None


async def lire_adresse_etablissement(
    run_configs: dict | None, organization_id: int | None
) -> AdresseEtablissement | None:
    """Read the organization's preferences and resolve. Never raises."""
    try:
        from api.services.organization_preferences import get_organization_preferences

        preferences = await get_organization_preferences(organization_id)
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Organization preferences unreadable, agent's address only: {erreur!r}")
        preferences = None
    return resoudre_adresse(run_configs, preferences)


def texte_adresse(adresse: AdresseEtablissement) -> str:
    """« 12 rue de la Gare, 60740 Saint-Maximin », or « 60740 Saint-Maximin »."""
    ville = f"{adresse.code_postal} {adresse.commune}"
    return f"{adresse.voie}, {ville}" if adresse.voie else ville


def injecter_adresse_etablissement(contexte: dict, adresse: AdresseEtablissement | None) -> dict:
    """Return the call context with ``adresse_etablissement`` added.

    - No address: the context is returned unchanged, key absent.
    - A value already present and non-empty is kept (a replay keeps it; the
      pre-call fetch, merged later, wins anyway).
    - ⛔ Never raises.
    """
    try:
        if adresse is None:
            return contexte
        actuelle = contexte.get(CLE_ADRESSE)
        if actuelle is not None and not (isinstance(actuelle, str) and not actuelle.strip()):
            return contexte
        return {**contexte, CLE_ADRESSE: texte_adresse(adresse)}
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.error(f"[.mark] Business address not injected, the call goes on without it: {erreur!r}")
        return contexte
