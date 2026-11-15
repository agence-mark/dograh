"""[.mark] Module Restauration, lot 8 : la SOURCE du moteur de réservation sur le classeur du restaurant.

Le moteur commun (``services/reservation/``) ne connaît ni les tables, ni la base : il parle à une source. Celle-ci lit et écrit le classeur de
CET établissement par la couche d'accès (``restauration_reservation.py`` et ``restauration.disponibilites_capacite``, jamais une requête ici).
L'agent est la source de l'écriture (journal : ``agent``). Le portail l'apprend en direct : ``reservation.creee`` et ``reservation.changee``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import asyncpg

from api.db.bases_clients import restauration
from api.db.bases_clients.connexion import connecter
from api.db.bases_clients.restauration_reservation import (
    annuler_reservation,
    creer_reservation,
    modifier_reservation,
    retrouver_reservation,
    telephone_de_la_reservation,
)
from api.services.commande.resultat import Resultat
from api.services.reservation.source import enregistrer_source
from api.services.restauration import envois, flux
from api.services.restauration.appel import Lieu, base_et_cle_de_l_appel, identifiant_de_l_etablissement
from api.services.restauration.source_commande import resoudre_la_date


def _vers_le_classeur(donnees: dict[str, Any]) -> dict[str, Any]:
    """Le moteur parle d'``effectif``, le classeur de ``couverts``."""
    return {("couverts" if k == "effectif" else k): v for k, v in donnees.items()}


def _vers_le_moteur(fait: dict[str, Any]) -> dict[str, Any]:
    return {**fait, "effectif": fait["couverts"]}


class SourceReservation:
    def __init__(self, connexion: asyncpg.Connection, lieu: Lieu):
        self.c = connexion
        self.lieu = lieu

    async def resoudre_une_date(self, texte: str, heure: str | None) -> Resultat:
        return await resoudre_la_date(self.c, self.lieu.etablissement_id, texte, heure)

    async def disponibilites(self, jour: date, effectif: int) -> Resultat:
        return await restauration.disponibilites_capacite(self.c, self.lieu.etablissement_id, jour, effectif)

    async def creer(self, brouillon: dict[str, Any]) -> Resultat:
        return await creer_reservation(self.c, self.lieu.etablissement_id, _vers_le_classeur(brouillon), source="agent")

    async def modifier(self, numero: str, changements: dict[str, Any]) -> Resultat:
        return await modifier_reservation(self.c, self.lieu.etablissement_id, numero, _vers_le_classeur(changements), source="agent")

    async def annuler(self, numero: str) -> Resultat:
        return await annuler_reservation(self.c, self.lieu.etablissement_id, numero, source="agent")

    async def retrouver(self, **criteres: Any) -> Resultat:
        r = await retrouver_reservation(self.c, self.lieu.etablissement_id, **criteres)
        if "reservations" in r.faits:
            r = Resultat(r.statut, {**r.faits, "reservations": [_vers_le_moteur(x) for x in r.faits["reservations"]]}, r.suggestion, r.manque)
        return r

    async def apres_le_geste(self, geste: str, r: Resultat, ctx: Any) -> None:
        """``reservation.creee`` (réservée), ``reservation.changee`` (modifiée ou annulée) : le portail relit la donnée. Hors organisation : rien."""
        if not ctx.organization_id or not r.faits.get("numero"):
            return
        type_ = "reservation.creee" if geste == "reserver" else "reservation.changee"
        await flux.emettre(ctx.organization_id, self.lieu.etablissement_id, type_, {"reservation_id": r.faits["numero"]})
        # Lot 7 (E-18) : le SMS de la réservation, seulement si l'établissement l'a allumé (éteint par défaut) ; ne défait jamais la réservation.
        declencheur = {"reserver": envois.RESERVATION_ENREGISTREE, "modifier_reservation": envois.RESERVATION_MODIFIEE}.get(geste, envois.RESERVATION_ANNULEE)
        telephone = await telephone_de_la_reservation(self.c, self.lieu.etablissement_id, r.faits["numero"])
        await envois.envoyer_apres(
            self.c, ctx.organization_id, self.lieu.etablissement_id, declencheur, telephone,
            {"prenom": r.faits.get("prenom") or "", "quand": r.faits.get("quand_dit") or "", "personnes": r.faits.get("couverts") or ""},
            f"{r.faits['numero']}:{r.faits.get('debut')}:{r.faits.get('couverts')}:{r.faits.get('statut')}",
        )


@asynccontextmanager
async def ouvrir_la_source(ctx: Any) -> AsyncIterator[SourceReservation]:
    """La source pour UN geste d'outil : connexion à la base du client (rôle d'écriture), établissement de l'appel."""
    nom_base, cle = await base_et_cle_de_l_appel(ctx)
    connexion = await connecter(nom_base)
    try:
        yield SourceReservation(connexion, Lieu(nom_base, await identifiant_de_l_etablissement(connexion, cle), ctx.organization_id))
    finally:
        await connexion.close()


enregistrer_source("classeur", ouvrir_la_source)
