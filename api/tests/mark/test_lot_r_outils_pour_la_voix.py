"""[.mark] Builder partie 3, lot R : ce que l'outil dit au modèle (R1), ce qu'il renvoie (R2), la relance du silence (R3).

| Test | Ce qu'il prouve |
|---|---|
| échec en mots de voix (C4) | chaque échec porte ``a_dire_au_client`` : jamais « bug, erreur, système, connexion » ; réglable par outil ; traverse le vrai gestionnaire |
| consigne de parole (C6) | éteinte par défaut ; texte fixe ou consigne du service ; jamais sur un échec |
| résumé pour la voix (C7) | éteint par défaut ; 3 éléments, 1 200 caractères, champs retirés ; la fiche garde tout |
| champs appliqués et ignorés (C8) | d'après la réponse du logiciel, sinon d'après l'envoi ; une lecture n'est pas touchée ; réglable |
| relance à 0 | un délai de 0 ne relance jamais ; un délai positif relance (le moniteur réel) |
| verrou par appel (C11) | éteint par défaut ; deux appels du même outil (ou du même verrou) ne partent pas ensemble |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.schemas.tool import HttpApiConfig, IntegrationToolConfig
from api.services.outils_mark import pour_la_voix
from api.services.outils_mark.comportement import executer_avec_comportement
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.services.workflow.tools.custom_tool import execute_http_tool
from api.tests.mark.test_connecteurs import CONFIG_RDV, _appeler, _moteur, _outil as _outil_connecteur, faux_nango  # noqa: F401

MODULE = "api.services.workflow.tools.custom_tool"
MOTS_INTERDITS = ("bug", "erreur", "système", "systeme", "connexion", "error")


def _outil(**config):
    return SimpleNamespace(
        tool_uuid="u-r",
        name="Chercher",
        description="Cherche.",
        category="http_api",
        definition={
            "schema_version": 1,
            "type": "http_api",
            "config": {"method": "POST", "url": "https://agenda.example.test/x", "timeout_ms": 5000, **config},
        },
    )


def _reponse(code=200, corps=None):
    r = Mock(status_code=code, text="")
    r.json.return_value = corps if corps is not None else {"ok": True}
    return r


async def _par_le_vrai_gestionnaire(config, arguments=None, *, reponse_http=None, fiche=None):
    """Traverse le vrai gestionnaire de l'outil HTTP du moteur (``_create_http_tool_handler``), le service est
    remplacé par une réponse enregistrée. Rend (ce que le modèle reçoit, la fiche)."""
    gestionnaire = CustomToolManager.__new__(CustomToolManager)
    fiche = {} if fiche is None else fiche
    gestionnaire._engine = SimpleNamespace(_call_context_vars={}, _gathered_context=fiche)
    gestionnaire._agent = None
    gestionnaire.get_organization_id = AsyncMock(return_value=1)
    handler = gestionnaire._create_http_tool_handler(_outil(**config), "chercher")
    recu = AsyncMock()
    with patch(f"{MODULE}.httpx.AsyncClient") as client:
        session = AsyncMock()
        if isinstance(reponse_http, Exception):
            session.request.side_effect = reponse_http
        else:
            session.request.return_value = reponse_http or _reponse()
        client.return_value.__aenter__.return_value = session
        await handler(SimpleNamespace(arguments=arguments or {}, result_callback=recu))
    return recu.await_args.args[0], fiche


# --------------------------------------------------------------------------- C4


@pytest.mark.asyncio
async def test_un_echec_du_service_dit_au_modele_quoi_repondre_en_mots_de_voix():
    recu, _ = await _par_le_vrai_gestionnaire({}, {"jour": "demain"}, reponse_http=_reponse(500, {"detail": "boom"}))
    assert recu["status"] == "error"
    consigne = recu["a_dire_au_client"].casefold()
    assert consigne and not any(m in consigne for m in MOTS_INTERDITS)
    assert "n'annonce rien comme fait" in consigne


@pytest.mark.asyncio
async def test_un_refus_un_delai_et_une_valeur_a_corriger_ont_chacun_leur_consigne():
    refus, _ = await _par_le_vrai_gestionnaire({}, reponse_http=_reponse(422, {"detail": "x"}))
    assert refus["a_dire_au_client"] == pour_la_voix.CONSIGNES_D_ECHEC["refuse"]
    import httpx

    delai, _ = await _par_le_vrai_gestionnaire({}, reponse_http=httpx.ReadTimeout("lent"))
    assert delai["a_dire_au_client"] == pour_la_voix.CONSIGNES_D_ECHEC["delai"]
    params = [
        {"name": "ton", "type": "string", "description": "x", "valeurs_permises": ["court", "long"]},
    ]
    corriger, _ = await _par_le_vrai_gestionnaire({"parameters": params}, {"ton": "moyen"})
    assert corriger["a_dire_au_client"] == pour_la_voix.CONSIGNES_D_ECHEC["a_corriger"]
    for texte in pour_la_voix.CONSIGNES_D_ECHEC.values():
        assert not any(m in texte.casefold() for m in MOTS_INTERDITS)


@pytest.mark.asyncio
async def test_la_consigne_d_echec_est_reglable_par_outil_et_un_succes_n_en_porte_pas():
    propre = "Dis que le cabinet rappellera dans la journée."
    recu, _ = await _par_le_vrai_gestionnaire({"consigne_en_cas_d_echec": propre}, reponse_http=_reponse(503))
    assert recu["a_dire_au_client"] == propre
    ok, _ = await _par_le_vrai_gestionnaire({}, reponse_http=_reponse(200, {"id": 1}))
    assert "a_dire_au_client" not in ok


@pytest.mark.asyncio
async def test_apres_la_phrase_de_repli_la_consigne_ne_redit_rien():
    moteur = SimpleNamespace(queue_text_message=AsyncMock())

    async def echec():
        return {"status": "error", "error": "x"}

    r = await executer_avec_comportement(moteur, {"phrase_repli": "Je vous rappelle."}, "t", echec)
    assert r["said_to_caller"] == "Je vous rappelle."
    assert r["a_dire_au_client"] == pour_la_voix.CONSIGNES_D_ECHEC["deja_dit"]


# --------------------------------------------------------------------------- C6


@pytest.mark.asyncio
async def test_la_consigne_de_parole_est_eteinte_par_defaut():
    recu, _ = await _par_le_vrai_gestionnaire({}, reponse_http=_reponse(200, {"consigne_de_parole": "Dis ceci", "n": 2}))
    assert "consigne_de_parole" not in recu
    assert recu["data"]["consigne_de_parole"] == "Dis ceci"  # rien n'est retiré tant que le réglage est éteint


@pytest.mark.asyncio
async def test_la_consigne_de_parole_fixe_ou_du_service():
    fixe, _ = await _par_le_vrai_gestionnaire({"consigne_de_parole": "Annonce le nombre de résultats puis le premier."})
    assert fixe["consigne_de_parole"].startswith("Annonce le nombre")
    service, _ = await _par_le_vrai_gestionnaire(
        {"consigne_de_parole_du_service": True},
        reponse_http=_reponse(200, {"consigne_de_parole": "Dis que c'est réservé pour jeudi.", "n": 1}),
    )
    assert service["consigne_de_parole"] == "Dis que c'est réservé pour jeudi."
    assert "consigne_de_parole" not in service["data"]


@pytest.mark.asyncio
async def test_jamais_de_consigne_de_parole_sur_un_echec():
    recu, _ = await _par_le_vrai_gestionnaire(
        {"consigne_de_parole": "Dis que c'est fait."}, reponse_http=_reponse(500)
    )
    assert "consigne_de_parole" not in recu
    assert "fait" not in recu["a_dire_au_client"].replace("comme fait", "")


# --------------------------------------------------------------------------- C7


GROS = {
    "resultats": [{"nom": f"n{i}", "photo": "x" * 5000, "texte": "y" * 3000} for i in range(7)],
    "page": 1,
}


@pytest.mark.asyncio
async def test_le_resume_est_eteint_par_defaut():
    recu, _ = await _par_le_vrai_gestionnaire({}, reponse_http=_reponse(200, GROS))
    assert len(recu["data"]["resultats"]) == 7 and "resume_pour_la_voix" not in recu


@pytest.mark.asyncio
async def test_le_resume_garde_trois_elements_coupe_les_chaines_retire_les_champs_lourds_et_la_fiche_garde_tout():
    config = {"resume_pour_la_voix": True, "resume_champs_retires": ["photo"], "copies_dans_la_fiche": [{"chemin": "resultats.5.nom", "cle": "sixieme"}]}
    recu, fiche = await _par_le_vrai_gestionnaire(config, reponse_http=_reponse(200, GROS))
    donnees = recu["data"]
    assert len(donnees["resultats"]) == 3 and donnees["resultats_total"] == 7
    assert all("photo" not in e for e in donnees["resultats"])
    assert all(len(e["texte"]) <= 1201 and e["texte"].endswith("…") for e in donnees["resultats"])
    assert recu["resume_pour_la_voix"] == {"elements_ecartes": 4, "chaines_coupees": 3, "champs_retires": 3}
    assert fiche["sixieme"] == "n5"  # la copie dans la fiche est faite sur la réponse entière


def test_le_resume_est_reglable_et_une_liste_seule_garde_son_total():
    r = pour_la_voix.resume_pour_la_voix(
        {"status": "success", "data": list(range(10))}, {"resume_pour_la_voix": True, "resume_max_elements": 2}
    )
    assert r["data"] == {"total": 10, "elements": [0, 1]}
    echec = {"status": "error", "error": "x", "data": list(range(10))}
    assert pour_la_voix.resume_pour_la_voix(echec, {"resume_pour_la_voix": True}) == echec


# --------------------------------------------------------------------------- C8


@pytest.mark.asyncio
async def test_une_ecriture_dit_les_champs_ignores_d_apres_la_reponse_du_logiciel():
    params = [{"name": n, "type": "string", "description": "x"} for n in ("nom", "telephone", "email")]
    corps = {"id": 9, "nom": "Dupont", "telephone": "0600000000"}  # le logiciel n'a pas gardé l'e-mail
    recu, _ = await _par_le_vrai_gestionnaire(
        {"parameters": params}, {"nom": "Dupont", "telephone": "0600000000", "email": "a@b.test"}, reponse_http=_reponse(200, corps)
    )
    assert recu["champs_appliques"] == ["nom", "telephone"]
    assert recu["champs_ignores"] == ["email"]
    assert recu["champs_source"] == "reponse"


@pytest.mark.asyncio
async def test_le_logiciel_peut_dire_lui_meme_ce_qu_il_a_ignore():
    params = [{"name": n, "type": "string", "description": "x"} for n in ("a", "b", "c")]
    recu, _ = await _par_le_vrai_gestionnaire(
        {"parameters": params}, {"a": 1, "b": 2, "c": 3}, reponse_http=_reponse(200, {"ignored_fields": ["c"]})
    )
    assert recu["champs_ignores"] == ["c"] and recu["champs_appliques"] == ["a", "b"] and recu["champs_source"] == "reponse"


@pytest.mark.asyncio
async def test_sans_echo_les_champs_sont_comptes_d_apres_l_envoi_et_la_source_le_dit():
    params = [{"name": "nom", "type": "string", "description": "x"}]
    recu, _ = await _par_le_vrai_gestionnaire({"parameters": params}, {"nom": "Dupont"}, reponse_http=_reponse(200, {"ok": True}))
    assert recu["champs_appliques"] == ["nom"] and recu["champs_ignores"] == [] and recu["champs_source"] == "envoi"


@pytest.mark.asyncio
async def test_une_lecture_et_un_echec_ne_portent_pas_de_champs_et_le_reglage_l_eteint():
    params = [{"name": "nom", "type": "string", "description": "x"}]
    lecture, _ = await _par_le_vrai_gestionnaire({"method": "GET", "parameters": params}, {"nom": "D"})
    assert "champs_appliques" not in lecture
    echec, _ = await _par_le_vrai_gestionnaire({"parameters": params}, {"nom": "D"}, reponse_http=_reponse(500))
    assert "champs_appliques" not in echec
    eteint, _ = await _par_le_vrai_gestionnaire({"parameters": params, "champs_appliques": False}, {"nom": "D"})
    assert "champs_appliques" not in eteint


@pytest.mark.asyncio
async def test_l_essai_de_l_ecran_voit_aussi_les_champs():
    with patch(f"{MODULE}.httpx.AsyncClient") as client:
        session = AsyncMock()
        session.request.return_value = _reponse(200, {"nom": "D"})
        client.return_value.__aenter__.return_value = session
        r = await execute_http_tool(_outil(parameters=[{"name": "nom", "type": "string", "description": "x"}]), {"nom": "D"})
    assert r["champs_appliques"] == ["nom"]


def test_les_reglages_neufs_sont_acceptes_par_le_schema_et_eteints_par_defaut():
    c = HttpApiConfig(method="GET", url="https://a.example.test")
    assert c.resume_pour_la_voix is False and c.un_seul_appel_a_la_fois is False
    assert c.consigne_de_parole is None and c.consigne_de_parole_du_service is False
    assert c.resume_max_elements == 3 and c.resume_max_caracteres == 1200
    i = IntegrationToolConfig(connecteur="google_agenda", action="book_appointment")
    assert i.consigne_de_parole is None and i.champs_appliques is True


# --------------------------------------------------------------------------- R3 : relance


def _moniteur(delai):
    moniteur = CallMonitorProcessor(
        response_source=lambda: None,
        on_response_timeout=lambda _s: None,
        on_user_idle=AsyncMock(),
        conversation_enabled=lambda: True,
    )
    moniteur.user_idle_timeout = delai
    moniteur.user_aggregator = SimpleNamespace(user_turn_controller=SimpleNamespace(has_active_user_turn=False))
    moniteur._active = True
    moniteur._waiting_for_user = True
    return moniteur


@pytest.mark.asyncio
async def test_un_delai_de_zero_ne_relance_jamais_un_delai_positif_relance():
    zero = _moniteur(0)
    zero._arm_idle()
    assert zero._deadline_kind is None and zero._idle_eligible() is False
    await asyncio.sleep(0.05)
    zero._on_user_idle.assert_not_awaited()
    cinq = _moniteur(0.05)
    cinq._arm_idle()
    await asyncio.sleep(0.2)
    cinq._on_user_idle.assert_awaited_once_with(1)
    cinq._cancel_deadline()


# --------------------------------------------------------------------------- R3 : verrou


async def _lent(duree=0.05):
    await asyncio.sleep(duree)
    return {"status": "success", "data": {"ok": True}}


@pytest.mark.asyncio
async def test_sans_verrou_deux_appels_partent_ensemble_comme_avant():
    moteur = SimpleNamespace()
    a, b = await asyncio.gather(
        executer_avec_comportement(moteur, {}, "chercher", _lent), executer_avec_comportement(moteur, {}, "chercher", _lent)
    )
    assert a["status"] == b["status"] == "success"


@pytest.mark.asyncio
async def test_avec_le_verrou_le_second_appel_est_refuse_puis_le_verrou_est_rendu():
    moteur = SimpleNamespace()
    config = {"un_seul_appel_a_la_fois": True}
    a, b = await asyncio.gather(
        executer_avec_comportement(moteur, config, "chercher", _lent), executer_avec_comportement(moteur, config, "chercher", _lent)
    )
    assert a["status"] == "success"
    assert b["status"] == "deja_en_cours" and b["a_dire_au_client"]
    c = await executer_avec_comportement(moteur, config, "chercher", _lent)
    assert c["status"] == "success"  # rendu à la fin


@pytest.mark.asyncio
async def test_le_verrou_est_rendu_apres_un_echec_et_se_partage_entre_deux_outils_et_pas_entre_deux_appels():
    moteur = SimpleNamespace()
    commun = {"un_seul_appel_a_la_fois": True, "verrou_commun": "recherches"}
    a, b = await asyncio.gather(
        executer_avec_comportement(moteur, commun, "chercher_un", _lent),
        executer_avec_comportement(moteur, commun, "chercher_deux", _lent),
    )
    assert {a["status"], b["status"]} == {"success", "deja_en_cours"}
    autre_appel = SimpleNamespace()
    c = await executer_avec_comportement(autre_appel, commun, "chercher_un", _lent)
    assert c["status"] == "success"

    async def plante():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await executer_avec_comportement(moteur, commun, "chercher_un", plante)
    d = await executer_avec_comportement(moteur, commun, "chercher_un", _lent)
    assert d["status"] == "success"


# --------------------------------------------------------------------------- connecteurs (vrai répartiteur)


@pytest.mark.asyncio
async def test_une_ecriture_de_connecteur_dit_les_champs_et_porte_sa_consigne_de_parole(faux_nango, monkeypatch):
    config = {**CONFIG_RDV, "delai_ms": 2000, "consigne_de_parole": "Confirme le jour et l'heure au client."}
    _, mgr, enregistres = _moteur(monkeypatch, [_outil_connecteur(config, "Poser")])
    await mgr.register_handlers(["uuid-Poser"])
    r = await _appeler(enregistres["poser"][0], {"debut": "2030-01-07T09:00:00+01:00"})
    assert r["champs_appliques"] == ["debut"] and r["champs_ignores"] == [] and r["champs_source"] == "envoi"
    assert r["consigne_de_parole"] == "Confirme le jour et l'heure au client."


@pytest.mark.asyncio
async def test_par_defaut_un_connecteur_ne_porte_pas_de_consigne_et_le_reglage_eteint_les_champs(faux_nango, monkeypatch):
    base = {**CONFIG_RDV, "delai_ms": 2000}
    _, mgr, enregistres = _moteur(monkeypatch, [_outil_connecteur({**base, "champs_appliques": False}, "Poser")])
    await mgr.register_handlers(["uuid-Poser"])
    r = await _appeler(enregistres["poser"][0], {"debut": "2030-01-07T09:00:00+01:00"})
    assert "consigne_de_parole" not in r and "champs_appliques" not in r
