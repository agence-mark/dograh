"""RA-A, R3 (a) (audit du 04/11, rouge n° 6) : une écriture mise de côté pendant l'appel n'est jamais perdue.

Un connecteur qui n'a pas pu écrire pendant l'appel (délai, logiciel en panne) range l'écriture dans la fiche
(``connecteurs_differes``). Elle n'était rejouée que si l'après-appel de l'agent était allumé ET le module
« connecteurs » coché, et un échec définitif ne laissait aucune demande de rappel. Maintenant : toujours
rejouée, une fois (jamais deux), et un échec définitif crée la demande de rappel et alerte l'équipe.

Sans réseau ni fournisseur : le magasin des runs, le connecteur et le courriel sont remplacés ; la demande de
rappel est écrite pour de vrai dans une base de client d'essai (Postgres des tests).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from api.db import db_client
from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients import connexion as schema
from api.schemas.apres_appel import ApresAppelAgent
from api.services.apres_appel import chaine
from api.services.integrations.connectors import execution
from api.tests.mark.test_base_client import base_essai  # noqa: F401

DIFFERE = {
    "connecteur": "google_agenda",
    "action": "book_appointment",
    "reglages": {},
    "arguments": {"debut": "2030-01-07T09:00:00+01:00"},
}
ETAPE = "module:connecteurs"


async def _async(valeur):
    return valeur


def _run(differes=(DIFFERE,), mode="twilio"):
    fiche = {"connecteurs_differes": copy.deepcopy(list(differes))} if differes else {}
    return SimpleNamespace(
        id=9, workflow_id=3, mode=mode, gathered_context=fiche, initial_context={}, annotations={},
        definition=SimpleNamespace(workflow_configurations={}, version_number=1), definition_id=1,
        workflow=SimpleNamespace(name="Agent"),
    )


# --------------------------------------------------------------------------- #
# 1. La règle : quelles étapes jouer
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_une_ecriture_mise_de_cote_est_rejouee_meme_si_l_apres_appel_est_eteint():
    etapes = await chaine._etapes_a_jouer(_run(), 5, ApresAppelAgent(actif=False))
    assert ETAPE in etapes


@pytest.mark.asyncio
async def test_une_ecriture_mise_de_cote_est_rejouee_meme_si_le_module_n_est_pas_coche():
    etapes = await chaine._etapes_a_jouer(_run(), 5, ApresAppelAgent(actif=True, modules=[]))
    assert ETAPE in etapes and etapes.count(ETAPE) == 1
    cochee = await chaine._etapes_a_jouer(_run(), 5, ApresAppelAgent(actif=True, modules=["connecteurs"]))
    assert cochee.count(ETAPE) == 1


@pytest.mark.asyncio
async def test_sans_ecriture_mise_de_cote_rien_ne_change():
    assert await chaine._etapes_a_jouer(_run(differes=()), 5, ApresAppelAgent(actif=False)) == []
    assert ETAPE not in await chaine._etapes_a_jouer(_run(differes=()), 5, ApresAppelAgent(actif=True))


# --------------------------------------------------------------------------- #
# 2. La chaîne : rejeu, jamais deux fois, échec définitif
# --------------------------------------------------------------------------- #


class FauxStockage:
    def __init__(self, run, bloc=None):
        self.run, self.bloc = run, bloc or {}

    async def get_workflow_run_with_context(self, run_id):
        return self.run, 5

    async def lire_apres_appel(self, run_id):
        return copy.deepcopy(self.bloc)

    async def fusionner_apres_appel(self, run_id, *, etape=None, valeur=None, racine=None):
        if racine:
            self.bloc.update(racine)
        if etape is not None:
            etapes = self.bloc.setdefault("etapes", {})
            etapes[etape] = {**etapes.get(etape, {}), **(valeur or {})}
        return copy.deepcopy(self.bloc)


class FausseConnexion:
    async def close(self):
        pass


@pytest.fixture
def banc(monkeypatch):
    """La chaîne réelle ; autour d'elle, le magasin des runs, le connecteur et l'alerte sont remplacés."""
    etat = SimpleNamespace(stock=None, appels=[], alertes=[], rappels=[], echoue=False, agent=ApresAppelAgent())

    async def appeler(organization_id, connecteur, action, arguments, ctx, delai):
        etat.appels.append((connecteur.nom, action.nom, arguments))
        if etat.echoue:
            raise RuntimeError("logiciel injoignable")
        return {"ok": True}

    async def analyse(run, organization_id):
        return {"conversation": {"lines": []}}

    async def sujets(connexion):
        return []

    async def notifier(organization_id, sujet, texte):
        etat.alertes.append(sujet)
        return ["equipe@exemple.test"]

    async def base(organization_id):
        return FausseConnexion()

    async def rappel(connexion, appel_id, resume):
        etat.rappels.append((appel_id, resume))
        return 77

    def monter(run, bloc=None, agent=None):
        etat.stock = FauxStockage(run, bloc)
        etat.agent = agent or ApresAppelAgent()
        # Le même objet que ``chaine`` et ``modules`` importent : un seul remplacement pour les deux.
        for nom in ("get_workflow_run_with_context", "lire_apres_appel", "fusionner_apres_appel"):
            monkeypatch.setattr(db_client, nom, getattr(etat.stock, nom))
        monkeypatch.setattr(chaine, "reglages_de_lagent", lambda configurations: etat.agent)

    monkeypatch.setattr(execution, "appeler", appeler)
    monkeypatch.setattr("api.services.analyse_run.du_run.analyser_le_run", analyse)
    monkeypatch.setattr(chaine, "lire_reglages", lambda organization_id: _async(SimpleNamespace(smtp=None)))
    monkeypatch.setattr(chaine, "construire_envoi", lambda *a, **k: {"numero_appelant": "+33612345678"})
    monkeypatch.setattr("api.services.fiche.verdict.verdict_du_run", lambda run: _async(None))
    monkeypatch.setattr("api.services.apres_appel.taches._fuseau", lambda organization_id: _async("Europe/Paris"))
    monkeypatch.setattr(chaine, "notifier", notifier)
    monkeypatch.setattr(chaine, "_base", base)
    monkeypatch.setattr(chaine.sql, "sujets_actifs", sujets)
    monkeypatch.setattr(chaine.sql, "demande_de_rappel_ecriture_perdue", rappel, raising=False)
    monkeypatch.setattr(chaine, "_reessayer", lambda *a, **k: _async(None))
    etat.monter = monter
    return etat


@pytest.mark.asyncio
async def test_le_rejeu_a_lieu_apres_appel_eteint_et_ne_se_fait_qu_une_fois(banc):
    banc.monter(_run(), agent=ApresAppelAgent(actif=False))
    etapes = await chaine._etapes_a_jouer(banc.stock.run, 5, banc.agent)
    await chaine.executer(9, etapes)
    assert banc.stock.bloc["etapes"][ETAPE]["statut"] == "ok", banc.stock.bloc["etapes"][ETAPE]
    assert [a[:2] for a in banc.appels] == [("google_agenda", "book_appointment")]
    await chaine.executer(9, etapes)  # une relance : l'étape est déjà faite
    assert len(banc.appels) == 1


@pytest.mark.asyncio
async def test_un_echec_definitif_cree_une_demande_de_rappel_et_alerte_l_equipe_une_seule_fois(banc):
    banc.echoue = True
    bloc = {"appel_id": 41, "demande_id": 8, "etapes": {"ecriture": {"statut": "ok"}}}
    banc.monter(_run(), bloc, agent=ApresAppelAgent(actif=False))
    for tentative in (1, 2, 3):  # trois essais : le dernier est définitif
        await chaine.executer(9, [ETAPE], tentative)
    assert banc.stock.bloc["etapes"][ETAPE]["definitive"] is True
    assert len(banc.alertes) == 1
    assert len(banc.rappels) == 1
    appel_id, resume = banc.rappels[0]
    assert appel_id == 41 and "book_appointment" in resume and "+33612345678" in resume
    await chaine.executer(9, [ETAPE], 3)  # « Retry » à l'écran qui échoue encore : pas de seconde demande
    assert len(banc.rappels) == 1


@pytest.mark.asyncio
async def test_un_echec_non_definitif_ne_cree_pas_de_demande(banc):
    banc.echoue = True
    banc.monter(_run(), {"appel_id": 41, "etapes": {}}, agent=ApresAppelAgent(actif=False))
    await chaine.executer(9, [ETAPE], 1)
    assert banc.rappels == [] and banc.alertes == []


# --------------------------------------------------------------------------- #
# 3. La demande de rappel, écrite dans la base du client (Postgres d'essai)
# --------------------------------------------------------------------------- #

TEXTE = "Rappel à faire : une écriture dans un outil de l'entreprise n'a pas abouti."


def _envoi(**demande):
    return {
        "dograh_run_id": 9, "dograh_workflow_id": 7, "agent_nom": "Agent", "dograh_definition_id": 70,
        "canal": "telephone", "numero_appelant": "+33612345678", "debut": datetime.now(UTC).isoformat(),
        "issue": "issue_nouvelle", "contact": {"nom": "Dupont"}, "demande": demande or None,
        "champs": [{"nom": "nom", "valeur": "Dupont", "origine": "dicte"}] if demande else [],
        "tours": [], "verbatim": [],
    }


@pytest.fixture
async def connexion_client(base_essai):  # noqa: F811
    await schema.creer_base(base_essai)
    connexion = await schema.connecter(base_essai)
    try:
        yield connexion
    finally:
        await connexion.close()


@pytest.mark.asyncio
async def test_la_demande_de_rappel_s_ajoute_a_la_demande_de_l_appel_sans_se_doubler(connexion_client):
    connexion = connexion_client
    ecrit = await sql.recevoir_appel(connexion, _envoi(type="autre", sujet=None))
    premiere = await sql.demande_de_rappel_ecriture_perdue(connexion, ecrit["appel_id"], TEXTE)
    seconde = await sql.demande_de_rappel_ecriture_perdue(connexion, ecrit["appel_id"], TEXTE)
    assert premiere == seconde == ecrit["demande_id"]
    ligne = await connexion.fetchrow("SELECT priorite, resume FROM mark.demande WHERE id = $1", premiere)
    assert ligne["priorite"] == 1 and ligne["resume"].count(TEXTE) == 1


@pytest.mark.asyncio
async def test_sans_demande_l_appel_en_recoit_une_a_rappeler(connexion_client):
    connexion = connexion_client
    ecrit = await sql.recevoir_appel(connexion, _envoi())
    assert ecrit["demande_id"] is None
    demande = await sql.demande_de_rappel_ecriture_perdue(connexion, ecrit["appel_id"], TEXTE)
    assert demande
    assert await connexion.fetchval("SELECT demande_id FROM mark.appel WHERE id = $1", ecrit["appel_id"]) == demande
    assert await sql.demande_de_rappel_ecriture_perdue(connexion, ecrit["appel_id"], TEXTE) == demande
    assert await connexion.fetchval("SELECT count(*) FROM mark.demande") == 1
