"""[.mark] Clôture, SA-3 (D18) : le délai Twilio de la panne (côté organisation) et la liste des issues sans SMS sont réglables.

| Test | Ce qu'il prouve |
|---|---|
| défauts | les valeurs d'avant (6 s, 24 h, 10 min ; la liste de onze issues) |
| bornes | une faute de frappe est refusée |
| délai Twilio | le délai posé est celui de la requête vers Twilio (renvoi, journal d'appels, adresse) |
| rattrapage | la fenêtre et l'attente posées sont celles du rattrapage |
| issues sans SMS | une issue ajoutée ne part plus, une issue retirée repart (le moteur lit le réglage) |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from api.schemas.apres_appel import ISSUES_SANS_SMS_PAR_DEFAUT, ReglagesApresAppel
from api.schemas.panne import ReglagesPanne
from api.services.apres_appel import sms
from api.services.panne import rattrapage, twilio


def test_les_defauts_sont_les_valeurs_d_avant():
    p = ReglagesPanne()
    assert (p.delai_twilio_s, p.rattrapage_fenetre_h, p.rattrapage_attente_run_min) == (6.0, 24, 10)
    assert ReglagesApresAppel().issues_sans_sms == ISSUES_SANS_SMS_PAR_DEFAUT and len(ISSUES_SANS_SMS_PAR_DEFAUT) == 11


@pytest.mark.parametrize("champ, mauvaise", [("delai_twilio_s", 0), ("delai_twilio_s", 600), ("rattrapage_fenetre_h", 0), ("rattrapage_fenetre_h", 9999), ("rattrapage_attente_run_min", 0)])
def test_une_faute_de_frappe_est_refusee(champ, mauvaise):
    with pytest.raises(ValidationError):
        ReglagesPanne(**{champ: mauvaise})
    with pytest.raises(ValidationError):
        ReglagesApresAppel(issues_sans_sms=["x" * 60])


async def test_le_delai_twilio_pose_est_celui_de_la_requete(monkeypatch):
    vus = []

    def client(**options):
        vus.append(options.get("timeout"))
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"calls": [], "incoming_phone_numbers": []})), **options)

    monkeypatch.setattr(twilio, "nouveau_client", client)
    await twilio.mettre_a_jour_appel("AC1", "jeton", "CA1", "<Response/>", 12.5)
    await twilio.appels_entrants("AC1", "jeton", "+33100000000", datetime.now(UTC), delai=7.0)
    await twilio.ecrire_adresse_de_secours("AC1", "jeton", "+33100000000", None, 9.0)
    assert vus == [12.5, 7.0, 9.0]
    vus.clear()
    await twilio.mettre_a_jour_appel("AC1", "jeton", "CA1", "<Response/>")
    assert vus == [twilio.DELAI_S]  # sans réglage : la valeur d'avant


async def test_l_attente_du_rattrapage_pose_est_celle_lue(monkeypatch):
    class Run:
        is_completed = False
        state = "running"
        created_at = datetime.now(UTC) - timedelta(minutes=20)

    async def run_par_appel(org, sid):
        return Run()

    monkeypatch.setattr(rattrapage.db_client, "run_par_appel", run_par_appel)
    appel = {"direction": "inbound", "status": "completed", "sid": "CA1"}
    maintenant = datetime.now(UTC)
    assert await rattrapage._perdu(1, appel, maintenant, 10) is True  # 20 min > 10 min : perdu
    assert await rattrapage._perdu(1, appel, maintenant, 60) is False  # 20 min < 60 min : encore en cours


def test_une_issue_ajoutee_ne_part_plus_une_issue_retiree_repart():
    envoi = {"motif": "Une demande", "issue": "Rendez-vous pris"}
    assert sms.sans_objet(envoi, ReglagesApresAppel().issues_sans_sms) is None
    ajoutee = ReglagesApresAppel(issues_sans_sms=[*ISSUES_SANS_SMS_PAR_DEFAUT, "rendez-vous"]).issues_sans_sms
    assert "no SMS" in sms.sans_objet(envoi, ajoutee)
    repondeur = {"motif": "Une demande", "issue": "répondeur"}
    assert sms.sans_objet(repondeur, ["busy"]) is None  # retirée : le SMS repart
    assert sms.sans_objet(repondeur) is not None  # sans réglage lu : la valeur d'avant
