"""[.mark] Chantier fiabilite-orchestration, lot 1 : l'attente parlée (F1, F2, C1, C2, R3, R15, G2).

| Test | La garantie |
|---|---|
| aucune relance après « lancé » | une réponse qui parle ET confie ne relance pas le modèle (R15, run 1463) ; sans parole, il parle |
| annuler | l'appelant annule : la trace dit « annulé », le résultat n'est jamais remis ; sans travail, rien |
| ligne du code | pendant un travail, la requête reçoit la ligne C2 avant la dernière parole ; jamais après |
| seconde phrase | le travail dure : la phrase fixe est dite par la voix, entre dans l'historique et la trace |
| horloge des attentes | elle ne court pas pendant que l'appelant parle et repart à la fin de sa réplique |
| avec la réplique | l'appelant parle : le résultat est posé sans réveiller le modèle (F1, run 1468) |
| calme | l'appel calme : le résultat réveille le modèle ; une question en suspens : il attend |
| rempli par l'outil | un champ qui déclare son outil n'est écrit que par son résultat (G2) : jamais le greffier, ni le modèle |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import LLMMessagesAppendFrame, LLMRunFrame

from api.schemas.fiche_agent import ChampFiche
from api.services.groupe.passations import est_un_resultat_de_travail
from api.services.phrases.catalogue import TRAVAIL_DURE
from api.services.phrases.diseur import CLE_TRACE, DiseurDePhrases
from api.services.travail.agent import (
    LIGNE_TRAVAIL_EN_COURS,
    ligne_du_travail,
    montrer_le_travail_en_cours,
)
from api.services.travail.reglages import NOM_OUTIL
from api.services.travail.retour import _VEILLES, remettre_le_resultat
from api.services.workflow.enveloppe_des_actions import (
    envelopper_l_action,
    remplir_par_l_action,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    ReglagesFiche,
    ecrire_dans_la_fiche,
    schema_outil,
)
from api.tests.mark.test_travail_de_fond import (
    DEMANDE,
    RESULTAT,
    Appel,
    _appel_d_outil,
    _texte,
)


@pytest.fixture
async def appel():
    a = Appel()
    try:
        yield a
    finally:
        await a.arreter()


# --------------------------------------------------------------------------- #
# R15 : aucune relance après « lancé » quand la réponse a déjà parlé
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_une_reponse_qui_parle_et_confie_ne_relance_pas_le_modele(appel):
    """Run 1463 : la phrase dite avec l'appel à « confier » n'est jamais redite. Le modèle ne
    reparle qu'au résultat (2e génération), pas après « lancé »."""
    appel.portail = asyncio.Event()
    await appel.monter(
        source_etapes=[
            _texte("Je regarde les disponibilités.")
            + _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte("J'ai trouvé : demain à 14 h."),
        ],
        fond_etapes=[
            _appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"),
            _texte(RESULTAT),
        ],
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["statut"] == "en_cours")
    await asyncio.sleep(0.5)
    # « lancé » est rentré, le modèle n'a pas été réinterrogé.
    assert appel.source_llm.get_current_step() == 1
    appel.portail.set()
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 2)
    dites = [
        m.get("content")
        for m in appel.messages()
        if m.get("role") == "assistant" and isinstance(m.get("content"), str)
    ]
    assert dites.count("Je regarde les disponibilités.") == 1


# --------------------------------------------------------------------------- #
# F2 : annuler
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_l_appelant_annule_le_resultat_n_est_jamais_remis(appel):
    await appel.monter(
        source_etapes=[_texte("rien")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False
    )
    travail = appel.engine.active_agent.travail
    assert await travail.annuler() == {"statut": "aucun travail en cours"}
    portail = asyncio.Event()

    async def bloque(_travail, _demande):
        await portail.wait()
        return RESULTAT

    travail._executeur = bloque
    assert await travail.confier(DEMANDE) == {"statut": "lancé"}
    assert await travail.annuler() == {"statut": "annulé"}
    assert travail.occupe is False
    trace = appel.travaux()[0]
    assert trace["statut"] == "annule"
    assert trace["remis"] is False
    portail.set()
    await asyncio.sleep(0.3)
    assert not [m for m in appel.messages() if est_un_resultat_de_travail(m)]


@pytest.mark.asyncio
async def test_l_outil_annuler_est_offert_avec_confier(appel):
    await appel.monter(source_etapes=[_texte("rien")], fond_etapes=[_texte(RESULTAT)])
    await appel.engine.set_node("start")
    noms = {
        getattr(f, "name", None) for f in appel.engine.context.tools.standard_tools
    }
    assert {NOM_OUTIL, "annuler_le_travail"} <= noms


# --------------------------------------------------------------------------- #
# C2 : la ligne du code pendant un travail
# --------------------------------------------------------------------------- #


class _FauxService:
    def __init__(self):
        self.vu = None

    async def get_chat_completions(self, context):
        self.vu = self.build_chat_completion_params(context)
        return self.vu

    def build_chat_completion_params(self, params_from_context):
        return {"messages": list(params_from_context)}


@pytest.mark.asyncio
async def test_la_ligne_du_travail_entre_avant_la_derniere_parole_pendant_le_travail():
    occupe = SimpleNamespace(occupe=True)
    moteur = SimpleNamespace(travaux=[occupe])
    service = _FauxService()
    assert montrer_le_travail_en_cours(moteur, service) is True
    assert montrer_le_travail_en_cours(moteur, service) is True  # une seule enveloppe
    conversation = [
        {"role": "system", "content": "Prompt."},
        {"role": "user", "content": "Bonjour."},
    ]
    await service.get_chat_completions(conversation)
    assert service.vu["messages"][1] == {"role": "user", "content": LIGNE_TRAVAIL_EN_COURS}
    assert service.vu["messages"][2]["content"] == "Bonjour."
    # Hors d'une requête de conversation (balayage, extraction) : rien.
    assert service.build_chat_completion_params(conversation)["messages"] == conversation
    occupe.occupe = False
    await service.get_chat_completions(conversation)
    assert service.vu["messages"] == conversation
    assert ligne_du_travail(moteur) is None


# --------------------------------------------------------------------------- #
# C1 : la seconde phrase d'attente, et l'horloge des attentes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_travail_qui_dure_fait_dire_la_seconde_phrase(appel):
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
        reglages={
            "travail_actif": True,
            "phrases_regles": [
                {"motif": TRAVAIL_DURE, "variantes": ["Merci de patienter."], "delai_s": 0.5}
            ],
        },
    )
    moteur = appel.engine
    travail = moteur.active_agent.travail
    portail = asyncio.Event()

    async def bloque(_travail, _demande):
        await portail.wait()
        return RESULTAT

    travail._executeur = bloque
    await travail.confier(DEMANDE)
    await appel.attendre(lambda: moteur._gathered_context.get(CLE_TRACE), delai=5)
    trace = moteur._gathered_context[CLE_TRACE]
    assert [(t["motif"], t["texte"], t["niveau"]) for t in trace] == [
        (TRAVAIL_DURE, "Merci de patienter.", "agent")
    ]
    await appel.attendre(
        lambda: any(
            m.get("role") == "assistant" and m.get("content") == "Merci de patienter."
            for m in appel.messages()
        ),
        delai=5,
    )
    portail.set()
    await travail.attendre()


@pytest.mark.asyncio
async def test_une_seconde_phrase_eteinte_n_est_jamais_dite(appel):
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
        reglages={
            "travail_actif": True,
            "phrases_regles": [
                {"motif": TRAVAIL_DURE, "variantes": ["X."], "delai_s": 0.5, "active": False}
            ],
        },
    )
    travail = appel.engine.active_agent.travail
    portail = asyncio.Event()

    async def bloque(_travail, _demande):
        await portail.wait()
        return RESULTAT

    travail._executeur = bloque
    await travail.confier(DEMANDE)
    await asyncio.sleep(1.0)
    assert not appel.engine._gathered_context.get(CLE_TRACE)
    portail.set()
    await travail.attendre()


class _Moniteur:
    def __init__(self):
        self.appelant_parle = False
        self.agent_au_repos = True
        self.appel_au_calme = True
        self.robot_parle = False


class _FauxMoteur:
    def __init__(self, horloge):
        self.call_monitor = _Moniteur()
        self._gathered_context = {}
        self.reglages_appel = {}
        self.active_agent = SimpleNamespace(reglages={}, current_node=None, workflow_id=1)
        self.dites: list[str] = []
        self._horloge = horloge

    def is_call_disposed(self):
        return False

    async def queue_speech(self, texte, **_):
        self.dites.append(texte)
        fin = asyncio.Event()
        fin.set()
        return SimpleNamespace(wait=fin.wait)


@pytest.mark.asyncio
async def test_l_horloge_des_attentes_repart_a_la_fin_de_la_replique():
    temps = [0.0]
    moteur = _FauxMoteur(lambda: temps[0])
    diseur = DiseurDePhrases(moteur, horloge=lambda: temps[0])

    async def avancer():
        # 0,6 s d'attente, l'appelant parle 2 s, puis 0,6 s : le délai de 1 s n'est atteint
        # qu'après la réplique (repartie de zéro), jamais pendant.
        for pas in range(60):
            await asyncio.sleep(0)
            temps[0] += 0.1
            moteur.call_monitor.appelant_parle = 6 <= pas < 26
            await asyncio.sleep(0.001)

    tache = asyncio.create_task(avancer())
    ok = await diseur.attendre_le_systeme(1.0, lambda: True, pas_s=0.001)
    assert ok is True
    assert temps[0] >= 3.5  # 0,6 + 2 + 1 au moins
    tache.cancel()


@pytest.mark.asyncio
async def test_deux_attentes_en_meme_temps_une_seule_phrase_puis_le_repos():
    temps = [100.0]
    moteur = _FauxMoteur(lambda: temps[0])
    diseur = DiseurDePhrases(moteur, horloge=lambda: temps[0])
    lente = asyncio.Event()

    async def queue_speech(texte, **_):
        moteur.dites.append(texte)
        return SimpleNamespace(wait=lente.wait)

    moteur.queue_speech = queue_speech
    assert await diseur.dire("travail_dure") is True
    assert await diseur.dire("modele_tarde") is False  # une attente à la fois
    lente.set()
    await diseur.attendre_la_fin()
    assert await diseur.dire("modele_tarde") is False  # repos de 3 s
    temps[0] += 3.1
    assert await diseur.dire("modele_tarde") is True
    # Une annonce passe toujours, repos ou pas.
    assert await diseur.dire("connecteur_echoue") is True
    # Jamais pendant que l'appelant parle.
    temps[0] += 10
    await diseur.attendre_la_fin()
    moteur.call_monitor.appelant_parle = True
    assert await diseur.dire("travail_dure") is False


@pytest.mark.asyncio
async def test_les_variantes_tournent_sans_redire_la_meme():
    temps = [0.0]
    moteur = _FauxMoteur(lambda: temps[0])
    moteur.active_agent.reglages = {
        "phrases_regles": [
            {"motif": "connecteur_echoue", "variantes": ["A.", "B.", "C."]},
        ]
    }
    diseur = DiseurDePhrases(moteur, horloge=lambda: temps[0])
    for _ in range(4):
        await diseur.dire("connecteur_echoue")
        await diseur.attendre_la_fin()
    assert moteur.dites[:3] == ["A.", "B.", "C."]
    assert moteur.dites[3] != "C."


# --------------------------------------------------------------------------- #
# F1 : la remise du résultat
# --------------------------------------------------------------------------- #


def _moteur_de_remise(messages):
    agent = SimpleNamespace(queue_frame=AsyncMock())
    moteur = SimpleNamespace(
        call_monitor=_Moniteur(),
        is_call_disposed=lambda: False,
        transfer_in_progress=False,
        selected_visit_id="v",
        active_agent=agent,
        agent_can_act=lambda _a: True,
        context=SimpleNamespace(get_messages=lambda: messages),
        expect_response=lambda: None,
    )
    return moteur, agent


@pytest.mark.asyncio
async def test_l_appelant_parle_le_resultat_part_avec_sa_replique():
    moteur, agent = _moteur_de_remise([{"role": "assistant", "content": "Je regarde."}])
    moteur.call_monitor.appel_au_calme = False
    moteur.call_monitor.appelant_parle = True
    assert await remettre_le_resultat(moteur, "[Résultat du travail : ok]") is True
    trame = agent.queue_frame.await_args.args[0]
    assert isinstance(trame, LLMMessagesAppendFrame)
    assert trame.run_llm is False
    for veille in list(_VEILLES):
        veille.cancel()


@pytest.mark.asyncio
async def test_une_replique_sans_reponse_reveille_le_modele_une_fois(monkeypatch):
    """Le tour de l'appelant se ferme sans réponse (bruit écarté) : le résultat ne reste pas en
    souffrance, le modèle est réveillé une fois."""
    from api.services.travail import retour

    monkeypatch.setattr(retour, "ATTENTE_DE_LA_REPONSE_S", 0.05)
    message = "[Résultat du travail : ok]"
    messages = [{"role": "assistant", "content": "Je regarde."}]
    moteur, agent = _moteur_de_remise(messages)
    moteur.call_monitor.appel_au_calme = False
    moteur.call_monitor.appelant_parle = True
    assert await remettre_le_resultat(moteur, message) is True
    messages.append({"role": "user", "content": message})
    moteur.call_monitor.appelant_parle = False
    moteur.call_monitor.appel_au_calme = True
    await asyncio.wait_for(asyncio.gather(*list(_VEILLES)), 3)
    assert isinstance(agent.queue_frame.await_args.args[0], LLMRunFrame)
    # Le modèle avait répondu : rien de plus.
    moteur, agent = _moteur_de_remise(messages + [{"role": "assistant", "content": "Bien."}])
    moteur.call_monitor.appel_au_calme = False
    moteur.call_monitor.appelant_parle = True
    await remettre_le_resultat(moteur, message)
    moteur.call_monitor.appelant_parle = False
    moteur.call_monitor.appel_au_calme = True
    await asyncio.wait_for(asyncio.gather(*list(_VEILLES)), 3)
    assert agent.queue_frame.await_count == 1


@pytest.mark.asyncio
async def test_l_appel_calme_le_resultat_reveille_le_modele_sauf_question_en_suspens():
    moteur, agent = _moteur_de_remise([{"role": "assistant", "content": "Je regarde."}])
    assert await remettre_le_resultat(moteur, "[Résultat du travail : ok]") is True
    assert agent.queue_frame.await_args.args[0].run_llm is True
    moteur, agent = _moteur_de_remise([{"role": "assistant", "content": "Votre nom ?"}])
    assert await remettre_le_resultat(moteur, "[Résultat du travail : ok]") is True
    assert agent.queue_frame.await_args.args[0].run_llm is False


@pytest.mark.asyncio
async def test_le_robot_parle_le_resultat_attend():
    moteur, agent = _moteur_de_remise([])
    moteur.call_monitor.appel_au_calme = False
    moteur.call_monitor.agent_au_repos = False
    moteur.call_monitor.appelant_parle = True
    tache = asyncio.create_task(remettre_le_resultat(moteur, "[Résultat du travail : ok]"))
    await asyncio.sleep(0.3)
    assert agent.queue_frame.await_count == 0
    moteur.call_monitor.agent_au_repos = True
    assert await asyncio.wait_for(tache, 2) is True


@pytest.mark.asyncio
async def test_la_veille_s_arrete_si_le_calme_ne_revient_jamais(monkeypatch):
    """Un appel qui ne retrouve jamais le calme et n'est jamais clos : la veille s'arrête
    d'elle-même au bout de sa limite, sans réveiller le modèle (20/10 : une veille sans fin a
    porté la suite de tests à plus de 100 Go)."""
    from api.services.travail import retour

    monkeypatch.setattr(retour, "ATTENTE_MAX_DE_LA_REPLIQUE_S", 0.05)
    monkeypatch.setattr(retour, "ATTENTE_DE_LA_REPONSE_S", 0.0)
    monkeypatch.setattr(retour, "ATTENTE_MAX_DU_CALME_S", 0.2)
    moteur, agent = _moteur_de_remise([])
    moteur.call_monitor.appel_au_calme = False
    moteur.call_monitor.appelant_parle = True
    await asyncio.wait_for(retour._veiller_sur_la_replique(moteur, agent, "[Résultat]"), 2)
    assert agent.queue_frame.await_count == 0


# --------------------------------------------------------------------------- #
# G2 : le champ rempli par l'outil
# --------------------------------------------------------------------------- #


def _reglages_rdv():
    return ReglagesFiche(
        champs=(
            ChampFiche(nom="nom", origine="dicte"),
            ChampFiche(
                nom="rendez_vous",
                origine="deduit",
                valeurs=["confirme", "a_rappeler"],
                rempli_par_outil="poser_rendez_vous_v2",
            ),
        )
    )


def test_le_greffier_et_le_modele_n_ecrivent_jamais_un_champ_rempli_par_l_outil():
    reglages = _reglages_rdv()
    fiche: dict = {}
    for source in ("greffier", "outil", "balayage"):
        verdict = ecrire_dans_la_fiche(fiche, reglages, "rendez_vous", "confirme", source=source)
        assert (verdict.statut, verdict.raison) == ("refuse", "rempli_par_l_outil")
    assert "rendez_vous" not in fiche
    # Ni l'outil de note ni le greffier ne le voient.
    assert "rendez_vous" not in schema_outil(reglages).properties
    from api.services.pipecat.greffier import consigne_du_greffier, schema_de_la_fiche

    assert "rendez_vous" not in schema_de_la_fiche(reglages)["properties"]
    assert "rendez_vous" not in consigne_du_greffier(reglages, None)


def test_le_resultat_de_l_outil_ecrit_le_champ_et_un_echec_n_ecrit_rien():
    moteur = SimpleNamespace(_fiche=_reglages_rdv(), _gathered_context={})
    assert remplir_par_l_action(moteur, "poser_rendez_vous_v2", {"status": "error"}) == []
    assert "rendez_vous" not in moteur._gathered_context
    assert remplir_par_l_action(moteur, "autre_outil", {"statut": "confirme"}) == []
    assert remplir_par_l_action(moteur, "poser_rendez_vous_v2", '{"statut": "confirme"}') == [
        "rendez_vous"
    ]
    assert moteur._gathered_context["rendez_vous"] == "confirme"
    # Une valeur hors de la liste fermée reste refusée (mêmes contrôles qu'ailleurs).
    moteur = SimpleNamespace(_fiche=_reglages_rdv(), _gathered_context={})
    assert remplir_par_l_action(moteur, "poser_rendez_vous_v2", {"statut": "ok"}) == []
    # Sans statut : la première valeur permise.
    assert remplir_par_l_action(moteur, "poser_rendez_vous_v2", {"creneau": "14h"}) == [
        "rendez_vous"
    ]


@pytest.mark.asyncio
async def test_l_enveloppe_lit_le_resultat_et_le_rend_tel_quel():
    moteur = SimpleNamespace(_fiche=_reglages_rdv(), _gathered_context={})
    rendus = []

    async def rendre(resultat, **kwargs):
        rendus.append(resultat)

    async def action(params):
        await params.result_callback({"statut": "confirme"})

    params = SimpleNamespace(result_callback=rendre, arguments={})
    await envelopper_l_action(moteur, "poser_rendez_vous_v2", action)(params)
    assert rendus == [{"statut": "confirme"}]
    assert moteur._gathered_context["rendez_vous"] == "confirme"


def test_un_champ_sans_outil_declare_ne_change_rien():
    champ = ChampFiche(nom="nom")
    assert champ.rempli_par_outil is None
    assert ChampFiche(nom="x", rempli_par_outil="  ").rempli_par_outil is None
    with pytest.raises(ValueError):
        ChampFiche(nom="x", rempli_par_outil="pas un nom !")
