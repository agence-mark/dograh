"""[.mark] Sous-lot 6 : évaluer les alertes d'un agent, les ranger, les dire. Le service unique (audit 12 § 3).

``evaluer_un_agent`` est le seul point d'entrée (la tâche de fond, la route « Vérifier maintenant » et les tests passent par lui) :

1. lit les réglages de l'agent (type éteint = rien n'est calculé) ;
2. calcule le type (``CALCULS``) sur les chiffres que la page Qualité lit déjà : aucune dépense, aucun appel à un modèle ;
3. range l'alerte (identifiant stable : la même alerte n'est levée qu'une fois) ;
4. la verse dans « À améliorer » avec le point d'origine **Déploiement** (``critere`` « deploiement:… ») ;
5. si le mail est allumé, la dit une fois aux adresses de notification (organisation et .mark).

⛔ Jamais de bascule automatique : rien ici ne publie, ne retire ni ne change une version. ⛔ Ne lève jamais vers l'appelant d'une tâche
de fond : une panne d'ici est tracée et dite, la tâche suivante repart.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.alertes_agent import appels, regression, reglages, types

ORIGINE = "deploiement"
PREFIXE_CRITERE = f"{ORIGINE}:"


async def _comparer_les_versions(
    organisation_id: int, workflow_id: int, seuils: dict[str, float], _lecture: appels.LectureDesAppels | None = None
) -> dict[str, Any] | None:
    from api.services.boucle import qualite

    donnees = await qualite.calculer(organisation_id, jours=int(seuils["jours"]), workflow_id=workflow_id)
    lignes = [v for v in donnees["versions"] if v["workflow_id"] == workflow_id]
    comparaison = regression.comparer(lignes, seuils)
    if comparaison is not None:
        comparaison["workflow_nom"] = lignes[0]["workflow_nom"]
    return comparaison


# Un type = une fonction qui rend ``{"version", "contre", "mesures", ...}`` ou ``None``. Les types à venir s'ajoutent ici.
CALCULS: dict[str, Callable[..., Awaitable[dict[str, Any] | None]]] = {
    types.VERSION_MOINS_BIEN: _comparer_les_versions,
    # L3e : les signaux des vrais appels, une période contre la précédente (``appels.py``).
    **{code: appels.un_calcul(code) for code in types.TYPES_DES_APPELS},
}


def identifiant(code: str, workflow_id: int, version: int | str) -> str:
    """Une version : ``code:agent:v7`` ; un signal des appels : ``code:agent:p2890`` (le bloc de jours, ``appels.cle_de_la_periode``)."""
    return f"{code}:{workflow_id}:{version if isinstance(version, str) else f'v{version}'}"


async def ranger_dans_a_ameliorer(organisation_id: int, workflow_id: int, alerte: dict[str, Any]) -> bool:
    """Le point d'origine « Déploiement » : un problème par version, le critère commence par ``deploiement:``. Ne lève jamais."""
    try:
        from api.services.boucle import ingestion

        critere = f"{PREFIXE_CRITERE}{alerte['type']}:v{alerte['version']}"
        note_baisse = next((m for m in alerte["mesures"] if m["nom"] == "note_du_juge"), None)
        await db_client.ajouter_un_cas_d_amelioration(
            organisation_id,
            workflow_id,
            ingestion.cle_de(ingestion.RELEVE_PAR_CODE, critere, None),
            {
                "releve_par": ingestion.RELEVE_PAR_CODE,
                "titre": f"La version {alerte['version']} fait moins bien que la version {alerte['contre']}"[: ingestion.TITRE_MAX],
                "critere": critere,
                "gravite": 3 if note_baisse is not None and abs(note_baisse["ecart"]) >= 1 else 2,
                "cause": "prompt",
                "replique": alerte["resume"][:600],
                "version_numero": alerte["version"],
            },
            {"deploiement": alerte["version"], "contre": alerte["contre"], "mesures": alerte["mesures"]},
        )
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[alertes-agent] problème non rangé : {type(erreur).__name__}")
        return False


async def dire_par_mail(organisation_id: int, workflow_id: int, alerte: dict[str, Any]) -> bool:
    """Une fois par alerte, aux adresses de notification de l'organisation et de .mark (jamais un détail d'appel). Ne lève jamais."""
    try:
        from api.services.apres_appel.notification import notifier

        if alerte["type"] in types.TYPES_DES_APPELS:
            sujet = f"Alerte : l'agent « {alerte['workflow_nom']} » : {types.TYPES[alerte['type']].titre['fr'].lower()}"
            fin = "Ouvrez la page Alertes de l'agent, puis « Voir les appels », pour lire les appels concernés. "
        else:
            sujet = f"Alerte : l'agent « {alerte['workflow_nom']} » fait moins bien depuis sa version {alerte['version']}"
            fin = "Ouvrez « À améliorer » (origine Déploiement) pour voir le détail. "
        envoyees = await notifier(
            organisation_id,
            sujet,
            f"{alerte['resume']}\n\n{fin}Rien n'a été retiré ni changé : c'est à une personne de décider.",
        )
        return bool(envoyees)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[alertes-agent] mail non envoyé : {type(erreur).__name__}")
        return False


async def evaluer_un_agent(organisation_id: int, workflow_id: int) -> dict[str, Any]:
    """Évalue tous les types actifs de l'agent. Rend ``{"alertes": [{statut: levee|deja_levee, alerte}], "eteints": [...]}``."""
    sortie: dict[str, Any] = {"alertes": [], "eteints": []}
    courant = await reglages.lire(organisation_id, workflow_id)
    lecture = appels.LectureDesAppels(organisation_id, workflow_id)
    for code, calcul in CALCULS.items():
        regle = courant["types"][code]
        if not regle["actif"]:
            sortie["eteints"].append(code)
            continue
        try:
            comparaison = await calcul(organisation_id, workflow_id, regle["seuils"], lecture)
        except Exception as erreur:  # noqa: BLE001 -- un signal illisible ne coupe ni les autres ni la tâche de nuit
            logger.warning(f"[alertes-agent] {code} non calculé : {type(erreur).__name__}")
            continue
        if comparaison is None:
            continue
        cle = comparaison.get("cle") or comparaison["version"]
        alerte = {
            "id": identifiant(code, workflow_id, cle),
            "type": code,
            "workflow_id": workflow_id,
            "workflow_nom": comparaison.get("workflow_nom", ""),
            "version": comparaison["version"],
            "contre": comparaison["contre"],
            "mesures": comparaison["mesures"],
            "resume": comparaison.get("resume") or regression.resume(comparaison),
            "levee_le": datetime.now(UTC).isoformat(),
            "notifiee": False,
            **({"appels": comparaison["appels"], "appels_concernes": comparaison["appels_concernes"], "periode_jours": comparaison["periode_jours"]} if code in types.TYPES_DES_APPELS else {}),
        }
        alerte, nouvelle = await reglages.lever(organisation_id, workflow_id, alerte)
        if nouvelle:
            if code not in types.TYPES_DES_APPELS:
                await ranger_dans_a_ameliorer(organisation_id, workflow_id, alerte)
            if courant["mail"] and await dire_par_mail(organisation_id, workflow_id, alerte):
                await reglages.marquer_notifiee(organisation_id, workflow_id, alerte["id"])
                alerte["notifiee"] = True
        sortie["alertes"].append({"statut": "levee" if nouvelle else "deja_levee", "alerte": alerte})
    return sortie
