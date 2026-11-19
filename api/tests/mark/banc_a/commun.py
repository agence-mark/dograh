"""[.mark] Banc A : le montage commun (une carte, un établissement, un appel rejoué) et le rejeu des vrais arguments du modèle.

Rien ici ne corrige quoi que ce soit : ce module monte ce que la production monte (la même source, la même porte, ``porte.executer``) et rejoue
les runs 2636 à 2678 écrits en FICHES, une par tour (``fiches_des_runs.py`` ; les appels d'origine restent dans ``donnees/runs_2636_2678.json``,
numéros de téléphone remplacés). Lot 3 (D48) : plus aucun ancien outil, chaque test envoie une fiche.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_ecran import poser_l_accord_du_produit, poser_les_synonymes
from api.services.commande import porte
from api.services.restauration.appel import Lieu
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.banc_a.fiches_des_runs import FICHES, SANS_TRANSCRIPTION

RUNS: dict[str, Any] = json.loads((Path(__file__).parent / "donnees" / "runs_2636_2678.json").read_text(encoding="utf-8"))
from api.tests.mark.partie_1.porte_essai import Essai
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

ICI = Path(__file__).parent
CARTES = ICI / "cartes"
ESSAI = ICI.parent / "cartes_essai"

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


def formulaire_de(slug: str) -> dict:
    """Le formulaire que le restaurateur de démo remplit (lot 8) : rôle des catégories, genre et nom commun des produits (``cartes_essai/formulaire-<slug>.json``)."""
    fichier = ESSAI / f"formulaire-{slug}.json"
    return json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {"roles": {}, "genres": {}}


def carte_de(slug: str) -> dict:
    carte = json.loads((CARTES / f"{slug}.json").read_text(encoding="utf-8"))["carte"]
    roles = formulaire_de(slug)["roles"]
    for c in carte.get("categories") or []:
        if c["id"] in roles:
            c["role"] = roles[c["id"]]  # le rôle que le restaurateur a donné à sa catégorie
    return carte


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
    deja: dict[str, int] = {}  # un même établissement monté deux fois dans un test (deux appels sur la même carte) : un nom d'entreprise et une clé de plus
    with horloge.remplacer(base_prete, getattr(request, "param", JEUDI_MIDI)):

        async def faire(slug: str, minimum: int | None = None, carte: dict | None = None) -> Monde:
            carte = carte if carte is not None else carte_de(slug)  # ``carte`` : une carte déjà en main (le rendu d'une brique sans ses données, lot 8)
            etab = carte.get("etablissement") or {}
            c = await schema.connecter(base_prete)
            ouverts.append(c)
            deja[slug] = deja.get(slug, 0) + 1
            nom = slug if deja[slug] == 1 else f"{slug}#{deja[slug]}"
            await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ($1)", nom)
            site = await c.fetchval(
                "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise WHERE raison_sociale = $1 RETURNING id", nom
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
            for ref, accord in formulaire_de(slug)["genres"].items():
                assert await poser_l_accord_du_produit(c, site, ref, accord["genre"], accord["nom_commun"], "essai"), ref
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


class TranscriptionManquante(LookupError):
    """Le run (ou cette suite du run) n'a pas de fiches écrites : les écrire imposerait un choix de sens (``fiches_des_runs.SANS_TRANSCRIPTION``)."""


class Appel(Essai):
    """Un appel : chaque tour envoie une FICHE à la vraie porte (``porte.executer``, le chemin de la production, D48), après le calcul des cases
    montrées comme avant une vraie requête (D52). La connexion de la source est chronométrée (``BANC_A_LATENCE``)."""

    def __init__(self, monde: Monde, monkeypatch, configurations: dict | None = None):
        super().__init__(monde, monkeypatch)
        self.connexion = ConnexionChronometree(monde.c)
        self.source = SourceClasseur(self.connexion, Lieu(monde.base, monde.a, 1), nom_prise="test", prise=PriseTest())
        self.ctx.configurations.update(configurations or {})
        self.journal: list[dict[str, Any]] = []  # chaque tour joué : ce qu'elle a dit, la fiche, le retour

    def noms(self) -> list[str]:
        return sorted(l["nom"] for l in self.p["lignes"])

    def quantite_de(self, debut_du_nom: str) -> int:
        return sum(l["quantite"] for l in self.p["lignes"] if l["nom"].casefold().startswith(debut_du_nom.casefold()))

    def _numero_de_ligne(self, nom: Any) -> Any:
        """La ligne nommée comme dans l'ancien appel : son numéro si UNE ligne porte ce nom (début du nom, sans casse) ; sinon le nom tel quel."""
        if not isinstance(nom, str):
            return nom
        trouvees = [i for i, l in enumerate(self.p["lignes"], 1) if l["nom"].casefold().startswith(nom.casefold())]
        return trouvees[0] if len(trouvees) == 1 else nom

    def _monter(self, fiche: dict[str, Any]) -> dict[str, Any]:
        fiche = json.loads(json.dumps(fiche))
        q = self.p.get("question") if isinstance(self.p.get("question"), dict) else None
        if isinstance(fiche.get("reponse"), dict) and fiche["reponse"].get("question_id") == "?":
            if q is None:
                # Lot 4 : « ? » est la question en attente ; sans question en attente, la case ``reponse`` n'est pas montrée au modèle (E26) : absente
                fiche.pop("reponse")
            else:
                fiche["reponse"]["question_id"] = q["id"]
        for c in fiche.get("changer_quantite") or []:
            c["ligne"] = self._numero_de_ligne(c.get("ligne"))
        if fiche.get("retirer_article"):
            fiche["retirer_article"] = [self._numero_de_ligne(n) for n in fiche["retirer_article"]]
        return fiche

    async def jouer_la_fiche(self, dit: str, fiche: dict[str, Any]) -> dict[str, Any]:
        """Un tour : ce qu'elle dit, puis la fiche (ou la lecture ``{"_lire": {...}}``) ; rend l'enveloppe."""
        self.connexion.requetes, self.connexion.secondes = 0, 0.0
        debut = time.perf_counter()
        self.dit(dit)
        if "_lire" in fiche:
            retour = await porte.executer(SimpleNamespace(nom="lire"), dict(fiche["_lire"]), self.ctx, 5.0)
            envoyee = fiche
        else:
            envoyee = self._monter(fiche)
            retour = await self.fiche(**envoyee)
        total = time.perf_counter() - debut
        if os.environ.get("BANC_A_LATENCE"):  # une ligne par tour : le temps total, le temps dans la base, le nombre de requêtes
            with open(os.environ["BANC_A_LATENCE"], "a", encoding="utf-8") as f:
                f.write(json.dumps({"action": "fiche", "ms": round(total * 1000, 2), "ms_base": round(self.connexion.secondes * 1000, 2),
                                    "requetes": self.connexion.requetes}) + chr(10))
        self.journal.append({"dit": dit, "fiche": envoyee, "retour": retour})
        return retour

    def fiche_du_run(self, run: int, tour: int, fiche: dict[str, Any]) -> dict[str, Any]:
        """Lot 4 : la convention des fiches (``fiches_des_runs``, en tête) appliquée à la question que le code pose MAINTENANT : la proposition naît
        après le premier article au contrat final (B12), l'ancien appel la recevait à la fin. Un ancien appel fait pendant une question en attente
        porte son ``sens`` en ``reponse`` (``accord`` → ``accepte``, ``refus`` → ``refuse``, tout autre → ``autre``), comme le modèle du contrat la
        remplit (B8 point 1)."""
        q = self.p.get("question") if isinstance(self.p.get("question"), dict) else None
        if q is None or "reponse" in fiche or "_lire" in fiche:
            return fiche
        appels = RUNS.get(str(run), {}).get("appels", [])
        appel = next((a for a in appels if a.get("tour") == tour), None)
        avant = [a for a in appels if a.get("tour", 0) < tour]
        reel = (avant[-1].get("reel") or {}) if avant else {}
        # l'ancien appel répondait-il à une question de l'ancien code ? Sinon son « sens » ne vaut pas pour celle d'aujourd'hui : « autre »
        repondait = reel.get("manque") in ("vente_en_plus", "relecture") or reel.get("statut") in ("CHOIX_OBLIGATOIRE", "AMBIGU")
        sens = {"accord": "accepte", "refus": "refuse"}.get(str(((appel or {}).get("arguments") or {}).get("sens")), "autre") if repondait else "autre"
        return {**fiche, "reponse": {"question_id": "?", "sens": sens}}

    async def rejouer(self, run: int, jusqu_au_tour: int | None = None) -> dict[str, Any]:
        """Rejoue les fiches écrites du run (``fiches_des_runs.FICHES``) jusqu'au tour inclus ; rend le dernier retour."""
        dernier_ecrit = max((t[0] for t in FICHES.get(run, [])), default=0)
        if run in SANS_TRANSCRIPTION and (jusqu_au_tour is None or jusqu_au_tour > dernier_ecrit):
            raise TranscriptionManquante(f"run {run} : {SANS_TRANSCRIPTION[run]}")
        dernier: dict[str, Any] = {}
        for tour, dit, fiche in FICHES[run]:
            if jusqu_au_tour is None or tour <= jusqu_au_tour:
                dernier = await self.jouer_la_fiche(dit, self.fiche_du_run(run, tour, fiche))
        return dernier


@pytest.fixture
async def appel_de(faire_monde, monkeypatch):
    """``a = await appel_de("casa-italia")`` : un appel monté sur la carte figée."""

    async def faire(slug: str = "casa-italia", minimum: int | None = None, carte: dict | None = None, **options) -> Appel:
        return Appel(await faire_monde(slug, minimum, carte), monkeypatch, **options)

    return faire


# --------------------------------------------------------------------------- #
# Aides des tests
# --------------------------------------------------------------------------- #


async def jouer_tour(a: Appel, run: int, tour: int) -> dict[str, Any]:
    """Le tour ``tour`` du run, tel qu'écrit dans ``fiches_des_runs`` (une fiche par tour)."""
    if run in SANS_TRANSCRIPTION and tour > max((t[0] for t in FICHES.get(run, [])), default=0):
        raise TranscriptionManquante(f"run {run} : {SANS_TRANSCRIPTION[run]}")
    _, dit, fiche = next(t for t in FICHES[run] if t[0] == tour)
    return await a.jouer_la_fiche(dit, a.fiche_du_run(run, tour, fiche))


def statuts_du_module(r: dict[str, Any]) -> list[str]:
    """Les statuts rendus par le module, opération par opération (``HORS_ZONE``, ``CHOIX_OBLIGATOIRE``...)."""
    return [x.get("statut_du_module") for x in r.get("resultats") or []]


def trace(a: Appel) -> str:
    """Ce qui s'est passé, pour le message d'un test rouge : chaque tour, sa fiche, son retour, et le panier."""
    lignes = []
    for j in a.journal:
        r = j["retour"]
        lignes.append(f"  « {j['dit'][:60]} » {json.dumps(j['fiche'], ensure_ascii=False)[:160]} -> {r.get('statut')}/{r.get('raison')} "
                      f"{statuts_du_module(r)} q={(r.get('question') or {}).get('type')}")
    return "\n" + "\n".join(lignes) + f"\n  panier : {a.lignes()} mode={a.p.get('mode')} zone={(a.p.get('zone') or {}).get('nom')} adresse={a.p.get('adresse')!r}"
