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

from api.db.bases_clients import restauration
from api.db.bases_clients.restauration_commun import Connexion
from api.db.bases_clients.restauration_reservation import (
    annuler_reservation,
    creer_reservation,
    modifier_reservation,
    retrouver_reservation,
    services_de_reservation,
    telephone_de_la_reservation,
)
from api.services.actions_communes.resultat import Resultat
from api.services.reservation.source import enregistrer_source
from api.services.restauration import envois, flux
from api.services.restauration.appel import (
    Lieu,
)
from api.services.restauration.source_commande import resoudre_la_date


# B07 (lot 7) : « personnes » partout où le modèle et le mécanisme commun parlent ; « couverts » reste le mot de la couche d'accès du restaurant (colonne,
# portail, écran de salle). Cette table est le SEUL endroit où les deux mots se rencontrent : une entrée et une sortie de la source, jamais au milieu du moteur.
DU_MOTEUR_AU_CLASSEUR = {"personnes": "couverts"}


def vers_le_classeur(donnees: dict[str, Any]) -> dict[str, Any]:
    return {DU_MOTEUR_AU_CLASSEUR.get(k, k): v for k, v in donnees.items()}


def vers_le_moteur(fait: dict[str, Any]) -> dict[str, Any]:
    retour = {k: v for k, v in fait.items() if k not in DU_MOTEUR_AU_CLASSEUR.values()}
    for moteur_, classeur in DU_MOTEUR_AU_CLASSEUR.items():
        if classeur in fait:
            retour[moteur_] = fait[classeur]
    return retour


def _resultat_vers_le_moteur(r: Resultat) -> Resultat:
    faits = vers_le_moteur(r.faits)
    if isinstance(faits.get("reservations"), list):
        faits["reservations"] = [vers_le_moteur(x) for x in faits["reservations"]]
    return Resultat(r.statut, faits, r.suggestion, r.manque)


class SourceReservation:
    def __init__(self, connexion: Connexion, lieu: Lieu):
        self.c = connexion
        self.lieu = lieu

    async def resoudre_une_date(self, texte: str, heure: str | None) -> Resultat:
        return await resoudre_la_date(self.c, self.lieu.etablissement_id, texte, heure)

    async def disponibilites(self, jour: date, personnes: int) -> Resultat:
        return await restauration.disponibilites_capacite(self.c, self.lieu.etablissement_id, jour, personnes)  # position, pas de nom : la couche d'accès dit « couverts »

    async def horaires(self) -> list[dict[str, Any]]:
        return await services_de_reservation(self.c, self.lieu.etablissement_id)

    async def creer(self, brouillon: dict[str, Any]) -> Resultat:
        return _resultat_vers_le_moteur(await creer_reservation(self.c, self.lieu.etablissement_id, vers_le_classeur(brouillon), source="agent"))

    async def modifier(self, numero: str, changements: dict[str, Any]) -> Resultat:
        return _resultat_vers_le_moteur(await modifier_reservation(self.c, self.lieu.etablissement_id, numero, vers_le_classeur(changements), source="agent"))

    async def annuler(self, numero: str) -> Resultat:
        return _resultat_vers_le_moteur(await annuler_reservation(self.c, self.lieu.etablissement_id, numero, source="agent"))

    async def retrouver(self, **criteres: Any) -> Resultat:
        return _resultat_vers_le_moteur(await retrouver_reservation(self.c, self.lieu.etablissement_id, **criteres))

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
            {"prenom": r.faits.get("prenom") or "", "quand": r.faits.get("quand_dit") or "", "personnes": r.faits.get("personnes") or ""},
            f"{r.faits['numero']}:{r.faits.get('debut')}:{r.faits.get('personnes')}:{r.faits.get('statut')}",
        )


@asynccontextmanager
async def ouvrir_la_source(ctx: Any) -> AsyncIterator[SourceReservation]:
    """La source pour UN geste d'outil, sur la connexion de l'appel (S15 : une par appel, partagée avec la commande ; ``memoire_de_l_appel``)."""
    from api.services.restauration import memoire_de_l_appel

    async with memoire_de_l_appel.geste(ctx) as (connexion, lieu):
        yield SourceReservation(connexion, lieu)


async def sans_tiers(ctx: Any) -> bool:
    """Le classeur est la base du client dans le fork : c'est son vrai cahier de réservations, sauf pour l'organisation Labo, dont les
    établissements sont des restaurants de test (la même garde que la caisse de démo, ``caisse_demo/garde.py``). Un essai au clavier y réserve
    pour de vrai ; chez un client, il reste simulé (B42)."""
    from api.services.restauration.caisse_demo.garde import organisation_est_labo

    return await organisation_est_labo(getattr(ctx, "organization_id", None))


enregistrer_source("classeur", ouvrir_la_source, sans_tiers=sans_tiers)
