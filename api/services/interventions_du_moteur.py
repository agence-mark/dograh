"""[.mark] Lot 8 de builder-agent-vocal : les interrupteurs des interventions du moteur.

Chaque intervention de notre code dans la conversation (ce qu'il ajoute à la requête, réécrit dans la réponse,
décide ou dit à la place du modèle) qui n'avait pas de réglage a ici le sien, dans les réglages de l'agent
(``workflow_configurations``, JSON, aucune migration). Ils préparent le banc « moteur nu contre moteur complet » :
garder ce qui améliore, éteindre ce qui abîme.

⛔ Règle unique : **la valeur par défaut reproduit le comportement d'avant, octet pour octet**. Une clé absente (un
agent existant), ``null`` ou illisible est lue **allumée** ; seul ``False`` éteint. Éteint = la fonctionnalité est
contournée proprement (elle ne s'applique pas), rien de plus : aucune logique nouvelle.

Deux façons de lire un interrupteur, selon l'endroit où la fonctionnalité vit :

- ``intervention_du_moteur(moteur, cle)`` : dans le moteur de l'appel (téléphone **et** clavier, le même
  ``PipecatEngine``), sur les réglages de l'agent qui a la main, sinon ceux de l'appel (même ordre que
  ``laisser_la_parole`` et ``fiche_dans_le_systeme``) ;
- ``intervention_du_service(llm, cle)`` : dans le service de conversation, qui ne connaît pas le moteur. Les
  interrupteurs éteints sont posés sur le service par ``brancher_les_interventions`` (les trois endroits qui
  construisent le cerveau d'un agent : appel, collègue au téléphone, tour au clavier). Rien de posé = tout allumé.

Aucun mot de métier : des noms de réglages. ⛔ Ne lève jamais : dans le doute, allumé (comme avant).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger

CLE_SORTIES_DE_L_ETAPE = "moteur_sorties_de_l_etape"
CLE_SORTIE_D_IMPASSE = "moteur_sortie_d_impasse"
CLE_PAROLE_AVANT_OUTIL = "moteur_parole_avant_outil"
CLE_MAIN_PASSEE = "moteur_main_passee"
CLE_ORDRE_OUTIL_PUIS_PAROLE = "moteur_ordre_outil_puis_parole"
CLE_COMPTE_RENDU_DE_PHRASE = "moteur_compte_rendu_de_phrase"
CLE_PHRASES_COUPEES = "moteur_phrases_coupees"
CLE_REPLIQUE_INACHEVEE = "moteur_replique_inachevee"
CLE_REPONSE_MUETTE = "moteur_reponse_muette"
CLE_NOTES_DE_PASSATION = "moteur_notes_de_passation"

# Dans l'ordre de l'écran (section « Interventions du moteur »).
CLES_DES_INTERVENTIONS: tuple[str, ...] = (
    CLE_SORTIES_DE_L_ETAPE,
    CLE_SORTIE_D_IMPASSE,
    CLE_PAROLE_AVANT_OUTIL,
    CLE_MAIN_PASSEE,
    CLE_ORDRE_OUTIL_PUIS_PAROLE,
    CLE_COMPTE_RENDU_DE_PHRASE,
    CLE_PHRASES_COUPEES,
    CLE_REPLIQUE_INACHEVEE,
    CLE_REPONSE_MUETTE,
    CLE_NOTES_DE_PASSATION,
)

# L'attribut posé sur le service de conversation : l'ensemble des interrupteurs ÉTEINTS.
ATTRIBUT = "_mark_interventions_eteintes"


def est_allumee(reglages: Any, cle: str) -> bool:
    """L'interrupteur ``cle`` dans ``reglages`` : allumé sauf ``False`` posé. ⛔ Ne lève jamais."""
    try:
        return not (isinstance(reglages, Mapping) and reglages.get(cle) is False)
    except Exception:  # noqa: BLE001
        return True


def intervention_du_moteur(moteur: Any, cle: str, agent: Any = None) -> bool:
    """L'interrupteur ``cle`` pour l'agent qui a la main (ou ``agent``), sinon pour l'appel."""
    try:
        agent = agent if agent is not None else getattr(moteur, "active_agent", None)
        reglages = getattr(agent, "reglages", None) or getattr(moteur, "reglages_appel", None) or {}
        return est_allumee(reglages, cle)
    except Exception:  # noqa: BLE001
        return True


def intervention_de_l_appel(moteur: Any, cle: str) -> bool:
    """L'interrupteur ``cle`` lu sur les réglages de l'APPEL (ceux du principal, ``moteur.reglages_appel``) : pour ce qui
    n'a de sens que pour tout le groupe (les notes de passation)."""
    try:
        return est_allumee(getattr(moteur, "reglages_appel", None), cle)
    except Exception:  # noqa: BLE001
        return True


def intervention_du_service(llm: Any, cle: str) -> bool:
    """L'interrupteur ``cle`` pour le service de conversation ``llm`` (posé par ``brancher_les_interventions``)."""
    try:
        eteintes = getattr(llm, ATTRIBUT, None)
        return not (isinstance(eteintes, frozenset) and cle in eteintes)
    except Exception:  # noqa: BLE001
        return True


def brancher_les_interventions(llm: Any, run_configs: Mapping[str, Any] | None) -> frozenset[str]:
    """Pose sur le service de conversation ``llm`` les interrupteurs éteints des réglages de l'agent. Tout allumé :
    rien n'est posé (le service reste celui d'avant). Rend l'ensemble des éteints. ⛔ Ne lève jamais."""
    try:
        eteintes = frozenset(cle for cle in CLES_DES_INTERVENTIONS if not est_allumee(run_configs, cle))
        if llm is not None and (eteintes or getattr(llm, ATTRIBUT, None)):
            setattr(llm, ATTRIBUT, eteintes)
        return eteintes
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[interventions] interrupteurs non posés sur le service : {erreur!r}")
        return frozenset()
