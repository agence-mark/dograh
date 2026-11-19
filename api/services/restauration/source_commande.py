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

from loguru import logger

from api.db.bases_clients import dates_futures, restauration, restauration_en_plus
from api.db.bases_clients.restauration_carte import accord_du_produit
from api.db.bases_clients.restauration_signalement_carte import signaler_une_regle_inconnue
from api.db.bases_clients.annonce_heure import dite
from api.db.bases_clients.recherche_liste_moteur import Reglages as ReglagesDeRecherche
from api.db.bases_clients.restauration_commande import (
    _quand_dit,
    article_de_la_carte,
    commande_complete,
    chiffrer_panier,
    creneau_refuse,
    statut_de_fermeture,
)
from api.db.bases_clients.restauration_commun import Connexion, fuseau_de, maintenant
from api.db.bases_clients.restauration_reglage import (
    PRISE_PAR_DEFAUT,
    prise_de_l_etablissement,
    reglage_du_type,
    reglages_de_paiement,
    types_de_commande_eteints,
)
from api.db.bases_clients.restauration_remise import remises_en_cours
from api.db.bases_clients.restauration_remise_offre import noter_une_offre_dite_par_ref
from api.db.bases_clients.restauration_temps import annonce_pour
from api.db.bases_clients.restauration_zone import (
    verifier_adresse as verifier_l_adresse,
)
from api.services.commande.parole import heure_en_lettres
from api.services.commande.resultat import Resultat
from api.services.commande.source import enregistrer_source
from api.services.restauration import envois, flux
from api.services.restauration.appel import (
    Lieu,
)
from api.services.restauration.prises.capacites import Capacites
from api.services.restauration.prises.envoi import declencheur_vers_la_prise
from api.services.restauration.prises.prise import Prise, capacites_de
from api.services.restauration.signalements import (
    LES_QUATORZE,
    code_dit,
    codes_nommes,
    regime_dit,
    signalements_de,
)

_TACHES: set[asyncio.Task] = set()


def _signalements_des_options(groupes: list[dict]) -> None:
    """M88 : chaque option dit ce qu'on sait de ses signalements. ``signalements`` : la donnée de l'option (``None`` = inconnue, tant que la
    carte n'en porte pas) ; ``signalements_du_nom`` : ce que son nom affirme (« Pistache »), qui ne prouve qu'une présence."""
    for g in groupes:
        for o in g.get("options") or []:
            o["signalements"] = signalements_de(o.get("allergenes"))
            o["signalements_du_nom"] = codes_nommes(o.get("nom") or "")
            _signalements_des_options(o.get("enfants") or [])


async def _envoyer_en_fond(nom_base: str, etablissement_id: int, nom_prise: str, numero: uuid.UUID) -> None:
    """Sur sa propre connexion : l'appel et son outil peuvent être finis. Ne lève jamais (R1 : l'échec se voit au journal, au flux et par le secours).
    La prise est celle de l'ÉTABLISSEMENT (son accès propre) : ``nom_prise`` n'est gardé que pour la signature du lanceur."""
    from api.services.restauration.envoi_caisse import (
        envoyer_la_commande,
        organisation_de_la_base,
    )

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


async def resoudre_la_date(connexion: Connexion, etablissement_id: int, texte: str, heure: str | None) -> Resultat:
    """Le jour et l'heure dits, résolus vers l'avenir au fuseau de l'établissement (la commande planifiée et la réservation)."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    local = (await maintenant(connexion)).astimezone(fuseau)
    return resolution_du_jour_et_de_l_heure(texte, heure, local)


def resolution_du_jour_et_de_l_heure(texte: str | None, heure: str | None, local: datetime) -> Resultat:
    """Pur : le jour et l'heure dits, vus de ``local`` (aware, à l'heure du lieu). Voir ``resoudre_la_date``.

    M109 (appel 2593) : une heure dite SANS jour (« pour dix-neuf heures », dans ``heure`` ou dans ``texte``) vaut aujourd'hui quand elle est encore à
    venir ; déjà passée, c'est une question (le jour), jamais un choix. Une heure ambiguë (« sept heures ») reste une question sur l'heure."""
    fuseau = local.tzinfo
    jour = dates_futures.resoudre_une_date(texte, local) if texte else dates_futures.Resolution(dates_futures.INTROUVABLE)
    if jour.statut == dates_futures.INTROUVABLE:
        seule = _heure_seule(texte, heure)
        if seule is None:
            return Resultat("INTROUVABLE", {}, "Pour quel jour ?", "jour")
        if seule.statut == dates_futures.AMBIGU:
            dites = [dates_futures.heure_dite(c) for c in seule.candidats]
            return Resultat("AMBIGU", {"candidats_heure": dites}, f"Est-ce {' ou '.join(dites)} ?", "heure")
        if datetime.combine(local.date(), seule.heure, tzinfo=fuseau) <= local:
            dite = dates_futures.heure_dite(seule.heure)
            return Resultat("INTROUVABLE", {"heure_dite": dite, "heure_passee_aujourd_hui": True}, f"Il est déjà plus de {dite} : pour quel jour ?", "jour")
        jour = dates_futures.Resolution(dates_futures.RETENU, local.date(), (local.date(),))
        heure = heure if heure and dates_futures.resoudre_l_heure(heure).statut != dates_futures.INTROUVABLE else texte
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


def _heure_seule(texte: str | None, heure: str | None) -> dates_futures.HeureResolue | None:
    """M109 : l'heure dite quand aucun jour ne l'est (dans ``heure``, sinon dans ``texte``) ; ``None`` : aucune heure lisible. Une durée (« dans deux
    heures ») ou une date écrite (« 2026-11-17… ») n'est jamais lue comme une heure du jour : la question du jour reste posée."""
    import re

    for dit in (heure, texte):
        if dit and dit.strip() and not re.search(r"\d{4}|\bdans\b", dit.casefold()):
            lue = dates_futures.resoudre_l_heure(dit)
            if lue.statut != dates_futures.INTROUVABLE:
                return lue
    return None


MODES_POSSIBLES = ("emporter", "livraison", "sur_place")


def objets_de_la_carte(carte: dict[str, Any], remises: list[Any]) -> dict[str, bool]:
    """Les objets de la carte chargée qui ouvrent des cases de la fiche (``contrat.CASES_DES_BRIQUES``) : ``choix`` (``composition``) quand la carte a une formule
    ou un groupe de choix qui n'est pas une taille, ``code_de_remise`` quand une remise est active. Une fonction pure : le rendu de la fiche d'une brique
    (lots 8 à 15, D66) la rejoue sur la carte avec et sans elle."""
    return {
        "choix": bool(carte["formules"]) or any(g["role"] != "taille" for g in carte["groupes"]),
        "code_de_remise": bool(remises), "poids": False, "personnes": False,
    }


class SourceClasseur:
    # Agent B (17/11) : le champ de la fiche du restaurant que la commande joint à sa note (le ticket en cuisine est complet).
    champs_du_greffier = {"note": ("allergie", "consigne_livreur")}  # Evan (18/11) : la consigne pour le livreur part dans la note de la commande
    modes = MODES_POSSIBLES
    libelles_des_modes = {"emporter": "à emporter", "livraison": "en livraison", "sur_place": "sur place"}
    question_de_la_zone = "Quelle est l'adresse de livraison ?"
    moyens_reserves_au_mode = {"carte_livraison": ("livraison",)}  # M90 : le TPE à la porte n'existe qu'en livraison
    libelles_des_moyens = {
        "carte": "par carte", "especes": "en espèces", "titre_restaurant": "en titres-restaurant", "cheque": "par chèque", "en_ligne": "en ligne",
        "carte_livraison": "par carte à la livraison",
    }

    def __init__(
        self, connexion: Connexion, lieu: Lieu, *, nom_prise: str = PRISE_PAR_DEFAUT, capacites: Capacites | None = None,
        reglages_de_recherche: ReglagesDeRecherche | None = None, prise: Prise | None = None,
    ):
        self.c = connexion
        self.lieu = lieu
        self.nom_prise = nom_prise
        self.capacites = capacites or capacites_de(nom_prise)
        self.reglages_de_recherche = reglages_de_recherche
        self.prise = prise

    # ---- le mode
    async def charger_les_modes(self) -> None:
        """C13 : les modes proposés sont ceux que l'établissement n'a pas éteints (un restaurant sans salle ne se voit jamais proposer « sur place »).
        Un type sans ligne de réglage, ou en pause, reste proposé : la pause se dit par son statut, jamais par un mode qui disparaît."""
        eteints = await types_de_commande_eteints(self.c, self.lieu.etablissement_id, MODES_POSSIBLES)
        reste = tuple(m for m in MODES_POSSIBLES if m not in eteints)
        if reste:
            self.modes = reste

    async def charger_pour_l_appel(self) -> tuple[dict[str, list[str]], dict[str, bool]]:
        """Lot 5 (E23, D61 points 1 et 3) : au décroché, en un nombre FIXE de requêtes, tout ce que les gestes de l'appel liront sans le relire :
        fuseau, carte (huit requêtes, une par table) et son index de recherche, ruptures connues, zones et commune du site, réglages, horaires de
        la fiche, remises actives, soirs chargés, prise, état vivant. Rangé dans l'instantané posé sur la connexion (``instantane.py``).

        ⛔ La carte chargée fait foi pour tout l'appel : un prix changé en caisse pendant l'appel vaut à l'appel suivant, jamais au milieu d'une
        commande (le client entend un seul prix du début à la fin). Ce qui peut changer pendant l'appel est relu à son moment : l'état vivant
        (pause, forçage, fermeture, caisse) à chaque geste, les ruptures à l'enregistrement. Toute donnée de carte d'une brique (lots 8 à 15)
        entre ici.

        Rend les listes fermées de la fiche pour le contexte de l'appel (``contrat.listes_du_contexte``) et les objets de la carte qui ouvrent
        des cases (``contrat.CLE_DES_OBJETS``)."""
        from api.db.bases_clients.horaires_caisse import horaires_du_classeur
        from api.db.bases_clients.restauration_carte import ruptures_du_restaurant
        from api.db.bases_clients.restauration_client import index_de_la_carte
        from api.db.bases_clients.restauration_commun import minutes_recurrentes
        from api.db.bases_clients.restauration_remise import remises_actives_a
        from api.db.bases_clients.restauration_zone import centre_de_l_etablissement, zones_de_l_etablissement
        from api.services.commande import contrat
        from api.services.commande.porte import MOYENS_DE_LA_FICHE
        from api.services.communes.base import obtenir_base

        etablissement = self.lieu.etablissement_id
        moment = await maintenant(self.c)
        await self.charger_les_modes()  # l'état vivant, une requête
        carte = await restauration.carte_du_restaurant(self.c, etablissement, moment)
        await ruptures_du_restaurant(self.c, etablissement, moment)
        await zones_de_l_etablissement(self.c, etablissement)
        await centre_de_l_etablissement(self.c, etablissement, await obtenir_base())
        reglages = await self.reglages()
        await horaires_du_classeur(self.c, etablissement)
        remises = await remises_actives_a(self.c, etablissement, moment)
        await minutes_recurrentes(self.c, etablissement, MODES_POSSIBLES[0], moment)
        await prise_de_l_etablissement(self.c, etablissement)
        await index_de_la_carte(self.c, etablissement)  # la recherche des noms préparée une fois pour la version de la carte
        moyens = [fiche for fiche, ici in MOYENS_DE_LA_FICHE.items() if ici in (reglages.get("moyens_paiement") or [])]
        variantes = list(dict.fromkeys(d["nom"] for p in carte["produits"] if len(p["declinaisons"]) > 1 for d in p["declinaisons"]))
        return contrat.listes_du_contexte(list(self.modes), moyens, variantes), objets_de_la_carte(carte, remises)

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
            # une pause (de la caisse, du type, forcée) : seule sa reprise compte, jamais la prochaine ouverture des horaires (lot 4, audit § 3.3)
            "en_pause": etat["raison"] in ("caisse_pause", "pause_type", "pause_force"),
        }
        if not etat["ouvert"]:
            sortie["phrase"] = await self._phrase_de_fermeture(sortie, mode)
        return sortie

    async def _phrase_de_fermeture(self, etat: dict[str, Any], mode: str) -> str:
        fuseau = ZoneInfo(await fuseau_de(self.c, self.lieu.etablissement_id))
        # Lot 4 (audit caisse § 3.3) : une pause dit sa reprise seulement quand elle est connue ; jamais la prochaine ouverture des horaires à sa place.
        quand = etat["reprise"] if etat.get("en_pause") else (etat["reprise"] or etat["prochaine_ouverture"])
        reprise = ""
        if isinstance(quand, datetime):
            local = quand.astimezone(fuseau)
            reprise = f" Nous reprenons à {heure_en_lettres(local.hour, local.minute)}."
        # D15 : quand le réglage du type permet de commander pour plus tard, la fermeture le propose (un créneau de la prochaine ouverture).
        propose = " Je peux prendre votre commande pour plus tard, sur un créneau de la prochaine ouverture." if etat.get("planifiee_permise") else ""
        if etat["statut"] == "LIVRAISON_TERMINEE":
            return "Les livraisons sont terminées pour aujourd'hui." + reprise + propose
        if etat["statut"] == "PAUSE_TYPE":
            return "Nous sommes en pause pour le moment." + reprise + propose
        return "Nous sommes fermés pour le moment." + reprise + propose

    async def verifier_un_creneau(self, mode: str, voulue: datetime) -> Resultat | None:
        """D15 : l'heure voulue tient-elle (réglage du type, jours à l'avance, délai minimal, ouvert à cette heure, place) ? ``None`` si oui,
        sinon le refus (statut, phrase qui dit quand on rouvre ou le premier créneau libre, ``manque = heure_voulue``). Lecture seule."""
        fuseau = ZoneInfo(await fuseau_de(self.c, self.lieu.etablissement_id))
        return await creneau_refuse(self.c, self.lieu.etablissement_id, mode, voulue, await maintenant(self.c), fuseau)

    async def quand_dit(self, voulue: datetime) -> str:
        """« dix-neuf heures trente » le jour même, « vendredi treize novembre à dix-neuf heures trente » un autre jour."""
        fuseau = ZoneInfo(await fuseau_de(self.c, self.lieu.etablissement_id))
        return _quand_dit(voulue, await maintenant(self.c), fuseau)

    # ---- le catalogue
    async def chercher(self, texte: str) -> Resultat:
        return await restauration.chercher_dans_la_liste(self.c, "carte", texte, self.lieu.etablissement_id, reglages=self.reglages_de_recherche)

    async def article(self, ref: str, mode: str) -> dict[str, Any] | None:
        fiche = await article_de_la_carte(self.c, self.lieu.etablissement_id, ref, mode=mode)
        if fiche is not None:
            # Lot 7 : ce que le moteur lit pour répondre sur un signalement (sans connaître le mot du métier).
            fiche["signalements"] = signalements_de(fiche.get("allergenes"))
            fiche["signalements_libelles"] = {c: libelle for c, (libelle, _) in LES_QUATORZE.items()}
            _signalements_des_options(fiche.get("groupes") or [])
            # Lot 26 (M26) et lot 8 : de quoi accorder ce que l'agent dit (genre, nom commun) est déjà dans la fiche, lu à la surcouche du produit.
        return fiche

    def signalement_dit(self, texte: str) -> str | None:
        return code_dit(texte)

    def codes_d_un_nom(self, nom: str) -> list[str]:
        """Lot 4 (C13) : les signalements que le NOM d'un ingrédient affirme (« thon » : poissons), pour chercher « du poisson »."""
        return codes_nommes(nom)

    def regime_dit(self, texte: str) -> str | None:
        return regime_dit(texte)

    async def catalogue(self, mode: str) -> dict[str, Any]:
        """M104 : la carte vendable à cet instant, en UNE lecture, pour chercher ce qui est « sans » une chose : chaque produit avec sa
        catégorie, ses signalements (``None`` = inconnu) et ses choix obligatoires (options et ce qu'on sait de leurs signalements). Les
        formules n'y sont pas : leur contenu dépend du choix, jamais garanti « sans »."""
        moment = await maintenant(self.c)
        carte = await restauration.carte_du_restaurant(self.c, self.lieu.etablissement_id, moment)
        ruptures = {r["code_caisse"] for r in await restauration.ruptures_du_restaurant(self.c, self.lieu.etablissement_id, moment)}
        categories = {c["id"]: c["nom"] for c in carte["categories"]}
        groupes = {g["id"]: g for g in carte["groupes"] if g["parent_option_id"] is None}
        articles = []
        for p in carte["produits"]:
            if not any(d["vendable"] and d["code_caisse"] not in ruptures for d in p["declinaisons"]):
                continue
            obligatoires = [
                [
                    {"nom": o["nom"], "signalements": signalements_de(o.get("allergenes")), "signalements_du_nom": codes_nommes(o["nom"] or "")}
                    for o in groupes[ref]["options"] if o["vendable"] and o["code_caisse"] not in ruptures
                ]
                for ref in p["groupes"] if ref in groupes and groupes[ref]["min"] >= 1
            ]
            ingredients = p.get("ingredients")
            articles.append({
                "id": p["id"], "nom": p["nom"], "categorie": categories.get(p["categorie_id"]),
                "signalements": signalements_de(p["allergenes"]), "obligatoires": obligatoires,
                # Lot 4 (C13) : ce que l'article contient, d'après la carte ; ``None`` quand la carte ne le dit pas (jamais « rien »)
                "ingredients": [str(i.get("nom") if isinstance(i, dict) else i) for i in ingredients] if ingredients else None,
            })
        return {"articles": articles, "libelles": {c: libelle for c, (libelle, _) in LES_QUATORZE.items()}}

    async def chiffrer(self, mode: str, lignes: list[dict[str, Any]], zone_id: int | None, regles: dict[str, Any]) -> Resultat:
        return await chiffrer_panier(
            self.c, self.lieu.etablissement_id, mode, _vers_le_classeur(lignes), zone_id,
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

    async def envoyer(self, quoi: str, telephone: str | None, cle_unique: str, organisation: int | None) -> Resultat:
        """Un message demandé par l'appelant (la carte, le lien d'avis) : ``OK`` s'il est parti, ``DEJA_FAIT`` s'il l'a déjà été dans cet appel,
        ``INDISPONIBLE`` s'il est éteint (le défaut), sans mobile ou sans compte."""
        if quoi not in envois.A_LA_DEMANDE:
            return Resultat("ARGUMENT_INVALIDE", {"possibles": list(envois.A_LA_DEMANDE)}, "", "quoi")
        envoi_allume = await envois.liaison_db.envoi_actif(self.c, self.lieu.etablissement_id, "sms", quoi)
        if envoi_allume is None or not telephone:
            return Resultat("INDISPONIBLE", {}, "Je ne peux pas envoyer de message pour le moment.")
        parti = await envois.envoyer_apres(self.c, organisation, self.lieu.etablissement_id, quoi, telephone, {}, cle_unique)
        return Resultat("OK", {"envoye": True}, "C'est envoyé.") if parti else Resultat("DEJA_FAIT", {"envoye": False}, "C'est déjà parti, ou je ne peux pas l'envoyer à ce numéro.")

    async def offres_a_portee(self, mode: str, lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Les offres atteintes ou presque atteintes par ces lignes chiffrées, avec l'article offert à proposer (lot 26, M25)."""
        return await restauration_en_plus.offres_a_portee(self.c, self.lieu.etablissement_id, mode, lignes, await maintenant(self.c))

    async def proposer_en_plus(self, mode: str, lignes: list[dict[str, Any]], avec_offre: bool = True) -> dict[str, Any] | None:
        """UN article précis à proposer en plus de ces lignes chiffrées, ou ``None`` (lot 26, M25)."""
        return await restauration_en_plus.proposition_en_plus(self.c, self.lieu.etablissement_id, mode, lignes, await maintenant(self.c), avec_offre)

    async def signaler_une_regle_inconnue(self, produit_ref: str, texte: str) -> bool:
        """E29 : une règle de la carte que l'agent ne sait pas appliquer est signalée au portail (une fois par produit et par texte)."""
        return await signaler_une_regle_inconnue(self.c, self.lieu.etablissement_id, produit_ref, texte)

    async def accords_de_la_carte(self) -> dict[str, tuple[str, bool]]:
        """Lot 8 : le genre et le nom commun de chaque produit de la carte, par son nom (sans casse) : de quoi accorder ce que le client a pris
        la dernière fois, dont les lignes ne portent que le nom. Lu dans la carte de l'appel (aucune requête de plus pendant un appel)."""
        carte = await restauration.carte_du_restaurant(self.c, self.lieu.etablissement_id)
        return {p["nom"].casefold().strip(): accord_du_produit(p) for p in carte["produits"]}

    async def remises_en_cours(self) -> list[dict[str, Any]]:
        return await remises_en_cours(self.c, self.lieu.etablissement_id, await maintenant(self.c))

    async def noter_une_offre_dite(self, ref: str, appel_id: str | None) -> None:
        """M38 : l'agent vient de dire cette offre (colonne « Dite » de l'écran Remises). Une fois par appel."""
        await noter_une_offre_dite_par_ref(self.c, self.lieu.etablissement_id, ref, appel_id)

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

    async def _panier_chiffre(self, p: dict[str, Any], ctx: Any) -> dict[str, Any]:
        """Le panier du direct AVEC ses prix : le prix de chaque ligne et le total, en centimes, chiffrés par la source (jamais par le modèle). Sans chiffrage possible
        (panier incomplet, source qui ne répond pas) : le panier sans prix, comme avant. Aucune donnée de l'appelant n'y entre."""
        from api.services.commande import moteur as moteur_commande
        from api.services.commande import panier as paniers
        from api.services.commande.reglages import reglages_de_la_commande

        try:
            regles = reglages_de_la_commande(ctx.configurations)
            chiffre = await moteur_commande._chiffrer(self, p, regles) if regles is not None else None
        except Exception as erreur:  # noqa: BLE001 -- R1 : un panier sans prix vaut mieux qu'un direct qui casse
            logger.error(f"[.mark] Live cart pricing failed: {erreur!r}")
            chiffre = None
        if chiffre is None or chiffre.statut != "OK":
            return p
        calculees = {l["n"]: c for l, c in zip(paniers.lignes_pretes(p), chiffre.faits.get("lignes", []))}
        lignes = []
        for l in p["lignes"]:
            c = calculees.get(l["n"])
            unitaire = c.get("prix_unitaire") if c else None
            lignes.append({**l, "prix": unitaire * l["quantite"] if isinstance(unitaire, int) and not isinstance(unitaire, bool) else None})
        return {**p, "lignes": lignes, "total": chiffre.faits.get("total") if not paniers.a_completer(p) else None}

    async def apres_le_geste(self, geste: str, avant: int, p: dict[str, Any], r: Resultat, ctx: Any) -> None:
        """Le portail l'apprend en direct (contrat portail ↔ fork § 3) : ``commande.panier`` quand le panier de l'appel a changé (le portail relit),
        ``commande.creee`` quand la commande est enregistrée. Un seul émetteur : ``flux.emettre``. Hors appel suivi (pas de run) : rien."""
        organisation, etablissement = ctx.organization_id, self.lieu.etablissement_id
        if not organisation:
            return
        if ctx.run_id and p["version"] != avant:
            await flux.poser_le_panier(organisation, etablissement, ctx.run_id, await self._panier_chiffre(p, ctx))
            await flux.emettre(organisation, etablissement, "commande.panier", {"appel_id": str(ctx.run_id), "version": p["version"]})
        if geste == "finaliser" and r.statut in ("ENREGISTREE", "TRANSMISE"):
            faits = r.faits
            await flux.emettre(
                organisation, etablissement, "commande.creee",
                {"numero": faits["numero"], "numero_court": faits["numero_court"], "mode": p["mode"], "heure_annoncee": faits["heure_annoncee"], "total": faits["total"]},
            )
            # Lot 7 (E-18) : le SMS de confirmation, seulement si l'établissement l'a allumé (éteint par défaut) ; ne défait jamais la commande.
            fuseau = ZoneInfo(await fuseau_de(self.c, etablissement))
            heure = faits["heure_annoncee"].astimezone(fuseau).strftime("%H:%M") if isinstance(faits.get("heure_annoncee"), datetime) else ""
            await envois.envoyer_apres(
                self.c, organisation, etablissement, envois.COMMANDE_ENREGISTREE, (p.get("client") or {}).get("telephone"),
                {"prenom": (p.get("client") or {}).get("prenom") or "", "numero_court": faits["numero_court"], "heure": heure, "quand": heure}, str(faits["numero"]),
            )

    def permet_l_annulation(self) -> bool:
        """Lot 4 (E10) : la caisse de l'établissement sait-elle annuler une commande reçue ? Lu sur la fiche de capacités de la prise, jamais sur son nom."""
        return bool(self.capacites.annulation)

    async def annuler_une_commande(self, numero: str) -> Resultat:
        """Lot 4 (E10) : la commande ``numero`` de CET établissement passe à ``annulee`` (chemin fermé du classeur, source ``agent``), puis la caisse est
        informée par sa prise. ``OK`` ; ``DEJA_FAIT`` ; ``INTERDIT`` (déjà préparée et remise, ou statut final) ; ``INTROUVABLE``. Une caisse en panne ne
        défait pas l'annulation (R1 : au journal, le rattrapage la rejoint)."""
        commande = await commande_complete(self.c, self.lieu.etablissement_id, numero)
        if commande is None:
            return Resultat("INTROUVABLE", {"numero": numero})
        r = await restauration.changer_statut(self.c, self.lieu.etablissement_id, numero, commande["statut"], "annulee", "agent")
        if r.statut != "OK":
            return r
        try:
            if self.prise is not None and self.prise.capacites.annulation:
                await self.prise.annuler_commande(numero)
            elif self.prise is None and self.lieu.organisation_id:
                from api.services.restauration.statut import _informer_la_caisse

                await _informer_la_caisse(self.lieu.organisation_id, self.c, self.lieu.etablissement_id, self.lieu.nom_base, numero, "annulee")
        except Exception as erreur:  # noqa: BLE001 -- R1 : la caisse en panne ne défait pas l'annulation ; on le voit ici
            logger.error(f"[.mark] Order {numero}: telling the till about the cancellation failed: {erreur!r}")
        if self.lieu.organisation_id:
            await flux.emettre(self.lieu.organisation_id, self.lieu.etablissement_id, "commande.statut",
                               {"numero": numero, "de": commande["statut"], "vers": "annulee", "source": "agent"})
        return r

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
    """La source pour UN geste d'outil, sur la connexion de l'appel (D53 : une par appel, rouverte une fois si la base l'a coupée, fermée à la fin
    de l'appel ; ``memoire_de_l_appel``), l'établissement de l'appel et sa prise."""
    from api.services.restauration import memoire_de_l_appel

    async with memoire_de_l_appel.geste(ctx) as (connexion, lieu):
        nom_prise = await prise_de_l_etablissement(connexion, lieu.etablissement_id)
        source = SourceClasseur(connexion, lieu, nom_prise=nom_prise, reglages_de_recherche=reglages_de_recherche)
        await source.charger_les_modes()
        yield source


enregistrer_source("classeur", ouvrir_la_source)
