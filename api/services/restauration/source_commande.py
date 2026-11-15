"""[.mark] Module Restauration, lot 5 : la SOURCE du moteur de commande sur le classeur du restaurant (T-18 : la première configuration).

Le moteur commun (``services/commande/``) ne connaît ni la carte, ni la caisse, ni la base : il parle à une source. Celle-ci lit et écrit
le classeur de CET établissement par la couche d'accès (``api/db/bases_clients/restauration.py``, jamais une requête ici) et lance
l'envoi à la prise par ``declencheur_vers_la_prise`` APRÈS l'enregistrement validé. Le moteur n'envoie jamais rien lui-même (§ 6 du contrat).

L'envoi part en tâche de fond de l'appel (``lancer_l_envoi``), sur sa propre connexion : l'outil rend la main tout de suite, l'agent dit
« c'est enregistré » (E-36). Une commande dont l'envoi n'a pas abouti reste ``nouvelle`` ou ``envoyee`` : le rattrapage (lot 10) la reprend,
et un envoi n'est jamais fait deux fois (anti-doublon de la prise).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients.connexion import connecter
from api.db.bases_clients.recherche_liste_moteur import Reglages as ReglagesDeRecherche
from api.db.bases_clients.restauration_commande import article_de_la_carte, chiffrer_panier, statut_de_fermeture
from api.db.bases_clients.restauration_commun import fuseau_de, maintenant
from api.db.bases_clients.restauration_reglage import PRISE_PAR_DEFAUT, prise_de_l_etablissement, reglage_du_type, reglages_de_paiement
from api.services.commande.parole import heure_en_lettres
from api.services.commande.resultat import Resultat
from api.services.commande.source import enregistrer_source
from api.services.restauration.appel import Lieu, base_et_cle_de_l_appel, identifiant_de_l_etablissement
from api.services.restauration.prises.capacites import Capacites
from api.services.restauration.prises.envoi import declencheur_vers_la_prise
from api.services.restauration.prises.prise import Prise, PrisePasBranchee, capacites_de, prise_de

_TACHES: set[asyncio.Task] = set()


async def _envoyer_en_fond(nom_base: str, etablissement_id: int, nom_prise: str, numero: uuid.UUID) -> None:
    """Sur sa propre connexion : l'appel et son outil peuvent être finis. Ne lève jamais (R1 : l'échec se voit au journal)."""
    try:
        prise = prise_de(nom_prise)
    except (PrisePasBranchee, KeyError) as erreur:
        logger.warning(f"[.mark] Order {numero}: the {nom_prise} socket is not plugged ({erreur!r}); order left to the catch-up")
        return
    try:
        connexion = await connecter(nom_base)
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] Order {numero}: no connection to send it: {erreur!r}")
        return
    try:
        await declencheur_vers_la_prise(connexion, etablissement_id, prise)(numero)
    finally:
        await connexion.close()


def lancer_l_envoi(nom_base: str, etablissement_id: int, nom_prise: str, numero: uuid.UUID) -> None:
    """Lance l'envoi en tâche de fond (référence gardée : une tâche sans référence peut disparaître). Un test le remplace pour l'attendre."""
    tache = asyncio.get_running_loop().create_task(_envoyer_en_fond(nom_base, etablissement_id, nom_prise, numero))
    _TACHES.add(tache)
    tache.add_done_callback(_TACHES.discard)


# Le lanceur en vigueur : ``lancer_l_envoi``, remplaçable (tests ; les lots 9 et 10 y branchent leur file de tâches).
LANCEUR: Callable[[str, int, str, uuid.UUID], None] = lancer_l_envoi


class SourceClasseur:
    modes = ("emporter", "livraison", "sur_place")
    libelles_des_modes = {"emporter": "à emporter", "livraison": "en livraison", "sur_place": "sur place"}
    libelles_des_moyens = {
        "carte": "par carte", "especes": "en espèces", "titre_restaurant": "en titres-restaurant", "cheque": "par chèque", "en_ligne": "en ligne",
    }

    def __init__(
        self, connexion: asyncpg.Connection, lieu: Lieu, *, nom_prise: str = PRISE_PAR_DEFAUT, capacites: Capacites | None = None,
        reglages_de_recherche: ReglagesDeRecherche | None = None, prise: Prise | None = None,
    ):
        self.c = connexion
        self.lieu = lieu
        self.nom_prise = nom_prise
        self.capacites = capacites or capacites_de(nom_prise)
        self.reglages_de_recherche = reglages_de_recherche
        self.prise = prise

    # ---- le mode
    def exige_une_zone(self, mode: str) -> bool:
        return mode == "livraison"

    async def etat(self, mode: str) -> dict[str, Any]:
        moment = await maintenant(self.c)
        etat = await restauration.etat_combine(self.c, self.lieu.etablissement_id, mode, moment)
        reglage = await reglage_du_type(self.c, self.lieu.etablissement_id, mode)
        sortie = {
            "ouvert": etat["ouvert"], "statut": None if etat["ouvert"] else statut_de_fermeture(etat["raison"]), "raison": etat["raison"],
            "reprise": etat["reprise"], "prochaine_ouverture": etat["prochaine_ouverture"], "delai_minutes": etat["delai_minutes"],
            "planifiee_permise": bool(reglage and reglage["planifiee_permise"]), "phrase": "",
        }
        if not etat["ouvert"]:
            sortie["phrase"] = await self._phrase_de_fermeture(sortie, mode)
        return sortie

    async def _phrase_de_fermeture(self, etat: dict[str, Any], mode: str) -> str:
        fuseau = ZoneInfo(await fuseau_de(self.c, self.lieu.etablissement_id))
        quand = etat["reprise"] or etat["prochaine_ouverture"]
        reprise = ""
        if isinstance(quand, datetime):
            local = quand.astimezone(fuseau)
            reprise = f" Nous reprenons à {heure_en_lettres(local.hour, local.minute)}."
        if etat["statut"] == "LIVRAISON_TERMINEE":
            return "Les livraisons sont terminées pour aujourd'hui." + reprise
        if etat["statut"] == "PAUSE_TYPE":
            return "Nous sommes en pause pour le moment." + reprise
        return "Nous sommes fermés pour le moment." + reprise

    # ---- le catalogue
    async def chercher(self, texte: str) -> Resultat:
        return await restauration.chercher_dans_la_liste(self.c, "carte", texte, self.lieu.etablissement_id, reglages=self.reglages_de_recherche)

    async def article(self, ref: str, mode: str) -> dict[str, Any] | None:
        return await article_de_la_carte(self.c, self.lieu.etablissement_id, ref, mode=mode)

    async def chiffrer(self, mode: str, lignes: list[dict[str, Any]], zone_id: int | None, regles: dict[str, Any]) -> Resultat:
        return await chiffrer_panier(self.c, self.lieu.etablissement_id, mode, lignes, zone_id, regle_moities=regles.get("regle_moities") or "plus_chere")

    # ---- le restaurant
    async def reglages(self) -> dict[str, Any]:
        return await reglages_de_paiement(self.c, self.lieu.etablissement_id)

    async def client(self, telephone: str) -> dict[str, Any] | None:
        return await restauration.client_par_numero(self.c, self.lieu.etablissement_id, telephone)

    async def consigne(self, telephone: str, texte: str) -> Resultat:
        return await restauration.ecrire_consigne_client(self.c, self.lieu.etablissement_id, telephone, texte)

    # ---- l'enregistrement
    async def enregistrer(self, brouillon: dict[str, Any], jeton: str) -> Resultat:
        async def envoyer(numero: uuid.UUID) -> None:
            if self.prise is not None:  # une prise donnée (essai) : envoyée ici, sur la même connexion
                await declencheur_vers_la_prise(self.c, self.lieu.etablissement_id, self.prise)(numero)
            else:
                LANCEUR(self.lieu.nom_base, self.lieu.etablissement_id, self.nom_prise, numero)

        return await restauration.enregistrer_commande(self.c, self.lieu.etablissement_id, brouillon, jeton, declencher_envoi=envoyer)

    def statut_de_l_enregistrement(self) -> str:
        return "ENREGISTREE" if "acceptee" in self.capacites.etapes else "TRANSMISE"

    async def annonce(self, mode: str, zone_id: int | None) -> dict[str, Any] | None:
        return None  # lot 6, étape 5 : l'heure annoncée (restauration_temps)


@asynccontextmanager
async def ouvrir_la_source(ctx: Any, *, reglages_de_recherche: ReglagesDeRecherche | None = None) -> AsyncIterator[SourceClasseur]:
    """La source pour UN geste d'outil : connexion à la base du client (rôle d'écriture), établissement de l'appel, prise de l'établissement."""
    nom_base, cle = await base_et_cle_de_l_appel(ctx)
    connexion = await connecter(nom_base)
    try:
        lieu = Lieu(nom_base, await identifiant_de_l_etablissement(connexion, cle), ctx.organization_id)
        nom_prise = await prise_de_l_etablissement(connexion, lieu.etablissement_id)
        yield SourceClasseur(connexion, lieu, nom_prise=nom_prise, reglages_de_recherche=reglages_de_recherche)
    finally:
        await connexion.close()


enregistrer_source("classeur", ouvrir_la_source)
