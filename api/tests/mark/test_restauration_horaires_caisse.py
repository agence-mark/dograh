"""[.mark] Module Restauration, SA-32 lot 2 (M57, E-49) : la caisse est maître des horaires quand elle est branchée.

Une seule source par donnée : la fiche de l'établissement, ``{{horaires_ouverture}}`` de l'agent et l'état d'ouverture du comptoir LISENT les
horaires de la caisse ; sans caisse (ou quand le restaurant les tient ici), la fiche reste la source. Rien n'est jamais recopié dans la fiche.

| Test | Ce qu'il prouve |
|---|---|
| lecture de la caisse | les jours de la caisse se lisent en toutes les écritures (noms, trois lettres, numéros) ; une plage illisible est ignorée, jamais inventée |
| texte de la fiche | sept jours de la caisse + ce que la fiche garde de plus (jours fériés, fermetures datées), accepté par l'écran |
| état d'ouverture | la caisse branchée qui dit « soir seulement » ferme le midi, quoi qu'en dise le classeur ; tenue ici ou débranchée : le classeur |
| copie des appels | la fiche porte ``horaires_de_la_caisse`` ; ``horaires_ouverture`` reste celui de la fiche ; débrancher rend la main à la fiche |
| ``{{horaires_ouverture}}`` | la configuration d'un appel lit les horaires de la caisse, sinon ceux de la fiche |
| notification | un changement d'horaires de la caisse fait reconstruire la copie des appels |
| avertissement | « horaires_differents » n'existe plus : la caisse fait foi, rien n'est comparé |
"""

from __future__ import annotations

import asyncio

import asyncpg

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horaires_caisse
from api.db.bases_clients.horaires_caisse import CLE_DU_REFERENTIEL, jours_de_la_caisse, texte_de_la_fiche
from api.db.bases_clients.restauration_carte import etat_combine
from api.db.bases_clients.restauration_liaison import poser_etat_de_la_caisse, retirer_l_etat_de_la_caisse
from api.schemas.etablissements import CatalogueEtablissements
from api.services.base_client.referentiel import lire_referentiel
from api.services.etablissements.appel import configuration_heritee
from api.services.pipecat.etat_ouverture import vers_expression_osm
from api.services.restauration.caisse import synchro_caisse
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI, resto  # noqa: F401

SOIR_SEULEMENT = {j: [{"from": "18:00", "to": "22:00"}] for j in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}
FICHE = "\n".join([f"{j} : 09:00-12:00" for j in ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")] + ["jours fériés : fermé", "exceptions :", "24/12/2026 : fermé"])


async def _fiche(c, site, texte=FICHE):
    await c.execute("UPDATE mark.site SET horaires_texte = $2 WHERE id = $1", site, texte)


async def _etat(c, site, horaires=SOIR_SEULEMENT):
    await poser_etat_de_la_caisse(c, site, {"mode": "normal"}, horaires=horaires)


async def _ouvert_a_midi(c, site) -> bool:
    return (await etat_combine(c, site, "emporter", JEUDI_MIDI))["ouvert"]


# --------------------------------------------------------------------------- #
# Les horaires de la caisse, lus et écrits
# --------------------------------------------------------------------------- #


def test_les_jours_de_la_caisse_se_lisent_en_toutes_les_ecritures_sans_rien_inventer():
    lus = jours_de_la_caisse({"monday": [{"from": "11:00", "to": "14:00"}], "tue": [{"from": "18:00", "to": "22:00"}], "3": [{"from": "09:00", "to": "10:00"}],
                              "sunday": [{"from": "20:00", "to": "19:00"}, {"from": "??", "to": "21:00"}, "bizarre"], "noel": [{"from": "10:00", "to": "11:00"}]})
    assert sorted(lus) == [1, 2, 3]  # dimanche : aucune plage valide ; « noel » n'est pas un jour
    assert [(d.hour, f.hour) for d, f in lus[1]] == [(11, 14)]
    assert jours_de_la_caisse(None) == {} and jours_de_la_caisse({}) == {} and jours_de_la_caisse("pas du json") == {}
    assert sorted(jours_de_la_caisse('{"monday": [{"from": "11:00", "to": "12:00"}]}')) == [1]


def test_le_texte_de_la_fiche_garde_les_sept_jours_de_la_caisse_puis_ce_que_la_caisse_ne_porte_pas():
    texte = texte_de_la_fiche(jours_de_la_caisse(SOIR_SEULEMENT), FICHE)
    lignes = texte.splitlines()
    assert lignes[:7] == [f"{j} : 18:00-22:00" for j in ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")]
    assert "09:00-12:00" not in texte  # la ligne de jour de la fiche est remplacée
    assert lignes[7:] == ["jours fériés : fermé", "exceptions :", "24/12/2026 : fermé"]
    vers_expression_osm(texte)  # l'écran et l'appel l'acceptent
    assert texte_de_la_fiche(jours_de_la_caisse({"monday": [{"from": "11:00", "to": "14:00"}]})).splitlines()[1] == "mardi : fermé"


# --------------------------------------------------------------------------- #
# L'état d'ouverture du comptoir
# --------------------------------------------------------------------------- #


async def test_la_caisse_branchee_qui_dit_soir_seulement_ferme_le_midi_quoi_qu_en_dise_le_classeur(resto):
    c = resto.c
    assert await _ouvert_a_midi(c, resto.a) is True  # le classeur : 11 h à 14 h
    await _etat(c, resto.a)
    etat = await etat_combine(c, resto.a, "emporter", JEUDI_MIDI)
    assert etat["ouvert"] is False and etat["raison"] == "ferme_horaires"
    assert etat["prochaine_ouverture"] == JEUDI_MIDI.replace(hour=18)  # la prochaine ouverture est celle de la caisse


async def test_tenue_ici_ou_debranchee_le_classeur_fait_foi(resto):
    c = resto.c
    await _etat(c, resto.a)
    assert await _ouvert_a_midi(c, resto.a) is False
    await c.execute("INSERT INTO mark.resto_reglage (site_id, sources) VALUES ($1, '{\"horaires\": \"ici\"}'::jsonb)", resto.a)
    assert await _ouvert_a_midi(c, resto.a) is True  # F4 : le restaurant tient ses horaires ici
    await c.execute("DELETE FROM mark.resto_reglage WHERE site_id = $1", resto.a)
    await retirer_l_etat_de_la_caisse(c, resto.a)
    assert await _ouvert_a_midi(c, resto.a) is True  # plus de caisse : le classeur reprend la main


async def test_la_caisse_d_un_autre_etablissement_ne_change_pas_celui_ci(resto):
    await _etat(resto.c, resto.b)
    assert await _ouvert_a_midi(resto.c, resto.a) is True


# --------------------------------------------------------------------------- #
# La copie que lisent les appels et la fiche
# --------------------------------------------------------------------------- #


async def test_la_fiche_lit_les_horaires_de_la_caisse_et_les_rend_au_debranchement(resto):
    c = resto.c
    await _fiche(c, resto.a)
    sans_caisse = (await lire_referentiel(c)).etablissements.etablissements[0]
    assert sans_caisse.horaires_de_la_caisse is None and sans_caisse.horaires_effectifs == FICHE  # sans caisse, la fiche est la source

    await _etat(c, resto.a)
    avec = (await lire_referentiel(c)).etablissements.etablissements[0]
    assert avec.horaires_ouverture == FICHE  # jamais recopiés dans la fiche
    assert avec.horaires_effectifs == avec.horaires_de_la_caisse and avec.horaires_de_la_caisse.startswith("lundi : 18:00-22:00")
    assert "24/12/2026 : fermé" in avec.horaires_de_la_caisse  # les fermetures datées de la fiche restent
    assert await c.fetchval("SELECT horaires_texte FROM mark.site WHERE id = $1", resto.a) == FICHE

    await retirer_l_etat_de_la_caisse(c, resto.a)
    rendue = (await lire_referentiel(c)).etablissements.etablissements[0]
    assert rendue.horaires_de_la_caisse is None and rendue.horaires_effectifs == FICHE


async def test_une_caisse_sans_horaires_ou_un_restaurant_qui_les_tient_ici_laisse_la_fiche(resto):
    c = resto.c
    await _fiche(c, resto.a)
    await _etat(c, resto.a, horaires=None)
    assert (await lire_referentiel(c)).etablissements.etablissements[0].horaires_de_la_caisse is None
    await _etat(c, resto.a)
    await c.execute("INSERT INTO mark.resto_reglage (site_id, sources) VALUES ($1, '{\"horaires\": \"ici\"}'::jsonb)", resto.a)
    assert (await lire_referentiel(c)).etablissements.etablissements[0].horaires_de_la_caisse is None


async def test_une_base_sans_le_module_ne_perd_pas_la_copie(resto, monkeypatch):
    await _fiche(resto.c, resto.a)
    await _etat(resto.c, resto.a)

    async def table_absente(connexion, etablissement_id):
        raise asyncpg.exceptions.UndefinedTableError("relation « mark.resto_etat_caisse » n'existe pas")

    monkeypatch.setattr(horaires_caisse, "horaires_de_la_caisse", table_absente)
    lu = (await lire_referentiel(resto.c)).etablissements.etablissements[0]
    assert lu.horaires_effectifs == FICHE and lu.horaires_de_la_caisse is None  # la fiche fait foi, la copie n'est pas vide


async def test_l_appel_lit_les_horaires_de_la_caisse_dans_horaires_ouverture(resto):
    c = resto.c
    await _fiche(c, resto.a)
    sans = (await lire_referentiel(c)).etablissements.etablissements[0]
    configs, origines = configuration_heritee({"horaires_ouverture": "propres a l'agent"}, sans)
    assert configs["horaires_ouverture"] == FICHE and origines["horaires_ouverture"] == "etablissement"

    await _etat(c, resto.a)
    avec = (await lire_referentiel(c)).etablissements.etablissements[0]
    configs, origines = configuration_heritee({"horaires_ouverture": "propres a l'agent"}, avec)
    assert configs["horaires_ouverture"].startswith("lundi : 18:00-22:00") and origines["horaires_ouverture"] == "caisse"
    assert isinstance(CatalogueEtablissements(etablissements=[avec]), CatalogueEtablissements)  # la copie reste un catalogue valide


# --------------------------------------------------------------------------- #
# La notification et l'avertissement
# --------------------------------------------------------------------------- #


async def test_un_changement_d_horaires_de_la_caisse_fait_reconstruire_la_copie_des_appels(resto):
    c = resto.c
    ecoute = await schema.connecter(resto.base)
    recus: list[str] = []
    await ecoute.add_listener(CLE_DU_REFERENTIEL, lambda _c, _pid, _canal, charge: recus.append(charge))
    try:
        await synchro_caisse.appliquer_l_etat(c, 1, resto.a, {"mode": "normal", "horaires": SOIR_SEULEMENT})
        await asyncio.sleep(0.3)
        assert "horaires_caisse" in recus
        recus.clear()
        await synchro_caisse.appliquer_l_etat(c, 1, resto.a, {"mode": "normal", "horaires": SOIR_SEULEMENT})  # rejeu sans effet double
        await asyncio.sleep(0.3)
        assert "horaires_caisse" not in recus
        await retirer_l_etat_de_la_caisse(c, resto.a)
        await asyncio.sleep(0.3)
        assert "caisse_retiree" in recus
    finally:
        await ecoute.remove_listener(CLE_DU_REFERENTIEL, recus.append)
        await ecoute.close()


async def test_les_horaires_differents_ne_sont_plus_un_avertissement_la_caisse_fait_foi(resto):
    c = resto.c
    await c.execute("INSERT INTO mark.resto_liaison (site_id, prise, avertissements) VALUES ($1, 'hubrise', '{horaires_differents,carte_sans_code}')", resto.a)
    await synchro_caisse.appliquer_l_etat(c, 1, resto.a, {"mode": "normal", "horaires": SOIR_SEULEMENT})
    avertissements = await c.fetchval("SELECT avertissements FROM mark.resto_liaison WHERE site_id = $1", resto.a)
    assert list(avertissements) == ["carte_sans_code"]
    assert not hasattr(synchro_caisse, "horaires_differents")


@pytest.mark.parametrize("horaires", [None, {}])
async def test_une_caisse_sans_horaires_ne_notifie_rien(resto, horaires):
    ecoute = await schema.connecter(resto.base)
    recus: list[str] = []
    await ecoute.add_listener(CLE_DU_REFERENTIEL, lambda _c, _pid, _canal, charge: recus.append(charge))
    try:
        await synchro_caisse.appliquer_l_etat(resto.c, 1, resto.a, {"mode": "normal", "horaires": horaires})
        await asyncio.sleep(0.3)
        assert "horaires_caisse" not in recus or horaires == {}
    finally:
        await ecoute.close()
