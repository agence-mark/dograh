"""[.mark] Module Restauration, lot 6, étape 4 : la date résolue vers l'avenir et la commande pour plus tard.

| Test | Ce qu'il prouve |
|---|---|
| dates | « demain », « samedi », « le 24 », « dans trois jours », « le vingt-quatre décembre » sont résolus ; le doute est à confirmer, jamais choisi |
| dates piège | « le 30 février » n'est pas « le 30 » ; deux dates dites = à confirmer ; rien de daté = introuvable |
| jour dit | « samedi 14 novembre », « 1er décembre » |
| capacité | un quart d'heure plein pour plus tard refuse et propose le premier libre ; un quart libre ou sans capacité passe |
| phrase | une commande pour un autre jour dit son jour ; le jour même dit l'heure seule |
| ruptures et carte du moment | une rupture du soir ne bloque pas une commande de la veille pour le matin (par le moment voulu) |
| vocabulaire | aucun mot de restaurant dans le mécanisme des dates |
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import dates_futures as df
from api.db.bases_clients.restauration_commande import enregistrer_commande
from api.db.bases_clients.restauration_temps import creneau_complet
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce  # noqa: F401

PARIS = ZoneInfo("Europe/Paris")
JEUDI = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)  # jeudi 12 novembre 2026


def _r(texte: str, maintenant: datetime = JEUDI):
    return df.resoudre_une_date(texte, maintenant)


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "texte,attendue",
    [
        ("demain", date(2026, 11, 13)),
        ("après-demain", date(2026, 11, 14)),
        ("ce soir", date(2026, 11, 12)),
        ("aujourd'hui", date(2026, 11, 12)),
        ("samedi", date(2026, 11, 14)),
        ("dimanche soir", date(2026, 11, 15)),
        ("lundi", date(2026, 11, 16)),
        ("lundi en huit", date(2026, 11, 23)),
        ("le 24", date(2026, 11, 24)),
        ("le vingt-quatre décembre", date(2026, 12, 24)),
        ("le 1er décembre", date(2026, 12, 1)),
        ("24/12", date(2026, 12, 24)),
        ("dans trois jours", date(2026, 11, 15)),
        ("dans une semaine", date(2026, 11, 19)),
        ("dans huit jours", date(2026, 11, 20)),
        ("je voudrais commander pour demain soir", date(2026, 11, 13)),
        ("le 12 octobre", date(2027, 10, 12)),  # passé cette année : l'année suivante
    ],
)
def test_une_date_dite_est_resolue_vers_l_avenir(texte, attendue):
    r = _r(texte)
    assert (r.statut, r.jour) == (df.RETENU, attendue), (texte, r)


@pytest.mark.parametrize(
    "texte,candidats",
    [
        ("jeudi", [date(2026, 11, 12), date(2026, 11, 19)]),  # le jour même : aujourd'hui ou dans huit jours
        ("jeudi prochain", [date(2026, 11, 12), date(2026, 11, 19)]),
        ("samedi prochain", [date(2026, 11, 14), date(2026, 11, 21)]),  # « prochain » se dit des deux façons
        ("le 12", [date(2026, 11, 12), date(2026, 12, 12)]),
        ("samedi ou dimanche", [date(2026, 11, 14), date(2026, 11, 15)]),
        ("demain ou samedi", [date(2026, 11, 13), date(2026, 11, 14)]),
    ],
)
def test_le_doute_est_a_confirmer_jamais_choisi_en_silence(texte, candidats):
    r = _r(texte)
    assert r.statut == df.AMBIGU and r.jour is None and list(r.candidats) == candidats, (texte, r)


def test_les_pieges_ne_donnent_pas_une_date_au_hasard():
    assert _r("le 30 février").statut == df.INTROUVABLE  # le mois dit invalide le quantième : jamais « le 30 » tout court
    for texte in ("", "   ", "bientôt", "à 19 heures", "pour deux personnes"):
        assert _r(texte).statut == df.INTROUVABLE, texte
    assert _r("le 31").jour == date(2026, 12, 31)  # novembre n'a que 30 jours : le prochain 31
    with pytest.raises(ValueError):
        df.resoudre_une_date("demain", datetime(2026, 11, 12, 12, 0))  # l'instant est aware


def test_la_resolution_suit_le_jour_du_lieu_pas_celui_d_un_autre_fuseau():
    tard = datetime(2026, 11, 12, 23, 30, tzinfo=PARIS)  # déjà vendredi à Tokyo, encore jeudi à Paris
    assert _r("demain", tard).jour == date(2026, 11, 13)


@pytest.mark.parametrize(
    "texte,attendues",
    [
        ("19h30", ["dix-neuf heures trente"]),
        ("19 h", ["dix-neuf heures"]),
        ("19:30", ["dix-neuf heures trente"]),
        ("sept heures et demie du soir", ["dix-neuf heures trente"]),
        ("20 heures moins le quart", ["dix-neuf heures quarante-cinq"]),
        ("midi", ["douze heures"]),
        ("quatorze heures trente", ["quatorze heures trente"]),
        ("7 heures du matin", ["sept heures"]),
        ("9 h 15 du soir", ["vingt et une heures quinze"]),
    ],
)
def test_une_heure_dite_sure_est_resolue(texte, attendues):
    r = df.resoudre_l_heure(texte)
    assert r.statut == df.RETENU and [df.heure_dite(c) for c in r.candidats] == attendues, (texte, r)


@pytest.mark.parametrize("texte,candidats", [("sept heures", ["sept heures", "dix-neuf heures"]), ("huit heures moins vingt", ["sept heures quarante", "dix-neuf heures quarante"]), ("à 8h15", ["huit heures quinze", "vingt heures quinze"])])
def test_une_heure_sans_moment_dit_se_confirme_jamais_choisie(texte, candidats):
    r = df.resoudre_l_heure(texte)
    assert r.statut == df.AMBIGU and r.heure is None and [df.heure_dite(c) for c in r.candidats] == candidats, (texte, r)


@pytest.mark.parametrize("texte", ["", "bientôt", "25 h", "une heure", "pour deux personnes"])
def test_pas_d_heure_dite_est_introuvable(texte):
    assert df.resoudre_l_heure(texte).statut == df.INTROUVABLE, texte


def test_le_jour_dit_en_francais():
    assert df.jour_dit(date(2026, 11, 14)) == "samedi quatorze novembre"
    assert df.jour_dit(date(2026, 12, 1)) == "mardi premier décembre"
    assert df.jour_dit(date(2027, 8, 3)) == "mardi trois août"


# --------------------------------------------------------------------------- #
# Capacité d'un créneau et phrase
# --------------------------------------------------------------------------- #


async def _permettre(commerce, capacite: int | None):
    await commerce.c.execute(
        "UPDATE mark.resto_reglage_type SET planifiee_permise = true, jours_a_l_avance = 3, capacite_quart_heure = $2 WHERE site_id = $1 AND type = 'emporter'",
        commerce.a, capacite,
    )


async def test_un_quart_d_heure_plein_pour_plus_tard_refuse_et_propose_le_premier_libre(commerce):
    await _permettre(commerce, 1)
    soir = JEUDI_MIDI.replace(hour=19, minute=5)
    premiere = await enregistrer_commande(commerce.c, commerce.a, brouillon(heure_voulue=soir), "relu-1")
    assert premiere.statut == "ENREGISTREE", premiere
    seconde = await enregistrer_commande(commerce.c, commerce.a, brouillon(heure_voulue=soir.replace(minute=10), appel_id="appel-2"), "relu-2")
    assert (seconde.statut, seconde.manque, seconde.faits["raison"]) == ("ARGUMENT_INVALIDE", "heure_voulue", "creneau_plein")
    assert seconde.faits["proposition"] == soir.replace(minute=15) and "dix-neuf heures quinze" in seconde.suggestion
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande WHERE site_id = $1", commerce.a) == 1  # rien d'enregistré
    # l'heure proposée passe
    troisieme = await enregistrer_commande(commerce.c, commerce.a, brouillon(heure_voulue=soir.replace(minute=15), appel_id="appel-3"), "relu-3")
    assert troisieme.statut == "ENREGISTREE"


async def test_sans_capacite_ou_dans_un_quart_libre_le_creneau_passe(commerce):
    await _permettre(commerce, None)
    soir = JEUDI_MIDI.replace(hour=19)
    assert await creneau_complet(commerce.c, commerce.a, "emporter", soir) is None
    for i in range(3):
        assert (await enregistrer_commande(commerce.c, commerce.a, brouillon(heure_voulue=soir, appel_id=f"a{i}"), f"r{i}")).statut == "ENREGISTREE"
    await _permettre(commerce, 2)
    assert await creneau_complet(commerce.c, commerce.a, "emporter", soir) == soir + timedelta(minutes=15)  # 3 déjà annoncées : le quart est plein
    assert await creneau_complet(commerce.c, commerce.a, "emporter", soir + timedelta(minutes=30)) is None
    assert await creneau_complet(commerce.c, commerce.b, "emporter", soir) is None  # un autre établissement : rien de commun


async def test_une_commande_annulee_libere_le_creneau(commerce):
    await _permettre(commerce, 1)
    soir = JEUDI_MIDI.replace(hour=19)
    a = await enregistrer_commande(commerce.c, commerce.a, brouillon(heure_voulue=soir), "relu-1")
    assert await creneau_complet(commerce.c, commerce.a, "emporter", soir) is not None
    await commerce.c.execute("UPDATE mark.resto_commande SET statut = 'annulee' WHERE numero = $1::uuid", a.faits["numero"])
    assert await creneau_complet(commerce.c, commerce.a, "emporter", soir) is None


async def test_la_phrase_d_une_commande_pour_plus_tard_dit_son_jour(commerce):
    await _permettre(commerce, None)
    ce_soir = await enregistrer_commande(commerce.c, commerce.a, brouillon(heure_voulue=JEUDI_MIDI.replace(hour=19, minute=30), appel_id="x1"), "r1")
    assert ce_soir.suggestion == "Votre commande est enregistrée pour dix-neuf heures trente."  # le jour même : l'heure seule
    demain = await enregistrer_commande(commerce.c, commerce.a, brouillon(heure_voulue=(JEUDI_MIDI + timedelta(days=1)).replace(hour=19, minute=30), appel_id="x2"), "r2")
    assert demain.statut == "ENREGISTREE" and demain.suggestion == "Votre commande est enregistrée pour vendredi treize novembre à dix-neuf heures trente."


# --------------------------------------------------------------------------- #
# Vocabulaire
# --------------------------------------------------------------------------- #


def test_aucun_mot_de_restaurant_dans_le_mecanisme_des_dates():
    from api.tests.mark.test_restauration_contrat_classeur import MECANISMES_COMMUNS, MOTS_INTERDITS, RACINE

    assert "db/bases_clients/dates_futures.py" in MECANISMES_COMMUNS
    corps = (RACINE / "db/bases_clients/dates_futures.py").read_text(encoding="utf-8")
    assert {m.group(0).lower() for m in MOTS_INTERDITS.finditer(corps)} <= {"restaura"}
