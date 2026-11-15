"""[.mark] Module Restauration, lot 3 : l'interface ``Prise`` (les gestes communs) et le registre des prises.

Le comptoir ne connaît jamais une caisse : il lit et écrit le classeur ; l'enregistrement d'une commande déclenche l'envoi par
la PRISE (``envoi.py``). Une prise a une fiche de capacités (déclarative, ``fiches.py``) ; chaque geste commence par vérifier
la fiche et se REFUSE (``GesteNonPermis``) quand la capacité est un ``non`` : le geste n'est jamais tenté, jamais simulé.
Le travail de chaque fournisseur (lots 9 et 10) se branche dans les méthodes ``faire_*`` ; il s'inscrit au registre par
``enregistrer_prise``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from api.services.restauration.prises import adaptation
from api.services.restauration.prises.capacites import Capacites
from api.services.restauration.prises.fiches import FICHES


class GesteNonPermis(Exception):
    """La fiche de la prise dit ``non`` à ce geste."""

    def __init__(self, prise: str, geste: str):
        super().__init__(f"La prise {prise} ne sait pas : {geste}")
        self.prise, self.geste = prise, geste


class PrisePasBranchee(LookupError):
    """La fiche existe, la prise n'est pas (encore) branchée (lots 9 et 10)."""


@dataclass(frozen=True)
class ResultatEnvoi:
    """Ce que rend un envoi. ``statut`` : ``ENVOYEE`` · ``REFUSEE`` (``raison`` de la liste fermée du contrat) ·
    ``INDISPONIBLE`` (panne : la tâche rejoue). ``etape`` : une étape de la fiche, ``inconnu`` si la prise ne sait pas."""

    statut: str
    etape: str | None = None
    ref_fournisseur: str | None = None
    raison: str | None = None
    heure_annoncee: datetime | None = None  # l'heure que la caisse a posée (changée par elle), si elle la dit

    def __post_init__(self):
        if self.statut not in ("ENVOYEE", "REFUSEE", "INDISPONIBLE"):
            raise ValueError(f"Statut d'envoi hors liste : {self.statut!r}")


class Prise:
    """Les gestes communs. Une sous-classe écrit les ``faire_*`` des gestes que sa fiche permet."""

    nom: str = ""

    def __init__(self, capacites: Capacites):
        self.capacites = capacites

    # ---- le garde : la fiche d'abord
    def _exiger(self, permis: bool, geste: str) -> None:
        if not permis:
            raise GesteNonPermis(self.nom, geste)

    # ---- gestes
    async def envoyer_commande(self, commande: dict[str, Any]) -> ResultatEnvoi:
        """Toujours permis. La commande est d'abord ramenée à ce que la prise représente (``adaptation``)."""
        return await self.faire_envoyer(adaptation.adapter_commande(self.capacites, commande))

    async def annuler_commande(self, numero: str) -> ResultatEnvoi:
        self._exiger(self.capacites.annulation, "annuler une commande")
        return await self.faire_annuler(numero)

    async def chercher_commande(self, numero: str) -> dict | None:
        """Retrouver une commande par NOTRE numéro (anti-doublon avant un renvoi)."""
        self._exiger(adaptation.doit_chercher_avant_renvoi(self.capacites), "chercher une commande par notre numéro")
        return await self.faire_chercher(numero)

    async def lire_carte(self) -> dict:
        self._exiger(self.capacites.carte == "lue", "lire la carte")
        return await self.faire_lire_carte()

    async def envoyer_carte(self, carte_commune: dict) -> None:
        self._exiger(self.capacites.carte == "envoyee", "envoyer la carte")
        await self.faire_envoyer_carte(carte_commune)

    async def lire_ruptures(self) -> list[dict]:
        self._exiger(self.capacites.ruptures == "lues", "lire les ruptures")
        return await self.faire_lire_ruptures()

    async def poser_rupture(self, code_caisse: str, disponible: bool, fin: datetime | None = None) -> None:
        self._exiger(self.capacites.ruptures_posees_par_nous, "poser une rupture")
        await self.faire_poser_rupture(code_caisse, disponible, fin)

    async def lire_etat(self) -> dict | None:
        self._exiger(self.capacites.lit_l_etat, "lire l'état du restaurant")
        return await self.faire_lire_etat()

    async def poser_etat(self, etat: dict) -> None:
        self._exiger(self.capacites.ecrit_l_etat, "écrire l'état du restaurant")
        await self.faire_poser_etat(etat)

    async def lire_client(self, telephone: str) -> dict | None:
        self._exiger(adaptation.client_lu_par_la_prise(self.capacites), "lire un client")
        return await self.faire_lire_client(telephone)

    async def lire_remises(self) -> list[dict]:
        self._exiger(self.capacites.remises_lues, "lire les remises")
        return await self.faire_lire_remises()

    # ---- à écrire par la prise (lots 9 et 10, ou ``PriseTest``)
    async def faire_envoyer(self, commande: dict[str, Any]) -> ResultatEnvoi:
        raise NotImplementedError

    async def faire_annuler(self, numero: str) -> ResultatEnvoi:
        raise NotImplementedError

    async def faire_chercher(self, numero: str) -> dict | None:
        raise NotImplementedError

    async def faire_lire_carte(self) -> dict:
        raise NotImplementedError

    async def faire_envoyer_carte(self, carte_commune: dict) -> None:
        raise NotImplementedError

    async def faire_lire_ruptures(self) -> list[dict]:
        raise NotImplementedError

    async def faire_poser_rupture(self, code_caisse: str, disponible: bool, fin: datetime | None) -> None:
        raise NotImplementedError

    async def faire_lire_etat(self) -> dict | None:
        raise NotImplementedError

    async def faire_poser_etat(self, etat: dict) -> None:
        raise NotImplementedError

    async def faire_lire_client(self, telephone: str) -> dict | None:
        raise NotImplementedError

    async def faire_lire_remises(self) -> list[dict]:
        raise NotImplementedError


class PrisePortail(Prise):
    """Le classeur est maître : il n'y a rien à envoyer, la commande y est déjà. Le Rush change les étapes à la main."""

    nom = "portail"

    def __init__(self):
        super().__init__(FICHES["portail"])

    async def faire_envoyer(self, commande: dict[str, Any]) -> ResultatEnvoi:
        return ResultatEnvoi("ENVOYEE", etape="recue")


# ---- le registre ------------------------------------------------------------------------------------------------------

_FABRIQUES: dict[str, Callable[[], Prise]] = {"portail": PrisePortail}
# La prise ``test`` ne se branche que dans les tests automatiques (jamais sur un établissement).
_FABRIQUES_DE_TEST: dict[str, Callable[[], Prise]] = {}


def enregistrer_prise(nom: str, fabrique: Callable[[], Prise]) -> None:
    """Lots 9 et 10 : branche la prise ``hubrise`` ou ``imprimante`` (leur fiche existe déjà)."""
    if nom not in FICHES:
        raise KeyError(f"Prise inconnue : {nom!r}")
    if nom == "test":
        raise ValueError("La prise test se pose par ``poser_prise_de_test`` (tests seulement).")
    _FABRIQUES[nom] = fabrique


def poser_prise_de_test(prise: Prise | None) -> None:
    """Tests seulement : la prise ``test`` que ``prise_de("test")`` rend. Refusé hors pytest."""
    import sys

    if "pytest" not in sys.modules:
        raise RuntimeError("La prise test ne se branche que dans les tests automatiques.")
    if prise is None:
        _FABRIQUES_DE_TEST.pop("test", None)
    else:
        _FABRIQUES_DE_TEST["test"] = lambda: prise


def prise_de(nom: str) -> Prise:
    import sys

    if nom == "test":
        if "pytest" not in sys.modules or "test" not in _FABRIQUES_DE_TEST:
            raise PrisePasBranchee("La prise test n'existe que dans les tests automatiques.")
        return _FABRIQUES_DE_TEST["test"]()
    if nom not in FICHES:
        raise KeyError(f"Prise inconnue : {nom!r}")
    if nom not in _FABRIQUES:
        raise PrisePasBranchee(f"La prise {nom} n'est pas branchée.")
    return _FABRIQUES[nom]()


def capacites_de(nom: str) -> Capacites:
    """La fiche d'une prise, branchée ou non : c'est elle que le reste du système lit."""
    return FICHES[nom]
