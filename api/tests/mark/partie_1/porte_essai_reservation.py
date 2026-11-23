"""[.mark] Chantier Partie 1, lot 7 : le montage des essais de la porte de la réservation, sur la vraie source et la vraie porte (R1), sans modèle.

Jumeau de ``porte_essai.py`` (commande). Un tour = ce que la personne dit (``dit``), puis la fiche que le modèle aurait remplie (``fiche``). Avant la fiche,
les cases montrées au modèle sont calculées comme avant une vraie requête (``cases_selon_l_etat``, D52) et gardées dans la fiche de l'appel ; la fiche passe
par l'action du connecteur (``porte.executer``), comme en production. Vraie base : la salle de ``test_restauration_reservation.py`` (jeudi 12 h).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

from api.services.integrations.connectors.actions.reservation import RESERVATION
from api.services.integrations.connectors.outil import _propriete
from api.services.reservation import contrat, moteur, porte
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.source_reservation import SourceReservation
from api.services.workflow import cases_selon_l_etat as CS

TEL = "+33612345678"


class EssaiReservation:
    def __init__(self, salle, monkeypatch, appelant: str | None = TEL):
        self.salle = salle
        self.source = SourceReservation(salle.c, Lieu(salle.base, salle.a, 1))
        self.fiche_de_l_appel: dict[str, Any] = {}
        self.appelant = appelant
        self.ctx = SimpleNamespace(fiche=self.fiche_de_l_appel, appel={"caller_number": appelant} if appelant else {}, run_id=None, organization_id=None,
                                   reglages={}, configurations={})
        self.paroles: list[str] = []
        self.retours: list[dict] = []

        @asynccontextmanager
        async def ouvrir(nom, ctx, **options):
            yield self.source

        monkeypatch.setattr(porte.registre_des_sources, "ouvrir", ouvrir)

    @property
    def etat(self) -> dict[str, Any]:
        return moteur.etat_du_dossier(self.fiche_de_l_appel)

    @property
    def moteur_appelant(self) -> moteur.Appelant:
        return moteur.Appelant(self.appelant, None)

    def dit(self, parole: str) -> EssaiReservation:
        self.paroles.append(parole)
        self.fiche_de_l_appel[CS.CLE_DES_PAROLES] = list(self.paroles)
        self.fiche_de_l_appel[CS.CLE_DU_TOUR] = int(self.fiche_de_l_appel.get(CS.CLE_DU_TOUR) or 0) + 1
        return self

    def montrer(self) -> list[str]:
        """Les cases montrées au modèle maintenant, gardées dans le tour comme le fait la requête (D52)."""
        proprietes = {p.nom: _propriete(p, None) for p in RESERVATION.action("fiche").parametres}
        vue = contrat.vue_de_l_appel(self.fiche_de_l_appel)
        visibles, _ = CS.schema_selon_l_etat(proprietes, ["a_dire"], contrat.cases_visibles_de_la_vue(vue), contrat.forme_de_la_vue(vue))
        montrees = CS.chemins_du_schema(visibles)
        CS.garder_les_cases_montrees(SimpleNamespace(_gathered_context=self.fiche_de_l_appel), {"fiche": montrees})
        return montrees

    async def fiche(self, **cases: Any) -> dict[str, Any]:
        self.montrer()
        retour = await porte.executer(SimpleNamespace(nom="fiche"), {"a_dire": "x", **cases}, self.ctx, 5.0)
        self.retours.append(retour)
        return retour

    async def lecture(self, **arguments: Any) -> dict[str, Any]:
        retour = await porte.executer(SimpleNamespace(nom="lire"), dict(arguments), self.ctx, 5.0)
        self.retours.append(retour)
        return retour

    async def tour(self, parole: str, **cases: Any) -> dict[str, Any]:
        return await self.dit(parole).fiche(**cases)

    async def nombre_de_reservations(self) -> int:
        return await self.salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation")
