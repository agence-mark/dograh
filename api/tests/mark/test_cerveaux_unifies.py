"""[.mark] Partie 2, U6 (sous-lot 1) : les trois cerveaux unifiés.

Ce qui doit tenir : les consignes de l'appelant simulé et du juge, formules d'au revoir comprises, sont VERSÉES mot pour mot
depuis le code, LUES en bibliothèque, et le texte du code ne sert qu'en SECOURS ; un juge sur clé d'API ne note jamais le modèle de
l'agent ni celui du builder ; sur Claude Code l'exemption est dite sur chaque avis ; les cerveaux sont simulés, rien n'est dépensé.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.schemas.appel_simule import (
    CONSIGNE_APPELANT,
    CONSIGNE_JUGE,
    ReglagesAppelantSimule,
    RoleSimule,
)
from api.services.builder import consignes, versement
from api.services.builder.bibliotheque import service
from api.services.builder.cerveau import independance, simules
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.services.builder.tests_agent import creation, execution, jeu
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT
from api.tests.mark.test_builder_tests_agent import EQUIPE, MoteurFactice, banc  # noqa: F401 -- la fixture `banc`


@pytest.fixture
async def verse(monde):
    rapport = await versement.verser()
    assert rapport.erreurs == [], rapport.erreurs
    return rapport


# --- versées / lues / secours -------------------------------------------------------------------------------------


async def test_les_consignes_sont_versees_mot_pour_mot(verse):
    assert await consignes.consigne_appelant() == CONSIGNE_APPELANT
    assert await consignes.consigne_juge() == CONSIGNE_JUGE
    assert await consignes.adieux() == jeu.ADIEUX
    element = await service.lire_element("personnages-appelant", "consigne")
    assert element.courante.contenu["consigne"] == CONSIGNE_APPELANT


async def test_la_consigne_ecrite_en_bibliotheque_est_celle_que_le_code_lit(verse):
    await service.ajouter_version(
        "personnages-appelant", "consigne", {"description": "d", "consigne": "Parle comme au comptoir.", "adieux": ["ciao"]}, "evan"
    )
    await service.ajouter_version(
        "criteres-types", "grille-juge", {"critere": {"type": "juge"}, "consigne": "Sois strict."}, "evan"
    )
    assert await consignes.consigne_appelant() == "Parle comme au comptoir."
    assert await consignes.adieux() == ("ciao",)
    assert await consignes.consigne_juge() == "Sois strict."
    # et c'est elle que reçoit l'appelant joué
    assert jeu.consigne_de_l_appelant({}, {}, await consignes.consigne_appelant()).startswith("Parle comme au comptoir.")


async def test_sans_element_ou_bibliotheque_illisible_le_texte_du_code_sert_de_secours(monde, monkeypatch):
    assert await consignes.consigne_appelant() == CONSIGNE_APPELANT
    assert await consignes.consigne_juge() == CONSIGNE_JUGE
    assert await consignes.adieux() == jeu.ADIEUX

    async def casse(*_):
        raise RuntimeError("bibliothèque indisponible")

    monkeypatch.setattr(service, "element_ou_none", casse)
    assert await consignes.consigne_appelant() == CONSIGNE_APPELANT
    assert await consignes.adieux() == jeu.ADIEUX


async def test_une_consigne_vide_ne_sert_pas(verse):
    await service.ajouter_version("personnages-appelant", "consigne", {"description": "d", "consigne": "   "}, "evan")
    assert await consignes.consigne_appelant() == CONSIGNE_APPELANT
    assert await consignes.adieux() == jeu.ADIEUX


async def test_les_adieux_de_la_bibliotheque_terminent_la_conversation(monde):
    await service.creer(
        "personnages-appelant", "consigne", "Consigne", {"description": "d", "consigne": "c", "adieux": ["ciao"]}, "evan"
    )

    class Appelant:
        async def repondre(self, lignes):
            return "Allez, ciao !"

    moteur = MoteurFactice(["Bonjour.", "Entendu, ciao.", "Je suis toujours là."])
    obs = await jeu.jouer_une_conversation(None, {"scenario": {}}, Appelant(), moteur.en_moteur(), tours_max=6)
    assert [r for r, _ in obs.lignes].count("moi") == 1  # la conversation s'arrête après le premier échange d'adieux


# --- l'indépendance du juge (D9) ----------------------------------------------------------------------------------


def test_un_juge_sur_cle_ne_note_ni_l_agent_ni_le_builder():
    a = independance.controler(source_juge="cle_api", modele_juge="mistral/mistral-large-latest", modele_agent="mistral-large-latest")
    assert a.refuse and "agent" in a.refus
    b = independance.controler(source_juge="cle_api", modele_juge="openai/gpt-x", modele_builder="gpt-x")
    assert b.refuse and "builder" in b.refus
    assert not independance.controler(source_juge="cle_api", modele_juge="a/m1", modele_agent="m2", modele_builder="m3").refuse


def test_sur_claude_code_l_exemption_est_dite():
    c = independance.controler(source_juge="claude_code", modele_juge="x", modele_agent="x", modele_builder="x")
    assert not c.refuse and c.mention == independance.MENTION_CLAUDE_CODE


async def test_la_route_refuse_un_juge_du_modele_du_builder(monkeypatch):
    from api.routes import appel_simule as route

    monkeypatch.setattr(independance, "modele_du_builder", AsyncMock(return_value="mistral-large-latest"))
    monkeypatch.setattr(route.stockage, "enregistrer_reglages", AsyncMock(side_effect=lambda org, r: r))
    reglages = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c"), juge=RoleSimule(consigne="j", modele="mistral/mistral-large-latest")
    )
    with pytest.raises(HTTPException) as erreur:
        await route.save_reglages_appelant_simule(reglages, user=EQUIPE.user)
    assert erreur.value.status_code == 422
    # sur Claude Code l'exemption passe
    ok = reglages.model_copy(update={"juge": reglages.juge.model_copy(update={"source": "claude_code"})})
    assert (await route.save_reglages_appelant_simule(ok, user=EQUIPE.user)).juge.source == "claude_code"


# --- les cerveaux d'un test : chacun son rôle, aucun appel réel -----------------------------------------------------


def test_tout_fournisseur_se_joint_par_son_prefixe_ou_ses_reglages():
    base = ReglagesCerveau()
    mistral = simules.reglages_du_role(RoleSimule(consigne="c", modele="mistral/mistral-small-latest"), base)
    assert (mistral.format, mistral.adresse, mistral.modele) == ("openai", "https://api.mistral.ai/v1", "mistral-small-latest")
    autre = simules.reglages_du_role(
        RoleSimule(consigne="c", modele="maison/modele-x", format="openai", adresse="https://llm.exemple.test/v1"), base
    )
    assert (autre.adresse, autre.modele) == ("https://llm.exemple.test/v1", "modele-x")


async def test_sur_claude_code_aucun_cerveau_n_est_construit():
    role = RoleSimule(consigne="c", source="claude_code", identifiant="x")
    assert await simules.cerveau_du_role(1, role, ReglagesCerveau()) is None


def _agent():
    return SimpleNamespace(id=AGENT, user_id=1, organization_id=ORG_CLIENT, workflow_configurations={})


async def _suite(banc, monkeypatch, roles, *, modele_agent="agent-m", modele_builder="builder-m"):
    from api.services.appel_simule import reglages as appel_simule
    from api.services.builder.cerveau import reglages as reglages_cerveau

    monkeypatch.setattr(appel_simule, "lire_reglages", AsyncMock(return_value=roles))
    monkeypatch.setattr(reglages_cerveau, "lire", AsyncMock(return_value=ReglagesCerveau(modele=modele_builder)))
    monkeypatch.setattr(reglages_cerveau, "organisation_des_reglages", AsyncMock(return_value=1))
    monkeypatch.setattr(execution, "_modele_de_l_agent", AsyncMock(return_value=modele_agent))
    construits: list[str] = []

    async def fabrique(organisation, role, base):
        construits.append(role.modele)
        if not role.identifiant:
            return None
        if role is roles.juge:
            return CerveauFactice(tour(texte('{"ok": true, "confiance": 0.9, "raison": "r"}')))
        return CerveauFactice(tour(texte("Un rendez-vous.")))

    monkeypatch.setattr(simules, "cerveau_du_role", fabrique)
    await creation.creer(
        ORG_CLIENT,
        AGENT,
        nom="Libre",
        scenario="Prendre un rendez-vous.",
        criteres=[{"type": "appel_clos_par_l_agent"}],
        questions_juge=["Le ton est-il naturel ?"],
    )
    execution.DEPENDANCES.moteur = MoteurFactice(["Bonjour.", "Noté, au revoir."], fin_au_tour=1).en_moteur
    return construits


async def test_un_test_prend_l_appelant_et_le_juge_du_labo_pas_celui_du_builder(banc, monkeypatch):
    roles = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c", modele="mistral/appelant-m", identifiant="k1"),
        juge=RoleSimule(consigne="j", modele="openai/juge-m", identifiant="k2"),
    )
    construits = await _suite(banc, monkeypatch, roles)
    r = await execution.rejouer_la_suite(EQUIPE.user, _agent(), repetitions=1)
    assert sorted(construits) == ["mistral/appelant-m", "openai/juge-m"]
    assert r["resultats"][0]["essais"][0]["reussi"] is True


async def test_un_juge_du_modele_de_l_agent_est_refuse_et_ne_juge_pas(banc, monkeypatch):
    roles = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c", modele="mistral/appelant-m", identifiant="k1"),
        juge=RoleSimule(consigne="j", modele="mistral/agent-m", identifiant="k2"),
    )
    construits = await _suite(banc, monkeypatch, roles)
    r = await execution.rejouer_la_suite(EQUIPE.user, _agent(), repetitions=1)
    avis = r["resultats"][0]["juge"]
    assert avis["avis"] == [] and "same model as the judged agent" in avis["erreur"]
    assert "mistral/agent-m" not in construits  # le cerveau du juge n'est même pas construit


async def test_sur_claude_code_le_juge_ne_fait_aucun_appel_et_porte_sa_mention(banc, monkeypatch):
    roles = ReglagesAppelantSimule(
        appelant=RoleSimule(consigne="c", identifiant="k1"),
        juge=RoleSimule(consigne="j", source="claude_code"),
    )
    await _suite(banc, monkeypatch, roles)
    r = await execution.rejouer_la_suite(EQUIPE.user, _agent(), repetitions=1)
    avis = r["resultats"][0]["juge"]
    assert avis["a_juger"] is True and avis["avis"] == [] and avis["mention"] == independance.MENTION_CLAUDE_CODE
