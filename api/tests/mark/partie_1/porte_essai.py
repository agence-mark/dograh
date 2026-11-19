"""[.mark] Chantier Partie 1, lot 3 : le montage des essais de la porte d'entrée, sur la vraie source et la vraie porte (R1), sans modèle.

Un tour = ce que la personne dit (``dit``), puis la fiche que le modèle aurait remplie (``fiche``). Avant la fiche, les cases montrées au modèle
sont calculées comme avant une vraie requête (``cases_selon_l_etat``, D52) et gardées dans la fiche de l'appel ; la fiche passe par l'action
du connecteur (``porte.executer``), comme en production.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from api.db.bases_clients.instantane import Instantane
from api.services.commande import contrat, porte
from api.services.commande import panier as P
from api.services.integrations.connectors.actions.commande import COMMANDE
from api.services.integrations.connectors.outil import _propriete
from api.services.restauration.appel import Lieu
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.services.workflow import cases_selon_l_etat as CS


class Essai:
    def __init__(self, monde, monkeypatch, appelant: str = "+33600000000"):
        self.monde = monde
        self.source = SourceClasseur(monde.c, Lieu(monde.base, monde.a, 1), nom_prise="test", prise=PriseTest())
        self.fiche_de_l_appel: dict[str, Any] = {contrat.CLE_DES_OBJETS: {"choix": True}}
        self.ctx = SimpleNamespace(fiche=self.fiche_de_l_appel, appel={"caller_number": appelant}, run_id=None, organization_id=None, reglages={},
                                   configurations={"commande_conduite_par_l_agent": True})
        self.paroles: list[str] = []
        self.retours: list[dict] = []

        self.instantane: Instantane | None = None
        self.listes_du_contexte: dict[str, list[str]] = {}

        @asynccontextmanager
        async def ouvrir(nom, ctx, **options):
            # Comme en production (lot 5) : l'appel est chargé au décroché, puis chaque geste relit l'état vivant
            if self.instantane is None:
                await self.charger()
            self.instantane.nouveau_geste()
            await self.source.charger_les_modes()
            yield self.source

        monkeypatch.setattr(porte.registre_des_sources, "ouvrir", ouvrir)

    async def charger(self) -> None:
        """Le chargement de l'appel (lot 5, ``SourceClasseur.charger_pour_l_appel``), sur la connexion du monde, comme au décroché."""
        self.instantane = Instantane(self.monde.a)
        self.monde.c.instantane = self.instantane
        self.listes_du_contexte, objets = await self.source.charger_pour_l_appel()
        self.fiche_de_l_appel.setdefault(contrat.CLE_DES_OBJETS, objets)

    @property
    def p(self) -> dict[str, Any]:
        return P.du_dossier(self.fiche_de_l_appel)

    def dit(self, parole: str) -> Essai:
        self.paroles.append(parole)
        self.fiche_de_l_appel[CS.CLE_DES_PAROLES] = list(self.paroles)
        self.fiche_de_l_appel[CS.CLE_DU_TOUR] = int(self.fiche_de_l_appel.get(CS.CLE_DU_TOUR) or 0) + 1
        return self

    def montrer(self) -> list[str]:
        """Les cases montrées au modèle maintenant, gardées dans le tour comme le fait la requête (D52)."""
        proprietes = {p.nom: _propriete(p, None) for p in COMMANDE.action("fiche").parametres}
        vue = contrat.vue_de_l_appel(self.fiche_de_l_appel)
        visibles, _ = CS.schema_selon_l_etat(proprietes, ["a_dire"], contrat.cases_visibles_de_la_vue(vue), contrat.forme_de_la_vue(vue))
        montrees = CS.chemins_du_schema(visibles)
        CS.garder_les_cases_montrees(SimpleNamespace(_gathered_context=self.fiche_de_l_appel), {"fiche": montrees})
        return montrees

    async def fiche(self, **cases: Any) -> dict[str, Any]:
        if CS.CLE_DES_CASES_MONTREES not in self.fiche_de_l_appel or cases.pop("_montrer", True):
            self.montrer()
        retour = await porte.executer(SimpleNamespace(nom="fiche"), {"a_dire": "x", **cases}, self.ctx, 5.0)
        self.retours.append(retour)
        return retour

    async def lecture(self, **arguments: Any) -> dict[str, Any]:
        """L'outil de lecture (``lire``, E16), par l'action du connecteur comme en production."""
        retour = await porte.executer(SimpleNamespace(nom="lire"), dict(arguments), self.ctx, 5.0)
        self.retours.append(retour)
        return retour

    async def tour(self, parole: str, **cases: Any) -> dict[str, Any]:
        return await self.dit(parole).fiche(**cases)

    def lignes(self) -> list[tuple]:
        return sorted((l["nom"], l["quantite"], tuple(sorted(l.get("retires") or []))) for l in self.p["lignes"])


@pytest.fixture
async def essai_de(faire_monde, monkeypatch):
    async def faire(slug: str = "casa-italia", minimum: int | None = None, carte: dict | None = None) -> Essai:
        return Essai(await faire_monde(slug, minimum, carte), monkeypatch)

    return faire
