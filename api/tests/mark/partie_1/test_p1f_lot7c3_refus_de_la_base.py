"""[.mark] Lot 7b-C3, commit 1 : les refus de la base de la réservation (``restauration_reservation``) ne portent plus de texte (lot 7b-C7, B7) ; C7 B9 : le catalogue supprimé,
ce que disait le texte d'avant est vérifié dans leurs faits. Le modèle lit ``resultats[].faits`` (``detail``, ``maximum``, ``propositions``) ; la raison qu'il reçoit porte le même ``detail`` (``porte._raison_du_refus``).
Le groupe trop grand garde son fait ``maximum`` (refus 14 et 17 : aucun fait neuf)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.db.bases_clients import horloge
from api.db.bases_clients import restauration_reservation as RR
from api.tests.mark import test_restauration_reservation as RESA
from api.tests.mark.partie_1.aides_secours_de_la_reservation import faits_publics

salle, creer, SAMEDI_20H = RESA.salle, RESA.creer, RESA.SAMEDI_20H  # les fixtures du classeur, reprises par affectation

PARIS = ZoneInfo("Europe/Paris")


def _verifie(r, detail: str, faits: dict):  # C7 B9 : la suite d'un groupe trop grand (``a_faire``) n'est plus un fait de la base, la porte la pose
    """C7 (B7) : la base ne porte plus de texte ; B9 : ce que disait le texte d'avant est dans les faits que le modèle lit (ceux qu'il lisait, ou tous)."""
    assert (r.statut, r.faits["raison"], r.faits["detail"], r.suggestion) == ("REFUSEE", "autre", detail, ""), r
    assert ({k: faits_publics(r).get(k) for k in faits} if faits else faits_publics(r)) == faits, r  # {} : le refus ne porte aucun fait
    assert "a_faire" not in r.faits, r  # C7 B9 : la base ne pose aucune consigne au modèle


async def test_ce_moment_est_passe(salle):
    r = await creer(salle, debut=datetime(2026, 11, 12, 11, 0, tzinfo=PARIS))
    _verifie(r, "passe", {'raison': 'autre', 'detail': 'passe'})


async def test_trop_tot(salle):
    r = await creer(salle, debut=datetime(2026, 11, 12, 12, 30, tzinfo=PARIS))
    _verifie(r, "trop_tot", {'raison': 'autre', 'detail': 'trop_tot'})


async def test_trop_loin(salle):
    r = await creer(salle, debut=datetime(2026, 12, 25, 20, 0, tzinfo=PARIS))
    _verifie(r, "trop_loin", {'raison': 'autre', 'detail': 'trop_loin'})


async def test_hors_service_dit_ses_propositions_quand_il_y_en_a(salle):
    r = await creer(salle, debut=datetime(2026, 11, 14, 15, 0, tzinfo=PARIS))
    assert (r.statut, r.faits["detail"]) == ("REFUSEE", "hors_service"), r
    dites = [p["quand_dit"] for p in r.faits.get("propositions") or []]
    publics = faits_publics(r)  # C7 (B7) puis B9 : ce que le texte d'avant disait (la raison, les heures proposées) est dans les faits que le modèle lit
    assert r.suggestion == "" and publics["detail"] == "hors_service" and [p["quand_dit"] for p in publics.get("propositions") or []] == dites, r


async def test_type_ferme(salle):
    await salle.c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, ouvert) VALUES ($1, 'reservation', false)", salle.a)
    r = await creer(salle)
    _verifie(r, "type_ferme", {'raison': 'autre', 'detail': 'type_ferme'})


async def test_groupe_trop_grand_a_l_enregistrement_garde_son_maximum(salle):
    r = await creer(salle, couverts=7)
    _verifie(r, "groupe_trop_grand", {'raison': 'autre', 'detail': 'groupe_trop_grand', 'maximum': 6})
    assert r.faits["maximum"] == 6


async def test_groupe_trop_grand_dit_avant_le_jour_est_le_meme_texte_et_le_meme_fait(salle):
    r = await RR.groupe_trop_grand(salle.c, salle.a, 25)
    _verifie(r, "groupe_trop_grand", {'raison': 'autre', 'detail': 'groupe_trop_grand', 'maximum': 6})
    assert r.faits["maximum"] == 6 and "personnes_max" not in r.faits


async def test_groupe_trop_grand_de_la_capacite_du_jour(salle):
    r = await RR.capacite_du_jour(salle.c, salle.a, SAMEDI_20H.date(), 7)
    _verifie(r, "groupe_trop_grand", {'raison': 'autre', 'detail': 'groupe_trop_grand', 'maximum': 6})
    assert r.faits["maximum"] == 6


async def test_complet_dit_ses_propositions(salle):
    for i, (couverts, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):
        await creer(salle, couverts=couverts, telephone=tel, appel_id=f"p{i}")
    r = await creer(salle, telephone="+33600000009", appel_id="p9")
    assert (r.statut, r.faits["detail"]) == ("REFUSEE", "complet"), r
    dites = [p["quand_dit"] for p in r.faits["propositions"]]
    assert dites and r.suggestion == "", r  # C7 (B7) : le texte se refait des faits
    publics = faits_publics(r)
    assert publics["detail"] == "complet" and [p["quand_dit"] for p in publics["propositions"]] == dites, r


async def test_passee_et_plus_modifiable(salle):
    n = (await creer(salle)).faits["numero"]
    with horloge.remplacer(salle.base, SAMEDI_20H + timedelta(minutes=5)):
        r = await RR.modifier_reservation(salle.c, salle.a, n, {"couverts": 3})
        _verifie(r, "passee", {'raison': 'autre', 'detail': 'passee'})
    await RR.annuler_reservation(salle.c, salle.a, n)
    r = await RR.modifier_reservation(salle.c, salle.a, n, {"couverts": 3})
    _verifie(r, "plus_modifiable", {'raison': 'autre', 'detail': 'plus_modifiable', 'statut': 'annulee'})
    assert r.faits["statut"] == "annulee"


async def test_la_base_ne_garde_plus_de_dictionnaire_de_phrases_de_refus():
    """Le texte d'un refus de la base se dit par la feuille de secours : ``_PHRASES`` n'existe plus dans la base."""
    assert not hasattr(RR, "_PHRASES")
