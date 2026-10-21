"""[.mark] Chantier correctifs-apres-banc-v4, lot 4 (4.4 à 4.11) : les règles de phrase traversent les vraies
routes (R1) : le travail de fond, l'enveloppe des outils, le transfert échoué, le silence, la passation.

| Test | La garantie |
|---|---|
| dès le lancement | une règle « le travail de fond travaille » à 0 s : la phrase part quand l'agent appelle ``confier_le_travail``, jamais avant, jamais sans appel |
| annonce de l'agent | case cochée : l'annonce écrite par l'agent passe en première phrase, les redites restent les phrases fixes ; invalide, la phrase fixe |
| annonce obligatoire | la case cochée rend ``annonce`` obligatoire dans l'outil ; décochée, l'outil est inchangé |
| échec du fond | le fond échoue : la règle dit sa phrase, le message remis au modèle porte le compte rendu en français, la phrase est dans l'historique AVANT ce message |
| échec du fond sans règle | aucune règle posée : le message est celui d'avant (zéro perte) |
| outil qui échoue | panne d'un outil (erreur après essais) : phrase, compte rendu dans le résultat ; ``missing`` et ``incomplet`` ne sont pas des pannes |
| sortie après le plafond | le 2e échec : note dans la fiche, raccrocher ; le modèle n'est pas relancé |
| sans règle posée | l'échec d'un outil HTTP sans règle ne dit rien et le résultat part tel quel (comme avant) |
| outil visé | une règle qui nomme un outil ne parle pas pour un autre |
| outil du fond | l'échec d'un outil du cerveau de fond ne passe jamais par « un outil échoue » |
| transfert échoué | la phrase, le compte rendu en français (rappel noté, transfert retiré) à la place de la consigne anglaise |
| silence | relances et sortie lues dans la règle : nombre de relances de la règle, phrase de sortie, note, raccrocher ; sinon Rythme et au revoir comme avant |
| passation | la phrase « un collègue prend la main » redit à l'intervalle, le son d'attente reprend entre deux |
| étape renommée | une règle repérée par l'identifiant de nœud suit l'étape renommée ; une règle d'avant se retrouve par le nom |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.groupe.passations import est_un_resultat_de_travail
from api.services.phrases.catalogue import (
    APPELANT_SE_TAIT,
    OUTIL_ECHOUE,
    OUTIL_TARDE,
    TRANSFERT_ECHOUE,
    TRAVAIL_DURE,
    TRAVAIL_ECHOUE,
)
from api.services.phrases.diseur import CLE_TRACE, DiseurDePhrases
from api.services.travail.agent import (
    STATUT_ECHEC,
    annonce_demandee,
    annonce_valide,
    schema_de_l_outil,
)
from api.services.travail.reglages import NOM_OUTIL
from api.services.workflow.enveloppe_des_actions import envelopper_l_action
from api.services.workflow.pipecat_engine_callbacks import handle_user_idle
from api.tests.mark.test_attente_parlee import _FauxMoteur
from api.tests.mark.test_phrases_veille_v4 import _Moteur as _MoteurVeille
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


def _regle(motif, variantes=("Une phrase.",), **champs):
    return {"motif": motif, "portee": "agent", "variantes": list(variantes), **champs}


# --------------------------------------------------------------------------- #
# Le travail de fond : dès le lancement, l'annonce de l'agent, l'échec
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_des_le_lancement_la_phrase_part_avec_l_appel_de_confier_jamais_avant(appel):
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
        reglages={
            "travail_actif": True,
            "phrases_regles": [
                _regle(
                    TRAVAIL_DURE,
                    ["Phrase 1.", "Phrase 2."],
                    delai_s=0,
                    redite_s=2,
                    max_par_attente=2,
                    ordre="dans_l_ordre",
                )
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
    # Pas d'appel de l'outil : aucune phrase, même longtemps après.
    await asyncio.sleep(0.4)
    assert not moteur._gathered_context.get(CLE_TRACE) and not travail.occupe
    # L'appel de l'outil lance la veille : la première phrase part tout de suite (0 s).
    await travail.confier(DEMANDE)
    await appel.attendre(lambda: moteur._gathered_context.get(CLE_TRACE), delai=3)
    assert moteur._gathered_context[CLE_TRACE][0]["texte"] == "Phrase 1."
    assert travail.occupe
    # La redite vient 2 s après la FIN de la première, dans l'ordre.
    await appel.attendre(lambda: len(moteur._gathered_context[CLE_TRACE]) >= 2, delai=6)
    trace = moteur._gathered_context[CLE_TRACE]
    assert [t["texte"] for t in trace] == ["Phrase 1.", "Phrase 2."]
    assert trace[1]["redite"] == 1
    # Le résultat arrive : plus rien.
    portail.set()
    await travail.attendre()
    await asyncio.sleep(0.3)
    assert len(moteur._gathered_context[CLE_TRACE]) == 2


@pytest.mark.asyncio
async def test_l_annonce_de_l_agent_passe_en_premiere_les_redites_restent_fixes(appel):
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
        reglages={
            "travail_actif": True,
            "phrases_regles": [
                _regle(
                    TRAVAIL_DURE,
                    ["Fixe 1.", "Fixe 2."],
                    delai_s=0,
                    redite_s=2,
                    max_par_attente=2,
                    ordre="dans_l_ordre",
                    texte_de_l_agent=True,
                )
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
    await travail.confier(DEMANDE, "Je cherche les dates.")
    await appel.attendre(lambda: len(moteur._gathered_context.get(CLE_TRACE, [])) >= 2, delai=8)
    assert [t["texte"] for t in moteur._gathered_context[CLE_TRACE]] == [
        "Je cherche les dates.",
        "Fixe 2.",
    ]
    portail.set()
    await travail.attendre()


@pytest.mark.asyncio
async def test_une_annonce_invalide_laisse_la_phrase_fixe(appel):
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
        reglages={
            "travail_actif": True,
            "phrases_regles": [
                _regle(TRAVAIL_DURE, ["Fixe."], delai_s=0, texte_de_l_agent=True)
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
    # Recopie de la demande : la phrase fixe.
    await travail.confier(DEMANDE, DEMANDE)
    await appel.attendre(lambda: moteur._gathered_context.get(CLE_TRACE), delai=3)
    assert moteur._gathered_context[CLE_TRACE][0]["texte"] == "Fixe."
    portail.set()
    await travail.attendre()


def test_l_annonce_est_valide_courte_et_non_recopiee():
    demande = "Cherche les dates de passage disponibles la semaine prochaine pour une personne."
    assert annonce_valide("Je regarde les dates.", demande) == "Je regarde les dates."
    assert annonce_valide("", demande) is None and annonce_valide(None, demande) is None
    assert annonce_valide("x" * 121, demande) is None
    assert annonce_valide("mot " * 40, demande) is None
    assert annonce_valide(demande, demande) is None  # recopie mot pour mot
    assert annonce_valide("  Je   regarde  ça ", demande) == "Je regarde ça"
    # Une annonce qui reprend l'essentiel de la demande, mot pour mot, est une recopie.
    assert annonce_valide("Cherche les dates de passage disponibles", demande) is None


def test_l_annonce_est_obligatoire_quand_la_case_est_cochee_sinon_l_outil_est_inchange():
    sans = schema_de_l_outil()
    assert sans.required == ["demande"] and set(sans.properties) == {"demande"}
    avec = schema_de_l_outil(True)
    assert avec.required == ["demande", "annonce"]
    assert avec.properties["annonce"]["description"] == (
        "Une phrase courte dite à l'appelant pendant le travail, qui ne donne aucun résultat."
    )
    moteur = _MoteurVeille()
    moteur.phrases = DiseurDePhrases(moteur)
    agent = moteur.active_agent
    assert annonce_demandee(moteur, agent) is False
    agent.reglages = {"phrases_regles": [_regle(TRAVAIL_DURE, ["Fixe."], delai_s=0, texte_de_l_agent=True)]}
    assert annonce_demandee(moteur, agent) is True
    agent.reglages = {"phrases_regles": [_regle(TRAVAIL_DURE, ["Fixe."], delai_s=0)]}
    assert annonce_demandee(moteur, agent) is False
    # Case cochée mais règle éteinte : l'outil reste inchangé.
    agent.reglages = {
        "phrases_regles": [_regle(TRAVAIL_DURE, [], delai_s=0, texte_de_l_agent=True, active=False)]
    }
    assert annonce_demandee(moteur, agent) is False


@pytest.mark.asyncio
async def test_le_fond_echoue_la_regle_parle_et_le_modele_recoit_le_compte_rendu(appel):
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte("Je regarde."),
            _texte("Je n'ai pas pu."),
        ],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
        reglages={
            "travail_actif": True,
            "phrases_regles": [_regle(TRAVAIL_ECHOUE, ["Je n'arrive pas à finaliser."])],
        },
    )

    async def echoue(_travail, _demande):
        raise RuntimeError("panne")

    appel.engine.active_agent.travail._executeur = echoue
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    assert appel.travaux()[0]["statut"] == STATUT_ECHEC
    messages = appel.messages()
    indice = next(i for i, m in enumerate(messages) if est_un_resultat_de_travail(m))
    resultat = messages[indice]["content"]
    assert "Ce qui vient de se passer : le travail de fond n'a pas abouti." in resultat
    assert "L'appelant a entendu : « Je n'arrive pas à finaliser. »" in resultat
    # La phrase du code est dans l'historique, comme réplique de l'agent, AVANT le message du résultat.
    avant = [m.get("content") for m in messages[:indice] if m.get("role") == "assistant"]
    assert any("Je n'arrive pas à finaliser." in (contenu or "") for contenu in avant)
    assert "do not repeat" not in resultat.lower()


@pytest.mark.asyncio
async def test_le_fond_echoue_sans_regle_posee_le_message_est_celui_d_avant(appel):
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte("Je regarde."),
            _texte("Je n'ai pas pu."),
        ],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )

    async def echoue(_travail, _demande):
        raise RuntimeError("panne")

    appel.engine.active_agent.travail._executeur = echoue
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    resultat = next(m["content"] for m in appel.messages() if est_un_resultat_de_travail(m))
    assert "Ce qui vient de se passer" not in resultat
    assert not appel.engine._gathered_context.get(CLE_TRACE)


# --------------------------------------------------------------------------- #
# L'enveloppe des outils : « un outil échoue »
# --------------------------------------------------------------------------- #


async def _lancer(moteur, resultat, nom="reserver", llm=None):
    rendus = []

    async def rendre(valeur, *args, **kwargs):
        rendus.append((valeur, kwargs))

    async def action(params):
        await params.result_callback(resultat)

    params = SimpleNamespace(
        result_callback=rendre,
        llm=llm if llm is not None else moteur.active_agent.llm,
        arguments={},
    )
    await envelopper_l_action(moteur, nom, action, moteur.active_agent, garde=False)(params)
    await moteur.phrases.attendre_la_fin()
    return rendus


def _moteur_outils(regles=None):
    moteur = _MoteurVeille()
    moteur.active_agent.llm = object()
    moteur.active_agent.reglages = {"phrases_regles": regles or []}
    moteur.phrases = DiseurDePhrases(moteur)
    moteur.phrases.repos_s = lambda: 0.0
    return moteur


@pytest.mark.asyncio
async def test_la_panne_d_un_outil_dit_la_phrase_et_donne_le_compte_rendu():
    moteur = _moteur_outils([_regle(OUTIL_ECHOUE, ["Je n'arrive pas à finaliser."])])
    rendus = await _lancer(moteur, {"status": "error", "error": "timeout"})
    assert moteur.dites == ["Je n'arrive pas à finaliser."]
    valeur, _ = rendus[0]
    assert valeur["status"] == "error" and valeur["error"] == "timeout"
    assert valeur["compte_rendu"].startswith("[Ce qui vient de se passer : l'outil n'a pas abouti.")
    assert "L'appelant a entendu : « Je n'arrive pas à finaliser. »" in valeur["compte_rendu"]
    # Un échec rendu en 200 par le service est une panne aussi.
    moteur2 = _moteur_outils([_regle(OUTIL_ECHOUE, ["Souci."])])
    rendus = await _lancer(moteur2, {"status_code": 200, "data": {"statut": "echec"}, "status": "success"})
    assert moteur2.dites == ["Souci."] and "compte_rendu" in rendus[0][0]


@pytest.mark.asyncio
async def test_missing_et_incomplet_ne_sont_pas_des_pannes_et_le_succes_non_plus():
    moteur = _moteur_outils([_regle(OUTIL_ECHOUE, ["Souci."])])
    for resultat in (
        {"status": "missing", "ask_for": ["date"]},
        {"statut": "incomplet", "manque": ["nom"]},
        {"status": "success", "data": {"ok": True}},
    ):
        rendus = await _lancer(moteur, resultat)
        assert rendus[0][0] == resultat
    assert moteur.dites == []


@pytest.mark.asyncio
async def test_sans_regle_posee_l_echec_d_un_outil_ne_dit_rien_et_part_tel_quel():
    moteur = _moteur_outils()
    resultat = {"status": "error", "error": "timeout"}
    rendus = await _lancer(moteur, resultat)
    # Le défaut du catalogue parle pour un connecteur (comme avant), pas pour un outil HTTP.
    assert rendus[0][0] == resultat and moteur.dites == []


@pytest.mark.asyncio
async def test_le_plafond_atteint_note_dans_la_fiche_et_raccroche_sans_relancer_le_modele():
    moteur = _moteur_outils(
        [
            _regle(
                OUTIL_ECHOUE,
                ["Je n'arrive pas à finaliser."],
                max_par_appel=2,
                ensuite={
                    "phrases": ["Un conseiller vous rappelle."],
                    "noter": {"champ": "rendez_vous", "valeur": "a_rappeler"},
                    "action": "raccrocher",
                },
            )
        ]
    )
    panne = {"status": "error", "error": "boom"}
    premier = await _lancer(moteur, panne)
    assert "properties" not in premier[0][1] and moteur._gathered_context.get("rendez_vous") is None
    second = await _lancer(moteur, panne)
    valeur, options = second[0]
    assert moteur._gathered_context["rendez_vous"] == "a_rappeler"
    assert "Noté dans la fiche : rendez_vous = a_rappeler." in valeur["compte_rendu"]
    assert options["properties"].run_llm is False  # l'appel est repris en main : le modèle ne parle pas
    moteur.end_call_with_reason.assert_awaited_once()
    assert moteur.dites == [
        "Je n'arrive pas à finaliser.",
        "Je n'arrive pas à finaliser.",
        "Un conseiller vous rappelle.",
    ]


@pytest.mark.asyncio
async def test_une_regle_qui_nomme_un_outil_ne_parle_pas_pour_un_autre():
    moteur = _moteur_outils([_regle(OUTIL_ECHOUE, ["Pour la réservation."], outils=["reserver"])])
    panne = {"status": "error", "error": "boom"}
    await _lancer(moteur, panne, nom="chercher")
    assert moteur.dites == []
    await _lancer(moteur, panne, nom="reserver")
    assert moteur.dites == ["Pour la réservation."]


@pytest.mark.asyncio
async def test_l_echec_d_un_outil_du_fond_ne_passe_jamais_par_un_outil_echoue():
    moteur = _moteur_outils([_regle(OUTIL_ECHOUE, ["Souci."])])
    rendus = await _lancer(moteur, {"status": "error", "error": "boom"}, llm=object())
    assert moteur.dites == [] and "compte_rendu" not in rendus[0][0]


@pytest.mark.asyncio
async def test_un_outil_lent_est_vise_par_son_nom_et_redit_a_l_intervalle():
    moteur = _moteur_outils(
        [
            _regle(OUTIL_TARDE, ["Je regarde les dates."], outils=["chercher"], delai_s=0, redite_s=2, max_par_attente=2),
            _regle(OUTIL_TARDE, ["Pour tous."], delai_s=0),
        ]
    )
    rendus = []

    async def rendre(valeur, *args, **kwargs):
        rendus.append(valeur)

    async def action(params):
        await asyncio.sleep(2.6)
        await params.result_callback({"status": "ok"})

    params = SimpleNamespace(result_callback=rendre, llm=moteur.active_agent.llm, arguments={})
    await envelopper_l_action(moteur, "chercher", action, moteur.active_agent, garde=False)(params)
    await moteur.phrases.attendre_la_fin()
    assert moteur.dites == ["Je regarde les dates.", "Je regarde les dates."]
    assert rendus == [{"status": "ok"}]


# --------------------------------------------------------------------------- #
# Le transfert échoué
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_transfert_echoue_donne_un_compte_rendu_en_francais():
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    moteur = _MoteurVeille()
    moteur.phrases = DiseurDePhrases(moteur)
    moteur.phrases.repos_s = lambda: 0.0
    moteur.active_agent.reglages = {
        "phrases_regles": [_regle(TRANSFERT_ECHOUE, ["Je n'ai pas pu vous mettre en relation."])]
    }
    outils = CustomToolManager.__new__(CustomToolManager)
    outils._engine = moteur
    rendu = AsyncMock()
    resultat = {"action": "transfer_failed", "status": "failed", "reason": "no_answer"}
    await outils._handle_transfer_result(resultat, SimpleNamespace(result_callback=rendu), None)
    echec = rendu.await_args.args[0]
    assert echec["said_to_caller"] == "Je n'ai pas pu vous mettre en relation."
    assert echec["compte_rendu"].startswith("[Ce qui vient de se passer : le transfert n'a pas abouti.")
    assert "instruction" not in echec and "do not repeat" not in str(echec).lower()
    # Éteinte (le défaut) : le résultat est celui d'avant, sans compte rendu.
    moteur.active_agent.reglages = {}
    rendu.reset_mock()
    await outils._handle_transfer_result(resultat, SimpleNamespace(result_callback=rendu), None)
    assert "compte_rendu" not in rendu.await_args.args[0]


# --------------------------------------------------------------------------- #
# Le silence de l'appelant
# --------------------------------------------------------------------------- #


class _Agregateur:
    def __init__(self):
        self.consignes: list[str] = []

    async def push_frame(self, frame):
        for message in frame.messages:
            self.consignes.append(message["content"])


class _MoteurSilence(_FauxMoteur):
    def __init__(self, reglages_agent=None, relances=None):
        super().__init__(lambda: 100.0)
        self.active_agent = SimpleNamespace(reglages=dict(reglages_agent or {}), current_node=None, workflow_id=7)
        self.reglages_relances = dict(relances or {})
        self.sans_sortie_audio = False
        self.raccroche = None
        self.call_monitor.relance_par_la_voix = lambda *, dite: None
        self.phrases = DiseurDePhrases(self)
        self.phrases.repos_s = lambda: 0.0
        self.travaux = []

    async def end_call_with_reason(self, raison):
        self.raccroche = raison


@pytest.mark.asyncio
async def test_le_silence_lit_ses_relances_et_sa_sortie_dans_la_regle():
    moteur = _MoteurSilence(
        {
            "phrases_regles": [
                _regle(
                    APPELANT_SE_TAIT,
                    ["Êtes-vous toujours là ?"],
                    delai_s=5,
                    max_par_attente=2,
                    ensuite={"phrases": ["Je vous laisse, au revoir."], "action": "raccrocher"},
                )
            ]
        },
        relances={"user_idle_max_prompts": 1},  # Rythme dit 1, la règle dit 2
    )
    agregateur = _Agregateur()
    for tentative in (1, 2):
        await handle_user_idle(moteur, agregateur, tentative)
        await moteur.phrases.attendre_la_fin()
    assert moteur.dites == ["Êtes-vous toujours là ?", "Êtes-vous toujours là ?"]
    assert moteur.raccroche is None and agregateur.consignes == []
    # Au silence qui suit la dernière relance : la sortie de la règle, pas le au revoir donné au modèle.
    await handle_user_idle(moteur, agregateur, 3)
    assert moteur.dites[-1] == "Je vous laisse, au revoir."
    assert moteur.raccroche == "user_idle_max_duration_exceeded"
    assert agregateur.consignes == []


@pytest.mark.asyncio
async def test_le_silence_sans_sortie_posee_garde_le_au_revoir_d_avant():
    from api.schemas.workflow_configurations import DEFAULT_USER_IDLE_GOODBYE_PROMPT

    moteur = _MoteurSilence()
    agregateur = _Agregateur()
    await handle_user_idle(moteur, agregateur, 1)
    await moteur.phrases.attendre_la_fin()
    await handle_user_idle(moteur, agregateur, 2)
    # Comme avant : une relance (Rythme : 1), puis le au revoir donné au modèle et l'appel raccroche.
    assert agregateur.consignes == [DEFAULT_USER_IDLE_GOODBYE_PROMPT]
    assert moteur.raccroche == "user_idle_max_duration_exceeded"


@pytest.mark.asyncio
async def test_le_silence_continuer_ne_raccroche_pas():
    moteur = _MoteurSilence(
        {
            "phrases_regles": [
                _regle(
                    APPELANT_SE_TAIT,
                    ["Allô ?"],
                    max_par_attente=1,
                    ensuite={"phrases": ["Je reste là."], "action": "continuer"},
                )
            ]
        }
    )
    agregateur = _Agregateur()
    await handle_user_idle(moteur, agregateur, 1)
    await moteur.phrases.attendre_la_fin()
    await handle_user_idle(moteur, agregateur, 2)
    assert moteur.dites[-1] == "Je reste là." and moteur.raccroche is None and agregateur.consignes == []


# --------------------------------------------------------------------------- #
# L'étape renommée
# --------------------------------------------------------------------------- #


def test_une_regle_d_etape_suit_l_etape_renommee_et_les_anciennes_se_retrouvent_par_le_nom():
    from api.services.phrases.regles import NIVEAU_AGENT, NIVEAU_ETAPE, resoudre

    reglages = {
        "phrases_regles": [
            _regle(OUTIL_TARDE, ["Par identifiant."], portee="etape", etape="Ancien nom", etape_id="n7", delai_s=1),
            _regle(OUTIL_TARDE, ["Par le nom."], portee="etape", etape="Rendez-vous", delai_s=1),
            _regle(OUTIL_TARDE, ["Agent."], delai_s=1),
        ]
    }
    # L'étape a été renommée : l'identifiant la retrouve.
    renommee = resoudre(OUTIL_TARDE, reglages_agent=reglages, etape="Nouveau nom", etape_id="n7")
    assert (renommee.niveau, renommee.variantes) == (NIVEAU_ETAPE, ("Par identifiant.",))
    # La règle d'avant (le nom seul) se retrouve par le nom.
    avant = resoudre(OUTIL_TARDE, reglages_agent=reglages, etape="Rendez-vous", etape_id="n9")
    assert avant.variantes == ("Par le nom.",)
    # Le nom d'une étape ne suffit pas quand la règle est repérée par identifiant.
    autre = resoudre(OUTIL_TARDE, reglages_agent=reglages, etape="Ancien nom", etape_id="n8")
    assert (autre.niveau, autre.variantes) == (NIVEAU_AGENT, ("Agent.",))
