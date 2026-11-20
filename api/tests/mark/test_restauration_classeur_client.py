"""[.mark] Module Restauration, lot 2 : les clients, la recherche dans la carte, la capacité (couche d'accès).

| Test | Ce qu'il prouve |
|---|---|
| fiche du client | rendue par numéro, seulement pour CET établissement ; expirée après la durée de conservation ; repli sur la caisse seulement quand la fiche manque |
| consignes | écrites, jamais en double, les 10 dernières ; une allergie est refusée (elle va sur la commande) ; relues à l'appel suivant ; cloisonnées |
| recherche | retenu quand un seul élément correspond exactement ; ambigu quand deux ; JAMAIS de faux sûr sur une faute ; synonymes actifs après relecture seulement ; l'autre établissement ne voit pas la carte |
| capacité | un créneau libre tant qu'une table tient le groupe ; occupé quand tout est pris, libre à la fin de la réservation ; tables assemblées ; groupe trop grand ; durée par taille ; réservation annulée libère |
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge, recherche_liste
from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_client import (
    chercher_dans_la_liste,
    client_par_numero,
    disponibilites_capacite,
    ecrire_consigne_client,
)
from api.db.bases_clients.restauration_commande import enregistrer_commande
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, JEUDI_MIDI

PARIS = ZoneInfo("Europe/Paris")
TEL = "+33612345678"
VENDREDI = date(2026, 11, 13)


@pytest.fixture
async def resto(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        ids = {}
        for cle in ("a", "b"):
            ids[cle] = await c.fetchval(
                "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise RETURNING id", cle
            )
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            yield SimpleNamespace(c=c, a=ids["a"], b=ids["b"], base=base_prete)
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# Clients et consignes
# --------------------------------------------------------------------------- #


async def test_la_fiche_du_client_est_cloisonnee_expire_et_le_repli_ne_sert_que_si_elle_manque(resto):
    c, a, b = resto.c, resto.a, resto.b
    assert await client_par_numero(c, a, TEL) is None
    assert (await ecrire_consigne_client(c, a, TEL, "Sonnez à l'interphone")).statut == "OK"
    fiche = await client_par_numero(c, a, TEL)
    assert fiche["telephone"] == TEL and fiche["consignes"] == ["Sonnez à l'interphone"] and fiche["nb_commandes"] == 0
    assert await client_par_numero(c, b, TEL) is None  # l'autre établissement n'a pas cette fiche
    assert await client_par_numero(c, a, "0612345678") is None and await client_par_numero(c, a, "") is None
    appels = []

    async def repli(numero):
        appels.append(numero)
        return {"telephone": numero, "prenom": "Caisse"}

    assert (await client_par_numero(c, a, TEL, repli_prise=repli))["consignes"] == ["Sonnez à l'interphone"] and appels == []
    assert (await client_par_numero(c, b, TEL, repli_prise=repli))["prenom"] == "Caisse" and appels == [TEL]
    # durée de conservation réglable (T-15) : 12 mois par défaut, 1 mois ici
    with horloge.remplacer(resto.base, JEUDI_MIDI + timedelta(days=200)):
        assert await client_par_numero(c, a, TEL) is not None
    await c.execute("INSERT INTO mark.resto_reglage (site_id, conservation_client_mois) VALUES ($1, 1)", a)
    with horloge.remplacer(resto.base, JEUDI_MIDI + timedelta(days=45)):
        assert await client_par_numero(c, a, TEL) is None
    with horloge.remplacer(resto.base, JEUDI_MIDI + timedelta(days=20)):
        assert await client_par_numero(c, a, TEL) is not None


async def test_les_consignes_sont_uniques_bornees_sans_allergie_et_relues(resto):
    c, a, b = resto.c, resto.a, resto.b
    assert (await ecrire_consigne_client(c, a, TEL, "Pas de sel")).statut == "OK"
    assert (await ecrire_consigne_client(c, a, TEL, "  pas de SEL ")).statut == "DEJA_FAIT"  # jamais deux fois la même
    for refusee in ("Il est allergique aux arachides", "intolérance au gluten", "cœliaque", ""):
        r = await ecrire_consigne_client(c, a, TEL, refusee)
        assert r.statut == "ARGUMENT_INVALIDE", refusee
    assert (await ecrire_consigne_client(c, a, TEL, "x" * 201)).manque == "consigne"
    assert (await ecrire_consigne_client(c, a, "pas-un-numero", "Pas de sel")).manque == "telephone"
    for i in range(12):
        await ecrire_consigne_client(c, a, TEL, f"Consigne {i}")
    consignes = (await client_par_numero(c, a, TEL))["consignes"]
    assert len(consignes) == 10 and consignes[-1] == "Consigne 11" and "Pas de sel" not in consignes
    assert await client_par_numero(c, b, TEL) is None
    assert await c.fetchval("SELECT count(*) FROM mark.resto_client WHERE site_id = $1", b) == 0
    # la fiche créée par une commande garde ses consignes
    await importer_carte(c, a, CARTE, "caisse")
    for jour in range(1, 8):
        await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, '11:00', '14:00')", a, jour)
    r = await enregistrer_commande(
        c, a, {"mode": "emporter", "client": {"telephone": TEL, "prenom": "Alice"}, "lignes": [{"code_caisse": "BOI-COCA-COLA-33-CL"}],
               "paiement": {"moyens": [{"moyen": "carte", "montant": 200}]}}, "relu",
    )
    assert r.statut == "ENREGISTREE"
    fiche = await client_par_numero(c, a, TEL)
    assert fiche["prenom"] == "Alice" and fiche["nb_commandes"] == 1 and fiche["consignes"][-1] == "Consigne 11" and fiche["derniere_commande_id"] == r.faits["numero"]


# --------------------------------------------------------------------------- #
# Recherche dans la carte
# --------------------------------------------------------------------------- #


async def test_la_recherche_ne_se_trompe_jamais_de_produit(resto):  # lot 4 : le vrai moteur (couches, sons) remplace le moteur exact du lot 2
    c, a = resto.c, resto.a
    await importer_carte(c, a, CARTE, "caisse")
    r = await chercher_dans_la_liste(c, "carte", "margherita", a)
    assert (r.statut, r.faits["retenu"]) == ("RETENU", "P-PIZZAS-TOMATE-MARGHE")
    for dit in ("Margherita", "MARGHERITA !", "margheritas", "  margherita  "):
        assert (await chercher_dans_la_liste(c, "carte", dit, a)).faits["retenu"] == "P-PIZZAS-TOMATE-MARGHE", dit
    assert (await chercher_dans_la_liste(c, "carte", "Coca-Cola", a)).statut == "RETENU"
    # une faute, un nom incomplet, un nom en trop, un autre produit : JAMAIS retenu (aucun faux sûr) ; au mieux, une question
    for faux in ("margarita", "marghe", "pizza", "regina margherita", "", "   "):
        r = await chercher_dans_la_liste(c, "carte", faux, a)
        assert r.statut in ("AMBIGU", "INTROUVABLE") and r.faits["retenu"] is None, faux
    for vide in ("", "   ", "pizza"):
        assert (await chercher_dans_la_liste(c, "carte", vide, a)).statut == "INTROUVABLE", vide
    r = await chercher_dans_la_liste(c, "carte", "margarita", a)
    assert r.statut == "AMBIGU" and r.faits["candidats"][0]["id"] == "P-PIZZAS-TOMATE-MARGHE"  # le plus proche est proposé, à confirmer
    # deux éléments du même nom : ambigu, avec les choix
    await c.execute("INSERT INTO mark.resto_produit (site_id, ref, nom, source) VALUES ($1, 'P-DOUBLON', 'Margherita', 'portail')", a)
    r = await chercher_dans_la_liste(c, "carte", "margherita", a)
    assert r.statut == "AMBIGU" and {x["id"] for x in r.faits["candidats"]} == {"P-PIZZAS-TOMATE-MARGHE", "P-DOUBLON"}
    assert r.suggestion.count("Margherita") == 2 and " ou " in r.suggestion
    await c.execute("DELETE FROM mark.resto_produit WHERE ref = 'P-DOUBLON'")
    # synonyme : actif seulement après relecture (T-14)
    await c.execute("INSERT INTO mark.resto_surcouche (site_id, objet, ref, synonymes, synonymes_a_relire) VALUES ($1, 'produit', 'P-PIZZAS-TOMATE-MARGHE', '{marguerite}', true)", a)
    assert (await chercher_dans_la_liste(c, "carte", "marguerite", a)).faits["retenu"] is None
    await c.execute("UPDATE mark.resto_surcouche SET synonymes_a_relire = false WHERE site_id = $1", a)
    assert (await chercher_dans_la_liste(c, "carte", "marguerite", a)).faits["retenu"] == "P-PIZZAS-TOMATE-MARGHE"
    # le même organisation, un autre établissement : sa propre carte, jamais celle-ci
    assert (await chercher_dans_la_liste(c, "carte", "margherita", resto.b)).statut == "INTROUVABLE"
    # une formule se retrouve ; une liste inconnue aussi est dite
    assert (await chercher_dans_la_liste(c, "carte", "Menu Entreprise", a)).faits["retenu"] == "F-MENU-ENTREPRISE"
    r = await chercher_dans_la_liste(c, "marques", "x", a)
    assert (r.statut, r.faits["raison"]) == ("INTROUVABLE", "liste_inconnue")


async def test_le_moteur_de_recherche_se_remplace_sans_changer_la_forme(resto):
    await importer_carte(resto.c, resto.a, CARTE, "caisse")
    avant = recherche_liste._moteur
    try:
        recherche_liste.poser_moteur(lambda elements, texte: {"statut": "RETENU", "retenu": elements[0].id, "candidats": []})
        assert (await chercher_dans_la_liste(resto.c, "carte", "n'importe quoi", resto.a)).statut == "RETENU"
    finally:
        recherche_liste.poser_moteur(avant)


# --------------------------------------------------------------------------- #
# Capacité
# --------------------------------------------------------------------------- #


async def _salle(resto):
    c, a = resto.c, resto.a
    salle = await c.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'Salle') RETURNING id", a)
    tables = {}
    for nom, mini, maxi in (("T1", 2, 4), ("T2", 2, 2), ("T3", 4, 8)):
        tables[nom] = await c.fetchval("INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, $3, $4, $5) RETURNING id", a, salle, nom, mini, maxi)
    await c.execute("UPDATE mark.resto_table SET assemblable_avec = $2 WHERE id = $1", tables["T3"], [tables["T1"]])
    await c.execute("UPDATE mark.resto_table SET assemblable_avec = $2 WHERE id = $1", tables["T1"], [tables["T3"]])
    await c.execute("INSERT INTO mark.resto_service (site_id, nom, debut, fin, pas_minutes) VALUES ($1, 'midi', '12:00', '13:30', 30)", a)
    await c.execute("INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, 4, 60), ($1, 5, 12, 90)", a)
    await c.execute("INSERT INTO mark.resto_regle_reservation (site_id, delai_minimal, jours_a_l_avance) VALUES ($1, 0, 30)", a)
    return tables


async def _reserver(c, a, debut, couverts, tables=(), duree=60, statut="confirmee"):
    await c.execute(
        "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, table_ids, statut) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6)",
        a, debut, duree, couverts, list(tables), statut,
    )


def _heures(r):
    return [x["debut"].astimezone(PARIS).strftime("%H:%M") for x in r.faits["creneaux"]]


async def test_la_capacite_donne_les_creneaux_ou_le_groupe_tient(resto):
    c, a, b = resto.c, resto.a, resto.b
    t = await _salle(resto)
    midi = datetime(2026, 11, 13, 12, 0, tzinfo=PARIS)
    r = await disponibilites_capacite(c, a, VENDREDI, 2)
    assert r.statut == "OK" and _heures(r) == ["12:00", "12:30", "13:00"] and r.faits["duree_minutes"] == 60
    assert r.faits["creneaux"][0]["fin"] == midi + timedelta(minutes=60)
    # le même établissement, mais pas les mêmes tables : B n'a rien
    # lot 7 (E4, D49) : ni table ni capacité, c'est un manque (``capacite``), jamais « complet » ; sens aussi tenu par partie_1/test_l07_sans_table.py::test_ni_table_ni_capacite_c_est_un_manque_jamais_complet
    assert (await disponibilites_capacite(c, b, VENDREDI, 2, duree_minutes=60)).manque == "capacite"
    assert (await disponibilites_capacite(c, b, VENDREDI, 2)).manque == "duree"  # B n'a aucune règle de durée
    # un jour où le service n'a pas lieu
    await c.execute("UPDATE mark.resto_service SET jours = '{1,2,3,4}' WHERE site_id = $1", a)
    assert _heures(await disponibilites_capacite(c, a, VENDREDI, 2)) == []
    await c.execute("UPDATE mark.resto_service SET jours = '{1,2,3,4,5,6,7}' WHERE site_id = $1", a)
    # tout est pris à 12 h : le créneau de 12 h n'est plus offert ; 13 h l'est (la réservation finit à 13 h)
    for nom in ("T1", "T2", "T3"):
        await _reserver(c, a, midi, 2, [t[nom]])
    assert _heures(await disponibilites_capacite(c, a, VENDREDI, 2)) == ["13:00"]
    # 12 h 30 aussi est pris (chevauche) ; une réservation annulée libère
    await c.execute("UPDATE mark.resto_reservation SET statut = 'annulee' WHERE site_id = $1 AND $2 = ANY(table_ids)", a, t["T2"])
    r = await disponibilites_capacite(c, a, VENDREDI, 2)
    assert "12:00" in _heures(r) and "12:30" in _heures(r)  # la T2 est libre
    # une table trop petite ne reçoit pas un groupe de 3 : seule la T1 (2 à 4) et la T3 (4 à 8) conviennent, toutes prises à 12 h
    assert _heures(await disponibilites_capacite(c, a, VENDREDI, 3)) == ["13:00"]


async def test_tables_assemblees_groupe_trop_grand_duree_et_reglages(resto):
    c, a = resto.c, resto.a
    await _salle(resto)
    # 10 personnes : la T3 (8) assemblée à la T1 (4) ; 12 : T3 + T1 = 12 ; durée 90 min (groupe de 5 à 12)
    r = await disponibilites_capacite(c, a, VENDREDI, 10)
    assert _heures(r) == ["12:00", "12:30", "13:00"] and r.faits["duree_minutes"] == 90
    assert _heures(await disponibilites_capacite(c, a, VENDREDI, 13, duree_minutes=90)) == []  # personne ne tient
    assert (await disponibilites_capacite(c, a, VENDREDI, 13, duree_minutes=90)).faits["complet"] is True
    # une durée donnée l'emporte sur la règle
    assert (await disponibilites_capacite(c, a, VENDREDI, 2, duree_minutes=120)).faits["duree_minutes"] == 120
    # groupe trop grand pour le téléphone : refusé, on appelle le restaurant
    await c.execute("UPDATE mark.resto_regle_reservation SET couverts_max_groupe = 6 WHERE site_id = $1", a)
    r = await disponibilites_capacite(c, a, VENDREDI, 7)
    assert (r.statut, r.faits["detail"]) == ("REFUSEE", "groupe_trop_grand")
    # plafond de couverts par créneau
    await c.execute("UPDATE mark.resto_regle_reservation SET couverts_max_creneau = 4 WHERE site_id = $1", a)
    await _reserver(c, a, datetime(2026, 11, 13, 12, 0, tzinfo=PARIS), 3, [])
    assert "12:00" not in _heures(await disponibilites_capacite(c, a, VENDREDI, 2))
    # un délai minimal : rien avant now + délai (jeudi midi + 26 h = vendredi 14 h : plus rien dans ce service)
    await c.execute("UPDATE mark.resto_regle_reservation SET delai_minimal = 60 * 26 WHERE site_id = $1", a)
    assert _heures(await disponibilites_capacite(c, a, VENDREDI, 2)) == []
    # jusqu'à combien de jours à l'avance
    await c.execute("UPDATE mark.resto_regle_reservation SET delai_minimal = 0, jours_a_l_avance = 2 WHERE site_id = $1", a)
    assert _heures(await disponibilites_capacite(c, a, date(2026, 11, 20), 2)) == []
    # pause du type « reservation » et fermeture exceptionnelle
    await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, pause_jusqu_a) VALUES ($1, 'reservation', $2)", a, datetime(2026, 11, 13, 12, 45, tzinfo=PARIS))
    assert _heures(await disponibilites_capacite(c, a, VENDREDI, 2)) == ["13:00"]
    await c.execute("UPDATE mark.resto_reglage_type SET ouvert = false WHERE site_id = $1 AND type = 'reservation'", a)
    assert (await disponibilites_capacite(c, a, VENDREDI, 2)).faits["raison"] == "type_ferme"
    # arguments
    assert (await disponibilites_capacite(c, a, VENDREDI, 0)).manque == "couverts"
    await c.execute("DELETE FROM mark.resto_duree_groupe WHERE site_id = $1", a)
    assert (await disponibilites_capacite(c, a, VENDREDI, 2)).manque == "duree"
