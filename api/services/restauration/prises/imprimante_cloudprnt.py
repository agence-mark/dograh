"""[.mark] Module Restauration, lot 10 : le protocole Star CloudPRNT, côté SERVEUR (l'imprimante vient chercher son ticket).

Le déroulé (documentation publique du protocole HTTP de Star, et son serveur d'exemple) :

1. ``POST`` (l'interrogation, toutes les quelques secondes) : l'imprimante envoie un JSON (``printerMAC``, ``statusCode``…) ; le serveur répond ``{"jobReady": …}``, et si un ticket
   attend : ``"mediaTypes"`` (les formats que nous savons servir) et ``"jobToken"`` (ici : le numéro de la commande).
2. ``GET ?type=<média>&mac=<mac>&token=<jobToken>`` : le ticket, dans le média choisi.
3. ``DELETE ?code=<code>&mac=<mac>&token=<jobToken>`` : le résultat. ``code`` commençant par ``2`` : imprimé ; ``520`` : le téléchargement a manqué (problème réseau, le ticket est
   GARDÉ pour la prochaine fois) ; autre : une erreur d'impression (papier, capot…), le ticket passe en ``erreur`` et le restaurant est alerté.

L'imprimante est reconnue par son JETON, présent dans l'adresse que le restaurant a posée dans l'imprimante (``org-secret``) ; il n'est gardé qu'EN EMPREINTE. Un ticket d'un autre
établissement n'est jamais servi ni confirmé par ce jeton. L'état (papier, capot…) vient du ``statusCode`` de l'interrogation ; nous le classons par son premier chiffre
(2 : bon, 4 et 5 : problème) et par les mots « paper » et « cover » : la table exacte des codes n'était pas lisible depuis ce poste (à confirmer à l'essai sur la vraie imprimante,
après le chantier, E-48).
"""

from __future__ import annotations

from typing import Any

from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commande import commande_complete
from api.db.bases_clients.restauration_commun import Connexion, fuseau_de
from api.services.restauration import flux
from api.services.restauration.prises import ticket
from api.services.restauration.synchro_caisse import dire_la_liaison

ETATS_D_IMPRIMANTE = ("inconnu", "ok", "papier", "capot", "erreur")
CODE_REPRISE = "520"  # le téléchargement a manqué : rien n'est imprimé, rien n'est perdu


def classer_le_statut(status_code: Any) -> str:
    """L'état de l'imprimante d'après son ``statusCode`` : ``papier`` et ``capot`` d'après les mots « paper » et « cover » (testés d'abord : un libellé de papier ou de capot
    peut commencer par 2), puis ``ok`` (2xx), sinon ``erreur`` (4xx, 5xx, autre) ; sans code : ``inconnu``."""
    code = str(status_code or "").strip().lower()
    if not code:
        return "inconnu"
    if "paper" in code:
        return "papier"
    if "cover" in code:
        return "capot"
    return "ok" if code.startswith("2") else "erreur"


_CODE_DE_LIAISON = {"papier": "papier", "capot": "capot", "erreur": "imprimante_erreur"}


async def _etat_de_l_imprimante(connexion, organization_id: int, imprimante: dict, etat: str) -> None:
    """L'état change : la liaison le dit (code fermé) et le flux aussi ; l'imprimante qui revient « ok » remet la liaison « ok » (même si c'est la surveillance qui l'avait
    mise en erreur pour cause de silence). Une lecture de la liaison par interrogation, une écriture seulement quand l'état change."""
    etablissement_id = imprimante["site_id"]
    await liaison_db.noter_l_interrogation(connexion, etablissement_id, etat)
    if etat == "inconnu":
        return
    liaison = await liaison_db.liaison(connexion, etablissement_id)
    if liaison is None:
        return
    if etat == "ok":
        if liaison["etat"] != "ok":
            await dire_la_liaison(connexion, organization_id, etablissement_id, "ok", synchro=True)
    elif liaison["etat"] != "erreur" or liaison["derniere_erreur"] != _CODE_DE_LIAISON[etat]:
        await dire_la_liaison(connexion, organization_id, etablissement_id, "erreur", _CODE_DE_LIAISON[etat])


async def interroger(connexion: Connexion, organization_id: int, imprimante: dict, corps: dict[str, Any]) -> dict[str, Any]:
    """L'interrogation (``POST``) : note l'état, dit s'il y a un ticket à imprimer. Un ticket n'est offert qu'à une imprimante en état d'imprimer."""
    etat = classer_le_statut(corps.get("statusCode"))
    await _etat_de_l_imprimante(connexion, organization_id, imprimante, etat)
    if etat not in ("ok", "inconnu"):
        return {"jobReady": False}
    numero = await liaison_db.ticket_a_imprimer(connexion, imprimante["site_id"])
    if numero is None:
        return {"jobReady": False}
    return {"jobReady": True, "mediaTypes": list(ticket.MEDIAS), "jobToken": numero}


async def donner_le_ticket(connexion: Connexion, organization_id: int, imprimante: dict, media: str | None, numero: str | None) -> tuple[bytes, str] | None:
    """Le ticket (``GET``), ou ``None`` (inconnu pour CET établissement, ou média non servi). Il passe à ``recupere`` ; la commande à ``recue`` (le ticket est entre les mains de la cuisine)."""
    etablissement_id = imprimante["site_id"]
    if media not in ticket.MEDIAS or not numero:
        return None
    ligne = await liaison_db.le_ticket(connexion, etablissement_id, numero)
    if ligne is None or ligne["statut"] == "imprime":
        return None
    commande = await commande_complete(connexion, etablissement_id, numero)
    if commande is None:
        return None
    corps = ticket.rendre(commande, media, fuseau=await fuseau_de(connexion, etablissement_id), programmee=ligne["programmee"])
    await liaison_db.marquer_le_ticket(connexion, etablissement_id, numero, "recupere")
    if commande["statut"] == "envoyee":
        pas = await restauration.changer_statut(connexion, etablissement_id, numero, "envoyee", "recue", "caisse")
        if pas.statut == "OK":
            await flux.emettre(organization_id, etablissement_id, "commande.statut", {"numero": numero, "de": "envoyee", "vers": "recue", "source": "caisse"})
    return corps, f"{media}; charset=utf-8"


async def confirmer(connexion: Connexion, organization_id: int, imprimante: dict, code: str | None, numero: str | None) -> str:
    """Le résultat de l'impression (``DELETE``). Rend ``imprime`` · ``a_reprendre`` · ``erreur`` · ``inconnu``. Rejouable : un ticket déjà imprimé ne change plus."""
    etablissement_id = imprimante["site_id"]
    code = (code or "").strip()
    if not numero or not code or await liaison_db.le_ticket(connexion, etablissement_id, numero) is None:
        return "inconnu"
    court = code[:3]
    if code.startswith("2"):
        pas = await liaison_db.marquer_le_ticket(connexion, etablissement_id, numero, "imprime", court)
        if pas.statut == "OK":
            await flux.emettre(organization_id, etablissement_id, "ticket.imprime", {"numero": numero, "code": court})
        return "imprime"
    if code.startswith(CODE_REPRISE):
        await liaison_db.marquer_le_ticket(connexion, etablissement_id, numero, "en_file", court)
        return "a_reprendre"
    pas = await liaison_db.marquer_le_ticket(connexion, etablissement_id, numero, "erreur", court)
    if pas.statut == "OK":
        await flux.emettre(organization_id, etablissement_id, "ticket.erreur", {"numero": numero, "code": court})
    return "erreur"
