"""[.mark] Contrôle d'avant le banc (23/11), Pierre 13, K6 : le ``cutoff_time`` du point de vente HubRise est lu (migration 052), plus supposé à 06:00 en dur.

| Test | Ce qu'il prouve |
|---|---|
| lecture | ``etat_de_hubrise`` rend le ``cutoff_time`` du point de vente ; ``poser_etat_de_la_caisse`` le range, et ne l'efface pas quand la caisse ne le redit pas |
| horaires | une plage qui passe minuit est lue d'après le cutoff de la caisse (03:00 refuse « 18:00 -> 04:00 », 08:00 accepte « 18:00 -> 07:00 ») ; sans cutoff, 06:00 comme avant |
| jour de service | une fin ``fin_par_jour`` « 04:00 » est la nuit suivante avec 06:00, mais l'heure du MÊME jour avec un cutoff à 03:00 |
| migration | la 052 se monte, se descend, se rejoue et se remonte ; rien n'est perdu |
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.horaires_caisse import jours_de_la_caisse
from api.db.bases_clients.instantane import instantane_de
from api.db.bases_clients.restauration_carte import etat_combine
from api.db.bases_clients.restauration_liaison import poser_etat_de_la_caisse
from api.services.restauration.caisse.prises import hubrise_traduction as ht
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import resto  # noqa: F401

PARIS = ZoneInfo("Europe/Paris")
VENDREDI_NUIT = {"friday": [{"from": "18:00", "to": "04:00"}]}


def _point_de_vente(cutoff):
    return {"order_acceptance": {"mode": "normal"}, **({"cutoff_time": cutoff} if cutoff else {})}


def test_le_cutoff_du_point_de_vente_est_lu():
    assert ht.etat_de_hubrise(_point_de_vente("03:00"))["cutoff"] == "03:00"
    assert ht.etat_de_hubrise(_point_de_vente(None))["cutoff"] is None


def test_les_horaires_sont_lus_d_apres_le_cutoff():
    assert jours_de_la_caisse(VENDREDI_NUIT) == {5: [(time(18, 0), time(23, 59, 59, 999999))], 6: [(time(0, 0), time(4, 0))]}  # sans cutoff : 06:00, comme avant
    assert jours_de_la_caisse(VENDREDI_NUIT, cutoff=time(3, 0)) == {}  # 04:00 est après le cutoff de 03:00 : horaire illisible, ignorée
    assert 6 in jours_de_la_caisse({"friday": [{"from": "18:00", "to": "07:00"}]}, cutoff=time(8, 0))  # un cutoff à 08:00 accepte 07:00


async def test_le_cutoff_est_garde_et_pas_efface_par_une_caisse_qui_ne_le_redit_pas(resto):  # noqa: F811
    c, site = resto.c, resto.a
    await poser_etat_de_la_caisse(c, site, {"mode": "normal", "cutoff": "03:00"})
    assert await c.fetchval("SELECT cutoff_time FROM mark.resto_etat_caisse WHERE site_id = $1", site) == time(3, 0)
    await poser_etat_de_la_caisse(c, site, {"mode": "normal"})
    assert await c.fetchval("SELECT cutoff_time FROM mark.resto_etat_caisse WHERE site_id = $1", site) == time(3, 0)
    await poser_etat_de_la_caisse(c, site, {"mode": "normal", "cutoff": "pas une heure"})
    assert await c.fetchval("SELECT cutoff_time FROM mark.resto_etat_caisse WHERE site_id = $1", site) == time(3, 0)  # une valeur illisible ne casse rien


async def test_les_horaires_de_la_caisse_suivent_son_cutoff(resto):  # noqa: F811
    from api.db.bases_clients.horaires_caisse import horaires_de_la_caisse

    c, site = resto.c, resto.a
    await poser_etat_de_la_caisse(c, site, {"mode": "normal"}, horaires=VENDREDI_NUIT)
    inst = instantane_de(c)
    if inst is not None:
        inst.nouveau_geste()
    assert 6 in await horaires_de_la_caisse(c, site)  # défaut 06:00 : 04:00 est la fin de la nuit
    await poser_etat_de_la_caisse(c, site, {"mode": "normal", "cutoff": "03:00"}, horaires=VENDREDI_NUIT)
    if inst is not None:
        inst.nouveau_geste()
    assert await horaires_de_la_caisse(c, site) == {}  # cutoff 03:00 : « 18:00 -> 04:00 » n'est plus une plage de nuit


async def test_la_fin_par_jour_suit_le_jour_de_service_de_la_caisse(resto):  # noqa: F811
    c, site = resto.c, resto.a
    await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, fin_par_jour) VALUES ($1, 'emporter', '{\"5\": \"04:00\"}') "
                    "ON CONFLICT (site_id, type) DO UPDATE SET fin_par_jour = EXCLUDED.fin_par_jour", site)
    await c.execute("DELETE FROM mark.horaire WHERE site_id = $1", site)  # pas d'horaire : seule la règle de fond ferme

    async def ouvert(moment: datetime) -> dict:
        inst = instantane_de(c)
        if inst is not None:
            inst.nouveau_geste()
        return await etat_combine(c, site, "emporter", moment)

    vendredi_20h = datetime(2026, 11, 13, 20, 0, tzinfo=PARIS)
    assert (await ouvert(vendredi_20h))["ouvert"] is True  # sans caisse : cutoff 06:00, « 04:00 » est la nuit de samedi
    await poser_etat_de_la_caisse(c, site, {"mode": "normal", "cutoff": "03:00"})
    coupe = await ouvert(vendredi_20h)
    assert (coupe["ouvert"], coupe["raison"]) == (False, "fin_du_jour"), coupe  # cutoff 03:00 : « 04:00 » est l'heure du vendredi, déjà passée


async def test_la_052_se_monte_se_descend_se_rejoue_et_se_remonte(base_prete):  # noqa: F811
    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert (await schema.version_de(c)) >= 52
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')")
        site = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'a', 'A' FROM mark.entreprise LIMIT 1 RETURNING id")
        await c.execute("INSERT INTO mark.resto_etat_caisse (site_id, mode, cutoff_time) VALUES ($1, 'normal', '03:00')", site)
        await descendre_jusqu_a(c, 52)
        await descendre_jusqu_a(c, 52)  # rejouable
        assert not await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_etat_caisse' AND column_name='cutoff_time'")
        assert 52 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
        assert await c.fetchval("SELECT mode FROM mark.resto_etat_caisse WHERE site_id = $1", site) == "normal"  # rien d'autre n'est perdu
        assert 52 in await schema.appliquer_migrations(c)
        assert await c.fetchval("SELECT cutoff_time FROM mark.resto_etat_caisse WHERE site_id = $1", site) is None  # la colonne revient vide
    finally:
        await c.close()
