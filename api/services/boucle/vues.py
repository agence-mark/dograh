"""[.mark] U8 : ce que l'écran « À améliorer » lit d'un problème, calculé à la lecture (jamais stocké).

* la fréquence « N appels sur M » : les cas des 30 derniers jours sur les appels jugés (problème du juge) ou tous les appels (trace du
  code) de l'agent ; pour un test, les essais réussis sur les essais ;
* la gravité EFFECTIVE : celle du cas la plus haute, relevée d'un cran quand le problème touche un appel sur cinq ou plus ;
* l'origine suggérée (client, recette, code), que la personne confirme ou change (C14 : pour « recette », les recettes que cet agent
  utilise sont proposées, lues dans les lignes d'usage de la bibliothèque).
⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from api.db import db_client
from api.services.boucle import avancement, ingestion, version

JOURS_DE_FREQUENCE = 30
PART_QUI_RELEVE_LA_GRAVITE = 0.2
ETATS_DE_L_ECRAN = ("a_trier", "en_cours", "testee", "publiee")


def _date(valeur: Any) -> datetime | None:
    if isinstance(valeur, datetime):
        return valeur
    try:
        return datetime.fromisoformat(str(valeur))
    except (TypeError, ValueError):
        return None


def origine_suggeree(probleme: dict[str, Any]) -> str:
    """Le client (sa fiche), la recette (la bibliothèque) ou le code (un chantier du fork). Suggestion seulement."""
    par = probleme.get("releve_par")
    critere = str(probleme.get("critere") or "")
    if par == ingestion.RELEVE_PAR_CODE:
        from api.services.builder.tests_agent.boucle import ORIGINE_SUGGEREE_PAR_CATEGORIE

        if critere.startswith("agent:"):
            return ORIGINE_SUGGEREE_PAR_CATEGORIE.get(critere.partition(":")[2], "recette")
        return "code"
    return "recette"


def frequence(probleme: dict[str, Any], appels_jugés: dict[int, int], appels: dict[int, int]) -> dict[str, Any]:
    """``{n, sur, genre}`` : ``genre`` = ``appels`` (N appels sur M) ou ``essais`` (k essais sur n, pour un test)."""
    cas = probleme.get("cas") or []
    if probleme["releve_par"] == ingestion.RELEVE_PAR_TEST:
        dernier = cas[-1] if cas else {}
        return {"n": int(dernier.get("reussis") or 0), "sur": int(dernier.get("total") or 0), "genre": "essais"}
    depuis = datetime.now(UTC) - timedelta(days=JOURS_DE_FREQUENCE)
    recents = [c for c in cas if (_date(c.get("le")) or depuis) >= depuis]
    base = appels_jugés if probleme["releve_par"] == ingestion.RELEVE_PAR_JUGE else appels
    return {"n": len(recents), "sur": max(base.get(probleme["workflow_id"], 0), len(recents)), "genre": "appels"}


def gravite_effective(probleme: dict[str, Any], freq: dict[str, Any]) -> int:
    base = int(probleme.get("gravite") or 2)
    if freq["genre"] == "appels" and freq["sur"] > 0 and freq["n"] / freq["sur"] >= PART_QUI_RELEVE_LA_GRAVITE:
        base += 1
    return max(1, min(3, base))


def vue_en_liste(probleme: dict[str, Any], nom_agent: str, freq: dict[str, Any]) -> dict[str, Any]:
    posee = probleme.get("origine")
    return {
        "id": probleme["id"],
        "workflow_id": probleme["workflow_id"],
        "workflow_nom": nom_agent,
        "titre": probleme["titre"],
        "critere": probleme.get("critere"),
        "etape": probleme.get("etape"),
        "gravite": gravite_effective(probleme, freq),
        "frequence": freq,
        "releve_par": probleme["releve_par"],
        "cause": probleme.get("cause"),
        "etat": probleme["etat"],
        "origine": posee,
        "origine_suggeree": origine_suggeree(probleme),
        "assigne": probleme.get("assigne"),
        "version": probleme.get("version_numero"),
        "derniere_le": probleme["derniere_le"].isoformat() if probleme.get("derniere_le") else None,
    }


async def liste(organisation_id: int, *, etat: str | None, workflow_id: int | None, page: int) -> dict[str, Any]:
    lignes, suite = await db_client.lister_les_ameliorations(organisation_id, etat=etat, workflow_id=workflow_id, page=page)
    ids = sorted({p["workflow_id"] for p in lignes})
    noms = await db_client.noms_des_agents(organisation_id, ids)
    juges = await db_client.appels_de_l_agent(organisation_id, jours=JOURS_DE_FREQUENCE, juges_seulement=True) if lignes else {}
    tous = await db_client.appels_de_l_agent(organisation_id, jours=JOURS_DE_FREQUENCE) if lignes else {}
    compteurs = await db_client.compter_les_ameliorations(organisation_id, workflow_id=workflow_id)
    return {
        "lignes": [vue_en_liste(p, noms.get(p["workflow_id"], ""), frequence(p, juges, tous)) for p in lignes],
        "page": page,
        "a_une_suite": suite,
        "compteurs": {e: compteurs.get(e, 0) for e in ETATS_DE_L_ECRAN},
    }


async def detail(organisation_id: int, probleme: dict[str, Any]) -> dict[str, Any]:
    """Le détail : les cas regroupés (avec leur appel), la réplique fautive, la cause et sa confiance, la correction proposée,
    l'avancement et, pour l'origine « recette », les recettes de l'agent."""
    noms = await db_client.noms_des_agents(organisation_id, [probleme["workflow_id"]])
    juges = await db_client.appels_de_l_agent(organisation_id, jours=JOURS_DE_FREQUENCE, juges_seulement=True)
    tous = await db_client.appels_de_l_agent(organisation_id, jours=JOURS_DE_FREQUENCE)
    freq = frequence(probleme, juges, tous)
    brouillon = await db_client.get_draft_version(probleme["workflow_id"])
    premiere = probleme.get("premiere_le")
    # Un brouillon compte seulement s'il est né après le premier cas : un brouillon plus ancien ne corrige rien de ce problème.
    a_un_brouillon = bool(brouillon is not None and premiere is not None and (_date(brouillon.created_at) or premiere) >= premiere)
    suggeree = origine_suggeree(probleme)
    effective = probleme.get("origine") or suggeree
    return {
        **vue_en_liste(probleme, noms.get(probleme["workflow_id"], ""), freq),
        "replique": probleme.get("replique"),
        "confiance": probleme.get("confiance"),
        "correction": probleme.get("correction"),
        "cas": [
            {k: c.get(k) for k in ("run_id", "test", "tour", "rang", "le", "citation", "reussis", "total", "a_revoir")}
            for c in reversed(probleme.get("cas") or [])
        ],
        "nb_cas": probleme.get("nb_cas") or 0,
        "avancement": avancement.temps_de_l_avancement(probleme, a_un_brouillon=a_un_brouillon),
        "recettes": await version.recettes_de_l_agent(organisation_id, probleme["workflow_id"]) if effective == "recette" else [],
    }
