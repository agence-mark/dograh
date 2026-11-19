"""[.mark] Module Restauration, lot 2 : la carte, les ruptures et l'état d'ouverture dans le classeur (couche d'accès).

Jeu d'essai : la carte de référence (pizzeria + burger, format commun) de ``cartes_essai/carte-reference.json``.
Chaque test passe par une VRAIE base (rôle ``_ecriture``) ; l'heure vient de la source d'heure (jamais de l'heure réelle).

| Test | Ce qu'il prouve |
|---|---|
| import idempotent | importer la carte de référence : tout est ajouté ; rejouée, rien ne change (ni ligne, ni version) |
| surcouche conservée | synonymes, étoile, lexique, phrase d'une surcouche survivent à un réimport qui renomme et retire des produits |
| ligne humaine protégée | une ligne écrite par le portail n'est ni écrasée ni retirée par un import de la caisse |
| fichier invalide | un fichier hors format n'écrit RIEN (une transaction) |
| allergènes | ``None`` = inconnu, ``[]`` = aucun, liste = ces codes, de l'import à la carte rendue |
| disponibilité | une déclinaison ou une formule hors de sa plage n'est pas à la carte ; produits sans plage toujours là |
| enseigne et exception | la carte d'enseigne s'applique ; une exception remplace ; une exception masquée retire ; l'autre établissement ne voit pas l'exception |
| cloisonnement | la carte, les ruptures d'un établissement ne sont jamais celles d'un autre |
| version | chaque changement de la carte augmente la version, une rupture non |
| ruptures | actives au bon moment seulement, fin respectée, code inconnu ou d'un autre établissement : INTROUVABLE |
| état combiné | horaires, fermeture exceptionnelle, fiche forcée, pause et fin de journée par type, caisse en pause ou débordée : le plus prudent gagne, la caisse prime pour ce qu'elle porte |
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import (
    CarteInvalide,
    carte_du_restaurant,
    etat_caisse,
    etat_combine,
    importer_carte,
    poser_rupture,
    ruptures_du_restaurant,
    version_carte,
)
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401

PARIS = ZoneInfo("Europe/Paris")


def _charger_la_carte_de_reference() -> dict:
    """La carte de référence. Son générateur tronque les identifiants à 20 caractères : deux produits (Cristaline
    Fraise et Pêche, deux Bardolino) portent le MÊME identifiant. Le fork refuse un identifiant en double (donnée
    fausse) : la copie d'essai suffixe le second, sans toucher au fichier d'origine du labo."""
    carte = json.loads((Path(__file__).parent / "cartes_essai" / "carte-reference.json").read_text(encoding="utf-8"))
    vus: set[str] = set()
    for p in carte["produits"]:
        if p["id"] in vus:
            ancien = p["id"]
            p["id"] = ancien + "-2"
            for d in p["declinaisons"]:
                d["id"] = d["id"].replace(ancien, p["id"], 1)
        vus.add(p["id"])
    return carte


CARTE = _charger_la_carte_de_reference()
# Un jeudi 12 novembre 2026, 12 h à Paris.
JEUDI_MIDI = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)


@pytest.fixture
async def resto(base_prete):
    """Deux établissements (A avec horaires, B), le rôle d'écriture, l'heure fixée au jeudi midi."""
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        ids = {}
        for cle in ("a", "b"):
            ids[cle] = await c.fetchval(
                "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise RETURNING id", cle
            )
        for jour in range(1, 8):
            for ouverture, fermeture in (("11:00", "14:00"), ("18:00", "22:30")):
                await c.execute(
                    "INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, $3::text::time, $4::text::time)", ids["a"], jour, ouverture, fermeture
                )
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            yield SimpleNamespace(c=c, a=ids["a"], b=ids["b"], base=base_prete)
    finally:
        await c.close()


def _carte(**modifs):
    carte = copy.deepcopy(CARTE)
    for cle, valeur in modifs.items():
        carte[cle] = valeur
    return carte


def _produit(carte, ref):
    return next(p for p in carte["produits"] if p["id"] == ref)


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #


async def test_importer_la_carte_de_reference_puis_la_rejouer_ne_change_rien(resto):
    c = resto.c
    bilan = await importer_carte(c, resto.a, CARTE, "caisse")
    attendu = 12 + len(CARTE["produits"]) + sum(len(p["declinaisons"]) for p in CARTE["produits"]) + len(CARTE["groupes"]) \
        + sum(len(g["options"]) for g in CARTE["groupes"]) + len(CARTE["formules"])
    assert bilan["ajoutes"] == attendu and bilan["changes"] == bilan["retires"] == bilan["conserves"] == 0
    assert bilan["sans_code_caisse"] == []
    version = await version_carte(c, resto.a)
    assert version >= 1
    journal = await c.fetchval("SELECT count(*) FROM mark.resto_journal")
    rejoue = await importer_carte(c, resto.a, CARTE, "caisse")
    assert (rejoue["ajoutes"], rejoue["changes"], rejoue["retires"], rejoue["conserves"]) == (0, 0, 0, 0)
    assert await version_carte(c, resto.a) == version  # ni ligne ni version
    assert await c.fetchval("SELECT count(*) FROM mark.resto_journal") == journal
    # le journal dit la source et l'auteur de l'import
    ligne = await c.fetchrow("SELECT source, auteur FROM mark.resto_journal WHERE objet = 'resto_produit' ORDER BY id LIMIT 1")
    assert (ligne["source"], ligne["auteur"]) == ("caisse", "import:caisse")


async def test_une_surcouche_survit_a_un_reimport_qui_renomme_et_retire(resto):
    c = resto.c
    await importer_carte(c, resto.a, CARTE, "caisse")
    marg = "P-PIZZAS-TOMATE-MARGHE"
    await c.execute(
        "INSERT INTO mark.resto_surcouche (site_id, objet, ref, synonymes, synonymes_a_relire, etoile, lexique, phrase) "
        "VALUES ($1, 'produit', $2, '{marguerite}', false, true, '{margarita}', 'La reine des pizzas')", resto.a, marg
    )
    nouvelle = _carte()
    _produit(nouvelle, marg)["nom"] = "Margherita classique"
    retire = nouvelle["produits"].pop()  # un produit disparaît de la caisse
    bilan = await importer_carte(c, resto.a, nouvelle, "caisse")
    assert bilan["changes"] == 1 and bilan["retires"] == 1 + len(retire["declinaisons"])
    s = await c.fetchrow("SELECT * FROM mark.resto_surcouche WHERE site_id = $1 AND ref = $2", resto.a, marg)
    assert (list(s["synonymes"]), s["etoile"], list(s["lexique"]), s["phrase"]) == (["marguerite"], True, ["margarita"], "La reine des pizzas")
    carte = await carte_du_restaurant(c, resto.a)
    p = next(p for p in carte["produits"] if p["id"] == marg)
    assert p["nom"] == "Margherita classique" and p["synonymes"] == ["marguerite"] and p["etoile"] is True and p["phrase"] == "La reine des pizzas"
    assert retire["id"] not in {p["id"] for p in carte["produits"]}
    # un synonyme proposé à l'import ne sert qu'après relecture (T-14)
    await c.execute("UPDATE mark.resto_surcouche SET synonymes_a_relire = true WHERE site_id = $1 AND ref = $2", resto.a, marg)
    p = next(p for p in (await carte_du_restaurant(c, resto.a))["produits"] if p["id"] == marg)
    assert p["synonymes"] == [] and p["synonymes_a_relire"] == ["marguerite"]


async def test_une_ligne_ecrite_par_le_portail_n_est_ni_ecrasee_ni_retiree_par_la_caisse(resto):
    c = resto.c
    await importer_carte(c, resto.a, CARTE, "caisse")
    await c.execute("UPDATE mark.resto_produit SET nom = 'Ma Margherita', source = 'portail' WHERE site_id = $1 AND ref = 'P-PIZZAS-TOMATE-MARGHE'", resto.a)
    await c.execute(
        "INSERT INTO mark.resto_produit (site_id, ref, nom, source) VALUES ($1, 'P-PORTAIL', 'Plat du jour', 'portail')", resto.a
    )
    nouvelle = _carte()
    _produit(nouvelle, "P-PIZZAS-TOMATE-MARGHE")["nom"] = "Nom de la caisse"
    bilan = await importer_carte(c, resto.a, nouvelle, "caisse")
    assert bilan["conserves"] == 1 and bilan["changes"] == 0 and bilan["retires"] == 0
    noms = {p["id"]: p["nom"] for p in (await carte_du_restaurant(c, resto.a))["produits"]}
    assert noms["P-PIZZAS-TOMATE-MARGHE"] == "Ma Margherita" and noms["P-PORTAIL"] == "Plat du jour"


async def test_un_fichier_invalide_n_ecrit_rien(resto):
    c = resto.c
    for faux in ({"format": "autre"}, _carte(format="mark-carte-commune/2"), {**_carte(), "produits": [{"nom": "Sans identifiant", "declinaisons": []}]}):
        with pytest.raises(CarteInvalide):
            await importer_carte(c, resto.a, faux, "caisse")
    assert await c.fetchval("SELECT count(*) FROM mark.resto_produit") == 0
    doublon = _carte()
    doublon["produits"].append(copy.deepcopy(doublon["produits"][0]))
    with pytest.raises(CarteInvalide):
        await importer_carte(c, resto.a, doublon, "caisse")
    # une erreur au milieu de l'écriture (prix négatif refusé par la base) annule tout l'import
    casse = _carte()
    casse["produits"][3]["declinaisons"][0]["prix"] = -5
    with pytest.raises(Exception):  # noqa: B017 - la contrainte de la base
        await importer_carte(c, resto.a, casse, "caisse")
    assert await c.fetchval("SELECT count(*) FROM mark.resto_categorie") == 0


async def test_les_allergenes_gardent_leurs_trois_etats(resto):
    c = resto.c
    carte = _carte()
    carte["produits"][0]["allergenes"] = None
    carte["produits"][1]["allergenes"] = []
    carte["produits"][2]["allergenes"] = ["gluten", "lait"]
    await importer_carte(c, resto.a, carte, "caisse")
    rendue = {p["id"]: p["allergenes"] for p in (await carte_du_restaurant(c, resto.a))["produits"]}
    ids = [p["id"] for p in carte["produits"][:3]]
    assert rendue[ids[0]] is None and rendue[ids[1]] == [] and rendue[ids[2]] == ["gluten", "lait"]
    carte["produits"][0]["allergenes"] = ["arachide"]  # hors des 14 codes : refusé par la base
    with pytest.raises(Exception):  # noqa: B017
        await importer_carte(c, resto.a, carte, "caisse")


# --------------------------------------------------------------------------- #
# Lecture de la carte
# --------------------------------------------------------------------------- #


async def test_la_disponibilite_marque_ce_qui_est_hors_de_sa_plage(resto):
    """Lot 12 (PRX1) : ce qui est hors de sa plage à ce moment n'est plus supprimé de la carte, il est marqué (``indisponible`` : la plage de la donnée) pour que la cuisine
    le refuse avec la raison ; la plage se lit au moment que le geste regarde."""
    c = resto.c
    carte = _carte()
    marg = _produit(carte, "P-PIZZAS-TOMATE-MARGHE")
    marg["declinaisons"][1]["disponibilite"] = {"jours": [1, 2, 3, 4, 5], "heures": [["11:00", "14:30"]]}  # Mega : en semaine, le midi
    await importer_carte(c, resto.a, carte, "caisse")
    formule = next(f for f in CARTE["formules"] if f.get("disponibilite"))  # la formule du midi
    noms = lambda cr: {d["nom"] for p in cr["produits"] if p["id"] == marg["id"] for d in p["declinaisons"] if d["indisponible"] is None}  # noqa: E731
    servie = lambda cr: next(f for f in cr["formules"] if f["id"] == formule["id"])["indisponible"] is None  # noqa: E731
    assert noms(await carte_du_restaurant(c, resto.a, JEUDI_MIDI)) == {"Normale", "Mega"}
    assert servie(await carte_du_restaurant(c, resto.a, JEUDI_MIDI))
    soir = JEUDI_MIDI.replace(hour=19)  # le soir : plus de Mega, plus de formule du midi
    cr = await carte_du_restaurant(c, resto.a, soir)
    assert noms(cr) == {"Normale"} and not servie(cr)
    dimanche = datetime(2026, 11, 15, 12, 0, tzinfo=PARIS)
    assert noms(await carte_du_restaurant(c, resto.a, dimanche)) == {"Normale"}
    # sans moment : l'heure de l'organisation (jeudi midi)
    assert noms(await carte_du_restaurant(c, resto.a)) == {"Normale", "Mega"}
    # un moment en UTC dit la même chose que le même moment à Paris
    assert noms(await carte_du_restaurant(c, resto.a, JEUDI_MIDI.astimezone(ZoneInfo("UTC")))) == {"Normale", "Mega"}
    # un produit dont TOUTES les déclinaisons sont hors plage est marqué hors plage (avec la plage de sa première déclinaison)
    await c.execute("UPDATE mark.resto_declinaison SET disponibilite = '{\"heures\": [[\"03:00\", \"04:00\"]]}' WHERE site_id = $1 AND produit_ref = $2", resto.a, marg["id"])
    produit = next(p for p in (await carte_du_restaurant(c, resto.a, JEUDI_MIDI))["produits"] if p["id"] == marg["id"])
    assert produit["indisponible"] == {"heures": [["03:00", "04:00"]]}


async def test_enseigne_exception_et_cloisonnement(resto):
    c = resto.c
    # la carte d'enseigne (écrite à la main, site_id vide), commune aux deux établissements
    await c.execute("INSERT INTO mark.resto_categorie (site_id, portee, ref, nom, source) VALUES (NULL, 'enseigne', 'boissons', 'Boissons', 'mark')")
    await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom, categorie_ref, source) VALUES (NULL, 'enseigne', 'cola', 'Cola', 'boissons', 'mark')")
    await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom, categorie_ref, source) VALUES (NULL, 'enseigne', 'eau', 'Eau', 'boissons', 'mark')")
    for etab in (resto.a, resto.b):
        assert {p["id"] for p in (await carte_du_restaurant(c, etab))["produits"]} == {"cola", "eau"}
    # exception chez A : renomme le cola ; chez A encore : masque l'eau
    await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom, source) VALUES ($1, 'exception', 'cola', 'Cola 33 cl', 'portail')", resto.a)
    await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom, masque, source) VALUES ($1, 'exception', 'eau', 'Eau', true, 'portail')", resto.a)
    a = {p["id"]: p["nom"] for p in (await carte_du_restaurant(c, resto.a))["produits"]}
    b = {p["id"]: p["nom"] for p in (await carte_du_restaurant(c, resto.b))["produits"]}
    assert a == {"cola": "Cola 33 cl"} and b == {"cola": "Cola", "eau": "Eau"}
    # une carte propre à A ne se voit pas chez B
    await importer_carte(c, resto.a, CARTE, "caisse")
    assert len((await carte_du_restaurant(c, resto.a))["produits"]) == 1 + len(CARTE["produits"])
    assert {p["id"] for p in (await carte_du_restaurant(c, resto.b))["produits"]} == {"cola", "eau"}
    # un établissement qui n'existe pas
    with pytest.raises(LookupError):
        await carte_du_restaurant(c, 999999)


async def test_la_version_de_la_carte_monte_a_chaque_changement_pas_a_une_rupture(resto):
    c = resto.c
    assert await version_carte(c, resto.a) == 0
    await importer_carte(c, resto.a, _carte(), "caisse")
    v = await version_carte(c, resto.a)
    assert v >= 1 and await version_carte(c, resto.b) == 0
    await c.execute("UPDATE mark.resto_produit SET nom = 'X' WHERE site_id = $1 AND ref = 'P-PIZZAS-TOMATE-MARGHE'", resto.a)
    assert await version_carte(c, resto.a) == v + 1
    await poser_rupture(c, resto.a, "PIZ-MARGHERITA-NORMALE", False, None, "portail")
    assert await version_carte(c, resto.a) == v + 1
    assert (await carte_du_restaurant(c, resto.a))["version"] == v + 1


# --------------------------------------------------------------------------- #
# Ruptures
# --------------------------------------------------------------------------- #


async def test_les_ruptures_sont_actives_au_bon_moment_et_cloisonnees(resto):
    c = resto.c
    await importer_carte(c, resto.a, CARTE, "caisse")
    code = "PIZ-MARGHERITA-NORMALE"
    # un code inconnu, ou celui d'un autre établissement : introuvable ; une fin passée : argument invalide
    assert (await poser_rupture(c, resto.a, "N-IMPORTE-QUOI", False, None, "agent")).statut == "INTROUVABLE"
    assert (await poser_rupture(c, resto.b, code, False, None, "agent")).statut == "INTROUVABLE"  # B n'a pas cette carte
    assert (await poser_rupture(c, resto.a, code, False, JEUDI_MIDI - timedelta(hours=1), "agent")).statut == "ARGUMENT_INVALIDE"
    assert (await poser_rupture(c, resto.a, code, False, JEUDI_MIDI.replace(tzinfo=None) + timedelta(hours=1), "agent")).statut == "ARGUMENT_INVALIDE"
    assert (await poser_rupture(c, resto.a, code, False, None, "inconnue")).statut == "ARGUMENT_INVALIDE"
    # rupture jusqu'à 15 h : active à midi, finie à 16 h
    fin = JEUDI_MIDI.replace(hour=15)
    assert (await poser_rupture(c, resto.a, code, False, fin, "agent")).statut == "OK"
    actives = await ruptures_du_restaurant(c, resto.a)
    assert [r["code_caisse"] for r in actives] == [code] and actives[0]["disponible"] is False and actives[0]["source"] == "agent"
    assert await ruptures_du_restaurant(c, resto.a, JEUDI_MIDI.replace(hour=16)) == []
    # une rupture qui commence plus tard ne bloque pas une commande planifiée AVANT elle
    assert await ruptures_du_restaurant(c, resto.a, JEUDI_MIDI - timedelta(days=1)) == []
    assert await ruptures_du_restaurant(c, resto.b) == []  # cloisonnement
    # la lever (disponible) : plus de rupture ; reposer : la dernière écriture gagne
    assert (await poser_rupture(c, resto.a, code, True, None, "portail")).statut == "OK"
    assert await ruptures_du_restaurant(c, resto.a) == []
    assert await c.fetchval("SELECT count(*) FROM mark.resto_rupture WHERE site_id = $1", resto.a) == 1
    # le journal dit qui a posé la rupture
    ligne = await c.fetchrow("SELECT source FROM mark.resto_journal WHERE objet = 'resto_rupture' ORDER BY id DESC LIMIT 1")
    assert ligne["source"] == "portail"
    # une option est aussi une référence permise
    assert (await poser_rupture(c, resto.a, "SAU-KET", False, None, "caisse")).statut == "OK"


# --------------------------------------------------------------------------- #
# État combiné
# --------------------------------------------------------------------------- #


async def _reglage(c, etab, type_, **colonnes):
    cles = ", ".join(["site_id", "type", *colonnes])
    marques = ", ".join(f"${i + 1}" for i in range(2 + len(colonnes)))
    await c.execute(f"INSERT INTO mark.resto_reglage_type ({cles}) VALUES ({marques}) ON CONFLICT (site_id, type) DO NOTHING", etab, type_, *colonnes.values())
    for cle, valeur in colonnes.items():
        await c.execute(f"UPDATE mark.resto_reglage_type SET {cle} = $3 WHERE site_id = $1 AND type = $2", etab, type_, valeur)


async def test_l_etat_combine_prend_le_plus_prudent_et_la_caisse_pour_ce_qu_elle_porte(resto):
    c, a = resto.c, resto.a
    # ouvert à midi, un jeudi : le délai annoncé du type
    await _reglage(c, a, "emporter", delai_annonce=20)
    e = await etat_combine(c, a, "emporter", JEUDI_MIDI)
    assert e == {"ouvert": True, "raison": None, "reprise": None, "delai_minutes": 20, "prochaine_ouverture": None}
    # hors des horaires (16 h) : fermé, rouvre à 18 h le même jour
    e = await etat_combine(c, a, "emporter", JEUDI_MIDI.replace(hour=16))
    assert (e["ouvert"], e["raison"], e["prochaine_ouverture"]) == (False, "ferme_horaires", JEUDI_MIDI.replace(hour=18))
    # un établissement sans horaire écrit n'est pas fermé par les horaires
    assert (await etat_combine(c, resto.b, "emporter", JEUDI_MIDI.replace(hour=3)))["ouvert"] is True
    # minutes ajoutées jusqu'à une heure : comptées avant, plus après
    await _reglage(c, a, "emporter", minutes_ajoutees=15, ajout_jusqu_a=JEUDI_MIDI.replace(hour=13))
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI))["delai_minutes"] == 35
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI.replace(hour=13, minute=30)))["delai_minutes"] == 20
    # la caisse porte son temps de préparation : il prime sur celui de la fiche ; débordée : minutes en plus
    await c.execute("INSERT INTO mark.resto_etat_caisse (site_id, mode, minutes_en_plus, temps_preparation) VALUES ($1, 'deborde', 10, 25)", a)
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI.replace(hour=13, minute=30)))["delai_minutes"] == 35  # 25 (caisse) + 10
    assert (await etat_caisse(c, a))["mode"] == "deborde" and await etat_caisse(c, resto.b) is None
    # caisse en pause jusqu'à 12 h 30 : fermé, reprise dite ; plus tard, rouvert
    reprise = JEUDI_MIDI.replace(minute=30)
    await c.execute("UPDATE mark.resto_etat_caisse SET mode = 'pause', reprise = $2 WHERE site_id = $1", a, reprise)
    e = await etat_combine(c, a, "emporter", JEUDI_MIDI)
    assert (e["ouvert"], e["raison"], e["reprise"]) == (False, "caisse_pause", reprise)
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI.replace(minute=45)))["ouvert"] is True
    await c.execute("DELETE FROM mark.resto_etat_caisse WHERE site_id = $1", a)
    # fiche forcée fermée : la plus parlante gagne ; rouverte (OUVERT) : passe outre les horaires
    await c.execute("UPDATE mark.site SET etat_force = 'FERME', etat_force_jusqu_a = '2026-11-12 18:00' WHERE id = $1", a)
    e = await etat_combine(c, a, "emporter", JEUDI_MIDI)
    assert (e["raison"], e["reprise"]) == ("ferme_force", JEUDI_MIDI.replace(hour=18))
    await c.execute("UPDATE mark.site SET etat_force = 'OUVERT', etat_force_jusqu_a = NULL WHERE id = $1", a)
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI.replace(hour=16)))["ouvert"] is True
    await c.execute("UPDATE mark.site SET etat_force = NULL WHERE id = $1", a)
    # fermeture exceptionnelle
    await c.execute("INSERT INTO mark.fermeture (site_id, du, au, motif) VALUES ($1, $2, $3, 'travaux')", a, JEUDI_MIDI - timedelta(hours=1), JEUDI_MIDI + timedelta(hours=1))
    e = await etat_combine(c, a, "emporter", JEUDI_MIDI)
    assert (e["raison"], e["reprise"]) == ("fermeture_exceptionnelle", JEUDI_MIDI + timedelta(hours=1))
    await c.execute("DELETE FROM mark.fermeture WHERE site_id = $1", a)
    # un type fermé, en pause, ou terminé pour la journée : sans toucher aux autres types
    await _reglage(c, a, "livraison", fin_par_jour='{"4": "11:30"}')
    e = await etat_combine(c, a, "livraison", JEUDI_MIDI)
    assert (e["ouvert"], e["raison"]) == (False, "livraison_terminee")
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI))["ouvert"] is True
    await _reglage(c, a, "sur_place", ouvert=False)
    assert (await etat_combine(c, a, "sur_place", JEUDI_MIDI))["raison"] == "type_ferme"
    await _reglage(c, a, "reservation", pause_jusqu_a=JEUDI_MIDI.replace(minute=40))
    e = await etat_combine(c, a, "reservation", JEUDI_MIDI)
    assert (e["raison"], e["reprise"]) == ("pause_type", JEUDI_MIDI.replace(minute=40))
    # arguments : type inconnu, moment sans fuseau, établissement inconnu
    with pytest.raises(ValueError):
        await etat_combine(c, a, "banquet", JEUDI_MIDI)
    with pytest.raises(ValueError):
        await etat_combine(c, a, "emporter", JEUDI_MIDI.replace(tzinfo=None))
    with pytest.raises(LookupError):
        await etat_combine(c, 999999, "emporter", JEUDI_MIDI)
