"""[.mark] Clôture, lot C (D18) : les valeurs de l'après-appel qui étaient des constantes du code sont réglables (avancé).

| Test | Ce qu'il prouve |
|---|---|
| défauts | chaque réglage vaut ce que valait la constante d'avant |
| bornes | une faute de frappe (0, un million, négatif) est refusée à l'enregistrement |
| synthèse | la température, la longueur et le délai posés sont ceux envoyés au modèle |
| mail, webhook, SMS | le délai posé est celui de l'appel |
| reprises | le nombre de tentatives et les deux délais posés sont ceux de la chaîne (vraie base) |
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from api.enums import OrganizationConfigurationKey
from api.schemas.apres_appel import ReglagesApresAppel, ReglagesReprises, ReglagesSmtp, ReglagesSynthese, ReglagesWebhook
from api.services.apres_appel import chaine, mail, modules, sms, synthese
from api.tests.mark.test_apres_appel import (  # noqa: F401
    SECRET_WEBHOOK,
    _equipe,
    _executer_tout_de_suite,
    _organisation,
    _regler,
    _run,
    base_essai,  # noqa: F401  (fixture de base_v4)
    base_v4,
    modele,
    smtp,
)


def test_les_defauts_sont_les_valeurs_d_avant():
    r = ReglagesApresAppel()
    assert (r.synthese.delai_s, r.synthese.temperature, r.synthese.longueur_max) == (30.0, 0.2, 400)
    assert (r.smtp.delai_s, r.webhook.delai_s, r.delai_sms_s) == (20, 10.0, 15.0)
    assert (r.reprises.tentatives_max, r.reprises.delai_1_s, r.reprises.delai_2_s) == (3, 60, 300)


@pytest.mark.parametrize(
    "modele_, champ, mauvaise",
    [
        (ReglagesSynthese, "delai_s", 0),
        (ReglagesSynthese, "delai_s", 100000),
        (ReglagesSynthese, "temperature", 2),
        (ReglagesSynthese, "temperature", -0.1),
        (ReglagesSynthese, "longueur_max", 5),
        (ReglagesSynthese, "longueur_max", 10**6),
        (ReglagesSmtp, "delai_s", 0),
        (ReglagesWebhook, "delai_s", 9999),
        (ReglagesReprises, "tentatives_max", 0),
        (ReglagesReprises, "tentatives_max", 50),
        (ReglagesReprises, "delai_1_s", 1),
        (ReglagesReprises, "delai_2_s", 10**7),
    ],
)
def test_une_faute_de_frappe_est_refusee(modele_, champ, mauvaise):
    with pytest.raises(ValidationError):
        modele_(**{champ: mauvaise})
    with pytest.raises(ValidationError):
        ReglagesApresAppel(delai_sms_s=0)


async def test_la_synthese_envoie_les_valeurs_posees():
    vus = {}

    def repondre(requete: httpx.Request):
        import json

        vus["corps"] = json.loads(requete.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Un résumé."}}], "usage": {}})

    def client(**options):
        vus["delai"] = options.get("timeout")
        return httpx.AsyncClient(transport=httpx.MockTransport(repondre), **options)

    reglages = ReglagesSynthese(consigne="Résume.", delai_s=44, temperature=0.7, longueur_max=900)
    with patch.object(synthese, "nouveau_client", client):
        await synthese.resumer("cle", reglages, [{"text": "bonjour", "role": "user"}], {})
    assert vus["corps"]["temperature"] == 0.7 and vus["corps"]["max_tokens"] == 900
    assert vus["delai"] == 44


def test_le_mail_prend_le_delai_pose():
    import smtplib

    vus = []

    class Faux:
        def __init__(self, *a, **k):
            vus.append(k.get("timeout"))
            raise RuntimeError("arrêt")

    for securite in ("aucune", "ssl"):
        reglage = ReglagesSmtp(hote="h", expediteur="a@b.fr", securite=securite, delai_s=37)
        with patch.object(smtplib, "SMTP", Faux), patch.object(smtplib, "SMTP_SSL", Faux), pytest.raises(RuntimeError):
            mail._envoyer(reglage, None, None)
    assert vus == [37, 37]


async def test_le_sms_et_le_webhook_prennent_le_delai_pose():
    vus = {}

    def client(**options):
        vus.setdefault("delais", []).append(options.get("timeout"))
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(201, json={"sid": "SM1"})), **options)

    with patch.object(sms, "nouveau_client", client):
        await sms.envoyer("AC1", "jeton", "+33612345678", "+33687654321", "Bonjour", delai_s=23)
        await sms.envoyer("AC1", "jeton", "+33612345678", "+33687654321", "Bonjour")
    assert vus["delais"] == [23, 15.0]  # posé, puis la valeur d'avant par défaut

    from types import SimpleNamespace

    contexte = SimpleNamespace(
        reglages=ReglagesApresAppel(webhook=ReglagesWebhook(url="https://x.example.org/h", delai_s=7.5)),
        organization_id=1,
        run=SimpleNamespace(id=1),
        envoi={},
    )
    vus2 = []

    def client2(**options):
        vus2.append(options.get("timeout"))
        raise RuntimeError("arrêt")

    async def secret(*a, **k):
        return "s"

    with patch.object(modules, "nouveau_client", client2), patch.object(modules, "secret", secret), patch.object(modules, "charge_utile", lambda c: {}):
        with pytest.raises(RuntimeError):
            await modules._webhook(contexte)
    assert vus2 == [7.5]


async def test_les_reprises_de_la_chaine_suivent_les_reglages(base_v4, smtp, modele, db_session, async_session):  # noqa: F811
    org = await _organisation(async_session, db_session, modules=["webhook"])
    await _regler(db_session, org, base_v4, smtp, webhook_url="https://webhook.example.org/fin")
    ligne = await db_session.get_configuration(org.organisation.id, OrganizationConfigurationKey.APRES_APPEL.value)
    posees = dict(ligne.value)
    posees["reprises"] = {"tentatives_max": 2, "delai_1_s": 77, "delai_2_s": 120}
    await db_session.upsert_configuration(org.organisation.id, OrganizationConfigurationKey.APRES_APPEL.value, posees)
    await _equipe(base_v4)
    run = await _run(db_session, org)

    file: list[dict] = []
    enqueue = await _executer_tout_de_suite(file)
    with patch(
        "api.services.apres_appel.modules.nouveau_client",
        lambda **options: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)), **options),
    ):
        await chaine.demarrer(run.id, enqueue=enqueue)
        etape = (await db_session.lire_apres_appel(run.id))["etapes"]["module:webhook"]
        assert etape["definitive"] is False
        assert [f["_defer_by"] for f in file if "_defer_by" in f] == [77]  # le délai posé, pas 60
        await chaine.executer(run.id, ["module:webhook"], 2, enqueue=enqueue)
    etape = (await db_session.lire_apres_appel(run.id))["etapes"]["module:webhook"]
    assert etape["definitive"] is True  # la 2e tentative est la dernière (trois par défaut)
