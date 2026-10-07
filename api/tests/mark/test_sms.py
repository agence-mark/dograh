"""[.mark] Non-regression test for the SMS after the call (chantier l-agent-travaille, L6; plan
sms-recapitulatif D1 to D11).

The questions this file answers:

    Off by default, does an agent never send an SMS? Switched on, does a call that ends go
    through the REAL ``process_workflow_completion`` to exactly one SMS per recipient, through
    the client's Twilio account, with the text filled by the record and never longer than 160
    characters? Is a call without a reason, or a caller on a landline, left without an SMS?
    Retried, does the chain never send twice? Refused by Twilio, is the step red and final,
    with the token never in an error? Are the counter and the preview scoped to the
    organization? Does the schema refuse what cannot work (no text, landline, sender name)?

The Twilio is a stand-in (``httpx.MockTransport``): no SMS leaves the machine.
"""

from __future__ import annotations

import copy
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
import pytest

from api.schemas.apres_appel import (
    ApresAppelAgent,
    SmsAgent,
    est_un_mobile,
    numero_e164,
)
from api.services.apres_appel import chaine, sms
from api.tests.mark.test_apres_appel import (
    _app,
    _executer_tout_de_suite,
    _organisation,
    _regler,
    _run,
    base_v4,  # noqa: F401  (fixture)
    modele,  # noqa: F401  (fixture)
    smtp,  # noqa: F401  (fixture)
)
from api.tests.mark.test_base_client import base_essai  # noqa: F401  (fixture)

JETON_TWILIO = "jeton-twilio-de-test-0123456789"
TEXTE_APPELANT = "{{nom}}, nous avons bien noté votre demande : {{motif}}. On vous rappelle sous 48 h."
TEXTE_EQUIPE = "Nouvel appel : {{nom}}, {{motif}}."


class FauxTwilio:
    def __init__(self, statut: int = 201):
        self.recus: list[dict] = []
        self.statut = statut

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        corps = {k: v[0] for k, v in parse_qs(requete.content.decode()).items()}
        self.recus.append(
            {
                "url": str(requete.url),
                "auth": requete.headers.get("Authorization"),
                **corps,
            }
        )
        if self.statut >= 400:
            return httpx.Response(
                self.statut,
                json={"code": 21211, "message": "Invalid 'To' Phone Number"},
            )
        return httpx.Response(201, json={"sid": f"SM{len(self.recus)}"})


@pytest.fixture
def twilio():
    faux = FauxTwilio()
    with patch.object(
        sms,
        "nouveau_client",
        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
    ):
        yield faux


async def _sms_allume(
    async_session,
    db_session,
    base,
    smtp_,
    *,
    appelant=True,
    equipe=True,
    expediteur="ESSAILOCAL",
):
    org = await _organisation(async_session, db_session, modules=["sms"])
    org.definition.workflow_configurations = {
        **org.definition.workflow_configurations,
        "apres_appel": ApresAppelAgent(
            actif=True,
            mail=False,
            synthese=False,
            modules=["sms"],
            sms=SmsAgent(
                expediteur=expediteur,
                appelant={"actif": appelant, "texte": TEXTE_APPELANT},
                equipe={
                    "actif": equipe,
                    "texte": TEXTE_EQUIPE,
                    "numeros": ["07 11 22 33 44"],
                },
            ),
        ).model_dump(),
    }
    await async_session.flush()
    await _regler(db_session, org, base, smtp_)
    await db_session.create_telephony_configuration(
        organization_id=org.organisation.id,
        name="Twilio du client",
        provider="twilio",
        credentials={"account_sid": "ACessai0001", "auth_token": JETON_TWILIO},
        is_default_outbound=True,
    )
    return org


async def test_sms_par_le_vrai_process_workflow_completion(
    base_v4, smtp, modele, twilio, db_session, async_session
):  # noqa: F811
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _sms_allume(async_session, db_session, base_v4, smtp)
    run = await _run(db_session, org, numero="+33612345678")
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)

    etape = (await db_session.lire_apres_appel(run.id))["etapes"]["module:sms"]
    assert etape["statut"] == "ok", etape
    assert sorted(r["To"] for r in twilio.recus) == ["+33612345678", "+33711223344"]
    a_l_appelant = next(r for r in twilio.recus if r["To"] == "+33612345678")
    assert (
        a_l_appelant["Body"]
        == "Dupont, nous avons bien noté votre demande : entretien de l'appareil. On vous rappelle sous 48 h."
    )
    assert (
        a_l_appelant["From"] == "ESSAILOCAL"
        and "/Accounts/ACessai0001/Messages.json" in a_l_appelant["url"]
    )
    assert all(len(r["Body"]) <= 160 for r in twilio.recus)

    # Retried (the safety net): nothing sent twice; one action row per SMS in the client's base.
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite(file)):
        await chaine.executer(run.id, ["module:sms"], 2)
    assert len(twilio.recus) == 2
    from api.db.bases_clients import connexion as schema

    connexion = await schema.connecter(base_v4)
    try:
        lignes = await connexion.fetch(
            "SELECT canal, destinataire FROM mark.action WHERE canal = 'sms' ORDER BY destinataire"
        )
        assert [tuple(l) for l in lignes] == [
            ("sms", "+33612345678"),
            ("sms", "+33711223344"),
        ]
    finally:
        await connexion.close()
    assert await db_session.compter_sms(org.agent.id) == 2


async def test_eteint_par_defaut_aucun_sms(
    base_v4, smtp, modele, twilio, db_session, async_session
):  # noqa: F811
    org = await _organisation(async_session, db_session)  # after-call on, no SMS module
    await _regler(db_session, org, base_v4, smtp)
    run = await _run(db_session, org)
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite([])):
        await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite([]))
    assert "module:sms" not in (await db_session.lire_apres_appel(run.id)).get(
        "etapes", {}
    )
    assert twilio.recus == []
    assert ApresAppelAgent().model_dump()["sms"]["appelant"]["actif"] is False


async def test_sans_motif_ou_fixe_pas_de_sms(
    base_v4, smtp, modele, twilio, db_session, async_session
):  # noqa: F811
    org = await _sms_allume(async_session, db_session, base_v4, smtp, equipe=False)
    # A landline presented, no call-back number: no SMS to the caller (D4).
    run = await _run(db_session, org, numero="+33344556677")
    await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite([]))
    etape = (await db_session.lire_apres_appel(run.id))["etapes"]["module:sms"]
    assert etape["statut"] == "ignoree" and "mobile" in etape["detail"]
    # The call-back number of the record, a mobile, is taken instead.
    run = await _run(db_session, org, numero="+33344556677")
    contexte = copy.deepcopy(run.gathered_context)
    contexte["extracted_variables"]["numero_rappel"] = "06 98 76 54 32"
    await db_session.update_workflow_run(run.id, gathered_context=contexte)
    await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite([]))
    assert [r["To"] for r in twilio.recus] == ["+33698765432"], (
        await db_session.lire_apres_appel(run.id)
    )
    # No reason in the record (D5): nobody asked anything.
    run = await _run(db_session, org)
    contexte = copy.deepcopy(run.gathered_context)
    contexte["extracted_variables"] = {"nom": "Dupont"}
    await db_session.update_workflow_run(run.id, gathered_context=contexte)
    await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite([]))
    etape = (await db_session.lire_apres_appel(run.id))["etapes"].get(
        "module:sms"
    ) or {}
    assert len(twilio.recus) == 1 and etape.get("statut") in ("ignoree", None)


async def test_refus_twilio_rouge_definitif_jeton_jamais_dans_l_erreur(
    base_v4, smtp, modele, db_session, async_session
):  # noqa: F811
    faux = FauxTwilio(statut=400)
    org = await _sms_allume(async_session, db_session, base_v4, smtp, appelant=False)
    run = await _run(db_session, org)
    with patch.object(
        sms,
        "nouveau_client",
        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
    ):
        await chaine.demarrer(run.id, enqueue=await _executer_tout_de_suite([]))
    etape = (await db_session.lire_apres_appel(run.id))["etapes"]["module:sms"]
    assert etape["statut"] == "echec" and etape["definitive"] is True
    assert "21211" in etape["detail"] and JETON_TWILIO not in str(etape)
    assert etape["notifie_a"] == ["alerte@example.org"]


async def test_compteur_et_apercu_cloisonnes(
    base_v4, smtp, modele, twilio, db_session, async_session
):  # noqa: F811
    org = await _sms_allume(async_session, db_session, base_v4, smtp)
    autre = await _organisation(async_session, db_session)
    await _run(db_session, org)
    async with _app(org.utilisateur) as c:
        r = await c.post(
            f"/workflow/{org.agent.id}/sms/apercu", json={"texte": TEXTE_EQUIPE}
        )
        assert (
            r.status_code == 200
            and r.json()["texte"] == "Nouvel appel : Dupont, entretien de l'appareil."
        )
        assert r.json()["parties"] == 1
        assert (await c.get(f"/workflow/{org.agent.id}/sms")).json() == {"envoyes": 0}
        assert (await c.get(f"/workflow/{autre.agent.id}/sms")).status_code == 404
        assert (
            await c.post(f"/workflow/{autre.agent.id}/sms/apercu", json={"texte": "x"})
        ).status_code == 404


def test_schema_refuse_ce_qui_ne_peut_pas_marcher():
    with pytest.raises(ValueError, match="needs its text"):
        SmsAgent(appelant={"actif": True})
    with pytest.raises(ValueError, match="not a French mobile"):
        SmsAgent(equipe={"actif": True, "texte": "x", "numeros": ["01 44 55 66 77"]})
    with pytest.raises(ValueError, match="one number at least"):
        SmsAgent(equipe={"actif": True, "texte": "x"})
    with pytest.raises(ValueError, match="sender name"):
        SmsAgent(expediteur="NUANCES DE FEU")
    assert numero_e164("0033 6 12 34 56 78") == "+33612345678" and est_un_mobile(
        "+33712345678"
    )
    assert not est_un_mobile(
        "+447700900123"
    )  # a foreign number is not taken (no phonenumbers)


def test_texte_rempli_coupe_a_160_et_parties():
    texte, coupe = sms.remplir("{{a}} " * 60, {"a": "mot"})
    assert coupe and len(texte) <= 160 and texte.endswith("…")
    assert sms.parties("Rappel demandé à 9 h") == (1, "gsm7")
    assert sms.parties("ô" * 71) == (2, "ucs2")
