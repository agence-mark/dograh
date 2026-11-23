"""Le numéro de l'appelant ne sort jamais en entier d'un journal technique (Evan, 23/11, point 1 de Tiao).

La base et le portail gardent le numéro entier ; seuls les journaux le masquent : deux derniers
chiffres, et l'identifiant de l'appel écrit sur la même ligne. Le jeton du flux audio sort du
journal d'accès d'uvicorn.
"""

import ast
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

# Une valeur écrite dans un journal qui porte le numéro d'une personne (appelant, ou personne appelée
# par nous), tel que le code la nomme.
NUMERO_DE_PERSONNE = re.compile(
    r"caller_number|caller\.get|from_number|to_number|phone_number|\.number\b|\bnumero_appelant\b"
)

# Les numéros de NOTRE côté (la ligne du restaurant, celle que le client a branchée) ne sont pas ceux
# d'une personne : (fichier, valeur écrite dans la ligne de journal).
NUMEROS_DE_LA_LIGNE = {
    ("routes/telephony.py", "normalized_data.to_number"),
    ("routes/telephony.py", "phone_number"),
    ("db/telephony_phone_number_client.py", "to_number"),
    ("db/telephony_phone_number_client.py", "phone_number.id"),
    ("db/telephony_phone_number_client.py", "phone_number.address"),
    ("db/telephony_phone_number_client.py", "phone_number.inbound_workflow_id"),
}
# Un appel sortant part de la ligne de l'organisation : son `from_number` est la ligne du restaurant.
LIGNE_SORTANTE = "services/telephony/providers/"


def _fichiers():
    for chemin in RACINE.rglob("*.py"):
        parties = chemin.relative_to(RACINE).parts
        if parties[0] in {"tests", "alembic", "venv", ".venv"} or ".venv" in parties:
            continue
        yield chemin


def _valeurs_ecrites_au_journal():
    for chemin in _fichiers():
        source = chemin.read_text(encoding="utf8")
        if "logger." not in source:
            continue
        try:
            arbre = ast.parse(source)
        except SyntaxError:
            continue
        relatif = chemin.relative_to(RACINE).as_posix()
        for noeud in ast.walk(arbre):
            if not (
                isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and isinstance(noeud.func.value, ast.Name)
                and noeud.func.value.id == "logger"
            ):
                continue
            ligne_complete = ast.get_source_segment(source, noeud) or ""
            for sous in ast.walk(noeud):
                if isinstance(sous, ast.FormattedValue):
                    yield relatif, sous.lineno, ast.get_source_segment(source, sous.value) or "", ligne_complete


def test_aucun_numero_de_personne_en_clair_dans_un_journal():
    fautes = []
    for relatif, ligne, valeur, ligne_complete in _valeurs_ecrites_au_journal():
        if not NUMERO_DE_PERSONNE.search(valeur) or "masquer_numero(" in valeur:
            continue
        if (relatif, valeur) in NUMEROS_DE_LA_LIGNE:
            continue
        if relatif.startswith(LIGNE_SORTANTE) and valeur == "from_number":
            continue
        fautes.append(f"{relatif}:{ligne}  {{{valeur}}}")
    assert not fautes, "numéro en clair dans un journal (le passer par masquer_numero) :\n" + "\n".join(fautes)


def test_la_garde_voit_un_numero_en_clair(tmp_path, monkeypatch):
    """Vu rouge : la même garde sur un fichier fautif."""
    fautif = "from loguru import logger\nlogger.info(f'appel de {caller_number}')\n"
    arbre = ast.parse(fautif)
    valeurs = [
        ast.get_source_segment(fautif, n.value)
        for n in ast.walk(arbre)
        if isinstance(n, ast.FormattedValue)
    ]
    assert valeurs == ["caller_number"] and NUMERO_DE_PERSONNE.search(valeurs[0])


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
