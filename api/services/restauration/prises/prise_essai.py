"""[.mark] Module Restauration, lot 3 : la prise ``test``, pour les TESTS AUTOMATIQUES seulement (lots 5 à 8, avant HubRise).

Ce n'est pas un objet du produit : jamais proposée à l'écran, jamais branchable sur un établissement (``prise_de("test")``
la refuse hors pytest). La caisse de démo du lot 20 passe, elle, par la prise HubRise.

La réponse est CALCULÉE depuis la demande (total recalculé depuis les lignes, choix, frais et remises ; rupture lue sur les
codes demandés), jamais une réponse figée. Profils : ``tout_va_bien``, ``rupture``, ``pause``, ``deborde``, ``panne``,
``lente``, ``refus``. La variante « sans étape acceptée » est ``PriseTest(capacites=TEST_SANS_ACCEPTEE)`` : elle prouve
``TRANSMISE``. La prise garde en mémoire ce qu'elle a reçu (``recues``) : un renvoi sans recherche s'y VOIT (doublon).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from api.services.restauration.prises.capacites import Capacites
from api.services.restauration.prises.fiches import TEST
from api.services.restauration.prises.prise import Prise, ResultatEnvoi

PROFILS = ("tout_va_bien", "rupture", "pause", "deborde", "panne", "lente", "refus")
MINUTES_DEBORDE = 15
DELAI_LENT_S = 0.05


def total_recalcule(commande: dict[str, Any]) -> int:
    """Le total TTC en centimes recalculé depuis la demande : lignes, choix, frais, moins les remises."""
    total = 0
    for ligne in commande.get("lignes") or []:
        supplement = sum(c.get("prix", 0) * c.get("quantite", 1) for c in ligne.get("choix") or [])
        total += (ligne["prix_unitaire"] + supplement) * ligne.get("quantite", 1)
    total += commande.get("frais") or 0
    total -= sum(r["montant"] for r in commande.get("remises") or [])
    return total


class PriseTest(Prise):
    nom = "test"
    sans_tiers = True  # la prise d'essai ne parle à aucun système (lot 6 : jouée pour de vrai au clavier)

    def __init__(self, profil: str = "tout_va_bien", *, capacites: Capacites = TEST, ruptures: set[str] | None = None):
        if profil not in PROFILS:
            raise ValueError(f"Profil inconnu : {profil!r}")
        super().__init__(capacites)
        self.profil = profil
        self.ruptures_de_la_caisse: set[str] = set(ruptures or ())
        self.recues: list[dict[str, Any]] = []  # ce que la caisse a reçu, dans l'ordre (un doublon s'y voit)
        self.annulees: list[str] = []
        self.carte: dict = {}
        self.etat: dict | None = {"mode": "normal", "minutes_en_plus": 0, "reprise": None}
        self.clients: dict[str, dict] = {}
        self.remises: list[dict] = []

    def _etape(self) -> str:
        return "acceptee" if "acceptee" in self.capacites.etapes else "recue"

    async def faire_envoyer(self, commande: dict[str, Any]) -> ResultatEnvoi:
        if self.profil == "panne":
            return ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable")
        if self.profil == "lente":
            await asyncio.sleep(DELAI_LENT_S)
        if self.profil == "pause":
            return ResultatEnvoi("REFUSEE", raison="restaurant_ferme")
        codes = {ligne["code_caisse"] for ligne in commande.get("lignes") or []}
        if self.profil == "rupture" and (codes & self.ruptures_de_la_caisse or not self.ruptures_de_la_caisse):
            return ResultatEnvoi("REFUSEE", raison="autre")
        if self.profil == "refus":
            juste = total_recalcule(commande) == commande.get("total")
            return ResultatEnvoi("REFUSEE", raison="autre" if juste else "prix_different")
        self.recues.append(commande)
        heure = commande.get("heure_annoncee")
        deborde = self.profil == "deborde"
        return ResultatEnvoi(
            "ENVOYEE", etape="recue" if deborde else self._etape(), ref_fournisseur=f"T-{str(commande['numero'])[:8]}",
            heure_annoncee=heure + timedelta(minutes=MINUTES_DEBORDE) if deborde and isinstance(heure, datetime) else None,
        )

    async def faire_annuler(self, numero: str) -> ResultatEnvoi:
        self.annulees.append(str(numero))
        return ResultatEnvoi("ENVOYEE", etape="annulee")

    async def faire_chercher(self, numero: str) -> dict | None:
        connue = any(str(c["numero"]) == str(numero) for c in self.recues)
        return {"numero": str(numero), "etape": self._etape(), "ref_fournisseur": f"T-{str(numero)[:8]}"} if connue else None

    async def faire_lire_carte(self) -> dict:
        return self.carte

    async def faire_envoyer_carte(self, carte_commune: dict) -> None:
        self.carte = carte_commune

    async def faire_lire_ruptures(self) -> list[dict]:
        return [{"code_caisse": c, "disponible": False} for c in sorted(self.ruptures_de_la_caisse)]

    async def faire_poser_rupture(self, code_caisse: str, disponible: bool, fin: datetime | None) -> None:
        (self.ruptures_de_la_caisse.discard if disponible else self.ruptures_de_la_caisse.add)(code_caisse)

    async def faire_lire_etat(self) -> dict | None:
        return self.etat

    async def faire_poser_etat(self, etat: dict) -> None:
        self.etat = etat

    async def faire_lire_client(self, telephone: str) -> dict | None:
        return self.clients.get(telephone)

    async def faire_lire_remises(self) -> list[dict]:
        return self.remises
