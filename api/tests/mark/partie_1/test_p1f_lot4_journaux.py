"""[.mark] Plan final Partie 1, lot 4 (n° 103 et 104) : un numéro de téléphone ne sort d'aucun journal, quelle que soit la ligne qui l'écrit.

Avant : le masque était posé ligne par ligne (14 appels de ``masquer_numero``) et trois fonctions donnaient trois formats. Règle : un filtre global de loguru
(``enrich_log_record``) masque tout numéro, au format ``***78``, une seule fonction (``masquer_numero``).
"""

from __future__ import annotations

import logging

import pytest
from loguru import logger

from api.logging_config import enrich_log_record
from api.services.equipe import transferts_humains as TH
from api.utils.masque_des_journaux import MasquerLeJetonDuFlux, masquer_les_numeros


def _ce_que_le_journal_ecrit(ecrire) -> list[str]:
    lignes: list[str] = []
    sortie = logger.add(lambda m: lignes.append(m.record["message"]), level="DEBUG")
    try:
        ecrire(logger.patch(enrich_log_record))
    finally:
        logger.remove(sortie)
    return lignes


@pytest.mark.parametrize("numero", ["+33612345678", "06 12 34 56 78", "06.12.34.56.78", "0612345678", "+33 6 12 34 56 78", "0033612345678", "+442071838750"])
def test_un_numero_ecrit_par_n_importe_quelle_ligne_sort_masque(numero):
    lignes = _ce_que_le_journal_ecrit(lambda l: (
        l.info(f"Incoming call from {numero} to the line"), l.warning(f"caller={numero}, called=+33344000099"), l.error(f"(numero: {numero})")))
    brut = "".join(c for c in numero if c.isdigit())
    for ligne in lignes:
        assert "***" in ligne
        assert brut[-6:] not in "".join(c for c in ligne if c.isdigit()), ligne


def test_ce_qui_n_est_pas_un_numero_n_est_pas_touche():
    for texte in ("run 123456 started at 2026-11-24 03:32:52.981", "order 8f0d6c64-6d62-4a42-9c0e-0c1c2c3c4c5c total 1250", "agent 42 workflow 7 ws/12/3/456"):
        assert masquer_les_numeros(texte) == texte


def test_un_appel_joue_puis_son_journal_balaye_ne_porte_aucun_numero():
    """Un appel entrant simulé : les lignes que le code des opérateurs écrit (appelant, appelé, sortant) passent toutes par le même filtre."""
    appelant = "+33612345678"

    def jouer(l):
        l.info(f"[ARI] Stasis start channel=1 (caller={appelant}, called=+33344000099)")
        l.info(f"Inbound call accepted to=+33344000099 from={appelant} provider=twilio")
        l.info(f"Selected phone number +33344000099 for outbound call to {appelant}")
        l.info(f"[Exotel] Initiating call to=0612345678 from=0344000099 run=5")

    lignes = _ce_que_le_journal_ecrit(jouer)
    assert len(lignes) == 4 and not any("612345678" in l or "33612345678" in l for l in lignes)
    assert all("***78" in l or "***99" in l for l in lignes)


def test_le_journal_d_acces_d_uvicorn_masque_aussi_les_numeros():
    enregistrement = logging.LogRecord("uvicorn.access", logging.INFO, "x", 1, "GET /voix/+33612345678 200", (), None)
    MasquerLeJetonDuFlux().filter(enregistrement)
    assert "612345678" not in enregistrement.getMessage() and "***78" in enregistrement.getMessage()


def test_le_masque_de_la_fiche_de_transfert_passe_par_la_meme_fonction():
    assert TH.masquer("+33344000099") == "numero:***0099" and TH.masquer("") == "numero:***" and TH.masquer("12") == "numero:***"


def test_un_numero_cite_par_une_exception_ou_un_champ_extra_sort_masque():
    """Le ``DETAIL`` d'une erreur asyncpg cite la ligne en cause (un numéro) : le texte de l'exception et sa pile sortent masqués, comme les champs ``extra``."""
    vues: list[str] = []
    sortie = logger.add(lambda m: vues.append(str(m) + "|" + str(m.record["extra"].get("telephone"))), level="DEBUG")  # ``str(m)`` : la ligne écrite, exception comprise
    try:
        l = logger.patch(enrich_log_record)
        try:
            raise ValueError("duplicate key: DETAIL: Key (telephone)=(+33612345678) already exists.")
        except ValueError:
            l.bind(telephone="+33698765432").exception("[.mark] write failed")
    finally:
        logger.remove(sortie)
    texte = "\n".join(vues)
    assert "612345678" not in texte and "698765432" not in texte
    assert "***78" in texte and "***32" in texte and "ValueError" in texte  # la pile et le type restent lisibles


def test_le_journal_d_acces_standard_masque_aussi_l_exception():
    try:
        raise ValueError("Key (telephone)=(+33612345678)")
    except ValueError:
        import sys

        enregistrement = logging.LogRecord("x", logging.ERROR, "x", 1, "echec", (), sys.exc_info())
    MasquerLeJetonDuFlux().filter(enregistrement)
    assert enregistrement.exc_info is None and "612345678" not in enregistrement.exc_text and "***78" in enregistrement.exc_text
