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

from api.db.bases_clients import dates_futures, restauration
from api.db.bases_clients.annonce_heure import dite
from api.db.bases_clients.connexion import connecter
from api.db.bases_clients.recherche_liste_moteur import Reglages as ReglagesDeRecherche
from api.db.bases_clients.restauration_commande import _quand_dit, article_de_la_carte, chiffrer_panier, statut_de_fermeture
from api.db.bases_clients.restauration_commun import fuseau_de, maintenant
from api.db.bases_clients.restauration_temps import annonce_pour
from api.db.bases_clients.restauration_zone import verifier_adresse as verifier_l_adresse
from api.db.bases_clients.restauration_remise import remises_en_cours
from api.db.bases_clients.restauration_reglage import PRISE_PAR_DEFAUT, prise_de_l_etablissement, reglage_du_type, reglages_de_paiement
from api.services.commande.parole import heure_en_lettres
from api.services.commande.resultat import Resultat
from api.services.commande.source import enregistrer_source
from api.services.restauration import flux
from api.services.restauration.appel import Lieu, base_et_cle_de_l_appel, identifiant_de_l_etablissement
from api.services.restauration.prises.capacites import Capacites
from api.services.restauration.signalements import LES_QUATORZE, code_dit, signalements_de
from api.services.restauration.prises.envoi import declencheur_vers_la_prise
from api.services.restauration.prises.prise import Prise, capacites_de

_TACHES: set[asyncio.Task] = set()


async def _envoyer_en_fond(nom_base: str, etablissement_id: int, nom_prise: str, numero: uuid.UUID) -> None:
    """Sur sa propre connexion : l'appel et son outil peuvent être finis. Ne lève jamais (R1 : l'échec se voit au journal, au flux et par le secours).
    La prise est celle de l'ÉTABLISSEMENT (son accès propre) : ``nom_prise`` n'est gardé que pour la signature du lanceur."""
    from api.services.restauration.envoi_caisse import envoyer_la_commande, organisation_de_la_base

    # Une base sans organisation rattachée (essai, installation en cours) : l'envoi se fait, sans flux ni accès de caisse propre à une organisation.
    await envoyer_la_commande(await organisation_de_la_base(nom_base), nom_base, etablissement_id, numero)


def lancer_l_envoi(nom_base: str, etablissement_id: int, nom_prise: str, numero: uuid.UUID) -> None:
    """Lance l'envoi en tâche de fond (référence gardée : une tâche sans référence peut disparaître). Un test le remplace pour l'attendre."""
    tache = asyncio.get_running_loop().create_task(_envoyer_en_fond(nom_base, etablissement_id, nom_prise, numero))
    _TACHES.add(tache)
    tache.add_done_callback(_TACHES.discard)


# Le lanceur en vigueur : ``lancer_l_envoi``, remplaçable (tests ; les lots 9 et 10 y branchent leur file de tâches).
LANCEUR: Callable[[str, int, str, uuid.UUID], None] = lancer_l_envoi


def _vers_le_classeur(lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les lignes du moteur (clé ``code``) au format du classeur (clé ``code_caisse``, contrat § 2)."""
    return [{**{k: v for k, v in l.items() if k != "code"}, "code_caisse": l["code"]} for l in lignes]


async def resoudre_la_date(connexion: asyncpg.Connection, etablissement_id: int, texte: str, heure: str | None) -> Resultat:
    """Le jour et l'heure dits, résolus vers l'avenir au fuseau de l'établissement (la commande planifiée et la réservation)."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    local = (await maintenant(connexion)).astimezone(fuseau)
    jour = dates_futures.resoudre_une_date(texte, local) if texte else dates_futures.Resolution(dates_futures.INTROUVABLE)
    if jour.statut == dates_futures.INTROUVABLE:
        return Resultat("INTROUVABLE", {}, "Pour quel jour ?", "jour")
    if jour.statut == dates_futures.AMBIGU:
        dits = [dates_futures.jour_dit(j) for j in jour.candidats]
        candidats = [{"jour": j.isoformat(), "jour_dit": d} for j, d in zip(jour.candidats, dits)]
        return Resultat("AMBIGU", {"candidats": candidats}, f"Est-ce {' ou '.join(dits)} ?", "jour")
    faits: dict[str, Any] = {"jour": jour.jour.isoformat(), "jour_dit": dates_futures.jour_dit(jour.jour)}
    if not heure:
        return Resultat("INCOMPLETE", faits, f"À quelle heure, {faits['jour_dit']} ?", "heure")
    h = dates_futures.resoudre_l_heure(heure)
    if h.statut == dates_futures.INTROUVABLE:
        return Resultat("INCOMPLETE", faits, "À quelle heure exactement ?", "heure")
    if h.statut == dates_futures.AMBIGU:
        dites = [dates_futures.heure_dite(c) for c in h.candidats]
        return Resultat("AMBIGU", {**faits, "candidats_heure": dites}, f"Est-ce {' ou '.join(dites)} ?", "heure")
    voulue = datetime.combine(jour.jour, h.heure, tzinfo=fuseau)
    faits.update({"heure_voulue": voulue.isoformat(), "heure_dite": dates_futures.heure_dite(h.heure)})
    if voulue <= local:
        return Resultat("ARGUMENT_INVALIDE", faits, "Cette heure est déjà passée, pour quelle heure ?", "heure")
    return Resultat("RETENU", faits, f"{faits['jour_dit']} à {faits['heure_dite']}.")


class SourceClasseur:
    modes = ("emporter", "livraison", "sur_place")
    libelles_des_modes = {"emporter": "à emporter", "livraison": "en livraison", "sur_place": "sur place"}
    question_de_la_zone = "Quelle est l'adresse de livraison ?"
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
        fiche = await article_de_la_carte(self.c, self.lieu.etablissement_id, ref, mode=mode)
        if fiche is not None:
            # Lot 7 : ce que le moteur lit pour répondre sur un signalement (sans connaître le mot du métier).
            fiche["signalements"] = signalements_de(fiche.get("allergenes"))
            fiche["signalements_libelles"] = {c: libelle for c, (libelle, _) in LES_QUATORZE.items()}
        return fiche

    def signalement_dit(self, texte: str) -> str | None:
        return code_dit(texte)

    async def chiffrer(self, mode: str, lignes: list[dict[str, Any]], zone_id: int | None, regles: dict[str, Any]) -> Resultat:
        return await chiffrer_panier(
            self.c, self.lieu.etablissement_id, mode, _vers_le_classeur(lignes), zone_id, regle_moities=regles.get("regle_moities") or "plus_chere",
            client=regles.get("client"),
        )

    async def retrouver(self, numero: str | None = None, telephone: str | None = None) -> Resultat:
        r = await restauration.statut_commande(self.c, self.lieu.etablissement_id, numero=numero, telephone=telephone)
        if r.statut != "OK":
            return r
        fuseau = ZoneInfo(await fuseau_de(self.c, self.lieu.etablissement_id))
        maintenant_ = await maintenant(self.c)
        commandes = [
            {
                "numero": c["numero"], "numero_court": c["numero_court"], "statut": c["statut"], "mode": c["mode"], "total": c["total"],
                "quand_dit": _quand_dit(c["heure_voulue"] or c["heure_annoncee"], maintenant_, fuseau) if (c["heure_voulue"] or c["heure_annoncee"]) else None,
            }
            for c in r.faits["commandes"]
        ]
        return Resultat("OK", {"commandes": commandes})

    async def remises_en_cours(self) -> list[dict[str, Any]]:
        return await remises_en_cours(self.c, self.lieu.etablissement_id, await maintenant(self.c))

    # ---- le restaurant
    async def reglages(self) -> dict[str, Any]:
        return await reglages_de_paiement(self.c, self.lieu.etablissement_id)

    async def client(self, telephone: str) -> dict[str, Any] | None:
        return await restauration.client_par_numero(self.c, self.lieu.etablissement_id, telephone)

    async def consigne(self, telephone: str, texte: str) -> Resultat:
        r = await restauration.ecrire_consigne_client(self.c, self.lieu.etablissement_id, telephone, texte)
        if r.statut == "ARGUMENT_INVALIDE" and r.faits.get("raison") == "allergie":  # T-16 : une allergie ne vit que dans la commande
            return Resultat("ARGUMENT_INVALIDE", {"raison": "pour_la_commande"}, r.suggestion, r.manque)
        return r

    # ---- l'enregistrement
    async def enregistrer(self, brouillon: dict[str, Any], jeton: str) -> Resultat:
        async def envoyer(numero: uuid.UUID) -> None:
            if self.prise is not None:  # une prise donnée (essai) : envoyée ici, sur la même connexion
                await declencheur_vers_la_prise(self.c, self.lieu.etablissement_id, self.prise)(numero)
            else:
                LANCEUR(self.lieu.nom_base, self.lieu.etablissement_id, self.nom_prise, numero)

        brouillon = {**brouillon, "lignes": _vers_le_classeur(brouillon["lignes"])}
        return await restauration.enregistrer_commande(self.c, self.lieu.etablissement_id, brouillon, jeton, declencher_envoi=envoyer)

    async def apres_le_geste(self, geste: str, avant: int, p: dict[str, Any], r: Resultat, ctx: Any) -> None:
        """Le portail l'apprend en direct (contrat portail ↔ fork § 3) : ``commande.panier`` quand le panier de l'appel a changé (le portail relit),
        ``commande.creee`` quand la commande est enregistrée. Un seul émetteur : ``flux.emettre``. Hors appel suivi (pas de run) : rien."""
        organisation, etablissement = ctx.organization_id, self.lieu.etablissement_id
        if not organisation:
            return
        if ctx.run_id and p["version"] != avant:
            await flux.poser_le_panier(organisation, etablissement, ctx.run_id, p)
            await flux.emettre(organisation, etablissement, "commande.panier", {"appel_id": str(ctx.run_id), "version": p["version"]})
        if geste == "finaliser" and r.statut in ("ENREGISTREE", "TRANSMISE"):
            faits = r.faits
            await flux.emettre(
                organisation, etablissement, "commande.creee",
                {"numero": faits["numero"], "numero_court": faits["numero_court"], "mode": p["mode"], "heure_annoncee": faits["heure_annoncee"], "total": faits["total"]},
            )

    def statut_de_l_enregistrement(self) -> str:
        return "ENREGISTREE" if "acceptee" in self.capacites.etapes else "TRANSMISE"

    async def annonce(self, mode: str, zone_id: int | None) -> dict[str, Any] | None:
        try:
            a = await annonce_pour(self.c, self.lieu.etablissement_id, mode, await maintenant(self.c), zone_id)
        except LookupError:
            return None  # une zone qui n'est pas de cet établissement : jamais son délai
        fuseau = ZoneInfo(await fuseau_de(self.c, self.lieu.etablissement_id))
        return {"prete": a["annonce"].prete, "texte": dite(a["annonce"], fuseau), "minutes": a["annonce"].minutes}

    async def verifier_adresse(self, texte: str) -> Resultat:
        return await verifier_l_adresse(self.c, self.lieu.etablissement_id, texte)

    async def resoudre_une_date(self, texte: str, heure: str | None) -> Resultat:
        return await resoudre_la_date(self.c, self.lieu.etablissement_id, texte, heure)


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
