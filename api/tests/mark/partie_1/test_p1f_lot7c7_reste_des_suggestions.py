"""[.mark] C7 B5, la suite : les dernières phrases que le moteur de la commande composait encore n'ont plus de texte ; ce qu'elles apprenaient reste dans les faits.

Décisions d'Evan 25/11 : le code ne compose aucune phrase, le modèle parle (8 h 45, 9 h) ; « pas juste une suppression » (10 h) : chaque test refait le texte d'avant à partir des
seuls faits du retour. Rien ne change à l'oreille : ces textes ne partaient plus au modèle (C4, C5), seuls les tests les lisaient.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.services.commande import moteur
from api.services.commande.moteur import mode_et_adresse
from api.services.commande.moteur.socle import Appelant
from api.services.mots_dits import liste_dite
from api.services.restauration.source_commande import SourceClasseur, resolution_du_jour_et_de_l_heure
from api.tests.mark import test_restauration_commande_panier as _PANIER
from api.tests.mark import test_restauration_classeur_commande as _CLASSEUR
from api.tests.mark import test_base_client as _BASE

base_essai, base_prete, commerce = _BASE.base_essai, _BASE.base_prete, _CLASSEUR.commerce  # les fixtures du classeur, reprises sans import inutile

ADRESSE_AVANT = "Quelle est l'adresse de livraison ?"  # le texte d'avant (``phrase_du_manque(Manque.ADRESSE_ET_COMMUNE)``), refait du seul manque


@pytest.fixture
def vierge(commerce):
    return _PANIER.Appel(commerce)


def _question_du_mode_d_avant(faits: dict) -> str:
    """Le texte d'avant (``_phrase_des_modes``), refait des seuls faits : les modes dits."""
    return f"{liste_dite(faits['modes_dits']).capitalize()} ?"


def _sans_texte_au_manque(r, manque: str) -> None:
    assert r.suggestion == "" and r.manque == manque, r


# ── les questions du mode et de la zone (prealables.py, mode_et_adresse.py, la source) ─────────────────────────────────────────


async def test_un_mode_inconnu_n_a_plus_de_question_composee_et_porte_les_modes_dits(vierge):
    r = await vierge.mode("trottinette")
    assert r.statut == "ARGUMENT_INVALIDE"
    _sans_texte_au_manque(r, "mode")
    assert r.faits["modes"] == list(vierge.source.modes)  # voisin : les codes restent
    assert _question_du_mode_d_avant(r.faits) == "À emporter, en livraison ou sur place ?"


async def test_l_etat_d_un_mode_inconnu_n_a_plus_de_question_composee(vierge):
    r = await moteur.etat_ouverture(vierge.source, vierge.p, vierge.regles, "trottinette")
    assert r.statut == "ARGUMENT_INVALIDE"
    _sans_texte_au_manque(r, "mode")
    assert _question_du_mode_d_avant(r.faits) == "À emporter, en livraison ou sur place ?"


async def test_l_heure_annoncee_sans_mode_lisible_n_a_plus_de_question_composee(vierge):
    r = await moteur.heure_annoncee(vierge.source, vierge.p, vierge.regles, "trottinette")
    assert r.statut == "INCOMPLETE"
    _sans_texte_au_manque(r, "mode")
    assert _question_du_mode_d_avant(r.faits) == "À emporter, en livraison ou sur place ?"


async def test_la_livraison_sans_zone_demande_l_adresse_par_le_seul_manque(vierge):
    r = await vierge.mode("livraison")
    assert r.statut == "OK"
    _sans_texte_au_manque(r, "zone")


async def test_l_ordre_impose_demande_la_zone_par_le_seul_manque_a_la_fin(commerce):
    a = _PANIER.Appel(commerce, ordre_impose=True)
    await a.mode("livraison")
    r = await moteur.finaliser(a.source, a.p, a.regles, Appelant())
    assert r.statut == "INCOMPLETE"
    _sans_texte_au_manque(r, "zone")


async def test_l_heure_annoncee_en_livraison_sans_zone_demande_la_zone_par_le_seul_manque(vierge):
    r = await moteur.heure_annoncee(vierge.source, vierge.p, vierge.regles, "livraison")
    assert r.statut == "INCOMPLETE"
    _sans_texte_au_manque(r, "zone")


async def test_une_adresse_vide_se_redemande_par_le_seul_manque(vierge):
    await vierge.mode("livraison")
    r = await mode_et_adresse.verifier_adresse(vierge.source, vierge.p, vierge.regles, None)
    assert r.statut == "ARGUMENT_INVALIDE"
    _sans_texte_au_manque(r, "adresse")


def test_la_source_n_a_plus_de_question_de_la_zone():
    """La question de la zone ne vit plus dans la source : le manque (``zone``, ``adresse``) la porte, le modèle la pose (Evan 25/11 8 h 45)."""
    assert not hasattr(SourceClasseur, "question_de_la_zone")


# ── le message, l'heure retenue (message.py, source_commande.py) ───────────────────────────────────────────────────────────────


async def test_un_message_sans_quoi_se_redemande_par_le_seul_manque(vierge):
    """Le texte d'avant, « Quel message voulez-vous recevoir ? », ne disait que le manque ``quoi``."""
    r = await moteur.envoyer_un_message(vierge.source, vierge.p, vierge.regles, Appelant(), None, None)
    assert r.statut == "ARGUMENT_INVALIDE" and r.faits == {}
    _sans_texte_au_manque(r, "quoi")


def test_le_jour_et_l_heure_retenus_n_ont_plus_de_texte_et_se_disent_par_leurs_faits():
    r = resolution_du_jour_et_de_l_heure("demain", "dix-neuf heures", datetime(2026, 11, 17, 10, 50, tzinfo=ZoneInfo("Europe/Paris")))
    assert r.statut == "RETENU" and r.suggestion == "", r
    assert f"{r.faits['jour_dit']} à {r.faits['heure_dite']}." == "mercredi dix-huit novembre à dix-neuf heures.", r.faits  # le texte d'avant, refait des faits
