"""Le numéro de l'appelant ne sort jamais en entier d'un journal technique (Evan, 23/11, point 1 de Tiao).

La base et le portail gardent le numéro entier ; seuls les journaux le masquent : deux derniers
chiffres, et l'identifiant de l'appel écrit sur la même ligne. Le masque est un filtre global de loguru
(``enrich_log_record``), jamais un geste ligne par ligne : ``test_p1f_lot4_journaux.py`` le joue. Le jeton du flux audio sort du
journal d'accès d'uvicorn.
"""

import logging
import re
from pathlib import Path

import pytest

from api.utils.masque_des_journaux import (
    MasquerLeJetonDuFlux,
    masquer_jeton_du_flux,
    masquer_numero,
)

RACINE = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "numero, attendu",
    [
        ("+33612345678", "***78"),
        ("06 12 34 56 78", "***78"),
        ("0033612345678", "***78"),
        ("5", "***5"),
        ("unknown", "unknown"),
        ("", ""),
        (None, ""),
    ],
)
def test_le_numero_ne_garde_que_deux_chiffres(numero, attendu):
    assert masquer_numero(numero) == attendu


def test_aucun_numero_complet_ne_survit_au_masque():
    for numero in ("+33612345678", "0612345678", "+442071838750"):
        assert re.search(r"\d{3,}", masquer_numero(numero)) is None
        assert numero.lstrip("+") not in masquer_numero(numero)


def test_le_jeton_du_flux_sort_du_journal_d_acces():
    jeton = "a" * 64
    ligne = f'WebSocket /api/v1/telephony/ws/12/3/456/{jeton} [accepted]'
    masque = masquer_jeton_du_flux(ligne)
    assert jeton not in masque
    assert "/api/v1/telephony/ws/12/3/456/***" in masque
    assert "token=***" in masquer_jeton_du_flux(f"GET /x?token={jeton} HTTP/1.1")
    # sans jeton : rien ne change
    sans = "WebSocket /api/v1/telephony/ws/12/3/456 [accepted]"
    assert masquer_jeton_du_flux(sans) == sans


def test_le_filtre_d_acces_reecrit_l_enregistrement():
    jeton = "b" * 64
    enregistrement = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "WebSocket %s" [accepted]', ("1.2.3.4:5", f"/api/v1/telephony/ws/1/2/3/{jeton}"), None,
    )
    assert MasquerLeJetonDuFlux().filter(enregistrement) is True
    assert jeton not in enregistrement.getMessage()


def test_uvicorn_porte_le_filtre_apres_la_mise_en_place_des_journaux():
    source = (RACINE / "logging_config.py").read_text(encoding="utf8")
    assert "addFilter(MasquerLeJetonDuFlux())" in source
