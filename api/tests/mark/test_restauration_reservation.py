"""[.mark] Module Restauration, lot 8, étape 2 : les réservations dans le classeur (notre moteur de réservation par capacité).

Vraie base, rôle ``_ecriture``, jeudi 12 h. Salle : deux tables de 2 (assemblables), une de 4, une de 6 ; service du soir 19 h à 22 h par pas de 15 minutes ;
durée 90 minutes jusqu'à 6 personnes ; règles : délai 60 minutes, 30 jours.

| Test | Ce qu'il prouve |
|---|---|
| créer | place attribuée automatiquement (la plus juste), réservation écrite, phrase dite |
| un manque | un manque à la fois, rien écrit |
| règles | passé, trop tôt, trop loin, hors grille, groupe trop grand, type fermé : chacun sa raison, rien écrit |
| capacité | complet : les créneaux libres les plus proches ; deux demandes simultanées, une seule table prise |
| doublon | même appel, même heure : le même numéro |
| modifier | ses propres tables comptent comme libres ; complet : refus et rien ne change ; cloisonnement |
| figée | une passée ne se change plus ; une annulée n'est plus modifiable ; annuler deux fois rend DEJA_FAIT |
| retrouver | par numéro, téléphone, prénom et jour ; jamais celle d'un autre établissement |
| journal | la source est dite (agent, portail) |
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_reservation import annuler_reservation, creer_reservation, modifier_reservation, retrouver_reservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

PARIS = ZoneInfo("Europe/Paris")
TEL = "+33612345678"
SAMEDI_20H = datetime(2026, 11, 14, 20, 0, tzinfo=PARIS)


@pytest.fixture
async def salle(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        ids = {}
        for cle in ("a", "b"):
            ids[cle] = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise RETURNING id", cle)
        a = ids["a"]
        s = await c.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'Salle') RETURNING id", a)
        t = {}
        for nom, mini, maxi in (("T1", 1, 2), ("T2", 1, 2), ("T3", 2, 4), ("T4", 4, 6)):
            t[nom] = await c.fetchval(
                "INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, $3, $4, $5) RETURNING id", a, s, nom, mini, maxi
            )
        await c.execute("UPDATE mark.resto_table SET assemblable_avec = ARRAY[$2::bigint] WHERE id = $1", t["T1"], t["T2"])
        await c.execute("UPDATE mark.resto_table SET assemblable_avec = ARRAY[$2::bigint] WHERE id = $1", t["T2"], t["T1"])
        await c.execute("INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, 'Soir', '{1,2,3,4,5,6,7}', '19:00', '22:00', 15)", a)
        await c.execute("INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, 10, 90)", a)
        await c.execute("INSERT INTO mark.resto_regle_reservation (site_id, delai_minimal, jours_a_l_avance, couverts_max_groupe) VALUES ($1, 60, 30, 6)", a)
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            yield SimpleNamespace(c=c, a=a, b=ids["b"], t=t, base=base_prete)
    finally:
        await c.close()


def demande(**plus):
    return {"debut": SAMEDI_20H, "couverts": 2, "prenom": "Alice", "telephone": TEL, "appel_id": "appel-1", **plus}


async def creer(salle, **plus):
    return await creer_reservation(salle.c, salle.a, demande(**plus))


async def test_creer_attribue_la_table_la_plus_juste_ecrit_et_dit(salle):
    r = await creer(salle)
    assert r.statut == "ENREGISTREE", r
    assert r.faits["tables"] == ["T1"] and r.faits["duree_minutes"] == 90 and r.faits["debut"] == SAMEDI_20H
    assert r.suggestion == "" and (r.faits["couverts"], r.faits["quand_dit"], r.faits["prenom"]) == (2, "samedi quatorze novembre à vingt heures", "Alice")  # C7 (B7) : des faits, le modèle dit
    ligne = await salle.c.fetchrow("SELECT * FROM mark.resto_reservation WHERE numero = $1", uuid.UUID(r.faits["numero"]))
    assert (ligne["statut"], ligne["cree_par"], list(ligne["table_ids"]), ligne["site_id"]) == ("confirmee", "agent", [salle.t["T1"]], salle.a)
    # la suivante, au même moment, prend la table d'à côté ; la troisième, la table de quatre
    assert (await creer(salle, appel_id="x2", telephone="+33611111111")).faits["tables"] == ["T2"]
    assert (await creer(salle, appel_id="x3", telephone="+33622222222")).faits["tables"] == ["T3"]
    # quatre personnes : la table de quatre est prise, la paire T1 + T2 aussi : la table de six
    assert (await creer(salle, couverts=4, appel_id="x4", telephone="+33633333333")).faits["tables"] == ["T4"]
    j = await salle.c.fetchrow("SELECT source FROM mark.resto_journal WHERE objet = 'resto_reservation' AND operation = 'insert' ORDER BY id LIMIT 1")
    assert j["source"] == "agent"


async def test_un_manque_a_la_fois(salle):
    for retire in ("couverts", "debut", "prenom", "telephone"):
        b = demande()
        b.pop(retire)
        r = await creer_reservation(salle.c, salle.a, b)
        assert (r.statut, r.manque) == ("INCOMPLETE", retire)
    assert (await creer(salle, telephone="pas un numéro")).statut == "ARGUMENT_INVALIDE"
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 0
    # le portail peut réserver sans téléphone
    b = demande()
    b.pop("telephone")
    assert (await creer_reservation(salle.c, salle.a, b, source="portail")).statut == "ENREGISTREE"


async def test_les_regles_refusent_chacune_pour_sa_raison_sans_rien_ecrire(salle):
    cas = {
        "passe": datetime(2026, 11, 12, 11, 0, tzinfo=PARIS),
        "trop_tot": datetime(2026, 11, 12, 12, 30, tzinfo=PARIS),
        "trop_loin": datetime(2026, 12, 25, 20, 0, tzinfo=PARIS),
        "hors_service": datetime(2026, 11, 14, 15, 0, tzinfo=PARIS),
    }
    for detail, debut in cas.items():
        r = await creer(salle, debut=debut)
        assert (r.statut, r.faits["raison"], r.faits["detail"]) == ("REFUSEE", "autre", detail), (detail, r)
    assert (await creer(salle, debut=datetime(2026, 11, 14, 20, 10, tzinfo=PARIS))).faits["detail"] == "hors_service"      # pas de 15 minutes
    assert (await creer(salle, couverts=7)).faits["detail"] == "groupe_trop_grand"
    await salle.c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, ouvert) VALUES ($1, 'reservation', false)", salle.a)
    assert (await creer(salle)).faits["detail"] == "type_ferme"
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 0


async def test_complet_rend_les_creneaux_libres_les_plus_proches(salle):
    for i, (couverts, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):
        assert (await creer(salle, couverts=couverts, telephone=tel, appel_id=f"p{i}")).statut == "ENREGISTREE"
    r = await creer(salle, telephone="+33600000009", appel_id="p9")
    assert (r.statut, r.faits["detail"]) == ("REFUSEE", "complet")
    propositions = r.faits["propositions"]
    assert 1 <= len(propositions) <= 3 and all(p["quand_dit"] for p in propositions) and r.suggestion == ""  # C7 (B7) : les propositions sont des faits
    # tout est pris de 20 h à 21 h 30 : une proposition ne chevauche jamais ce moment
    assert all(p["debut"] >= SAMEDI_20H + timedelta(minutes=90) or p["debut"] + timedelta(minutes=90) <= SAMEDI_20H for p in propositions)
    # ce qui est proposé est réellement réservable
    assert (await creer(salle, debut=propositions[0]["debut"], telephone="+33600000010", appel_id="p10")).statut == "ENREGISTREE"


async def test_deux_demandes_en_meme_temps_une_seule_table_prise(salle):
    # une seule table de six : deux groupes de six à la même heure, deux connexions
    b = await schema.connecter(salle.base)
    try:
        async def autre():
            return await creer_reservation(b, salle.a, demande(couverts=6, telephone="+33611111111", appel_id="b"))

        r1, r2 = await asyncio.gather(creer(salle, couverts=6, appel_id="a"), autre())
        assert sorted([r1.statut, r2.statut]) == ["ENREGISTREE", "REFUSEE"], (r1, r2)
        assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation WHERE statut = 'confirmee'") == 1
    finally:
        await b.close()


async def test_meme_appel_meme_heure_meme_numero(salle):
    r1, r2 = await creer(salle), await creer(salle)
    assert (r1.statut, r2.statut) == ("ENREGISTREE", "DEJA_FAIT") and r1.faits["numero"] == r2.faits["numero"]
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 1


async def test_modifier_ses_propres_tables_comptent_comme_libres(salle):
    # la table de six est la seule qui accueille six : la réservation peut glisser sans se gêner elle-même
    r = await creer(salle, couverts=6)
    n = r.faits["numero"]
    m = await modifier_reservation(salle.c, salle.a, n, {"debut": SAMEDI_20H + timedelta(minutes=30)})
    assert (m.statut, m.faits["debut"], m.faits["tables"]) == ("OK", SAMEDI_20H + timedelta(minutes=30), ["T4"]), m
    # une autre réservation prend la table de six de 19 h à 20 h 30 : s'y déplacer (19 h 30) est refusé et RIEN ne change
    assert (await creer(salle, couverts=6, debut=SAMEDI_20H - timedelta(hours=1), telephone="+33600000005", appel_id="z")).statut == "ENREGISTREE"
    refus = await modifier_reservation(salle.c, salle.a, n, {"debut": SAMEDI_20H - timedelta(minutes=30)})
    assert (refus.statut, refus.faits["detail"]) == ("REFUSEE", "complet")
    assert (await salle.c.fetchval("SELECT debut FROM mark.resto_reservation WHERE numero = $1", uuid.UUID(n))) == SAMEDI_20H + timedelta(minutes=30)
    # le nom et la note ne touchent pas à la place ; rien à changer : DEJA_FAIT
    m = await modifier_reservation(salle.c, salle.a, n, {"prenom": "Alicia", "note": "près de la fenêtre"})
    assert (m.statut, m.faits["prenom"], m.faits["note"], m.faits["tables"]) == ("OK", "Alicia", "près de la fenêtre", ["T4"])
    assert (await modifier_reservation(salle.c, salle.a, n, {"prenom": "Alicia"})).statut == "DEJA_FAIT"
    # moins de personnes : la table la plus juste
    m = await modifier_reservation(salle.c, salle.a, n, {"couverts": 2, "debut": SAMEDI_20H + timedelta(hours=1)})
    assert (m.statut, m.faits["couverts"], m.faits["tables"]) == ("OK", 2, ["T1"])
    # inconnue ou d'un autre établissement
    assert (await modifier_reservation(salle.c, salle.b, n, {"couverts": 3})).statut == "INTROUVABLE"
    assert (await modifier_reservation(salle.c, salle.a, uuid.uuid4(), {"couverts": 3})).statut == "INTROUVABLE"
    assert (await modifier_reservation(salle.c, salle.a, "pas-un-numero", {})).statut == "ARGUMENT_INVALIDE"


async def test_une_reservation_passee_est_figee_une_annulee_n_est_plus_modifiable(salle):
    r = await creer(salle)
    n = r.faits["numero"]
    with horloge.remplacer(salle.base, SAMEDI_20H + timedelta(minutes=5)):
        m = await modifier_reservation(salle.c, salle.a, n, {"couverts": 3})
        assert (m.statut, m.faits["detail"]) == ("REFUSEE", "passee")
        assert (await annuler_reservation(salle.c, salle.a, n)).faits["detail"] == "passee"
    a = await annuler_reservation(salle.c, salle.a, n)
    assert (a.statut, a.suggestion, a.faits["statut"]) == ("OK", "", "annulee")  # C7 (B7) : le fait, sans texte
    assert (await annuler_reservation(salle.c, salle.a, n)).statut == "DEJA_FAIT"                # le second geste identique n'écrase rien
    m = await modifier_reservation(salle.c, salle.a, n, {"couverts": 3})
    assert (m.statut, m.faits["detail"]) == ("REFUSEE", "plus_modifiable")
    assert (await annuler_reservation(salle.c, salle.b, n)).statut == "INTROUVABLE"
    # la table annulée est de nouveau libre
    assert (await creer(salle, appel_id="apres")).faits["tables"] == ["T1"]


async def test_retrouver_par_numero_telephone_ou_prenom_et_jour_jamais_chez_un_autre(salle):
    r = await creer(salle)
    await creer(salle, prenom="Bob", telephone="+33644444444", appel_id="bob", debut=SAMEDI_20H + timedelta(days=1))
    assert (await retrouver_reservation(salle.c, salle.a, numero=r.faits["numero"])).faits["reservations"][0]["prenom"] == "Alice"
    par_tel = await retrouver_reservation(salle.c, salle.a, telephone=TEL)
    assert [x["prenom"] for x in par_tel.faits["reservations"]] == ["Alice"]
    assert par_tel.suggestion == "" and [(x["quand_dit"], x["couverts"]) for x in par_tel.faits["reservations"]] == [("samedi quatorze novembre à vingt heures", 2)]  # C7 (B7)
    par_nom = await retrouver_reservation(salle.c, salle.a, prenom="bob", jour=(SAMEDI_20H + timedelta(days=1)).date())
    assert [x["prenom"] for x in par_nom.faits["reservations"]] == ["Bob"]
    assert (await retrouver_reservation(salle.c, salle.a, prenom="Bob", jour=SAMEDI_20H.date())).statut == "INTROUVABLE"
    assert (await retrouver_reservation(salle.c, salle.b, numero=r.faits["numero"])).statut == "INTROUVABLE"
    assert (await retrouver_reservation(salle.c, salle.b, telephone=TEL)).statut == "INTROUVABLE"
    assert (await retrouver_reservation(salle.c, salle.a)).manque == "reference"
    # une annulée ne se retrouve plus
    await annuler_reservation(salle.c, salle.a, r.faits["numero"])
    assert (await retrouver_reservation(salle.c, salle.a, telephone=TEL)).statut == "INTROUVABLE"


async def test_la_source_est_au_journal(salle):
    r = await creer_reservation(salle.c, salle.a, demande(), source="portail", auteur="portail:evan")
    assert r.statut == "ENREGISTREE"
    j = await salle.c.fetchrow("SELECT source, auteur FROM mark.resto_journal WHERE objet = 'resto_reservation' ORDER BY id DESC LIMIT 1")
    assert (j["source"], j["auteur"]) == ("portail", "portail:evan")
    assert await salle.c.fetchval("SELECT cree_par FROM mark.resto_reservation") == "portail"
