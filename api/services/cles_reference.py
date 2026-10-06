"""[.mark] Une clé de la bibliothèque désignée par référence dans une configuration de modèle
(chantier direct-et-passe-muette, lot 0 bis, P21, P22).

« Models » et les réglages de modèle d'un agent rangent ``mark-cle:<uuid>`` à la place d'une clé.
Le serveur remplace la référence par la clé de la bibliothèque à deux endroits seulement, en
amont des quelque 70 lecteurs de ``api_key`` :

- au chargement de la configuration effective (``ai_model_configuration.py``), donc tout appel :
  une référence introuvable s'écrit au journal d'erreur et reste telle quelle (le fournisseur la
  refusera), jamais en silence ;
- au début de la validation auprès du fournisseur (``check_validity.py``), donc tout
  enregistrement : une référence introuvable refuse l'enregistrement en le disant.

Une référence n'est pas un secret : elle n'est pas masquée (``masking.py``).

Module sans dépendance vers les routes ni l'appelant simulé : ``masking.py`` et
``check_validity.py`` l'importent sans circuit.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

PREFIXE = "mark-cle:"
MARQUE = "mark_bibliotheque"
SERVICES = ("llm", "stt", "tts", "embeddings", "realtime")


def est_reference(valeur) -> bool:
    return isinstance(valeur, str) and valeur.startswith(PREFIXE)


def reference_de(uuid: str) -> str:
    return f"{PREFIXE}{uuid}"


def uuid_de(reference: str) -> str:
    return reference[len(PREFIXE) :]


class CleIntrouvable(ValueError):
    """Une référence désigne une clé supprimée ou absente de l'organisation."""


async def _cle(uuid: str, organization_id: int) -> Optional[str]:
    from api.db import (
        db_client,  # à l'usage : masking.py importe ce module sans la base
    )

    identifiant = await db_client.get_credential_by_uuid(uuid, organization_id)
    donnees = (identifiant.credential_data or {}) if identifiant else {}
    if not donnees.get(MARQUE):
        return None
    valeur = donnees.get("token")
    return valeur if isinstance(valeur, str) and valeur.strip() else None


async def resoudre_les_cles(
    configuration, organization_id: Optional[int], *, strict: bool
):
    """Une copie de la configuration effective où chaque référence est remplacée par sa clé.

    ``strict`` (enregistrement) : une référence introuvable lève ``CleIntrouvable``.
    Sinon (appel) : elle s'écrit au journal d'erreur et reste telle quelle.
    Sans référence, la configuration est rendue telle quelle (aucune lecture de la base).
    """
    if configuration is None:
        return configuration
    a_resoudre = {}
    for nom in SERVICES:
        service = getattr(configuration, nom, None)
        if service is None or "api_key" not in type(service).model_fields:
            continue
        # La valeur rangée, sans le tirage au sort de ``__getattribute__`` sur une liste.
        brut = service.__dict__.get("api_key")
        valeurs = brut if isinstance(brut, list) else [brut]
        if any(est_reference(v) for v in valeurs):
            a_resoudre[nom] = (service, brut, valeurs)
    if not a_resoudre:
        return configuration

    mises_a_jour = {}
    for nom, (service, brut, valeurs) in a_resoudre.items():
        resolues = []
        for valeur in valeurs:
            if not est_reference(valeur):
                resolues.append(valeur)
                continue
            cle = (
                await _cle(uuid_de(valeur), organization_id)
                if organization_id is not None
                else None
            )
            if cle is None:
                message = (
                    f"The {nom} key chosen in the key library was deleted or is unusable: "
                    "pick another in « Keys »."
                )
                if strict:
                    raise CleIntrouvable(message)
                logger.error(f"[.mark] {message} (organization {organization_id})")
                cle = valeur
            resolues.append(cle)
        mises_a_jour[nom] = service.model_copy(
            update={"api_key": resolues if isinstance(brut, list) else resolues[0]}
        )
    return configuration.model_copy(update=mises_a_jour)
