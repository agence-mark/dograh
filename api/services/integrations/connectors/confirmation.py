"""[.mark] SA-33, défaut 3 (appel 2559) : une confirmation n'est jamais acceptée sans la réponse de la personne.

Constat : ``finaliser`` rend la relecture (dite par le code, « Je vous relis : … C'est bon ? »), puis le modèle rappelle aussitôt
``finaliser`` avec ``confirmer: true`` DANS LE MÊME TOUR : la commande est enregistrée sans l'accord de la personne. La relecture en deux
temps (empreinte, jeton) prouve que ce qui est confirmé a été relu, jamais que la personne a répondu.

Mécanisme commun à toute action interne, sans un mot de métier, sous l'interrupteur ``garde_confirmation_apres_reponse`` (thème
« Interventions du moteur », éteint par défaut, allumé par le modèle de réglages Restauration) :

- un résultat qui demande une confirmation (``faits.a_confirmer`` vrai) note le tour de la personne où il a été rendu
  (``CLE_TOUR`` de la fiche), par action ;
- un appel de la même action avec ``confirmer`` vrai, dans ce MÊME tour, n'est pas joué : un refus neutre, sans phrase à dire, avec la consigne d'attendre la réponse ; au tour suivant de la personne, il est joué comme avant ;
- invisible quand tout va bien : rien n'est ajouté à un résultat, aucune question ni phrase n'est imposée à l'agent.

Sans compteur de tours dans la fiche (agent sans fiche), rien n'est retenu : le comportement d'avant. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

# Dans la fiche de l'appel : {"<connecteur>.<action>": <tour de la personne où la relecture a été rendue>}.
CLE_RELECTURES = "relectures_rendues"
CONSIGNE = (
    "La relecture vient d'être donnée à la personne et elle n'a pas encore répondu : n'appelle pas la confirmation maintenant, "
    "attends sa réponse. Si elle dit oui, confirme ; si elle corrige, corrige d'abord."
)


def _tour(fiche: dict) -> int | None:
    from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

    tour = fiche.get(CLE_TOUR)
    return tour if isinstance(tour, int) and not isinstance(tour, bool) else None


def confirmation_avant_la_reponse(fiche: Any, cle: str, arguments: dict | None) -> dict | None:
    """Le refus neutre si ``arguments`` confirme l'action ``cle`` dans le tour même où sa relecture a été rendue ; sinon ``None``."""
    try:
        if not isinstance(fiche, dict) or (arguments or {}).get("confirmer") is not True:
            return None
        rendues = fiche.get(CLE_RELECTURES)
        tour = _tour(fiche)
        if not isinstance(rendues, dict) or tour is None or rendues.get(cle) != tour:
            return None
        logger.info(f"[confirmation] {cle} : confirmation refusée, la personne n'a pas encore répondu à la relecture")
        return {
            "statut": "INCOMPLETE",
            "faits": {"en_attente_de_la_reponse": True},
            "manque": "reponse_a_la_relecture",
            "consigne": CONSIGNE,
        }
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[confirmation] garde non lue : {erreur!r}")
        return None


def noter_la_relecture(fiche: Any, cle: str, resultat: Any) -> None:
    """Un résultat qui demande une confirmation : le tour où il est rendu est retenu pour ``cle``."""
    try:
        if not isinstance(fiche, dict) or not isinstance(resultat, dict):
            return
        faits = resultat.get("faits")
        if not (isinstance(faits, dict) and faits.get("a_confirmer") is True):
            return
        tour = _tour(fiche)
        if tour is None:
            return
        rendues = fiche.get(CLE_RELECTURES)
        if not isinstance(rendues, dict):
            rendues = fiche[CLE_RELECTURES] = {}
        rendues[cle] = tour
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[confirmation] relecture non notée : {erreur!r}")
