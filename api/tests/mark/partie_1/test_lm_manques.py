"""[.mark] Chantier Partie 1, lot des manques (décision d'Evan du 19/11 soir, reçue de la séance Partie 2) : le délai annoncé par zone de livraison (E5)
et la fin du service pour aujourd'hui (E6), sans changer le contrat avec le modèle (E7). Lignes LM-01 à LM-07 du registre.

Chaque test a été vu rouge sur ``81081df3`` (sans la migration 045 ni ses règles).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from api.db.bases_clients import restauration_carte as carte
from api.db.bases_clients import restauration_temps as temps
from api.db.bases_clients.instantane import instantane_de
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a

PARIS = ZoneInfo("Europe/Paris")
COLONNES_045 = [("resto_zone", "minutes_ajoutees"), ("resto_zone", "ajout_jusqu_a"), ("resto_reglage_type", "fin_aujourd_hui"),
                ("resto_reglage_type", "fin_aujourd_hui_le")]


def _geste(c) -> None:
    """Un nouveau geste : l'état vivant est relu (ce qu'un geste suivant de l'appel verrait)."""
    inst = instantane_de(c)
    if inst is not None:
        inst.nouveau_geste()


async def _zones(e) -> list[dict]:
    return [dict(r) for r in await e.monde.c.fetch("SELECT id, nom, delai FROM mark.resto_zone WHERE site_id = $1 ORDER BY ordre, id", e.monde.a)]


async def _dit(e, zone_id: int, moment: datetime) -> int:
    _geste(e.monde.c)
    return (await temps.annonce_pour(e.monde.c, e.monde.a, "livraison", moment, zone_id))["annonce"].minutes


# --------------------------------------------------------------------------- E5 : minutes ajoutées par zone de livraison


async def test_lm01_minutes_ajoutees_par_zone_avec_leur_jusqu_a(essai_de):
    """LM-01 (E5) : zone de Senlis (30 min) à +0, zone de Chantilly (50 min) à +30 jusqu'à 13 h : l'agent annonce 30 et 80 minutes ; une fois le
    « jusqu'à » passé, 50."""
    e = await essai_de("casa-italia")
    senlis, chantilly = await _zones(e)
    assert (senlis["delai"], chantilly["delai"]) == (30, 50)
    midi = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)
    await e.monde.c.execute("UPDATE mark.resto_zone SET minutes_ajoutees = 30, ajout_jusqu_a = $2 WHERE id = $1", chantilly["id"], midi + timedelta(hours=1))
    assert await _dit(e, senlis["id"], midi) == 30
    assert await _dit(e, chantilly["id"], midi) == 80
    assert await _dit(e, chantilly["id"], midi + timedelta(hours=1, minutes=1)) == 50


async def test_lm02_le_delai_de_zone_s_ajoute_au_reste(essai_de):
    """LM-02 (E5) : le délai dit vaut le délai de la zone + ses minutes + les minutes du type (la puce) + celles d'un soir chargé, comme aujourd'hui ;
    les minutes d'une zone ne touchent jamais une autre zone ni l'emporter."""
    e = await essai_de("casa-italia")
    senlis, chantilly = await _zones(e)
    midi = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)
    await e.monde.c.execute("UPDATE mark.resto_zone SET minutes_ajoutees = 30 WHERE id = $1", chantilly["id"])
    await e.monde.c.execute("UPDATE mark.resto_reglage_type SET minutes_ajoutees = 10 WHERE site_id = $1 AND type = 'livraison'", e.monde.a)
    await e.monde.c.execute(
        "INSERT INTO mark.resto_temps_recurrent (site_id, type, jours, debut, fin, minutes_ajoutees) VALUES ($1, 'livraison', '{4}', '11:00', '14:00', 5)", e.monde.a
    )
    assert await _dit(e, chantilly["id"], midi) == 50 + 30 + 10 + 5
    assert await _dit(e, senlis["id"], midi) == 30 + 10 + 5
    _geste(e.monde.c)
    emporter = await temps.annonce_pour(e.monde.c, e.monde.a, "emporter", midi)
    assert emporter["ajout_minutes"] == 0, emporter


async def test_lm03_les_minutes_de_zone_s_ecrivent_par_la_couche_d_acces(essai_de):
    """LM-03 (E5) : l'écriture passe par la couche d'accès, bornée comme la puce du type (0 à 240), jamais sur la zone d'un autre établissement ; la
    puce du temps rend les minutes de chaque zone et leur « jusqu'à »."""
    e = await essai_de("casa-italia")
    senlis, chantilly = await _zones(e)
    autre = await essai_de("kebab-demo")
    zone_d_un_autre = (await _zones(autre))[0]["id"]
    jusqu_a = datetime(2026, 11, 12, 13, 0, tzinfo=PARIS)
    assert (await temps.ecrire_ajout_de_la_zone(e.monde.c, e.monde.a, chantilly["id"], 30, jusqu_a)).statut == "OK"
    assert (await temps.ecrire_ajout_de_la_zone(e.monde.c, e.monde.a, chantilly["id"], 241)).statut == "ARGUMENT_INVALIDE"
    assert (await temps.ecrire_ajout_de_la_zone(e.monde.c, e.monde.a, zone_d_un_autre, 30)).statut == "INTROUVABLE"
    _geste(e.monde.c)
    puce = await temps.temps_par_type(e.monde.c, e.monde.a, datetime(2026, 11, 12, 12, 0, tzinfo=PARIS))
    par_zone = {z["zone_id"]: z for z in next(t for t in puce["types"] if t["type"] == "livraison")["par_zone"]}
    assert (par_zone[chantilly["id"]]["minutes_ajoutees"], par_zone[chantilly["id"]]["ajout_jusqu_a"]) == (30, jusqu_a)
    assert par_zone[chantilly["id"]]["annonce"]["minutes"] == 80 and par_zone[senlis["id"]]["minutes_ajoutees"] == 0


# --------------------------------------------------------------------------- E6 : fin du service pour aujourd'hui


async def _vendredi_ouvert(e) -> None:
    """Le vendredi de 11 h à 23 h 30 dans les horaires, la fin de fond du vendredi à 22 h, pour l'emporter et la livraison."""
    await e.monde.c.execute("DELETE FROM mark.horaire WHERE site_id = $1 AND jour = 5", e.monde.a)
    await e.monde.c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, 5, '11:00', '23:30')", e.monde.a)
    await e.monde.c.execute(
        "UPDATE mark.resto_reglage_type SET fin_par_jour = '{\"5\": \"22:00\"}' WHERE site_id = $1 AND type IN ('emporter', 'livraison')", e.monde.a
    )


async def _etat(e, type_: str, moment: datetime) -> dict:
    _geste(e.monde.c)
    return await carte.etat_combine(e.monde.c, e.monde.a, type_, moment)


async def test_lm04_fin_d_aujourd_hui_prime_et_s_efface_a_minuit(essai_de):
    """LM-04 (E6) : `fin_par_jour` du vendredi à 22 h, ce soir à 21 h 30 : une commande à 21 h 35 est refusée (`fin_du_jour`) ; le vendredi suivant,
    de nouveau 22 h (la fin d'aujourd'hui ne vaut que son jour, effacée seule à minuit du lieu)."""
    e = await essai_de("casa-italia")
    await _vendredi_ouvert(e)
    vendredi = datetime(2026, 11, 13, 21, 35, tzinfo=PARIS)
    assert (await _etat(e, "emporter", vendredi))["ouvert"] is True  # la règle de fond seule : 22 h
    await e.monde.c.execute(
        "UPDATE mark.resto_reglage_type SET fin_aujourd_hui = '21:30', fin_aujourd_hui_le = $2 WHERE site_id = $1 AND type = 'emporter'", e.monde.a, vendredi.date()
    )
    refus = await _etat(e, "emporter", vendredi)
    assert (refus["ouvert"], refus["raison"]) == (False, "fin_du_jour"), refus
    assert (await _etat(e, "emporter", vendredi.replace(hour=21, minute=25)))["ouvert"] is True
    assert (await _etat(e, "livraison", vendredi))["ouvert"] is True  # par type : la livraison garde sa fin
    suivant = vendredi + timedelta(days=7)
    assert (await _etat(e, "emporter", suivant))["ouvert"] is True
    assert (await _etat(e, "emporter", suivant.replace(hour=22, minute=5)))["raison"] == "fin_du_jour"


async def test_lm05_le_plus_prudent_gagne(essai_de):
    """LM-05 (E6) : une fin d'aujourd'hui plus tard que la règle de fond ne la repousse pas (22 h reste) ; elle ferme avant les horaires ; en
    livraison, la raison est `livraison_terminee`."""
    e = await essai_de("casa-italia")
    await _vendredi_ouvert(e)
    vendredi = datetime(2026, 11, 13, 22, 5, tzinfo=PARIS)
    await e.monde.c.execute(
        "UPDATE mark.resto_reglage_type SET fin_aujourd_hui = '23:00', fin_aujourd_hui_le = $2 WHERE site_id = $1 AND type = 'emporter'", e.monde.a, vendredi.date()
    )
    assert (await _etat(e, "emporter", vendredi))["raison"] == "fin_du_jour"
    await e.monde.c.execute("UPDATE mark.resto_reglage_type SET fin_par_jour = '{}' WHERE site_id = $1", e.monde.a)
    await e.monde.c.execute(
        "UPDATE mark.resto_reglage_type SET fin_aujourd_hui = '20:00', fin_aujourd_hui_le = $2 WHERE site_id = $1 AND type = 'livraison'", e.monde.a, vendredi.date()
    )
    livraison = await _etat(e, "livraison", vendredi.replace(hour=20, minute=30))
    assert (livraison["ouvert"], livraison["raison"]) == (False, "livraison_terminee"), livraison  # avant la fermeture des horaires (23 h 30)


async def test_lm06_la_fin_d_aujourd_hui_s_ecrit_par_la_couche_d_acces(essai_de):
    """LM-06 (E6) : l'écriture pose l'heure ET le jour du lieu (celui de l'horloge de l'établissement) ; `None` la retire ; la puce la rend le jour même
    seulement ; jamais pour la réservation."""
    e = await essai_de("casa-italia")  # l'horloge des essais : jeudi 12 novembre, midi
    assert (await temps.ecrire_fin_d_aujourd_hui(e.monde.c, e.monde.a, "reservation", time(21, 0))).statut == "ARGUMENT_INVALIDE"
    r = await temps.ecrire_fin_d_aujourd_hui(e.monde.c, e.monde.a, "emporter", time(13, 0))
    assert r.statut == "OK" and r.faits["le"] == datetime(2026, 11, 12).date(), r
    assert (await _etat(e, "emporter", datetime(2026, 11, 12, 13, 5, tzinfo=PARIS)))["raison"] == "fin_du_jour"
    assert (await _etat(e, "emporter", datetime(2026, 11, 19, 13, 5, tzinfo=PARIS)))["raison"] != "fin_du_jour"  # le jeudi suivant : effacée
    _geste(e.monde.c)
    puce = await temps.temps_par_type(e.monde.c, e.monde.a, datetime(2026, 11, 12, 12, 0, tzinfo=PARIS))
    assert next(t for t in puce["types"] if t["type"] == "emporter")["fin_aujourd_hui"] == time(13, 0)
    assert (await temps.ecrire_fin_d_aujourd_hui(e.monde.c, e.monde.a, "emporter", None)).statut == "OK"
    assert (await _etat(e, "emporter", datetime(2026, 11, 12, 13, 5, tzinfo=PARIS)))["raison"] != "fin_du_jour"


# --------------------------------------------------------------------------- la migration


async def test_lm07_migration_045_montee_descente(base_prete):
    """LM-07 : la 045 monte, descend et remonte (deux fois, rejouable) ; une seule tête (la 045 est la dernière)."""
    from api.db.bases_clients import connexion as schema

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col))
                for t, col in COLONNES_045]

    assert schema.version_attendue() == 45
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        for _ in range(2):
            await descendre_jusqu_a(c, 45)
            assert not any(await presentes(c)) and 45 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 45 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()
