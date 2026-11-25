"""[.mark] Lot 7a, ligne 129 : une lecture qui échoue et rend sa valeur de repli laisse une trace structurée (``logger.exception``), sans nom ni numéro dans la ligne écrite par le code (la pile que le filtre de la production colle après elle, numéros masqués, n'est pas cette ligne)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from loguru import logger

from api.services.integrations.connectors import outil
from api.services.workflow import parole_de_la_fiche as PF


@pytest.fixture
def journal():
    lignes: list[str] = []
    identifiant = logger.add(lambda m: lignes.append(m.record["message"]), level="ERROR")
    yield lignes
    logger.remove(identifiant)


def test_connecteur_de_l_etape_illisible_est_journalise(monkeypatch, journal):
    def casse(*_a, **_k):
        raise RuntimeError("Paul 0612345678")

    monkeypatch.setattr("api.services.workflow.cases_selon_l_etat._connecteur_de", casse)
    assert PF._connecteur_de_l_etape(object()) is None
    # La ligne écrite par le code (la première) ne dit ni nom ni numéro ; le filtre de la production (``enrich_log_record``, posé à l'import de ``api.app`` hors
    # test) colle ensuite la pile au message, numéros masqués : le texte de l'exception y reste (décision du lot 4), il n'est pas la ligne du code.
    ligne = journal[0].splitlines()[0] if journal else ""
    assert len(journal) == 1 and "[parole]" in ligne and "Paul" not in ligne and "0612" not in ligne, journal


def test_annonce_non_jugee_est_journalisee(monkeypatch, journal):
    def casse(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr("api.services.workflow.verite_des_actions.regle_de_l_action_faite", casse)
    assert PF.annonce_non_fondee("Votre commande est enregistrée.", {"enregistree": False}) is False
    assert len(journal) == 1 and "[parole]" in journal[0], journal


def test_nom_non_retire_est_journalise(monkeypatch, journal):
    monkeypatch.setattr(PF, "CHEMINS_DU_NOM", None)
    assert PF.sans_le_nom("Paul, c'est noté.", [None]) == "Paul, c'est noté." and len(journal) == 1, journal


def test_nom_vu_non_retenu_et_action_locale_illisible_sont_journalises(monkeypatch, journal):
    monkeypatch.setattr(outil, "config_de", lambda _tool: (_ for _ in ()).throw(RuntimeError("boom")))
    outil.retenir_le_nom({}, SimpleNamespace(), "outil")
    assert outil.action_locale(SimpleNamespace()) is False
    assert len(journal) == 2 and all("[outil]" in ligne for ligne in journal), journal
