"""[.mark] Clôture, SA-3 (D18) : la vérification de l'appelant, ses essais, son code et sa durée sont réglables (avancé).

| Test | Ce qu'il prouve |
|---|---|
| défauts | chaque réglage vaut ce que valait la constante d'avant (2 essais, 6 chiffres, 10 minutes) |
| bornes | une faute de frappe (0, 99, durée d'un jour) est refusée à l'enregistrement |
| essais | avec 3 essais, le troisième échec seulement bloque (vraie base, vrai moteur) |
| code | la longueur et la durée posées sont celles du SMS envoyé et de l'expiration gardée |
"""

from __future__ import annotations

import re
import time
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.schemas.verification import NiveauLecture, ReglagesVerification
from api.services.verification import etat as etats
from api.tests.mark.test_verification_appelant import (  # noqa: F401
    UN_FACTEUR,
    DUPONT,
    _appeler,
    _pret,
    _regler,
    installe,
    base_v4,
    base_essai,
    modele,
    smtp,
)


def test_les_defauts_sont_les_valeurs_d_avant():
    r = ReglagesVerification()
    assert (r.tentatives_max, r.code_longueur, r.code_validite_s) == (2, 6, 600)


@pytest.mark.parametrize("champ, mauvaise", [("tentatives_max", 0), ("tentatives_max", 99), ("code_longueur", 2), ("code_longueur", 40), ("code_validite_s", 5), ("code_validite_s", 86400)])
def test_une_faute_de_frappe_est_refusee(champ, mauvaise):
    with pytest.raises(ValidationError):
        ReglagesVerification(**{champ: mauvaise})


async def test_trois_essais_regles_bloquent_au_troisieme_echec(installe, monkeypatch):
    await _regler(installe, numero=False, lisibles=UN_FACTEUR, tentatives_max=3)
    _engine, verifier, _lire = await _pret(installe, monkeypatch)
    r = await _appeler(verifier, {"nom": "Durand", "code_postal": "60100"})
    assert r["status"] == "not_verified" and r["attempts_left"] == 2
    r = await _appeler(verifier, {"nom": "Durand", "code_postal": "60100"})
    assert r["status"] == "not_verified" and r["attempts_left"] == 1  # avec le réglage d'avant, bloqué ici
    r = await _appeler(verifier, {"nom": "Durand", "code_postal": "60100"})
    assert r["status"] == "blocked"


async def test_la_longueur_et_la_duree_du_code_sont_celles_posees(installe, monkeypatch):
    from api.services.apres_appel import sms
    from api.services.telephony import factory

    envoyes = []

    async def envoyer(sid, jeton, expediteur, destinataire, texte):
        envoyes.append(texte)
        return "SM1"

    monkeypatch.setattr(sms, "envoyer", envoyer)
    monkeypatch.setattr(factory, "get_telephony_provider_for_run", AsyncMock(return_value=SimpleNamespace(
        account_sid="AC1", auth_token="jeton", default_from_number="+33900000000")))
    await _regler(installe, numero=False, question=False, code_sms=True, code_longueur=8, code_validite_s=300,
                  lisibles={"demandes": NiveauLecture(facteurs_requis=1, champs=["statut"])})
    _e, verifier, _lire = await _pret(installe, monkeypatch)
    avant = time.time()
    r = await _appeler(verifier, {"envoyer_code": True})
    assert r["code"] == "sent"
    [texte] = envoyes
    assert re.search(r": \d{8}\.", texte) and "expire dans 5 minutes" in texte
    etat = await etats.charger(installe.org.organisation.id, installe.run.id)
    assert 290 <= etat.code_expire - avant <= 310
