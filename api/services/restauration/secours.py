"""[.mark] Module Restauration, lot 10 : l'ÉCHELLE DE SECOURS quand l'envoi d'une commande à la caisse échoue pour de bon (note de Pierre du 11/11, § 10).

Dans l'ordre de l'échelle, chaque échelon indépendant des autres (l'échec de l'un n'arrête pas le suivant) ; le MAIL aux personnes d'Équipe (``envoi_caisse._alerter``) part en plus :

1. **ticket sur l'imprimante de l'établissement**, si elle est liée : un ticket est posé dans son journal (le numéro de la commande en est la clé : jamais deux tickets) ; elle le
   vient chercher à sa prochaine interrogation. Sans imprimante : rien, dit dans le bilan ;
2. **SMS au gérant** : les mobiles français des personnes de l'équipe marquées « destinataire par défaut » (``mark.personne``), par l'envoi de SMS EXISTANT du fork et le compte
   Twilio de « Téléphonie » de l'organisation (``sms_restauration``) ; une seule fois par commande et par numéro ;
3. **appel au restaurant** : NON FAIT. Un appel sortant du fork (``routes/telephony.initiate_call``, ``services/campaign``) lance l'exécution d'un agent (workflow) depuis une session
   de compte, vers un numéro : le fork n'a aucun agent qui dicte une commande, et chaque appel est une dépense. Il faut d'abord un agent « dictée de commande » (décision et dépense
   à Evan, ``A-VALIDER``). Le bilan le dit : ``appel: non_fait``.

``secours_de_la_commande`` ne lève jamais et rend le bilan (``ticket``, ``sms``, ``appel``) : ce qui a été fait, jamais un échec silencieux.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commun import Connexion
from api.services.restauration import sms_restauration as sms_resto


def _resume(commande: dict[str, Any]) -> str:
    return ", ".join(f"{l['quantite']} {l['nom']}" for l in commande.get("lignes") or [])


async def secours_de_la_commande(connexion: Connexion, organization_id: int | None, etablissement_id: int, commande: dict[str, Any], raison: str) -> dict[str, Any]:
    bilan: dict[str, Any] = {"ticket": "aucune_imprimante", "sms": 0, "appel": "non_fait"}
    numero = str(commande["numero"])
    try:
        if await liaison_db.imprimante(connexion, etablissement_id) is not None:
            cree = await liaison_db.creer_le_ticket(connexion, etablissement_id, numero)
            bilan["ticket"] = "pose" if cree else "deja_la"
    except Exception as erreur:  # noqa: BLE001
        bilan["ticket"] = "echec"
        logger.error(f"[.mark] Rescue ticket for order {numero} failed: {type(erreur).__name__}")
    if organization_id is not None:
        try:
            fiche = {"numero_court": commande.get("numero_court") or numero[:8], "resume": _resume(commande), "telephone": (commande.get("client") or {}).get("telephone") or "", "raison": raison}
            modele = "Commande {{numero_court}} NON transmise a la caisse ({{raison}}) : {{resume}}. Client {{telephone}}"
            for destinataire in await sms_resto.numeros_du_gerant(connexion, etablissement_id):
                if await sms_resto.envoyer_un_sms(organization_id, destinataire, modele, fiche, f"secours:{etablissement_id}:{numero}"):
                    bilan["sms"] += 1
        except Exception as erreur:  # noqa: BLE001
            logger.error(f"[.mark] Rescue SMS for order {numero} failed: {type(erreur).__name__}")
    return bilan
