"""[.mark] fiabilite-de-la-conversation, lot B (B4) : le plafond d'appels d'outil par tour de l'appelant.

**Au plus trois appels d'outil par tour de l'appelant, pour l'agent qui parle** (« confier au fond » compris),
comme LiveKit (``max_tool_steps = 3``, Pipecat n'a rien d'équivalent). Le quatrième n'est pas exécuté : il rend
``{"statut": "plafond", "consigne": ...}`` et le modèle répond avec ce qu'il a.

- **Le travail de fond n'est pas compté** (revue D4) : ses outils passent par l'enveloppe des actions avec le
  faux agent du fond ; il garde sa propre limite (``travail_delai_max_s``).
- **L'appelant peut toujours revenir sur sa décision** : une annulation passe toujours et ne compte pas, ni
  l'outil « annuler le travail ». Changer de date (annuler, chercher, réserver) tient donc dans le plafond.
- Le tour est celui de la fiche de l'appel (``tour_appelant``, compté à chaque parole de l'appelant). Sans compteur
  (agent sans fiche), rien n'est compté : l'appel se comporte comme avant.

Aucun mot de métier. ⛔ Ne lève jamais : dans le doute, l'appel d'outil passe.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.fiche.traces import CLE_TOUR

# LiveKit Agents : ``max_tool_steps = 3``. Une constante nommée, pas un réglage : aucune case nouvelle (F-8, F-9).
APPELS_D_OUTIL_PAR_TOUR = 3
STATUT_PLAFOND = "plafond"
CONSIGNE_PLAFOND = (
    "Tu as déjà fait trois appels d'outil pour cette parole de la personne : n'en fais pas d'autre. "
    "Réponds avec ce que tu as, ou demande-lui ce qui te manque."
)
_ATTRIBUT = "_mark_appels_d_outil_du_tour"


def est_l_agent_qui_parle(agent: Any) -> bool:
    """Faux pour le faux agent du cerveau de fond (``AgentDeFond``) : ses appels ne comptent pas."""
    return agent is not None and getattr(agent, "agent_qui_confie", None) is None


def compter_un_appel(moteur: Any, agent: Any) -> dict | None:
    """Compte un appel d'outil de l'agent qui parle dans le tour de l'appelant en cours. ``None`` : il passe ;
    sinon le résultat de refus (le quatrième appel du tour). ⛔ Ne lève jamais."""
    try:
        if not est_l_agent_qui_parle(agent):
            return None
        fiche = getattr(moteur, "_gathered_context", None)
        tour = fiche.get(CLE_TOUR) if isinstance(fiche, dict) else None
        if not isinstance(tour, int):
            return None
        etat = getattr(moteur, _ATTRIBUT, None)
        if not isinstance(etat, dict) or etat.get("tour") != tour:
            etat = {"tour": tour, "appels": 0}
            setattr(moteur, _ATTRIBUT, etat)
        if etat["appels"] >= APPELS_D_OUTIL_PAR_TOUR:
            logger.info(f"[plafond] tour {tour} : plus de {APPELS_D_OUTIL_PAR_TOUR} appels d'outil, refusé")
            return {"statut": STATUT_PLAFOND, "consigne": CONSIGNE_PLAFOND}
        etat["appels"] += 1
        return None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[plafond] appels d'outil non comptés : {erreur!r}")
        return None
