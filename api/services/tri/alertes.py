"""[.mark] passages-fiables (lot G) : les alertes de l'appel (le problème du CLIENT, D9).

Quatre faits : appel terminé en erreur, outil en échec, panne du modèle, transfert échoué. Chacun est écrit **pendant
l'appel** dans ``gathered_context["alertes"]`` (téléphone ET clavier : le moteur est le même), puis lu par la page
« Alertes » de Dograh et par la route de lecture des alertes d'une organisation (le portail la lira plus tard).

Deux sorties, les deux construites :
- la page (toujours) ;
- le mail, par ``apres_appel/notification.notifier`` (adresses de l'organisation et de .mark), **un seul mail par appel,
  regroupé**, envoyé à la fin de l'appel. Il ne part que si la case « Alertes par mail » de l'agent est allumée (éteinte par
  défaut : D8, le mail n'est pas branché cette semaine). Pas de serveur de mail = l'alerte reste dans la page et le journal,
  jamais perdue (``notifier`` rend alors une liste vide).

La panne du modèle est déjà notifiée par le gardien de panne (``panne/gardien.py``) : elle est tracée ici avec
``deja_notifiee`` et le mail regroupé ne la redit pas.

⛔ Zéro vocabulaire métier. ⛔ Ne lève jamais dans le chemin de l'appel.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.tri import donnees

CLE_ALERTES_PAR_MAIL = "alertes_par_mail"

LIBELLES = {
    donnees.ALERTE_APPEL_EN_ERREUR: "appel terminé en erreur",
    donnees.ALERTE_OUTIL_EN_ECHEC: "outil en échec",
    donnees.ALERTE_PANNE_MODELE: "panne du modèle",
    donnees.ALERTE_TRANSFERT_ECHOUE: "transfert échoué",
}


def _contexte(moteur: Any) -> dict | None:
    contexte = getattr(moteur, "_gathered_context", None)
    return contexte if isinstance(contexte, dict) else None


def alerter(moteur: Any, type_d_alerte: str, *, detail: str | None = None, deja_notifiee: bool = False, **plus: Any) -> bool:
    """Écrit une alerte dans le run de l'appel. ⛔ Ne lève jamais."""
    try:
        contexte = _contexte(moteur)
        if contexte is None:
            return False
        if plus.get("etape") is None:
            agent = getattr(moteur, "active_agent", None)
            plus["etape"] = getattr(getattr(agent, "current_node", None), "name", None)
        return donnees.ajouter_une_alerte(contexte, type_d_alerte, detail=detail, deja_notifiee=deja_notifiee, **plus)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[alertes] alerte non écrite : {erreur!r}")
        return False


# Les motifs de phrases du code qui sont des faits d'échec (``diseur.signaler_un_probleme``) : le moteur ne les rate jamais.
def alerter_un_fait(moteur: Any, motif_id: str, *, outil: str | None = None, etape: str | None = None) -> None:
    """Un fait d'échec du diseur (outil, travail de fond, transfert). ⛔ Ne lève jamais."""
    try:
        from api.services.phrases.catalogue import OUTIL_ECHOUE, TRANSFERT_ECHOUE, TRAVAIL_ECHOUE

        if motif_id == TRANSFERT_ECHOUE:
            alerter(moteur, donnees.ALERTE_TRANSFERT_ECHOUE, etape=etape)
        elif motif_id in (OUTIL_ECHOUE, TRAVAIL_ECHOUE):
            alerter(
                moteur,
                donnees.ALERTE_OUTIL_EN_ECHEC,
                detail="travail de fond" if motif_id == TRAVAIL_ECHOUE else None,
                outil=outil,
                etape=etape,
            )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[alertes] fait non alerté : {erreur!r}")


def alerter_la_fin_en_erreur(moteur: Any, raison: str) -> None:
    """L'appel se termine par une erreur. Si le gardien de panne l'a déjà dite, rien de plus. ⛔ Ne lève jamais."""
    try:
        contexte = _contexte(moteur)
        if contexte is None or contexte.get("panne"):
            return
        from pipecat.utils.enums import EndTaskReason

        if raison in (EndTaskReason.PIPELINE_ERROR.value, EndTaskReason.UNEXPECTED_ERROR.value):
            alerter(moteur, donnees.ALERTE_APPEL_EN_ERREUR, detail=raison)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[alertes] fin en erreur non alertée : {erreur!r}")


def mail_allume(moteur: Any) -> bool:
    """La case « Alertes par mail » : le réglage de l'APPEL (celui du principal, ``reglages_appel``) d'abord, puis celui
    de l'agent actif (un appel fini chez un spécialisé garde la case du principal). ``True`` seulement. Éteinte par
    défaut. ⛔ Ne lève jamais."""
    try:
        appel = getattr(moteur, "reglages_appel", None) or {}
        if isinstance(appel, dict) and appel.get(CLE_ALERTES_PAR_MAIL) is not None:
            return appel.get(CLE_ALERTES_PAR_MAIL) is True
        agent = getattr(moteur, "active_agent", None)
        reglages = getattr(agent, "reglages", None) or {}
        return reglages.get(CLE_ALERTES_PAR_MAIL) is True
    except Exception:  # noqa: BLE001
        return False


def composer_le_mail(run_id: Any, alertes: list[dict]) -> tuple[str, str]:
    sujet = f"Alerte sur l'appel n° {run_id}" if len(alertes) == 1 else f"{len(alertes)} alertes sur l'appel n° {run_id}"
    lignes = [f"Appel n° {run_id} : {len(alertes)} alerte(s)."]
    for a in alertes:
        ligne = f"- {LIBELLES.get(a.get('type'), a.get('type'))}"
        if a.get("outil"):
            ligne += f" ({a['outil']})"
        if a.get("etape"):
            ligne += f", étape « {a['etape']} »"
        if a.get("detail"):
            ligne += f" : {a['detail']}"
        lignes.append(ligne)
    return sujet, "\n".join(lignes)


async def envoyer_le_mail_de_l_appel(moteur: Any, run_id: Any, organization_id: int | None) -> str | None:
    """Au plus UN mail par appel, qui regroupe les alertes que personne n'a encore dites. Rend l'état écrit dans le run
    (``envoye`` · ``non_envoye``) ou ``None`` (rien à dire, case éteinte, déjà fait). ⛔ Ne lève jamais."""
    try:
        contexte = _contexte(moteur)
        if contexte is None or contexte.get(donnees.CLE_ALERTES_MAIL) is not None or not mail_allume(moteur):
            return None
        a_dire = [
            a
            for a in contexte.get(donnees.CLE_ALERTES) or []
            if isinstance(a, dict) and not a.get("deja_notifiee")
        ]
        if not a_dire:
            return None
        # Posé AVANT l'envoi : un second appel de cette fonction ne renverrait rien (un seul mail par appel).
        contexte[donnees.CLE_ALERTES_MAIL] = {"etat": "en_cours", "nombre": len(a_dire)}
        from api.services.apres_appel.notification import notifier

        sujet, texte = composer_le_mail(run_id, a_dire)
        destinataires = await notifier(organization_id, sujet, texte)
        etat = "envoye" if destinataires else "non_envoye"
        contexte[donnees.CLE_ALERTES_MAIL] = {"etat": etat, "nombre": len(a_dire), "destinataires": len(destinataires)}
        if not destinataires:
            logger.error(f"[alertes] pas de mail pour l'appel {run_id} (aucun serveur ou adresse) : les alertes restent dans la page")
        return etat
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[alertes] mail de l'appel {run_id} en échec : {erreur!r}")
        return None
