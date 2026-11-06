"""[.mark] U11 (E103), partie 3 SA-L3b (05 § 12) : la répartition du trafic ENTRE BRANCHES (le déploiement progressif d'avant).

Un seul mécanisme de part du trafic : chaque branche active d'un agent porte une part (``workflow_branches.part_trafic``, total 100)
et sert sa version en ligne (``head_definition_id``). Éteint (réglage ``publication.deploiement.actif``) : une publication vaut pour
tous les appels, aucune ligne de branche n'est lue. Allumé : l'appel reçoit la version de SA branche à son début, d'après sa clé de
répartition. La même clé tombe toujours sur la même branche (empreinte, jamais le numéro écrit) ; en poussant une branche de 10 % à
25 %, un appelant ne passe que de la principale à la branche, jamais l'inverse. Chaque appel porte déjà sa version
(``workflow_runs.definition_id``).

⛔ Aucune bascule ni retour en arrière automatique : régler les parts est un geste humain (voir ``services/branches``).
"""

from __future__ import annotations

import hashlib
from typing import Any

from loguru import logger

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
    parts: list[dict[str, Any]] | None, workflow_id: int, appelant: str | None, cle_de_repartition: str | None = None
) -> int | None:
    """Le ``definition_id`` à donner à cet appel, ou ``None`` (= la version publiée de l'agent, comme sans répartition).

    ``parts`` : les branches actives, les non principales d'abord (``repartition_en_cours``). Une branche non principale occupe les
    places basses, dans l'ordre ; la principale garde le reste. Clé absente ou masquée : la principale, jamais un tirage."""
    if not parts:
        return None
    principale = next((p for p in parts if p.get("principale")), None)
    sans_place = principale["definition"] if principale else None
    place = part_de_cle(workflow_id, cle_de_repartition) if cle_de_repartition is not None else part_de(workflow_id, appelant)
    if place is None:
        return sans_place
    cumul = 0
    for branche in parts:
        if branche.get("principale") or not isinstance(branche.get("definition"), int):
            continue
        cumul += int(branche.get("part") or 0)
        if place < cumul:
            return branche["definition"]
    return sans_place


async def lire(organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
    from api.db import db_client

    return await db_client.repartition_en_cours(organization_id, workflow_id)


async def definition_pour_l_appel(
    workflow: Any, appelant: str | None = None, cle_de_repartition: str | None = None
) -> int | None:
    """Appelé à la création de tout appel (entrant, sortant, campagne, site, flux d'agent, ARI). Rien à lire quand c'est éteint."""
    from api.services.publication.reglages import deploiement_actif

    configurations = getattr(getattr(workflow, "released_definition", None), "workflow_configurations", None) or getattr(
        workflow, "workflow_configurations", None
    )
    if not deploiement_actif(configurations):
        return None
    try:
        parts = await lire(workflow.organization_id, workflow.id)
    except Exception as erreur:  # noqa: BLE001 -- une panne de lecture : la version publiée, comme avant
        logger.warning(f"[publication] répartition non lue ({type(erreur).__name__})")
        return None
    return version_attribuee(parts, workflow.id, appelant, cle_de_repartition)
