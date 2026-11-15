"""[.mark] Module Restauration, lot 10 : la prise IMPRIMANTE (Star CloudPRNT).

Aucune adresse sortante : c'est l'imprimante qui INTERROGE le serveur (fiche : ``notifications = interrogation``, ``adresses_permises = ()``). Envoyer une commande ici =
poser UN ticket dans le journal des tickets de l'établissement (``resto_ticket``, clé = le numéro de la commande : jamais deux tickets, anti-doublon ``notre_table``) ;
l'imprimante le vient chercher au prochain passage (``imprimante_cloudprnt``).

Commande planifiée (T-11), deux modes AU CHOIX par établissement (``resto_imprimante.mode_planifiee``) :

- ``differe`` : le ticket est LIBÉRÉ ``minutes_avant`` minutes avant l'heure voulue (la cuisine ne voit pas un ticket de 20 h à 11 h) ;
- ``immediat`` : imprimé tout de suite, marqué « PROGRAMMÉE ».

Une commande « dès que possible », ou dont l'heure tombe dans les ``minutes_avant`` minutes, s'imprime tout de suite et sans marque.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import asyncpg

from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commun import maintenant
from api.services.restauration.prises.fiches import IMPRIMANTE
from api.services.restauration.prises.prise import ContexteDePrise, Prise, PrisePasBranchee, ResultatEnvoi, enregistrer_prise, enregistrer_prise_liee

NOM = "imprimante"


class PriseImprimante(Prise):
    nom = NOM

    def __init__(self, connexion: asyncpg.Connection | None = None, etablissement_id: int | None = None):
        super().__init__(IMPRIMANTE)
        self._connexion, self._etablissement_id = connexion, etablissement_id

    def _contexte(self) -> tuple[asyncpg.Connection, int]:
        if self._connexion is None or self._etablissement_id is None:
            raise PrisePasBranchee("La prise imprimante se branche par établissement (liaison).")
        return self._connexion, self._etablissement_id

    async def faire_envoyer(self, commande: dict[str, Any]) -> ResultatEnvoi:
        connexion, etablissement_id = self._contexte()
        reglage = await liaison_db.imprimante(connexion, etablissement_id)
        if reglage is None:
            return ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable")  # pas d'imprimante posée : le rattrapage reprendra quand elle le sera
        liberer_le, programmee = await planning_du_ticket(connexion, commande.get("heure_voulue"), reglage["mode_planifiee"], reglage["minutes_avant"])
        await liaison_db.creer_le_ticket(connexion, etablissement_id, commande["numero"], liberer_le=liberer_le, programmee=programmee)
        # Le ticket attend l'imprimante : ``recue`` viendra quand elle l'aura récupéré. Aucune étape « acceptée » : l'outil dit TRANSMISE.
        return ResultatEnvoi("ENVOYEE", etape=None)


async def planning_du_ticket(connexion: asyncpg.Connection, heure_voulue: datetime | None, mode: str, minutes_avant: int) -> tuple[datetime | None, bool]:
    """``(liberer_le, programmee)`` d'un ticket. ``liberer_le`` vide : tout de suite."""
    if heure_voulue is None:
        return None, False
    debut = heure_voulue - timedelta(minutes=minutes_avant)
    if debut <= await maintenant(connexion):
        return None, False  # l'heure approche : comme une commande du moment
    return (debut, False) if mode == "differe" else (None, True)


async def _fabrique(contexte: ContexteDePrise) -> PriseImprimante:
    return PriseImprimante(contexte.connexion, contexte.etablissement_id)


enregistrer_prise(NOM, lambda: PriseImprimante())
enregistrer_prise_liee(NOM, _fabrique)
