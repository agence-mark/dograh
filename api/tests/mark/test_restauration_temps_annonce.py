"""[.mark] Module Restauration, lot 6, étape 1 : l'heure annoncée (heure fixe, tranche, durée), la durée ajoutée par la puce, l'attente de capacité, l'état par type.

Calcul pur (``annonce_heure.py``, mécanisme commun) et vraie base (``restauration_temps.py``), carte de référence, heure fixée au jeudi 12 h.

| Test | Ce qu'il prouve |
|---|---|
| arrondi vers le haut | durée à la minute, heure fixe au multiple de 5, tranche alignée sur le quart : jamais une promesse plus tôt que le calcul |
| dite | « dans 30 minutes », « à 20 h 15 », « entre 20 h 15 et 20 h 30 » |
| capacité | un quart plein pousse au suivant ; sans capacité réglée aucune attente ; borné |
| le délai en entier | la livraison annonce le délai de SA zone, jamais « base + zone » (E-42) ; à emporter celui de son type |
| durée ajoutée | par-dessus, par type, jusqu'à son heure ; s'éteint toute seule ; une commande déjà annoncée garde la sienne (E-05) |
| trois formats | réglables par type, jusqu'à l'enregistrement : l'heure écrite et la phrase suivent |
| capacité par quart d'heure | le second du quart plein est annoncé au quart suivant |
| état par type | pause et reprise automatique, fin de service, zones annoncées, caisse qui porte l'état en lecture seule |
| la puce | durée ajoutée, jusqu'à, pause (absente, levée, durée, heure, fin de journée) ; refusée quand la caisse porte l'état ; bornes ; journalisée |
| fin du service | lue dans les horaires de l'établissement |
| cloisonnement | la zone d'un autre établissement n'est jamais utilisée ; la puce d'un établissement ne touche pas l'autre |
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import annonce_heure as ah
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import etat_combine
from api.db.bases_clients.restauration_commande import enregistrer_commande
from api.db.bases_clients.restauration_temps import PAS_DE_CHANGEMENT, annonce_pour, ecrire_temps, fin_du_service, temps_par_type
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce  # noqa: F401

PARIS = ZoneInfo("Europe/Paris")


# --------------------------------------------------------------------------- #
# Le calcul pur
# --------------------------------------------------------------------------- #


def test_une_duree_est_arrondie_a_la_minute_au_dessus_jamais_en_dessous():
    base = datetime(2026, 11, 12, 12, 0, 20, tzinfo=PARIS)
    a = ah.annoncer(base, 20, 0, 0, "duree")
    assert a.prete == datetime(2026, 11, 12, 12, 21, tzinfo=PARIS) and a.minutes == 21 and a.prete >= base + timedelta(minutes=20)


@pytest.mark.parametrize(
    "minute,attendue",
    [(0, 0), (1, 5), (4, 5), (5, 5), (6, 10), (58, 0)],
)
def test_une_heure_fixe_se_dit_au_multiple_de_cinq_au_dessus(minute, attendue):
    a = ah.annoncer(datetime(2026, 11, 12, 12, minute, tzinfo=PARIS), 0, 0, 0, "heure_fixe")
    assert a.prete.minute == attendue and a.prete >= datetime(2026, 11, 12, 12, minute, tzinfo=PARIS)


def test_une_tranche_tient_sur_un_quart_d_heure_aligne_et_ne_promet_pas_plus_tot():
    a = ah.annoncer(datetime(2026, 11, 12, 20, 0, tzinfo=PARIS), 7, 0, 0, "tranche")
    assert (a.debut, a.fin) == (datetime(2026, 11, 12, 20, 15, tzinfo=PARIS), datetime(2026, 11, 12, 20, 30, tzinfo=PARIS))
    assert a.debut >= datetime(2026, 11, 12, 20, 7, tzinfo=PARIS)
    assert ah.annoncer(datetime(2026, 11, 12, 20, 0, tzinfo=PARIS), 15, 0, 0, "tranche").debut == datetime(2026, 11, 12, 20, 15, tzinfo=PARIS)


def test_le_delai_la_duree_ajoutee_et_l_attente_s_additionnent_une_fois_chacun():
    a = ah.annoncer(datetime(2026, 11, 12, 12, 0, tzinfo=PARIS), 30, 10, 5, "duree")
    assert a.minutes == 45


def test_l_annonce_se_dit_en_francais():
    maintenant = datetime(2026, 11, 12, 20, 0, tzinfo=PARIS)
    assert ah.dite(ah.annoncer(maintenant, 30, 0, 0, "duree"), PARIS) == "dans trente minutes"
    assert ah.dite(ah.annoncer(maintenant, 1, 0, 0, "duree"), PARIS) == "dans une minute"
    assert ah.dite(ah.annoncer(maintenant, 75, 0, 0, "duree"), PARIS) == "dans une heure quinze"
    assert ah.dite(ah.annoncer(maintenant, 20, 0, 0, "heure_fixe"), PARIS) == "à vingt heures vingt"
    assert ah.dite(ah.annoncer(maintenant, 60, 0, 0, "heure_fixe"), PARIS) == "à vingt et une heures"
    assert ah.dite(ah.annoncer(maintenant, 10, 0, 0, "tranche"), PARIS) == "entre vingt heures quinze et vingt heures trente"
    # l'heure dite est celle du lieu, pas celle du serveur
    utc = ah.annoncer(datetime(2026, 11, 12, 19, 0, tzinfo=PARIS).astimezone(ZoneInfo("UTC")), 20, 0, 0, "heure_fixe")
    assert ah.dite(utc, PARIS) == "à dix-neuf heures vingt"


def test_un_format_inconnu_ou_un_instant_naif_est_refuse():
    with pytest.raises(ValueError):
        ah.annoncer(datetime(2026, 11, 12, 12, 0, tzinfo=PARIS), 0, 0, 0, "en_chantant")
    with pytest.raises(ValueError):
        ah.annoncer(datetime(2026, 11, 12, 12, 0), 0, 0, 0, "duree")


def test_attente_par_quart_un_quart_plein_pousse_au_suivant_sans_capacite_aucune_attente():
    prete = datetime(2026, 11, 12, 20, 7, tzinfo=PARIS)
    q = ah.quart_de(prete)
    assert q == datetime(2026, 11, 12, 20, 0, tzinfo=PARIS)
    assert ah.attente_par_quart(prete, {q: 1}, 1) == 8  # 20 h 07 -> 20 h 15
    assert ah.attente_par_quart(prete, {q: 1, q + timedelta(minutes=15): 1}, 1) == 23  # deux quarts pleins
    assert ah.attente_par_quart(prete, {q: 3}, 4) == 0  # il reste de la place
    assert ah.attente_par_quart(prete, {q: 99}, None) == 0 and ah.attente_par_quart(prete, {q: 99}, 0) == 0  # sans capacité réglée


def test_attente_par_quart_est_bornee():
    prete = datetime(2026, 11, 12, 20, 0, tzinfo=PARIS)
    tout_plein = {prete + timedelta(minutes=15 * i): 5 for i in range(40)}
    assert ah.attente_par_quart(prete, tout_plein, 5) == 15 * ah.QUARTS_MAX  # au-delà de quatre heures : on s'arrête là


# --------------------------------------------------------------------------- #
# En base : le délai en entier, la durée ajoutée, les formats, la capacité
# --------------------------------------------------------------------------- #


async def _reglage(commerce, **colonnes):
    for type_, valeurs in colonnes.items():
        sets = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(valeurs))
        await commerce.c.execute(f"UPDATE mark.resto_reglage_type SET {sets} WHERE site_id = $1 AND type = $2", commerce.a, type_, *valeurs.values())


async def test_la_livraison_annonce_le_delai_de_sa_zone_en_entier_jamais_une_addition(commerce):
    await _reglage(commerce, livraison={"delai_annonce": None})
    a = await annonce_pour(commerce.c, commerce.a, "livraison", JEUDI_MIDI, commerce.zones["Senlis"])
    assert a["annonce"].minutes == 30 and a["delai_minutes"] == 30 and a["ajout_minutes"] == 0
    proches = await annonce_pour(commerce.c, commerce.a, "livraison", JEUDI_MIDI, commerce.zones["Proches"])
    assert proches["annonce"].minutes == 40
    emporter = await annonce_pour(commerce.c, commerce.a, "emporter", JEUDI_MIDI)
    assert emporter["annonce"].minutes == 20  # le délai de SON type, pas celui d'une zone


async def test_la_duree_ajoutee_vient_par_dessus_le_delai_de_la_zone_et_s_eteint_a_son_heure(commerce):
    await _reglage(commerce, livraison={"minutes_ajoutees": 10, "ajout_jusqu_a": JEUDI_MIDI + timedelta(hours=1)})
    a = await annonce_pour(commerce.c, commerce.a, "livraison", JEUDI_MIDI, commerce.zones["Senlis"])
    assert (a["annonce"].minutes, a["delai_minutes"], a["ajout_minutes"]) == (40, 30, 10)
    assert (await annonce_pour(commerce.c, commerce.a, "emporter", JEUDI_MIDI))["annonce"].minutes == 20  # par type : l'emporter n'est pas touché
    apres = JEUDI_MIDI + timedelta(hours=1, minutes=1)
    with horloge.remplacer(commerce.base, apres):
        a = await annonce_pour(commerce.c, commerce.a, "livraison", apres, commerce.zones["Senlis"])
    assert (a["annonce"].minutes, a["ajout_minutes"]) == (30, 0)  # s'éteint toute seule


async def test_une_commande_deja_annoncee_garde_son_heure_quand_la_puce_change(commerce):
    premiere = await enregistrer_commande(commerce.c, commerce.a, brouillon(), "relu-1")
    assert premiere.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=20)
    assert (await ecrire_temps(commerce.c, commerce.a, "emporter", 15)).statut == "OK"
    seconde = await enregistrer_commande(commerce.c, commerce.a, brouillon(appel_id="appel-2"), "relu-2")
    assert seconde.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=35)  # 20 + 15 : effet au changement seulement
    ecrite = await commerce.c.fetchval("SELECT heure_annoncee FROM mark.resto_commande WHERE numero = $1::uuid", premiere.faits["numero"])
    assert ecrite == JEUDI_MIDI + timedelta(minutes=20)


@pytest.mark.parametrize(
    "format_,attendue,phrase",
    [
        ("duree", JEUDI_MIDI + timedelta(minutes=22), "dans vingt-deux minutes"),
        ("heure_fixe", JEUDI_MIDI + timedelta(minutes=25), "à douze heures vingt-cinq"),
        ("tranche", JEUDI_MIDI + timedelta(minutes=30), "entre douze heures trente et douze heures quarante-cinq"),
    ],
)
async def test_les_trois_formats_se_reglent_par_type_l_heure_ecrite_et_la_phrase_suivent(commerce, format_, attendue, phrase):
    await _reglage(commerce, emporter={"delai_annonce": 22, "annonce": format_})
    r = await enregistrer_commande(commerce.c, commerce.a, brouillon(), "relu-1")
    assert r.statut == "ENREGISTREE"
    assert r.faits["heure_annoncee"] == attendue and r.faits["annonce"]["format"] == format_
    assert r.suggestion == f"Votre commande est enregistrée, elle sera prête {phrase}."
    assert await commerce.c.fetchval("SELECT heure_annoncee FROM mark.resto_commande WHERE numero = $1::uuid", r.faits["numero"]) == attendue


async def test_le_second_d_un_quart_plein_est_annonce_au_quart_suivant(commerce):
    await _reglage(commerce, emporter={"capacite_quart_heure": 1, "annonce": "heure_fixe", "delai_annonce": 20})
    a = await enregistrer_commande(commerce.c, commerce.a, brouillon(), "relu-1")
    b = await enregistrer_commande(commerce.c, commerce.a, brouillon(appel_id="appel-2"), "relu-2")
    assert a.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=20)  # 12 h 20, dans le quart 12 h 15
    assert b.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=30)  # le quart 12 h 15 est plein : 12 h 30
    c = await enregistrer_commande(commerce.c, commerce.a, brouillon(appel_id="appel-3"), "relu-3")
    assert c.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=45)


async def test_une_commande_annulee_ne_compte_plus_dans_la_capacite(commerce):
    await _reglage(commerce, emporter={"capacite_quart_heure": 1, "annonce": "heure_fixe"})
    a = await enregistrer_commande(commerce.c, commerce.a, brouillon(), "relu-1")
    await commerce.c.execute("UPDATE mark.resto_commande SET statut = 'annulee' WHERE numero = $1::uuid", a.faits["numero"])
    b = await enregistrer_commande(commerce.c, commerce.a, brouillon(appel_id="appel-2"), "relu-2")
    assert b.faits["heure_annoncee"] == a.faits["heure_annoncee"]


async def test_la_capacite_d_un_type_ne_compte_pas_les_commandes_d_un_autre(commerce):
    await _reglage(commerce, emporter={"capacite_quart_heure": 1, "annonce": "heure_fixe"})
    liv = await enregistrer_commande(
        commerce.c, commerce.a, brouillon(mode="livraison", zone_id=commerce.zones["Senlis"], adresse={"voie": "1 rue X"}, lignes=[{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 3}],
                                          paiement={"moyens": [{"moyen": "carte", "montant": 3270}]}), "relu-1",
    )
    assert liv.statut == "ENREGISTREE", liv  # la livraison occupe le quart de 12 h 30 (zone de 30 minutes), pas celui de l'emporter
    emporter = await enregistrer_commande(commerce.c, commerce.a, brouillon(appel_id="appel-9"), "relu-2")
    assert emporter.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=20)


# --------------------------------------------------------------------------- #
# L'état par type
# --------------------------------------------------------------------------- #


async def test_l_etat_par_type_rend_les_annonces_par_zone_et_les_types_dans_l_ordre(commerce):
    etat = await temps_par_type(commerce.c, commerce.a)
    assert [t["type"] for t in etat["types"]] == ["emporter", "livraison", "sur_place", "reservation"]
    emporter, livraison, _, reservation = etat["types"]
    assert emporter["ouvert"] and emporter["annonce"]["phrase"] == "dans vingt minutes" and emporter["delai_minutes"] == 20
    assert [(z["nom"], z["delai_zone"], z["annonce"]["minutes"]) for z in livraison["par_zone"]] == [("Senlis", 30, 30), ("Proches", 40, 40)]
    assert reservation["annonce"] is None and reservation["par_zone"] == []
    assert (etat["lecture_seule"], etat["source_de_l_etat"], etat["etat_caisse"]) == (False, "portail", None)


async def test_la_pause_d_un_type_ferme_ce_type_et_reprend_toute_seule(commerce):
    await ecrire_temps(commerce.c, commerce.a, "livraison", 0, pause={"minutes": 30})
    etat = await temps_par_type(commerce.c, commerce.a)
    liv = next(t for t in etat["types"] if t["type"] == "livraison")
    assert liv["ouvert"] is False and liv["raison"] == "pause_type" and liv["pause_jusqu_a"] == JEUDI_MIDI + timedelta(minutes=30)
    assert next(t for t in etat["types"] if t["type"] == "emporter")["ouvert"] is True  # par type : l'emporter reste ouvert
    plus_tard = JEUDI_MIDI + timedelta(minutes=31)
    with horloge.remplacer(commerce.base, plus_tard):
        assert (await etat_combine(commerce.c, commerce.a, "livraison", plus_tard))["ouvert"] is True  # retour automatique


async def test_la_caisse_qui_porte_l_etat_le_rend_en_lecture_seule(commerce):
    await commerce.c.execute("INSERT INTO mark.resto_etat_caisse (site_id, mode, minutes_en_plus, temps_preparation, source) VALUES ($1, 'deborde', 10, 25, 'caisse')", commerce.a)
    etat = await temps_par_type(commerce.c, commerce.a)
    assert etat["lecture_seule"] is True and etat["source_de_l_etat"] == "caisse"
    assert etat["etat_caisse"]["mode"] == "deborde" and etat["etat_caisse"]["minutes_en_plus"] == 10
    emporter = etat["types"][0]
    assert emporter["delai_minutes"] == 25 + 10 - 0 and emporter["annonce"]["minutes"] == 35  # la caisse prime : son temps et son débordement


# --------------------------------------------------------------------------- #
# La puce
# --------------------------------------------------------------------------- #


async def test_la_puce_pose_la_duree_ajoutee_jusqu_a_une_heure_et_la_remet_a_zero(commerce):
    fin = JEUDI_MIDI + timedelta(hours=2)
    r = await ecrire_temps(commerce.c, commerce.a, "emporter", 15, fin)
    assert r.statut == "OK" and (r.faits["minutes_ajoutees"], r.faits["jusqu_a"], r.faits["pause_changee"]) == (15, fin, False)
    ligne = await commerce.c.fetchrow("SELECT minutes_ajoutees, ajout_jusqu_a FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'emporter'", commerce.a)
    assert (ligne["minutes_ajoutees"], ligne["ajout_jusqu_a"]) == (15, fin)
    assert (await ecrire_temps(commerce.c, commerce.a, "emporter", 0)).statut == "OK"
    ligne = await commerce.c.fetchrow("SELECT minutes_ajoutees, ajout_jusqu_a FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'emporter'", commerce.a)
    assert (ligne["minutes_ajoutees"], ligne["ajout_jusqu_a"]) == (0, None)


async def test_la_puce_cree_la_ligne_d_un_type_qui_n_en_a_pas(commerce):
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'sur_place'", commerce.a) == 0
    assert (await ecrire_temps(commerce.c, commerce.a, "sur_place", 5)).statut == "OK"
    assert await commerce.c.fetchval("SELECT minutes_ajoutees FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'sur_place'", commerce.a) == 5


async def test_la_pause_absente_n_est_pas_touchee_levee_ou_posee(commerce):
    await ecrire_temps(commerce.c, commerce.a, "livraison", 0, pause={"jusqu_a": JEUDI_MIDI + timedelta(hours=1)})
    assert (await ecrire_temps(commerce.c, commerce.a, "livraison", 5)).faits["pause_changee"] is False  # pause absente : intacte
    ligne = await commerce.c.fetchval("SELECT pause_jusqu_a FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'livraison'", commerce.a)
    assert ligne == JEUDI_MIDI + timedelta(hours=1)
    await ecrire_temps(commerce.c, commerce.a, "livraison", 5, pause=None)  # levée
    assert await commerce.c.fetchval("SELECT pause_jusqu_a FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'livraison'", commerce.a) is None
    await ecrire_temps(commerce.c, commerce.a, "livraison", 5, pause={})  # sans heure : jusqu'à la fin de la journée, jamais plus d'un jour
    fin_de_journee = await commerce.c.fetchval("SELECT pause_jusqu_a FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'livraison'", commerce.a)
    assert fin_de_journee == datetime(2026, 11, 13, 0, 0, tzinfo=PARIS)
    _ = PAS_DE_CHANGEMENT


async def test_la_puce_est_refusee_quand_la_caisse_porte_l_etat_et_ne_change_rien(commerce):
    await commerce.c.execute("INSERT INTO mark.resto_etat_caisse (site_id, mode, source) VALUES ($1, 'normal', 'caisse')", commerce.a)
    r = await ecrire_temps(commerce.c, commerce.a, "emporter", 15)
    assert r.statut == "REFUSEE" and r.faits["detail"] == "caisse_maitre" and "caisse" in r.suggestion
    assert await commerce.c.fetchval("SELECT minutes_ajoutees FROM mark.resto_reglage_type WHERE site_id = $1 AND type = 'emporter'", commerce.a) == 0


@pytest.mark.parametrize(
    "type_,minutes,kw",
    [
        ("sur_la_lune", 5, {}),
        ("emporter", -1, {}),
        ("emporter", 241, {}),
        ("emporter", True, {}),
        ("emporter", 5, {"jusqu_a": JEUDI_MIDI - timedelta(hours=1)}),
        ("emporter", 5, {"jusqu_a": datetime(2026, 11, 12, 15, 0)}),
        ("reservation", 5, {}),
        ("emporter", 5, {"pause": {"minutes": 0}}),
        ("emporter", 5, {"pause": {"minutes": 99999}}),
        ("emporter", 5, {"pause": {"jusqu_a": JEUDI_MIDI - timedelta(minutes=5)}}),
        ("emporter", 5, {"pause": "oui"}),
    ],
)
async def test_la_puce_refuse_ce_qui_n_a_pas_de_sens_et_n_ecrit_rien(commerce, type_, minutes, kw):
    avant = await commerce.c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE site_id = $1", commerce.a)
    r = await ecrire_temps(commerce.c, commerce.a, type_, minutes, **kw)
    assert r.statut == "ARGUMENT_INVALIDE"
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE site_id = $1", commerce.a) == avant


async def test_un_reglage_de_la_puce_est_journalise_avec_sa_source_et_son_auteur(commerce):
    await ecrire_temps(commerce.c, commerce.a, "emporter", 15, source="portail")
    j = await commerce.c.fetchrow(
        "SELECT source, auteur FROM mark.resto_journal WHERE site_id = $1 AND objet = 'resto_reglage_type' ORDER BY id DESC LIMIT 1", commerce.a
    )
    assert (j["source"], j["auteur"]) == ("portail", "puce:portail")


# --------------------------------------------------------------------------- #
# Fin du service, cloisonnement
# --------------------------------------------------------------------------- #


async def test_la_fin_du_service_est_lue_dans_les_horaires(commerce):
    assert await fin_du_service(commerce.c, commerce.a, JEUDI_MIDI) == datetime(2026, 11, 12, 14, 0, tzinfo=PARIS)  # la plage du midi en cours
    assert await fin_du_service(commerce.c, commerce.a, datetime(2026, 11, 12, 15, 0, tzinfo=PARIS)) == datetime(2026, 11, 12, 22, 30, tzinfo=PARIS)
    assert await fin_du_service(commerce.c, commerce.a, datetime(2026, 11, 12, 23, 0, tzinfo=PARIS)) == datetime(2026, 11, 13, 0, 0, tzinfo=PARIS)
    assert await fin_du_service(commerce.c, commerce.b, JEUDI_MIDI) == datetime(2026, 11, 13, 0, 0, tzinfo=PARIS)  # B n'a pas d'horaires


async def test_la_zone_d_un_autre_etablissement_n_est_jamais_utilisee_et_la_puce_de_l_un_ne_touche_pas_l_autre(commerce):
    with pytest.raises(LookupError):
        await annonce_pour(commerce.c, commerce.a, "livraison", JEUDI_MIDI, commerce.zone_b)
    await ecrire_temps(commerce.c, commerce.a, "emporter", 30)
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_reglage_type WHERE site_id = $1 AND minutes_ajoutees > 0", commerce.b) == 0
    etat_b = await temps_par_type(commerce.c, commerce.b)
    assert next(t for t in etat_b["types"] if t["type"] == "emporter")["minutes_ajoutees"] == 0
