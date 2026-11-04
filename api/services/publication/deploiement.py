"""[.mark] U11 (E103) : le déploiement progressif. Construit et testé, ÉTEINT par défaut.

Éteint (réglage ``publication.deploiement.actif``) : une publication vaut pour tous les appels, aucune ligne n'est lue.
Allumé et une part en cours (ligne ``MARK_DEPLOIEMENT:<agent>``) : l'appel reçoit sa version à son début, d'après le numéro de
l'appelant. Le même numéro tombe toujours du même côté (empreinte du numéro, jamais le numéro écrit). Chaque appel porte déjà sa
version (``workflow_runs.definition_id``).

⛔ Aucune bascule ni retour en arrière automatique : « passer à 100 % » et « revenir à la vN » sont des gestes humains.
La ligne ne contient que des numéros de versions et un pourcentage, jamais de donnée personnelle.
"""

from __future__ import annotations

import hashlib
from typing import Any

from loguru import logger

from api.services.builder import stock

PREFIXE = "MARK_DEPLOIEMENT:"


class ErreurDeploiement(Exception):
    pass


def cle(workflow_id: int) -> str:
    return f"{PREFIXE}{workflow_id}"


def part_de(workflow_id: int, appelant: str | None) -> int | None:
    """La place stable (0 à 99) d'un appelant pour cet agent. ``None`` : numéro absent ou masqué (aucune place)."""
    chiffres = "".join(c for c in (appelant or "") if c.isdigit())
    if not chiffres:
        return None
    # Les 9 derniers chiffres : « +33 6 12... » et « 06 12... » sont le même appelant.
    empreinte = hashlib.sha256(f"{workflow_id}:{chiffres[-9:]}".encode()).hexdigest()
    return int(empreinte[:8], 16) % 100


# [.mark] Partie 3, sous-lot 2 (SE-8) : la clé de répartition de CHAQUE chemin de création d'un appel. Une clé est stable (le
# même interlocuteur tombe toujours du même côté) et ne contient aucune donnée écrite en clair : seule son empreinte sert.
#   entrant (téléphonie, ARI, flux d'agent) : le numéro de l'appelant (``appelant=``, chiffres seulement) ;
#   sortant direct et déclenché par l'API    : le numéro appelé (même empreinte que s'il appelait : même côté dans les deux sens) ;
#   campagne                                  : la campagne ET le contact (``cle_campagne``) ;
#   widget du site                            : le jeton du site ET l'adresse du visiteur (``cle_site``) ;
#   transfert vers un agent                   : l'appel qui transfère (``cle_appel``), pour que la destination soit la même
#                                               à chaque lecture de cet appel.
def cle_campagne(campagne_id: int, contact: str | None) -> str:
    chiffres = "".join(c for c in (contact or "") if c.isdigit())
    reste = chiffres[-9:] if chiffres else (contact or "").strip()
    return f"campagne:{campagne_id}:{reste}" if reste else ""


def cle_site(jeton_id: int, visiteur: str | None) -> str:
    """``visiteur`` vide (adresse illisible) : clé vide, donc la version qui tenait avant, jamais un tirage."""
    return f"site:{jeton_id}:{visiteur.strip()}" if visiteur and visiteur.strip() else ""


def appelant_du_flux(params: dict[str, Any]) -> str:
    """Le numéro de l'appelant d'un flux d'agent, d'après les paramètres que le fournisseur envoie. ``""`` : masqué ou absent."""
    for nom in ("from", "From", "caller", "caller_number", "from_number", "ani"):
        valeur = params.get(nom)
        if isinstance(valeur, str) and valeur.strip():
            return valeur
    return ""


def cle_appel(workflow_run_id: int) -> str:
    return f"appel:{workflow_run_id}"


def part_de_cle(workflow_id: int, cle_de_repartition: str) -> int | None:
    """La place stable (0 à 99) d'une clé de répartition pour cet agent. ``None`` : clé vide (aucune place)."""
    if not cle_de_repartition or not cle_de_repartition.strip().strip(":"):
        return None
    empreinte = hashlib.sha256(f"{workflow_id}:{cle_de_repartition.strip()}".encode()).hexdigest()
    return int(empreinte[:8], 16) % 100


def version_attribuee(
    ligne: dict[str, Any] | None, workflow_id: int, appelant: str | None, cle_de_repartition: str | None = None
) -> int | None:
    """Le ``definition_id`` à donner à cet appel, ou ``None`` (= la version publiée, comme sans déploiement)."""
    if not ligne:
        return None
    nouvelle, precedente = ligne.get("nouvelle"), ligne.get("precedente")
    if not isinstance(nouvelle, int) or not isinstance(precedente, int):
        return None
    pourcentage = int(ligne.get("pourcentage") or 0)
    place = part_de_cle(workflow_id, cle_de_repartition) if cle_de_repartition is not None else part_de(workflow_id, appelant)
    if place is None:  # appelant masqué : la version qui tenait avant, jamais un tirage
        return precedente
    return nouvelle if place < pourcentage else precedente


async def lire(organization_id: int, workflow_id: int) -> dict[str, Any] | None:
    return await stock.lire(organization_id, cle(workflow_id))


async def definition_pour_l_appel(
    workflow: Any, appelant: str | None = None, cle_de_repartition: str | None = None
) -> int | None:
    """Appelé à la création de tout appel (entrant, sortant, campagne, site, flux d'agent, ARI). Rien à lire quand le déploiement est éteint."""
    from api.services.publication.reglages import deploiement_actif

    configurations = getattr(getattr(workflow, "released_definition", None), "workflow_configurations", None) or getattr(
        workflow, "workflow_configurations", None
    )
    if not deploiement_actif(configurations):
        return None
    try:
        ligne = await lire(workflow.organization_id, workflow.id)
    except Exception as erreur:  # noqa: BLE001 -- une panne de lecture : la version publiée, comme avant
        logger.warning(f"[publication] déploiement non lu ({type(erreur).__name__})")
        return None
    return version_attribuee(ligne, workflow.id, appelant, cle_de_repartition)


async def demarrer(
    organization_id: int, workflow_id: int, nouvelle: int, precedente: int | None, pourcentage: int, par: str
) -> dict[str, Any]:
    if not 1 <= pourcentage <= 99:
        raise ErreurDeploiement("The share of calls is between 1 and 99 (100 is a normal publication).")
    if precedente is None:
        raise ErreurDeploiement("There is no earlier published version to keep the rest of the calls on.")
    ligne = {"nouvelle": nouvelle, "precedente": precedente, "pourcentage": pourcentage, "par": par}
    await stock.ecrire(organization_id, cle(workflow_id), ligne)
    return ligne


async def passer_a_100(organization_id: int, workflow_id: int) -> dict[str, Any]:
    """Un geste humain : la version publiée prend tous les appels (la ligne disparaît)."""
    return {"supprime": await stock.supprimer(organization_id, cle(workflow_id))}


async def revenir(organization_id: int, workflow_id: int, definition_id: int, numero: int | None, par: str) -> dict[str, Any]:
    """Un geste humain : tous les appels repartent sur la version ``definition_id`` (0 % à la version publiée)."""
    from api.db import db_client

    workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
    nouvelle = getattr(getattr(workflow, "released_definition", None), "id", None)
    if not isinstance(nouvelle, int):
        raise ErreurDeploiement("No published version.")
    ligne = {"nouvelle": nouvelle, "precedente": definition_id, "pourcentage": 0, "par": par, "revenu_a": numero}
    await stock.ecrire(organization_id, cle(workflow_id), ligne)
    return ligne

