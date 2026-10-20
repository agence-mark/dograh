"""[.mark] Chantier fiabilite-orchestration, lot 4 bis : le mécanisme des phrases dites par le code
(F15, F17, F18, F21, F23 à F25).

Les verrous du diseur (une attente à la fois, repos, annonce jamais bloquée, horloge qui repart,
variantes) sont tenus par ``test_attente_parlee.py``. Ici : la résolution, la reprise des anciens
réglages, chaque phrase d'avant passée par le mécanisme, et la copie du catalogue à l'écran.

| Test | La garantie |
|---|---|
| écran | la copie du catalogue lue par le thème Phrases est égale au catalogue du code |
| éteinte | une règle éteinte n'est jamais dite, même avec une phrase propre à l'action |
| niveaux | étape, puis agent, puis règle « groupe » du principal, puis défaut ; texte, variantes et délai pris |
| spécialisé | il hérite de la phrase du principal, puis garde la sienne quand il la règle |
| reprise | la phrase pont et la mise en relation d'avant valent règle « groupe » ; une règle les remplace |
| historique | une phrase du code entre dans l'historique ; la phrase pont non (résumé en construction) |
| coupable | toute phrase du code part sans couper le micro de l'appelant (F25), et n'est jamais relancée |
| réfléchit | sans attente du système (condition fausse), aucune phrase d'un motif système, quel que soit le temps |
| outil lent | un outil du tour qui dépasse son délai fait dire la phrase une fois ; rapide : rien ; fond : rien |
| réponse perdue | le filet du flux vide dit la phrase de la règle de l'agent ; éteinte : silence, comme avant |
| connecteur | un connecteur en échec dit la règle (ou la phrase du connecteur) ; éteinte : rien, le modèle répond |
| transfert échoué | éteinte par défaut : rien ; allumée : la phrase, et le modèle sait qu'elle est dite |
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.schemas.phrases_du_code import (
    DELAI_MAX_S,
    DELAI_MIN_S,
    MAX_LONGUEUR_PHRASE,
    MAX_REGLES,
    MAX_VARIANTES,
)
from api.services.phrases.catalogue import (
    APPELANT_SE_TAIT,
    CONNECTEUR_ECHOUE,
    MISE_EN_RELATION,
    MOTIFS,
    OUTIL_TARDE,
    PASSATION_TARDE,
    REPONSE_PERDUE,
    TRANSFERT_ECHOUE,
)
from api.services.phrases.diseur import CLE_TRACE, DiseurDePhrases
from api.services.phrases.regles import (
    NIVEAU_AGENT,
    NIVEAU_DEFAUT,
    NIVEAU_ETAPE,
    NIVEAU_PRINCIPAL,
    resoudre,
)
from api.services.workflow.enveloppe_des_actions import envelopper_l_action
from api.tests.mark.test_attente_parlee import _FauxMoteur

COPIE_ECRAN = (
    Path(__file__).resolve().parents[3]
    / "ui/src/components/mark/reglages-agent/phrases/catalogue-des-phrases.json"
)


def _regle(motif, variantes, portee="agent", etape=None, delai_s=None, active=True):
    return {
        "motif": motif,
        "portee": portee,
        "etape": etape,
        "variantes": variantes,
        "delai_s": delai_s,
        "active": active,
    }


def test_la_copie_du_catalogue_a_l_ecran_est_celle_du_code():
    copie = json.loads(COPIE_ECRAN.read_text(encoding="utf-8"))
    assert copie["bornes"] == {
        "variantes_max": MAX_VARIANTES,
        "longueur_max": MAX_LONGUEUR_PHRASE,
        "regles_max": MAX_REGLES,
        "delai_min_s": DELAI_MIN_S,
        "delai_max_s": DELAI_MAX_S,
    }
    attendu = [
        {
            "id": m.id,
            "famille": m.famille,
            "libelle": {"en": m.libelle_en, "fr": m.libelle_fr},
            "quand": {"en": m.quand_en, "fr": m.quand_fr},
            "a_un_delai": m.a_un_delai,
            "variantes_defaut": list(m.variantes_defaut),
            "delai_defaut_s": m.delai_defaut_s,
            "actif_par_defaut": m.actif_par_defaut,
            "eteinte": {"en": m.eteinte_en, "fr": m.eteinte_fr},
            "silence_de_l_appelant": m.silence_de_l_appelant,
        }
        for m in MOTIFS.values()
    ]
    assert copie["motifs"] == attendu


def test_les_niveaux_etape_agent_principal_defaut():
    principal = {"phrases_regles": [_regle(OUTIL_TARDE, ["Du groupe."], "groupe", delai_s=5)]}
    agent = {
        "phrases_regles": [
            _regle(OUTIL_TARDE, ["De l'agent.", "Bis."], delai_s=4),
            _regle(OUTIL_TARDE, ["De l'étape."], "etape", "Rendez-vous", delai_s=6),
        ]
    }
    etape = resoudre(OUTIL_TARDE, reglages_agent=agent, reglages_principal=principal, etape="Rendez-vous")
    assert (etape.niveau, etape.variantes, etape.delai_s) == (NIVEAU_ETAPE, ("De l'étape.",), 6)
    a = resoudre(OUTIL_TARDE, reglages_agent=agent, reglages_principal=principal, etape="Accueil")
    assert (a.niveau, a.variantes, a.delai_s) == (NIVEAU_AGENT, ("De l'agent.", "Bis."), 4)
    p = resoudre(OUTIL_TARDE, reglages_agent={}, reglages_principal=principal)
    assert (p.niveau, p.variantes, p.delai_s) == (NIVEAU_PRINCIPAL, ("Du groupe.",), 5)
    d = resoudre(OUTIL_TARDE, reglages_agent={}, reglages_principal={})
    assert d.niveau == NIVEAU_DEFAUT and d.active is MOTIFS[OUTIL_TARDE].actif_par_defaut


def test_le_specialise_herite_puis_garde_la_sienne():
    principal = {"phrases_regles": [_regle(CONNECTEUR_ECHOUE, ["Pour tous."], "groupe")]}
    herite = resoudre(CONNECTEUR_ECHOUE, reglages_agent={}, reglages_principal=principal)
    assert herite.variantes == ("Pour tous.",) and herite.niveau == NIVEAU_PRINCIPAL
    sienne = resoudre(
        CONNECTEUR_ECHOUE,
        reglages_agent={"phrases_regles": [_regle(CONNECTEUR_ECHOUE, ["La mienne."])]},
        reglages_principal=principal,
    )
    assert sienne.variantes == ("La mienne.",) and sienne.niveau == NIVEAU_AGENT


def test_les_anciens_reglages_sont_repris_et_une_regle_les_remplace():
    ancien = {
        "attente": {"phrase_pont": "Une seconde.", "delai_phrase_pont_s": 3},
        "transfert_humain": {"phrase_mise_en_relation": "Je vous passe un collègue."},
    }
    pont = resoudre(PASSATION_TARDE, reglages_agent={}, reglages_principal=ancien)
    assert (pont.dite, pont.variantes, pont.delai_s, pont.niveau) == (
        True,
        ("Une seconde.",),
        3,
        NIVEAU_PRINCIPAL,
    )
    relation = resoudre(MISE_EN_RELATION, reglages_agent=ancien, reglages_principal=ancien)
    assert relation.dite and relation.variantes == ("Je vous passe un collègue.",)
    # Le thème Phrases a écrit la règle : elle l'emporte sur l'ancien réglage.
    neuf = {**ancien, "phrases_regles": [_regle(PASSATION_TARDE, ["Neuf."], "groupe", delai_s=2)]}
    assert resoudre(PASSATION_TARDE, reglages_agent={}, reglages_principal=neuf).variantes == ("Neuf.",)
    # Sans ancien réglage : le défaut (éteint, comme avant le chantier).
    assert not resoudre(PASSATION_TARDE, reglages_agent={}, reglages_principal={}).dite
    assert not resoudre(MISE_EN_RELATION, reglages_agent={}, reglages_principal={}).dite


@pytest.mark.asyncio
async def test_une_regle_eteinte_n_est_jamais_dite_meme_avec_une_phrase_propre():
    moteur = _FauxMoteur(lambda: 0.0)
    moteur.active_agent.reglages = {
        "phrases_regles": [_regle(CONNECTEUR_ECHOUE, ["X."], active=False)]
    }
    diseur = DiseurDePhrases(moteur)
    assert await diseur.dire(CONNECTEUR_ECHOUE) is False
    assert await diseur.dire_la_parole(CONNECTEUR_ECHOUE, texte="Propre.") is None
    assert diseur.prendre(CONNECTEUR_ECHOUE) is None
    assert moteur.dites == [] and not moteur._gathered_context.get(CLE_TRACE)


@pytest.mark.asyncio
async def test_historique_et_micro_jamais_coupe():
    moteur = _FauxMoteur(lambda: 0.0)
    appels = []

    async def queue_speech(texte, **options):
        appels.append((texte, options))
        fin = asyncio.Event()
        fin.set()
        return SimpleNamespace(wait=fin.wait, text=texte)

    moteur.queue_speech = queue_speech
    diseur = DiseurDePhrases(moteur)
    parole = await diseur.dire_la_parole(CONNECTEUR_ECHOUE, texte="Je transmets.")
    assert parole.text == "Je transmets."
    await diseur.attendre_la_fin()
    await diseur.dire_la_parole(APPELANT_SE_TAIT, historique=False)
    (t1, o1), (t2, o2) = appels
    assert o1["append_to_context"] is True and o1["mute_user"] is False
    assert o2["append_to_context"] is False and o2["mute_user"] is False
    trace = moteur._gathered_context[CLE_TRACE]
    assert [e["motif"] for e in trace] == [CONNECTEUR_ECHOUE, APPELANT_SE_TAIT]


@pytest.mark.asyncio
async def test_une_phrase_coupee_n_est_jamais_relancee():
    moteur = _FauxMoteur(lambda: 0.0)
    coupee = asyncio.Event()

    async def queue_speech(texte, **_):
        moteur.dites.append(texte)
        return SimpleNamespace(wait=coupee.wait, text=texte)

    moteur.queue_speech = queue_speech
    diseur = DiseurDePhrases(moteur)
    assert await diseur.dire(CONNECTEUR_ECHOUE) is True
    assert diseur.en_cours
    coupee.set()  # l'appelant l'a coupée : la lecture se termine là
    await diseur.attendre_la_fin()
    await asyncio.sleep(0.05)
    assert moteur.dites == [MOTIFS[CONNECTEUR_ECHOUE].variantes_defaut[0]]
    assert not diseur.en_cours


@pytest.mark.asyncio
async def test_l_appelant_qui_reflechit_ne_declenche_aucune_phrase_systeme():
    """Aucune attente du système en cours (la condition est fausse) : l'horloge rend « non »,
    quel que soit le temps que l'appelant met à répondre."""
    moteur = _FauxMoteur(lambda: 0.0)
    diseur = DiseurDePhrases(moteur)
    assert await diseur.attendre_le_systeme(0.01, lambda: False, pas_s=0.001) is False


@pytest.mark.asyncio
async def test_au_clavier_aucune_attente_n_est_dite():
    moteur = _FauxMoteur(lambda: 0.0)
    moteur.sans_sortie_audio = True
    diseur = DiseurDePhrases(moteur)
    assert await diseur.dire("travail_dure") is False
    assert await diseur.dire(CONNECTEUR_ECHOUE) is True  # une annonce s'écrit comme avant


# --------------------------------------------------------------------------- #
# F21 : l'outil lent
# --------------------------------------------------------------------------- #


def _moteur_outil(delai=0.05, active=True):
    moteur = _FauxMoteur(lambda: 0.0)
    moteur.active_agent.llm = object()
    moteur.active_agent.reglages = {
        "phrases_regles": [_regle(OUTIL_TARDE, ["Je vérifie."], delai_s=0.5, active=active)]
    }
    moteur.phrases = DiseurDePhrases(moteur)
    # Le délai réel est la borne basse du schéma (0,5 s) ; le test le raccourcit.
    phrase = moteur.phrases.phrase(OUTIL_TARDE)
    moteur.phrases.phrase = lambda *_a, **_k: type(phrase)(
        motif=phrase.motif, variantes=phrase.variantes, delai_s=delai, active=phrase.active, niveau=phrase.niveau
    )
    return moteur


async def _lancer(moteur, duree, llm=None):
    rendu = AsyncMock()

    async def action(params):
        await asyncio.sleep(duree)
        await params.result_callback({"status": "ok"})

    params = SimpleNamespace(
        result_callback=rendu, llm=llm if llm is not None else moteur.active_agent.llm, arguments={}
    )
    await envelopper_l_action(moteur, "outil", action, moteur.active_agent, garde=False)(params)
    await moteur.phrases.attendre_la_fin()
    rendu.assert_awaited_once()


@pytest.mark.asyncio
async def test_un_outil_lent_fait_dire_la_phrase_une_fois():
    moteur = _moteur_outil()
    await _lancer(moteur, 0.3)
    assert moteur.dites == ["Je vérifie."]


@pytest.mark.asyncio
async def test_un_outil_rapide_ou_du_fond_ou_eteint_ne_dit_rien():
    moteur = _moteur_outil()
    await _lancer(moteur, 0.0)
    await _lancer(moteur, 0.3, llm=object())  # le cerveau de fond
    await asyncio.sleep(0.1)
    assert moteur.dites == []
    eteint = _moteur_outil(active=False)
    await _lancer(eteint, 0.3)
    assert eteint.dites == []


# --------------------------------------------------------------------------- #
# Réponse perdue, connecteur, transfert échoué
# --------------------------------------------------------------------------- #


def test_la_reponse_perdue_suit_la_regle_de_l_agent():
    from api.services.panne.garde_modele import poser_la_reponse_perdue
    from api.services.pipecat.reponse_avalee import phrase_de_repli

    moteur = _FauxMoteur(lambda: 0.0)
    moteur.phrases = DiseurDePhrases(moteur)
    agent = SimpleNamespace(
        reglages={"phrases_regles": [_regle(REPONSE_PERDUE, ["Pardon ?"])]},
        current_node=None,
        workflow_id=3,
    )
    llm = SimpleNamespace()
    poser_la_reponse_perdue(moteur, agent, llm)
    assert phrase_de_repli(llm) == "Pardon ?"
    assert moteur._gathered_context[CLE_TRACE][-1]["motif"] == REPONSE_PERDUE
    agent.reglages = {"phrases_regles": [_regle(REPONSE_PERDUE, [], active=False)]}
    assert phrase_de_repli(llm) is None
    # Un service sans moteur garde le défaut du catalogue.
    assert phrase_de_repli(SimpleNamespace()) == MOTIFS[REPONSE_PERDUE].variantes_defaut[0]


@pytest.mark.asyncio
async def test_le_connecteur_en_echec_dit_la_regle_ou_sa_phrase_propre():
    from api.services.integrations.connectors.outil import _dire_le_repli

    moteur = _FauxMoteur(lambda: 0.0)

    async def queue_speech(texte, **_):
        moteur.dites.append(texte)
        fin = asyncio.Event()
        fin.set()
        return SimpleNamespace(wait=fin.wait, text=texte)

    moteur.queue_speech = queue_speech
    moteur.phrases = DiseurDePhrases(moteur)
    assert await _dire_le_repli(moteur, None) == MOTIFS[CONNECTEUR_ECHOUE].variantes_defaut[0]
    await moteur.phrases.attendre_la_fin()
    assert await _dire_le_repli(moteur, "Phrase du connecteur.") == "Phrase du connecteur."
    await moteur.phrases.attendre_la_fin()
    moteur.active_agent.reglages = {
        "phrases_regles": [_regle(CONNECTEUR_ECHOUE, [], active=False)]
    }
    assert await _dire_le_repli(moteur, "Phrase du connecteur.") is None
    # Un moteur sans diseur (simulé) ne dit rien.
    assert await _dire_le_repli(SimpleNamespace(), None) is None


@pytest.mark.asyncio
async def test_le_transfert_echoue_ne_dit_rien_par_defaut_puis_sa_phrase_allumee():
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    moteur = _FauxMoteur(lambda: 0.0)

    async def queue_speech(texte, **_):
        moteur.dites.append(texte)
        fin = asyncio.Event()
        fin.set()
        return SimpleNamespace(wait=fin.wait, text=texte)

    moteur.queue_speech = queue_speech
    moteur.phrases = DiseurDePhrases(moteur)
    outils = CustomToolManager.__new__(CustomToolManager)
    outils._engine = moteur
    rendu = AsyncMock()
    resultat = {"action": "transfer_failed", "status": "failed", "reason": "no_answer"}
    await outils._handle_transfer_result(resultat, SimpleNamespace(result_callback=rendu), None)
    assert moteur.dites == [] and "said_to_caller" not in rendu.await_args.args[0]
    moteur.active_agent.reglages = {
        "phrases_regles": [_regle(TRANSFERT_ECHOUE, ["Personne ne répond."])]
    }
    await outils._handle_transfer_result(resultat, SimpleNamespace(result_callback=rendu), None)
    assert moteur.dites == ["Personne ne répond."]
    assert rendu.await_args.args[0]["said_to_caller"] == "Personne ne répond."
