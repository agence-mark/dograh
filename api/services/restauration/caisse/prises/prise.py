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

from api.services.restauration.caisse.prises import adaptation
from api.services.restauration.caisse.prises.capacites import Capacites
from api.services.restauration.caisse.prises.fiches import FICHES


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
    motif: str | None = None  # le message que la caisse a écrit en refusant (``seller_notes``), quand elle le dit (Pierre 13)
    total_caisse: int | None = None  # le total (centimes) que la caisse a compté, si elle le dit (lot 19 bis, K4) : comparé au nôtre après l'envoi
    lecture_impossible: bool = False  # la commande EST en caisse mais notre lecture de sa réponse a échoué : le total n'a pas pu être relu, une personne le vérifie
    definitif: bool = False  # ``INDISPONIBLE`` que rejouer ne changera pas (accès retiré, droits, adresse) : la commande passe en échec et le restaurant est prévenu tout de suite (A4)

    def __post_init__(self):
        if self.statut not in ("ENVOYEE", "REFUSEE", "INDISPONIBLE"):
            raise ValueError(f"Statut d'envoi hors liste : {self.statut!r}")


class Prise:
    """Les gestes communs. Une sous-classe écrit les ``faire_*`` des gestes que sa fiche permet."""

    nom: str = ""

    def __init__(self, capacites: Capacites):
        self.capacites = capacites

    @property
    def sans_tiers(self) -> bool:
        """Chantier Partie 1, lot 6 : la prise ne parle au système d'AUCUN client (la caisse de démo du Labo, la prise d'essai). Un essai au
        clavier y joue les actions pour de vrai (``tests_rejouables/simulation.py``) ; toute autre prise reste simulée (B42). Faux par défaut."""
        return False

    # ---- le garde : la fiche d'abord
    def _exiger(self, permis: bool, geste: str) -> None:
        if not permis:
            raise GesteNonPermis(self.nom, geste)

    # ---- gestes
    async def envoyer_commande(self, commande: dict[str, Any]) -> ResultatEnvoi:
        """Toujours permis. La commande est d'abord ramenée à ce que la prise représente (``adaptation``)."""
        return await self.faire_envoyer(adaptation.adapter_commande(self.capacites, commande))

    async def annuler_commande(self, numero: str, **plus: Any) -> ResultatEnvoi:
        """``plus`` : ``ref_fournisseur`` pour une commande née dans la caisse (elle n'a pas notre numéro, la caisse la retrouve par le sien)."""
        self._exiger(self.capacites.annulation, "annuler une commande")
        return await self.faire_annuler(numero, **plus)

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

    async def lire_les_messages_en_attente(self) -> list[dict]:
        """Les messages signés que la caisse a gardés pour nous (mode passif, relecture) : permis seulement à une prise qui prévient par messages."""
        self._exiger(self.capacites.notifications == "signees", "lire les messages en attente")
        return await self.faire_lire_evenements()

    async def acquitter_un_message(self, identifiant: str) -> None:
        self._exiger(self.capacites.notifications == "signees", "acquitter un message")
        await self.faire_acquitter_evenement(identifiant)

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

    async def faire_lire_evenements(self) -> list[dict]:
        raise NotImplementedError

    async def faire_acquitter_evenement(self, identifiant: str) -> None:
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


def _brancher_les_prises() -> None:
    """Les prises de fournisseur s'inscrivent à l'import de leur module (``enregistrer_prise``) : on les charge au premier ``prise_de``."""
    from api.services.restauration.caisse.prises import hubrise_liaison, prise_hubrise, prise_imprimante  # noqa: F401


def prise_de(nom: str) -> Prise:
    import sys

    _brancher_les_prises()

    if nom == "test":
        if "pytest" not in sys.modules or "test" not in _FABRIQUES_DE_TEST:
            raise PrisePasBranchee("La prise test n'existe que dans les tests automatiques.")
        return _FABRIQUES_DE_TEST["test"]()
    if nom not in FICHES:
        raise KeyError(f"Prise inconnue : {nom!r}")
    if nom not in _FABRIQUES:
        raise PrisePasBranchee(f"La prise {nom} n'est pas branchée.")
    return _FABRIQUES[nom]()


# Les prises qui ont besoin d'un CONTEXTE (l'accès propre à un établissement : jeton, point de vente). Une fabrique liée reçoit ce contexte
# (``ContexteDePrise``) et rend la prise prête à servir CET établissement.
@dataclass
class ContexteDePrise:
    connexion: Any  # la connexion de la base du client (rôle d'écriture), ouverte par l'appelant
    organization_id: int | None
    etablissement_id: int
    nom_base: str | None = None
    transport: Any = None  # tests seulement : un transport enregistré à la place du réseau


_FABRIQUES_LIEES: dict[str, Callable[[ContexteDePrise], Any]] = {}


def enregistrer_prise_liee(nom: str, fabrique: Callable[[ContexteDePrise], Any]) -> None:
    if nom not in FICHES or nom == "test":
        raise KeyError(f"Prise inconnue : {nom!r}")
    _FABRIQUES_LIEES[nom] = fabrique


async def prise_de_l_etablissement(contexte: ContexteDePrise) -> Prise:
    """La prise attachée à CET établissement (sa fiche de liaison), prête à servir : sans liaison, le portail (le classeur est maître)."""
    from api.db.bases_clients.restauration_reglage import prise_de_l_etablissement as nom_de_la_prise

    _brancher_les_prises()
    nom = await nom_de_la_prise(contexte.connexion, contexte.etablissement_id)
    if nom in _FABRIQUES_LIEES:
        return await _FABRIQUES_LIEES[nom](contexte)
    return prise_de(nom)


def capacites_de(nom: str) -> Capacites:
    """La fiche d'une prise, branchée ou non : c'est elle que le reste du système lit."""
    return FICHES[nom]
