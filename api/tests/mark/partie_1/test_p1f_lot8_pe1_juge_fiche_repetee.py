"""[.mark] Lot 8, PE-1 : le juge des combinaisons tient la fiche identique au tour d'avant comme le code (Q1/Q2 c, Pierre 26/11 ; reprise R2 de ``fiches/lot-8-pe1-audit.md``).

La fiche refaite dans le MÊME tour après un refus partiel (G33 : la regina seule, après la regina dite avec un téléphone que la personne n'a pas dit) compte pour « la même au tour d'après ».
Client « Une regina. » (téléphone refusé, la regina entre ; le modèle refait la fiche) ... tour suivant « Une regina. » / le modèle « Une deuxième regina, ou c'était la même ? » ; une seule
regina. Le juge attend « panier inchangé » ET le refus ``fiche_identique_au_tour_d_avant`` (la question au client) : un article ajouté sans question, ou perdu en silence, est une faute."""

from __future__ import annotations

import pytest

from api.services.actions_communes.enveloppe import Enveloppe
from api.services.commande import porte as PORTE
from api.tests.mark.partie_1 import combinaisons as C

RAISON = "fiche_identique_au_tour_d_avant"
LA_MEME_REDITE = ("E1", ("G1", "G1"))  # « une regina normale », puis la même au tour d'après


async def test_la_fiche_refaite_dans_le_meme_tour_puis_redite_au_tour_d_apres_n_est_pas_une_faute(faire_monde, monkeypatch):
    """E18 → G33 · G1 (garde du lot 8, ``test_profondeur_2[E18]``) : le code refuse la regina redite et demande ; le juge ne l'attend plus ajoutée."""
    monde = await faire_monde("casa-italia")
    r = await C.jouer(monde, monkeypatch, "E18", ("G33", "G1"))
    assert r.atteint and r.joues == 2, r
    assert not r.fautes, r.fautes


async def test_garde_le_code_qui_ajoute_la_fiche_identique_sans_question_est_une_faute(faire_monde, monkeypatch):
    """Mutation du code : la fiche identique au tour d'avant est appliquée (une seconde regina, rien demandé) ; le juge la voit (RC2)."""
    monde = await faire_monde("casa-italia")
    monkeypatch.setattr(PORTE, "_fiche_identique_au_tour_d_avant", lambda p, tour, fiche: None)
    r = await C.jouer(monde, monkeypatch, *LA_MEME_REDITE)
    assert r.atteint and r.joues == 2, r
    assert any(pas == "G1" and regle == "RC2" for pas, regle, _ in r.fautes), r.fautes


def _sans_la_question(origine):
    def refus_muet(p, tour, fiche):
        refus = origine(p, tour, fiche)
        if refus is None:
            return None
        return Enveloppe("FAIT", faits={"deja_fait": True}, plus={"fiche_appliquee": False, "rien_ajoute": True}).vers_json()

    return refus_muet


def _avec_une_autre_raison(origine):
    def autre_refus(p, tour, fiche):
        refus = origine(p, tour, fiche)
        if refus is None:
            return None
        autre = "question_inconnue"
        return {**refus, "raison": autre, "refus": [{**x, "raison": autre} for x in refus.get("refus") or []]}

    return autre_refus


@pytest.mark.parametrize("mutation", [_sans_la_question, _avec_une_autre_raison], ids=["refus_absent", "raison_absente"])
async def test_garde_le_code_qui_refuse_la_fiche_identique_sans_demander_est_une_faute(faire_monde, monkeypatch, mutation):
    """Mutation du code : la fiche identique n'est pas appliquée, mais sans le refus qui fait demander au modèle « un de plus ou le même ? » : l'article est perdu en silence ;
    le juge le voit (RC2)."""
    monde = await faire_monde("casa-italia")
    monkeypatch.setattr(PORTE, "_fiche_identique_au_tour_d_avant", mutation(PORTE._fiche_identique_au_tour_d_avant))
    r = await C.jouer(monde, monkeypatch, *LA_MEME_REDITE)
    assert r.atteint and r.joues == 2, r
    assert any(pas == "G1" and regle == "RC2" and RAISON in detail for pas, regle, detail in r.fautes), r.fautes
