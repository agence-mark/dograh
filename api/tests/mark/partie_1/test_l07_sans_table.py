"""[.mark] Chantier Partie 1, lot 7 (complément, ordre d'Evan du 19/11 soir) : la réservation sans plan ni tables.

La salle se règle en trois niveaux : un formulaire (couverts présents en même temps, durée d'un repas par taille de groupe), une liste de tables
facultative, un plan facultatif. Sans table, l'agent accepte ou refuse sur la seule capacité du formulaire ; jamais « complet » à un restaurant vide.

| Ligne | Exigence | Test |
|---|---|---|
| L07-20 | E1 : sans table, la capacité du créneau vient du formulaire | des créneaux sont proposés ; 38 présents sur 40 : le groupe de 4 est refusé |
| L07-21 | E1 : les couverts comptent PRÉSENTS EN MÊME TEMPS sur la durée du repas | deux groupes qui se chevauchent s'additionnent, ceux qui se suivent non |
| L07-22 | E1 : le plafond d'arrivées par créneau reste en plus, inchangé | capacité 40, arrivées 6 : le 7e couvert au même créneau est refusé |
| L07-23 | E2 : ni table ni capacité : INCOMPLETE (``capacite``), jamais « complet » | recherche, réservation, modification ; avec des tables, rien ne change |
| L07-24 | E2 : à la porte, le manque est un refus du métier à dire, pas une case à remplir | la fiche rend ``capacite_non_reglee`` sans « complet » |
| L07-25 | E3 : une réservation sans table occupe la capacité ; ajouter des tables ensuite ne casse rien | les disponibilités restent justes avant et après |
| L07-26 | E4 : le contrat du modèle ne change pas, aucun mot de table dit | dans les trois niveaux, le retour ne porte ni table ni salle |
| L07-28 | Migration 041 | monte, se descend (rejouable), remonte ; la colonne va et vient, rien d'autre ne bouge |
| L07-27 | La salle par défaut se crée à l'écriture d'une liste de tables sans salle | une seule salle, rien d'écrasé |
"""

from __future__ import annotations

import uuid
from pathlib import Path
from datetime import date, datetime, timedelta

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.restauration_reservation import capacite_du_jour, creer_reservation, modifier_reservation
from api.db.bases_clients.restauration_salle_ecran import ecrire_des_tables
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_reservation import PARIS, SAMEDI_20H, TEL, demande, salle  # noqa: F401

SAMEDI = date(2026, 11, 14)


async def _sans_table(salle, capacite: int | None = 40, par_creneau: int | None = None) -> None:
    """La salle du test sans aucune table : le niveau 1 seul (formulaire)."""
    await salle.c.execute("DELETE FROM mark.resto_table WHERE site_id = $1", salle.a)
    await salle.c.execute(
        "UPDATE mark.resto_regle_reservation SET couverts_simultanes = $2, couverts_max_creneau = $3 WHERE site_id = $1", salle.a, capacite, par_creneau
    )


async def _present(salle, couverts: int, debut: datetime = SAMEDI_20H, minutes: int = 90) -> None:
    """Des couverts déjà réservés, sans table (le chemin sans affectation)."""
    await salle.c.execute(
        "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, telephone, prenom, table_ids, cree_par, cree_le, maj_le) "
        "VALUES ($1, $2, $3, $4, $5, $6, 'Déjà', '{}', 'portail', now(), now())",
        uuid.uuid4(), salle.a, debut, minutes, couverts, TEL,
    )


def _heures(r) -> list[str]:
    return [c["debut"].astimezone(PARIS).strftime("%H:%M") for c in r.faits["creneaux"]]


# --------------------------------------------------------------------------- L07-20 : E1


async def test_sans_table_la_capacite_du_formulaire_donne_des_creneaux(salle):
    await _sans_table(salle, 40)
    r = await capacite_du_jour(salle.c, salle.a, SAMEDI, 4)
    assert r.statut == "OK" and not r.faits["complet"], r
    assert "20:00" in _heures(r)


async def test_sans_table_38_presents_sur_40_le_groupe_de_4_est_refuse(salle):
    await _sans_table(salle, 40)
    await _present(salle, 38)
    assert "20:00" not in _heures(await capacite_du_jour(salle.c, salle.a, SAMEDI, 4))
    refus = await creer_reservation(salle.c, salle.a, demande(couverts=4))
    assert refus.statut == "REFUSEE" and refus.faits["detail"] == "complet", refus
    assert (await creer_reservation(salle.c, salle.a, demande(couverts=2))).statut == "ENREGISTREE"   # 38 + 2 = 40 : la borne tient


# --------------------------------------------------------------------------- L07-21 : E1, présents en même temps


async def test_les_couverts_comptent_presents_en_meme_temps_sur_la_duree_du_repas(salle):
    await _sans_table(salle, 40)
    await _present(salle, 20, SAMEDI_20H - timedelta(minutes=60))    # 19 h à 20 h 30
    await _present(salle, 20, SAMEDI_20H)                            # 20 h à 21 h 30 : 40 présents entre 20 h et 20 h 30
    heures = _heures(await capacite_du_jour(salle.c, salle.a, SAMEDI, 2))
    assert "19:30" not in heures and "20:00" not in heures and "20:15" not in heures      # un repas de 90 min touche le pic de 40
    assert "21:30" in heures and "19:00" not in heures                                    # 19 h : 20 + 20 présents à 20 h, le repas les croise
    # deux groupes qui se SUIVENT ne s'additionnent pas : 20 h 30 est libre pour 6 (le premier part, 20 restent) ; 20 h reste refusé (40 + 6)
    six = _heures(await capacite_du_jour(salle.c, salle.a, SAMEDI, 6))
    assert "20:30" in six and "20:00" not in six


# --------------------------------------------------------------------------- L07-22 : E1, le plafond d'arrivées reste


async def test_le_plafond_d_arrivees_par_creneau_reste_en_plus(salle):
    await _sans_table(salle, 40, par_creneau=6)
    await _present(salle, 6)                                                 # 6 arrivées à 20 h
    assert "20:00" not in _heures(await capacite_du_jour(salle.c, salle.a, SAMEDI, 2))
    assert "20:15" in _heures(await capacite_du_jour(salle.c, salle.a, SAMEDI, 2))       # 6 présents sur 40, l'arrivée de 20 h 15 est libre


# --------------------------------------------------------------------------- L07-23 : E2


async def test_ni_table_ni_capacite_c_est_un_manque_jamais_complet(salle):
    await _sans_table(salle, None)
    r = await capacite_du_jour(salle.c, salle.a, SAMEDI, 4)
    assert (r.statut, r.manque) == ("INCOMPLETE", "capacite"), r
    r = await creer_reservation(salle.c, salle.a, demande(couverts=4))
    assert (r.statut, r.manque) == ("INCOMPLETE", "capacite"), r
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 0


async def test_modifier_sans_table_ni_capacite_est_un_manque_aussi(salle):
    await _sans_table(salle, 40)
    r = await creer_reservation(salle.c, salle.a, demande(couverts=2))
    assert r.statut == "ENREGISTREE", r
    await salle.c.execute("UPDATE mark.resto_regle_reservation SET couverts_simultanes = NULL WHERE site_id = $1", salle.a)
    m = await modifier_reservation(salle.c, salle.a, r.faits["numero"], {"couverts": 3})
    assert (m.statut, m.manque) == ("INCOMPLETE", "capacite"), m


async def test_avec_des_tables_sans_capacite_rien_ne_change(salle):
    r = await capacite_du_jour(salle.c, salle.a, SAMEDI, 4)          # les quatre tables du test, aucune capacité dite
    assert r.statut == "OK" and "20:00" in _heures(r), r


# --------------------------------------------------------------------------- L07-24 : E2 à la porte


async def test_a_la_porte_le_manque_de_capacite_est_un_refus_du_metier_sans_complet(salle, monkeypatch):
    await _sans_table(salle, None)
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("une table pour quatre samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert r["raison"] == "capacite_non_reglee", r
    assert "complet_a_cette_heure" not in str(r) and "complets" not in str(r).lower() and r["statut"] != "ENREGISTREE", r
    assert "manque" not in r and "texte_a_dire" not in r, r                 # ce n'est pas une case que le modèle sait remplir


# --------------------------------------------------------------------------- L07-25 : E3


async def test_une_reservation_sans_table_occupe_la_capacite_puis_les_tables_arrivent(salle):
    await _sans_table(salle, 40)
    assert (await creer_reservation(salle.c, salle.a, demande(couverts=6))).statut == "ENREGISTREE"
    r = await salle.c.fetchrow("SELECT table_ids FROM mark.resto_reservation")
    assert list(r["table_ids"]) == []                                         # sans table : rien d'affecté
    await _present(salle, 30)                                                  # 36 présents : un groupe de 6 ne tient plus à 20 h
    assert "20:00" not in _heures(await capacite_du_jour(salle.c, salle.a, SAMEDI, 6))
    # les tables arrivent : 14 places de tables (2 + 2 + 4 + 6), 36 déjà présents sans table : plus rien de libre à 20 h, libre à 21 h 30
    await ecrire_des_tables(salle.c, salle.a, [{"nom": n, "couverts_min": a, "couverts_max": b} for n, a, b in (("T1", 1, 2), ("T2", 1, 2), ("T3", 2, 4), ("T4", 4, 6))], "test")
    avec = _heures(await capacite_du_jour(salle.c, salle.a, SAMEDI, 2))
    assert "20:00" not in avec and "21:30" in avec, avec


# --------------------------------------------------------------------------- L07-26 : E4


async def test_le_contrat_du_modele_ne_change_pas_et_ne_dit_aucune_table(salle, monkeypatch):
    for niveau in ("formulaire", "liste", "plan"):
        if niveau == "formulaire":
            await _sans_table(salle, 40)
        elif niveau == "liste":
            await ecrire_des_tables(salle.c, salle.a, [{"nom": "T1", "couverts_min": 1, "couverts_max": 6}], "test")
        else:
            await salle.c.execute("UPDATE mark.resto_table SET x = 3, y = 4 WHERE site_id = $1", salle.a)
        essai = EssaiReservation(salle, monkeypatch)
        r = await essai.tour("une table pour quatre samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
        assert r["question"]["type"] == "recapitulatif", (niveau, r)
        r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
        assert r["statut"] == "ENREGISTREE", (niveau, r)
        texte = str(r).lower()
        assert "table" not in texte and "salle" not in texte, (niveau, r)
        await salle.c.execute("DELETE FROM mark.resto_reservation WHERE site_id = $1", salle.a)


# --------------------------------------------------------------------------- L07-27 : la salle par défaut


async def test_une_liste_de_tables_sans_salle_cree_la_salle_par_defaut_une_seule_fois(salle):
    await salle.c.execute("DELETE FROM mark.resto_table WHERE site_id = $1", salle.a)
    await salle.c.execute("DELETE FROM mark.resto_salle WHERE site_id = $1", salle.a)
    await ecrire_des_tables(salle.c, salle.a, [{"nom": "T1", "couverts_min": 1, "couverts_max": 2}], "test")
    await ecrire_des_tables(salle.c, salle.a, [{"nom": "T2", "couverts_min": 2, "couverts_max": 4}], "test")
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_salle WHERE site_id = $1", salle.a) == 1
    assert await salle.c.fetchval("SELECT count(DISTINCT salle_id) FROM mark.resto_table WHERE site_id = $1", salle.a) == 1
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_table WHERE site_id = $1 AND actif", salle.a) == 2


# --------------------------------------------------------------------------- L07-28 : la migration 041 monte, se descend, remonte


async def test_la_migration_041_monte_se_descend_et_remonte(base_prete):
    colonne = "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'mark' AND table_name = 'resto_regle_reservation' AND column_name = 'couverts_simultanes'"
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert await c.fetchval(colonne) == 1 and await c.fetchval("SELECT max(version) FROM mark.schema_version") >= 41
        for _ in range(2):   # descente puis remontée, deux fois (rejouable)
            await descendre_jusqu_a(c, 41)  # lot 12 : les migrations d'après la 041 se descendent d'abord, dans l'ordre inverse
            assert await c.fetchval(colonne) == 0 and await c.fetchval("SELECT count(*) FROM mark.schema_version WHERE version = 41") == 0
            assert 41 in await schema.appliquer_migrations(c)
            assert await c.fetchval(colonne) == 1
    finally:
        await c.close()
