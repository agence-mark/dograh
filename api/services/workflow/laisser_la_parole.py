"""[.mark] passages-fiables (lot E) : laisser la parole.

Quand la personne demande un moment (chercher, vérifier), le **code** accorde l'attente : le moniteur de silence
(``CallMonitorProcessor``) passe en ATTENTE, son délai est celui de la phrase ``attente_accordee`` du catalogue (défaut
45 s), puis cette phrase douce (modifiable à l'écran) remplace la relance normale, jamais de raccrochage pendant
l'attente ; la personne qui reparle la lève, puis le comportement normal reprend. L'agent, lui, répond normalement (il
peut dire « je vous attends »).

Décision d'Evan (29/10, après le rebanc) : **plus aucun outil offert au modèle**. Offrir un outil sans argument à Small le
poussait à « passer » par lui (runs 22, 30, 33, 59 t3, 60, 64) ; il a même corrompu son nom
(``laisser_la_paroleYfc6dd4H4[TOOL_CALLS]``, run 59) ; l'appel légitime du run 65 a été refusé. La demande de temps est
reconnue par l'arbitre : une **question oui/non à part** (``QUESTION_DU_TEMPS``) dans le même appel au classifieur que
la question du passage, posée seulement case allumée (même si l'arbitre de l'étape est éteint). Oui, au-dessus du seuil
de l'étape : ``accorder``.

Branchements existants du moteur : ``call_monitor.delai_de_relance`` et ``handle_user_idle`` (``pipecat_engine_callbacks``).
Le clavier n'a pas de silence (aucun agrégateur de parole n'est lié au moniteur) : l'attente y est accordée et tracée,
sans relance (écart écrit dans ``test_parite_clavier_telephone``).

⛔ Zéro vocabulaire métier (la question est une consigne au modèle, jamais dite). ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.classifiers.base_classifier import YesNoQuestion

CLE_LAISSER_LA_PAROLE = "laisser_la_parole"
# La trace de l'appel, lue par l'analyse : ce qui s'est passé de l'attente.
CLE_TRACE = "attentes_accordees"

# La question posée à l'arbitre, à part de celle du passage (une consigne au modèle, jamais dite à l'appelant).
NOM_DE_LA_QUESTION = "temps"
QUESTION_DU_TEMPS = YesNoQuestion(
    instructions=(
        "Dans sa dernière parole, la personne demande-t-elle un moment pour chercher, retrouver ou vérifier quelque "
        "chose avant de répondre ?"
    ),
    yes="Elle demande explicitement d'attendre, de patienter ou un instant, le temps de chercher ou de vérifier.",
    no=(
        "Elle répond, donne une information, accepte, refuse, pose une question ou demande autre chose. Une phrase "
        "qui donne déjà l'information n'est pas une demande de temps."
    ),
)


def case_allumee(agent: Any, moteur: Any) -> bool:
    """La case « Laisser l'appelant prendre son temps » de l'agent : posée à ``True`` seulement."""
    try:
        reglages = getattr(agent, "reglages", None) or getattr(moteur, "reglages_appel", None) or {}
        return reglages.get(CLE_LAISSER_LA_PAROLE) is True
    except Exception:  # noqa: BLE001
        return False


def tracer(moteur: Any, evenement: str, **detail: Any) -> None:
    """Une ligne dans la fiche de l'appel (``attentes_accordees``). ⛔ Ne lève jamais."""
    try:
        contexte = getattr(moteur, "_gathered_context", None)
        if isinstance(contexte, dict):
            contexte.setdefault(CLE_TRACE, []).append({"evenement": evenement, **detail})
    except Exception:  # noqa: BLE001
        pass


def accorder(moteur: Any, probabilite: float, etape: str | None = None) -> bool:
    """La personne a demandé du temps (l'arbitre en est sûr) : le moniteur passe en attente. Rien si elle parle déjà de
    nouveau (sa nouvelle parole a sa propre décision). Rend ``True`` si l'attente est accordée. ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.passage_sur_la_fiche import la_personne_parle

        if la_personne_parle(moteur):
            return False
        moniteur = getattr(moteur, "call_monitor", None)
        if moniteur is not None:
            moniteur.sur_attente_levee = lambda: tracer(moteur, "levee_la_personne_reparle")
            moniteur.accorder_l_attente()
        tracer(moteur, "accordee", etape=etape, probabilite=probabilite)
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[parole] attente non accordée : {erreur!r}")
        return False
