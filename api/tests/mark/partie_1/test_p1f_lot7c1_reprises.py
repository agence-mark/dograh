"""[.mark] Lot 7b-C1, reprises de l'audit du 25/11 : un test par reprise (R2 à R6), chacun vu rouge avant son correctif."""

from __future__ import annotations

from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES


def test_la_note_de_moitie_est_une_phrase_du_code_relue_dans_la_relecture():
    """R2 : la note « sans X sur la moitié Y » est relue à la personne (relecture) : elle vit au registre, avec son exception, pas dans une fonction identité."""
    assert PHRASES_DITES.note_de_moitie(ingredient="oignons", moitie="Regina") == "sans oignons sur la moitié Regina"
    assert PHRASES_DITES.PHRASES["note_de_moitie"].exception == PHRASES_DITES.EXCEPTION_RELECTURE


# ── R4 : la promesse de lecture.py devient une offre en question, tenue par le modèle avec laisser_un_message ──────────

import pytest

from api.services.actions_communes.resultat import Resultat
from api.services.commande import moteur, porte, textes_de_secours as TS
from api.services.commande.moteur import socle
from api.services.commande.moteur.socle import Appelant
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_classeur_commande as _CLASSEUR
from api.tests.mark import test_restauration_commande_panier as _PANIER

base_essai, base_prete, commerce = _BASE.base_essai, _BASE.base_prete, _CLASSEUR.commerce  # les fixtures du classeur, reprises sans import inutile


@pytest.fixture
async def appel(commerce):
    a = _PANIER.Appel(commerce)
    await a.mode()
    return a


def _commande(statut: str) -> dict:
    return {"numero_court": "12", "statut": statut, "mode": "emporter", "quand_dit": "dix-neuf heures"}


async def _retrouver(appel, monkeypatch, statut: str) -> Resultat:
    async def retrouver(numero=None, telephone=None):
        return Resultat("OK", {"commandes": [_commande(statut)]})
    monkeypatch.setattr(appel.source, "retrouver", retrouver)
    return await moteur.retrouver_commande(appel.source, appel.p, appel.regles, Appelant(), "12")


@pytest.mark.parametrize("statut", sorted(socle.STATUTS_PERDUS))
async def test_une_commande_perdue_se_dit_par_une_offre_en_question(appel, monkeypatch, statut):
    r = await _retrouver(appel, monkeypatch, statut)
    assert r.suggestion == TS.commande_pas_passee(porte.faits_vus_par_le_modele(r))
    assert r.suggestion == "Cette commande n'est pas passée à la préparation : je laisse un message à l'équipe pour qu'elle vous rappelle ?"


def test_les_statuts_perdus_sont_ceux_de_la_lecture():
    assert socle.STATUTS_PERDUS == frozenset({"refusee", "echec"})


async def _suivi(essai_de, monkeypatch, statut: str) -> dict:
    """Le suivi d'une commande par la vraie porte du service ; le classeur rend une commande au statut voulu."""
    e = await essai_de()

    async def retrouver(numero=None, telephone=None):
        return Resultat("OK", {"commandes": [_commande(statut)]})
    monkeypatch.setattr(e.source, "retrouver", retrouver)
    e.dit("où en est ma commande d'hier")
    r = await porte.executer_la_fiche_du_service({"retrouver_une_commande_enregistree": {}, "a_dire": "x"}, e.ctx)
    return r, e


@pytest.mark.parametrize("statut", sorted(socle.STATUTS_PERDUS))
async def test_le_suivi_d_une_commande_perdue_donne_au_modele_l_offre_du_message(essai_de, monkeypatch, statut):
    r, _ = await _suivi(essai_de, monkeypatch, statut)
    assert r["a_faire"] == porte.A_FAIRE_DE_LA_COMMANDE_PERDUE and "laisser_un_message" in r["a_faire"], r


@pytest.mark.parametrize("statut", ["terminee", "envoyee", "annulee"])
async def test_le_suivi_d_une_autre_commande_ne_propose_pas_le_message(essai_de, monkeypatch, statut):
    r, _ = await _suivi(essai_de, monkeypatch, statut)
    assert not r.get("a_faire"), r


async def test_si_elle_dit_oui_le_message_part_pour_de_bon(essai_de, monkeypatch):
    from api.services.apres_appel import rappels

    _, e = await _suivi(essai_de, monkeypatch, "refusee")
    e.dit("oui")
    r = await porte.executer_la_fiche_du_service({"laisser_un_message": {"objet": "rappel commande refusée"}, "a_dire": "x"}, e.ctx)
    assert r["statut"] == "FAIT" and e.ctx.fiche[porte.CLE_MESSAGE_LAISSE] is True, r
    assert e.ctx.fiche[rappels.CLE_RAPPEL][0]["objet"] == "rappel commande refusée"
    assert e.ctx.fiche["call_disposition"] == "message_a_transmettre"  # l'issue de l'appel : sans réglage, le code est le nom de l'issue
