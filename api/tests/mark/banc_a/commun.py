"""[.mark] Banc A : le montage commun (une carte, un établissement, un appel rejoué) et le rejeu des vrais arguments du modèle.

Rien ici ne corrige quoi que ce soit : ce module monte ce que la production monte (la même source, le même ``action.executer``) et rejoue les
appels d'outil tels que Gemma 4 les a envoyés dans les runs 2636 à 2678 (``donnees/runs_2636_2678.json``, numéros de téléphone remplacés).

Ce qui n'est PAS rejoué : le greffier (second modèle). Quand un cas dépend de ce qu'il avait noté, le test le pose à la main (``notes``) et le dit.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_ecran import poser_les_synonymes
from api.services.commande import action, panier as P
from api.services.restauration.appel import Lieu
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

ICI = Path(__file__).parent
CARTES = ICI / "cartes"
RUNS = json.loads((ICI / "donnees" / "runs_2636_2678.json").read_text(encoding="utf-8"))
ESSAI = ICI.parent / "cartes_essai"

# Le nom que le modèle voit pour chaque action de la commande (``noms_des_outils`` des runs de la nuit).
ACTION_DU_NOM_VU = {
    "type_de_commande": "choisir_mode", "ajouter_au_panier": "ajouter", "valider_la_commande": "finaliser", "lire_la_commande": "voir_commande",
    "modifier": "modifier", "retirer": "retirer", "voir_produit": "voir_produit", "retrouver_commande": "retrouver_commande",
    "ouverture_en_ce_moment": "etat_ouverture", "heure_annoncee": "heure_annoncee", "envoyer_un_message": "envoyer_un_message",
    "remises_disponibles": "remises_disponibles", "resoudre_une_date": "resoudre_une_date",
}
NOM_VU_DE_L_ACTION = {v: k for k, v in ACTION_DU_NOM_VU.items()}

# Zones de livraison des cartes de démo, en codes INSEE (le format de carte porte des noms de communes, la base des codes).
SENLIS, CHANTILLY, PONT, PONT_2, PONT_3 = "60612", "60141", "60509", "60508", "60587"
GOUVIEUX = "60282"
ZONES = {
    "casa-italia": [("Senlis", [SENLIS], 0, 0, 30), ("Chantilly, Gouvieux, Pontarmé", [CHANTILLY, GOUVIEUX], 2500, 0, 50)],
}
ZONE_PAR_DEFAUT = [("Pont", [PONT, PONT_2, PONT_3], 0, 0, 30)]
ADRESSES = {"casa-italia": "12 rue de la République, 60300 Senlis"}
ADRESSE_PAR_DEFAUT = "5 rue Louis Boilet, 60700 Pont-Sainte-Maxence"
REINE = ["reine", "la reine", "pizza reine"]  # le synonyme posé à l'écran en production (« une reine » donne la Regina)


def carte_de(slug: str) -> dict:
    return json.loads((CARTES / f"{slug}.json").read_text(encoding="utf-8"))["carte"]


def synonymes_de(slug: str) -> dict[str, list[str]]:
    fichier = {"casa-italia": "synonymes-casa-italia.json", "kebab-demo": "synonymes-kebab-demo.json"}.get(slug)
    if not fichier:
        return {}
    donnees = {k: v for k, v in json.loads((ESSAI / fichier).read_text(encoding="utf-8")).items() if not k.startswith("_")}
    if slug == "casa-italia":
        donnees["P-PIZZAS-TOMATE-REGINA"] = REINE
    return donnees


class Monde:
    """Un établissement monté dans la base de test depuis une carte figée."""

    def __init__(self, c, site: int, base, slug: str, carte: dict, minimum: int | None):
        self.c, self.a, self.base, self.slug, self.carte, self.minimum = c, site, base, slug, carte, minimum
        self.adresse = ADRESSES.get(slug, ADRESSE_PAR_DEFAUT)

    def produit(self, nom: str) -> dict:
        return next(p for p in self.carte["produits"] if p["nom"].casefold() == nom.casefold())


@pytest.fixture
async def faire_monde(base_prete, request):
    """``await faire_monde("casa-italia")`` : l'établissement, ses horaires (jeudi midi, ouvert), ses modes, ses zones, sa carte et ses synonymes."""
    ouverts: list = []
    with horloge.remplacer(base_prete, getattr(request, "param", JEUDI_MIDI)):

        async def faire(slug: str, minimum: int | None = None) -> Monde:
            carte = carte_de(slug)
            etab = carte.get("etablissement") or {}
            c = await schema.connecter(base_prete)
            ouverts.append(c)
            await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ($1)", slug)
            site = await c.fetchval(
                "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise WHERE raison_sociale = $1 RETURNING id", slug
            )
            # Le centre de l'établissement (commune de son adresse) départage les homonymes : sans lui « Senlis » est toujours ambigu.
            await c.execute("UPDATE mark.site SET adresse_insee = $2 WHERE id = $1", site, ZONES.get(slug, ZONE_PAR_DEFAUT)[0][1][0])
            for jour, plages in (etab.get("horaires") or {}).items():
                for ouverture, fermeture in plages or []:
                    await c.execute(
                        "INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, $3::text::time, $4::text::time)", site, int(jour), ouverture, fermeture
                    )
            maintenant = getattr(request, "param", JEUDI_MIDI)
            if maintenant.hour < 6:
                # La nuit du 18/11 : Casa avait été laissé ouvert ce jour-là (essais de 2 h à 3 h) ; les autres jours gardent leurs horaires.
                await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, '00:00'::time, '06:00'::time)", site, maintenant.isoweekday())
            await c.execute(
                "INSERT INTO mark.resto_reglage (site_id, prefixe_numero_court, moyens_paiement) VALUES ($1, 'T', $2::text[])", site, sorted({*(etab.get("paiements") or ["carte", "especes"]), *(["carte_livraison"] if slug == "casa-italia" else [])})
            )
            types = etab.get("types") or {}
            await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, delai_annonce) VALUES ($1, 'emporter', $2)", site, (types.get("emporter") or {}).get("delai_annonce") or 20)
            await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type) VALUES ($1, 'livraison')", site)
            # Les commandes pour plus tard sont permises (Casa de démo en production : « nous rouvrons jeudi à onze heures, pour quelle heure ? »).
            await c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = true, jours_a_l_avance = 3, delai_minimal = 30 WHERE site_id = $1 AND type IN ('emporter', 'livraison')", site)
            await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, ouvert) VALUES ($1, 'sur_place', $2)", site, types.get("sur_place") is not None)
            for nom, communes, mini, frais, delai in ZONES.get(slug, ZONE_PAR_DEFAUT):
                await c.execute(
                    "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, minimum, frais, delai) VALUES ($1, $2, 'communes', $3::text[], $4, $5, $6)",
                    site, nom, communes, minimum if minimum is not None else mini, frais, delai,
                )
            await importer_carte(c, site, carte, "caisse")
            for ref, synonymes in synonymes_de(slug).items():
                assert await poser_les_synonymes(c, site, ref, synonymes, "essai"), ref
            return Monde(c, site, base_prete, slug, carte, minimum)

        yield faire
    for c in ouverts:
        await c.close()


class ConnexionChronometree:
    """La connexion de la base de test vue par la source : mesure le temps passé dans les requêtes (``fetch``, ``fetchrow``, ``fetchval``, ``execute``)."""

    def __init__(self, c):
        self._c = c
        self.requetes = 0
        self.secondes = 0.0

    def __getattr__(self, nom):
        attribut = getattr(self._c, nom)
        if nom not in ("fetch", "fetchrow", "fetchval", "execute", "executemany"):
            return attribut

        async def mesure(*a, **k):
            debut = time.perf_counter()
            try:
                return await attribut(*a, **k)
            finally:
                self.requetes += 1
                self.secondes += time.perf_counter() - debut

        return mesure


class Appel:
    """Un appel : le panier vit dans la fiche, chaque appel d'outil passe par ``action.executer`` (le chemin de la production)."""

    def __init__(self, monde: Monde, monkeypatch, conduite: bool = True, configurations: dict | None = None):
        self.monde = monde
        self.connexion = ConnexionChronometree(monde.c)
        self.source = SourceClasseur(self.connexion, Lieu(monde.base, monde.a, 1), nom_prise="test", prise=PriseTest())
        self.fiche: dict[str, Any] = {"noms_des_outils": dict(NOM_VU_DE_L_ACTION)}
        self.ctx = SimpleNamespace(
            fiche=self.fiche, appel={"caller_number": "+33600000000"}, run_id=None, organization_id=None, reglages={},
            configurations={"commande_conduite_par_l_agent": conduite, **(configurations or {})},
        )
        self.journal: list[dict[str, Any]] = []  # chaque appel joué : outil, arguments, retour
        self._pas_encore_ecrit: dict[str, str] = {}  # ce que le greffier de CE tour n'a pas encore écrit : le code l'attend (``rattraper``) quand sa question est posée
        self.ctx.rattraper = self._rattraper

        @asynccontextmanager
        async def ouvrir(nom, ctx, **options):
            await self.source.charger_les_modes()
            yield self.source

        monkeypatch.setattr(action.registre_des_sources, "ouvrir", ouvrir)

    # ------------------------------------------------------------------ lecture
    @property
    def p(self) -> dict[str, Any]:
        return P.du_dossier(self.fiche)

    def lignes(self) -> list[tuple]:
        """(nom, quantité, retraits, choix) de chaque ligne du panier, triées."""
        return sorted((l["nom"], l["quantite"], tuple(sorted(l.get("retires") or [])), tuple(sorted(c["nom"] for c in l.get("choix") or []))) for l in self.p["lignes"])

    def noms(self) -> list[str]:
        return sorted(l["nom"] for l in self.p["lignes"])

    def quantite_de(self, debut_du_nom: str) -> int:
        return sum(l["quantite"] for l in self.p["lignes"] if l["nom"].casefold().startswith(debut_du_nom.casefold()))

    # ------------------------------------------------------------------ jeu
    def greffier(self, **notes: str) -> "Appel":
        """Ce que le greffier (second modèle, non rejoué ici) avait noté : ``type_de_commande``, ``adresse_livraison``, ``commune``, ``mode_de_paiement``, ``prenom``, ``numero_dicte``."""
        self.fiche.setdefault("extracted_variables", {}).update({k: v for k, v in notes.items() if v})
        return self

    async def _rattraper(self, delai_s: float) -> None:
        """Le code attend la passe du greffier en cours (2,5 s au plus) quand il a posé la question de ce champ : elle est alors écrite."""
        self.greffier(**self._pas_encore_ecrit)
        self._pas_encore_ecrit = {}

    async def jouer(self, outil: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Un appel d'outil du modèle (nom vu : ``type_de_commande``, ``ajouter_au_panier``, ``valider_la_commande``, ``modifier``...)."""
        nom = ACTION_DU_NOM_VU.get(outil, outil)
        self.connexion.requetes, self.connexion.secondes = 0, 0.0
        debut = time.perf_counter()
        retour = await action.executer(SimpleNamespace(nom=nom), dict(arguments or {}), self.ctx, 5.0)
        total = time.perf_counter() - debut
        if os.environ.get("BANC_A_LATENCE"):  # une ligne par appel d'outil : l'opération, le temps total, le temps dans la base, le nombre de requêtes
            with open(os.environ["BANC_A_LATENCE"], "a", encoding="utf-8") as f:
                f.write(json.dumps({"action": nom, "ms": round(total * 1000, 2), "ms_base": round(self.connexion.secondes * 1000, 2), "requetes": self.connexion.requetes}) + chr(10))
        self.journal.append({"outil": outil, "arguments": dict(arguments or {}), "retour": retour})
        return retour

    async def rejouer(
        self, run: int | str, jusqu_au_tour: int | None = None, apres_le_tour: int = 0, sauf: tuple[tuple[int, str], ...] = (), greffier: bool = True, en_retard: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        """Rejoue les appels d'outil de commande du run, dans l'ordre, avec les arguments réels du modèle, jusqu'au tour ``jusqu_au_tour`` inclus.
        Rend le retour du dernier appel joué. ``sauf`` : des (tour, outil) à ne pas rejouer (un appel que le test remplace).
        ``greffier`` : les notes du greffier sont reconstituées (valeur FINALE du champ, visible dès le tour où la production l'a écrit : la passe du greffier
        dure 0,4 à 0,6 s, avant l'appel d'outil). ``en_retard`` : des champs écrits trop tard pour ce tour (visibles au suivant, ou quand le code les attend)."""
        dernier: dict[str, Any] = {}
        donnees = RUNS[str(run)]
        premier_tour_du_champ: dict[str, int] = {}
        for passe in donnees.get("greffier_passes", []):
            for champ in passe["champs"]:
                premier_tour_du_champ.setdefault(champ, passe["tour"])
        for appel in RUNS[str(run)]["appels"]:
            if appel["action"] is None or appel["outil_vu"] not in ACTION_DU_NOM_VU:
                continue
            if jusqu_au_tour is not None and appel["tour"] > jusqu_au_tour:
                break
            if appel["tour"] <= apres_le_tour or (appel["tour"], appel["outil_vu"]) in sauf:
                continue
            if greffier:
                finales = donnees.get("greffier_final", {})
                tour_du_champ = lambda c: premier_tour_du_champ.get(c, 10**6) + (1 if c in en_retard else 0)  # noqa: E731
                self.greffier(**{c: v for c, v in finales.items() if tour_du_champ(c) <= appel["tour"]})
                self._pas_encore_ecrit = {c: v for c, v in finales.items() if c in en_retard and premier_tour_du_champ.get(c, 10**6) == appel["tour"]}
            dernier = await self.jouer(appel["outil_vu"], appel["arguments"])
            self.journal[-1]["reel"] = appel["reel"]
            self.journal[-1]["tour"] = appel["tour"]
        return dernier

    def ecarts_de_rejeu(self) -> list[str]:
        """Les appels rejoués dont le statut diffère de celui de la production (le montage n'est pas le même, ou le code a changé depuis la nuit)."""
        return [
            f"tour {j['tour']} {j['outil']} : production {j['reel']['statut']}/{j['reel']['manque']}, rejoué {j['retour'].get('statut')}/{j['retour'].get('manque')}"
            for j in self.journal if "reel" in j and (j["reel"]["statut"], j["reel"]["manque"]) != (j["retour"].get("statut"), j["retour"].get("manque"))
        ]


@pytest.fixture
async def appel_de(faire_monde, monkeypatch):
    """``a = await appel_de("casa-italia")`` : un appel monté sur la carte figée."""

    async def faire(slug: str = "casa-italia", minimum: int | None = None, **options) -> Appel:
        return Appel(await faire_monde(slug, minimum), monkeypatch, **options)

    return faire


# --------------------------------------------------------------------------- #
# Aides des tests
# --------------------------------------------------------------------------- #


def reel(run: int, tour: int, rang: int = 0, outil: str | None = None) -> tuple[str, dict[str, Any]]:
    """L'appel d'outil tel que le modèle l'a envoyé : (nom vu de l'outil, arguments). ``rang`` : le n-ième appel du tour ; ``outil`` : le premier de cet outil."""
    appels = [x for x in RUNS[str(run)]["appels"] if x["tour"] == tour and (outil is None or x["outil_vu"] == outil)]
    return appels[rang]["outil_vu"], dict(appels[rang]["arguments"])


async def jouer_reel(a: Appel, run: int, tour: int, rang: int = 0, outil: str | None = None) -> dict[str, Any]:
    nom, arguments = reel(run, tour, rang, outil)
    return await a.jouer(nom, arguments)


def trace(a: Appel) -> str:
    """Ce qui s'est passé, pour le message d'un test rouge : chaque appel, son statut, ce qui manque, et le panier."""
    lignes = []
    for j in a.journal:
        r = j["retour"]
        lignes.append(f"  {j['outil']} {json.dumps(j['arguments'], ensure_ascii=False)[:150]} -> {r.get('statut')}/{r.get('manque')} | {(r.get('suggestion') or '')[:90]}")
    return "\n" + "\n".join(lignes) + f"\n  panier : {a.lignes()} mode={a.p.get('mode')} zone={(a.p.get('zone') or {}).get('nom')} adresse={a.p.get('adresse')!r}"
