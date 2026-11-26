"""[.mark] Partie 1, lot 8a (C2, C3, 114) : le moteur d'appel (voix et clavier) joue le crochet ``au_decroche`` des modules allumés au lieu d'appeler la restauration par son nom.

Ce qui tient : le moteur n'importe plus la restauration ; la voix pose l'ouverture, le canal du direct et le chargement dans l'ordre d'avant (S15 : la phrase d'accueil n'attend pas le
chargement) ; le clavier pose la même ouverture et ATTEND le chargement, borné ; le direct se compose au canal et se ferme à la fin.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path

import pytest

from api.services.modules import crochets
from api.services.pipecat import run_pipeline
from api.services.restauration import crochets as restauration
from api.services.restauration.appel_et_memoire import memoire_de_l_appel as M
from api.services.workflow import text_chat_runner

ALLUMEE = {"commande_sur_catalogue": True}
RACINE = Path(__file__).resolve().parents[3] / "services"


def test_le_moteur_d_appel_n_importe_plus_la_restauration():
    """Le Grep de la fiche : ni ``workflow`` ni ``pipecat`` ne nomment ``services.restauration`` (le contrat 2 de 8c part de là)."""
    trouves = [
        f"{fichier.relative_to(RACINE)}:{numero}"
        for dossier in ("workflow", "pipecat")
        for fichier in sorted((RACINE / dossier).rglob("*.py"))
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"services\.restauration", ligne)
    ]
    assert trouves == []


def test_la_voix_joue_ses_trois_moments_dans_l_ordre_de_l_appel_et_la_fin_dans_le_finally():
    corps = inspect.getsource(run_pipeline._run_pipeline_corps)
    contexte, canal, montage = (corps.index(f"crochets.{m}") for m in ("CONTEXTE", "CANAL", "MONTAGE"))
    assert contexte < canal < montage
    assert "crochets.fin_de_l_appel" in corps[corps.rindex("finally:") :]  # la fin de l'appel est dans le dernier finally, jouée même sur une coupure


def test_le_clavier_joue_les_memes_moments_dans_le_meme_ordre():
    corps = inspect.getsource(text_chat_runner._executer_le_tour)
    assert corps.index("crochets.CONTEXTE") < corps.index("crochets.MONTAGE")
    assert "au_clavier=True" in corps[corps.index("crochets.MONTAGE") :]  # le clavier attend le chargement : sa phrase d'accueil n'existe pas


# ---- ce que fait la restauration à chaque moment


@pytest.fixture
def decroche_espionne(monkeypatch):
    appels: list[tuple] = []

    async def ouverture(contexte, run_configs, organization_id, workflow_id, reglages=None, direction=None):
        appels.append(("ouverture", organization_id, workflow_id, direction))
        return {**contexte, "etat_ouverture": "PAUSE"}

    def charger_au_decroche(organization_id, run_id, run_configs, contexte, fiche):
        appels.append(("charge_a_la_voix", organization_id, run_id, fiche))
        return asyncio.get_running_loop().create_future()  # une tâche jamais terminée : la voix ne l'attend pas

    async def charger_au_clavier(organization_id, run_id, run_configs, contexte, fiche):
        appels.append(("charge_au_clavier", organization_id, run_id, fiche))

    monkeypatch.setattr(restauration, "injecter_l_ouverture_de_la_caisse", ouverture)
    monkeypatch.setattr(M, "charger_au_decroche", charger_au_decroche)
    monkeypatch.setattr(M, "charger_au_clavier", charger_au_clavier)
    return appels


async def test_le_decroche_a_la_voix_pose_l_ouverture_puis_lance_le_chargement_sans_l_attendre(decroche_espionne):
    d = await crochets.au_decroche(crochets.Decroche(crochets.CONTEXTE, {"a": 1}, ALLUMEE, 7, 3, 42, direction="entrant"))
    assert d.contexte == {"a": 1, "etat_ouverture": "PAUSE"} and decroche_espionne == [("ouverture", 7, 3, "entrant")]
    fiche = {}
    await asyncio.wait_for(crochets.au_decroche(crochets.Decroche(crochets.MONTAGE, d.contexte, ALLUMEE, 7, 3, 42, fiche=fiche)), 1)  # rend la main tout de suite (S15)
    assert decroche_espionne[-1] == ("charge_a_la_voix", 7, 42, fiche)


async def test_le_decroche_au_clavier_pose_la_meme_ouverture_et_attend_le_chargement(decroche_espionne):
    d = await crochets.au_decroche(crochets.Decroche(crochets.CONTEXTE, {"a": 1}, ALLUMEE, 7, 3, 42, au_clavier=True))
    assert d.contexte == {"a": 1, "etat_ouverture": "PAUSE"}  # la même ouverture qu'à la voix
    fiche = {}
    await crochets.au_decroche(crochets.Decroche(crochets.MONTAGE, d.contexte, ALLUMEE, 7, 3, 42, fiche=fiche, au_clavier=True))
    assert decroche_espionne[-1] == ("charge_au_clavier", 7, 42, fiche)


async def test_un_module_eteint_ne_pose_rien_au_decroche(decroche_espionne):
    d = await crochets.au_decroche(crochets.Decroche(crochets.CONTEXTE, {"a": 1}, {"commande_sur_catalogue": False}, 7, 3, 42))
    await crochets.au_decroche(crochets.Decroche(crochets.MONTAGE, d.contexte, {"commande_sur_catalogue": False}, 7, 3, 42, fiche={}))
    assert d.contexte == {"a": 1} and decroche_espionne == []


async def test_un_crochet_qui_leve_au_decroche_laisse_le_contexte_et_ne_coupe_pas_l_appel(monkeypatch):
    async def ouverture(*_a, **_k):
        raise RuntimeError("la caisse ne répond pas")

    monkeypatch.setattr(restauration, "injecter_l_ouverture_de_la_caisse", ouverture)
    d = await crochets.au_decroche(crochets.Decroche(crochets.CONTEXTE, {"a": 1}, ALLUMEE, 7, 3, 42))
    assert d.contexte == {"a": 1}


# ---- le direct des appels (C3)


class _Direct:
    def __init__(self):
        self.vu: list = []
        self.ferme: list = []

    def composer(self, original):
        async def canal(message):
            self.vu.append(message)
            if original is not None:
                await original(message)

        return canal

    def commencer(self):
        self.vu.append("commence")

    async def fermer(self, fiche=None):
        self.ferme.append(fiche)


@pytest.fixture
def direct(monkeypatch):
    fait = _Direct()
    prepares: list[dict] = []

    async def preparer(**options):
        prepares.append(options)
        return fait

    monkeypatch.setattr(restauration, "preparer_le_direct", preparer)
    fait.prepares = prepares
    yield fait
    restauration._DIRECTS.clear()


async def test_le_direct_se_compose_au_canal_de_l_amont_sans_le_remplacer(direct):
    recus: list = []

    async def amont(message):
        recus.append(message)

    d = await crochets.au_decroche(
        crochets.Decroche(crochets.CANAL, {"caller_number": "x"}, ALLUMEE, 7, 3, 42, cle_de_l_etablissement=11, canal=amont)
    )
    await d.canal({"type": "rtf-bot-text"})
    assert direct.vu == ["commence", {"type": "rtf-bot-text"}] and recus == [{"type": "rtf-bot-text"}]  # le direct le voit, l'amont aussi
    assert direct.prepares[0]["cle_etablissement"] == 11 and direct.prepares[0]["workflow_run_id"] == 42 and direct.prepares[0]["workflow_id"] == 3


async def test_sans_direct_le_canal_reste_celui_de_l_amont(monkeypatch):
    async def aucun(**_options):
        return None

    monkeypatch.setattr(restauration, "preparer_le_direct", aucun)

    async def amont(_message):
        return None

    d = await crochets.au_decroche(crochets.Decroche(crochets.CANAL, {}, ALLUMEE, 7, 3, 42, canal=amont))
    assert d.canal is amont and restauration._DIRECTS == {}


async def test_le_direct_se_ferme_a_la_fin_meme_sur_une_coupure_et_une_seule_fois(direct):
    await crochets.au_decroche(crochets.Decroche(crochets.CANAL, {}, ALLUMEE, 7, 3, 42))
    fiche = {"x": 1}
    await crochets.fin_de_l_appel(crochets.FinDeLAppel(42, fiche, 7, ALLUMEE))
    await crochets.fin_de_l_appel(crochets.FinDeLAppel(42, fiche, 7, ALLUMEE))  # rejouée (un échec du montage, puis le finally) : rien de plus
    assert direct.ferme == [fiche]


async def test_la_connexion_de_l_appel_est_fermee_meme_si_la_fermeture_du_direct_leve(direct):
    class Connexion:
        fermee = False

        def is_closed(self):
            return self.fermee

        async def close(self):
            self.fermee = True

    async def qui_leve(fiche=None):
        raise RuntimeError("flux en panne")

    direct.fermer = qui_leve
    connexion = Connexion()
    M._APPELS["42"] = M.AppelOuvert("base_essai", connexion=connexion)
    try:
        await crochets.au_decroche(crochets.Decroche(crochets.CANAL, {}, ALLUMEE, 7, 3, 42))
        await crochets.fin_de_l_appel(crochets.FinDeLAppel(42, None, 7, ALLUMEE))
        assert connexion.fermee and M.appel_ouvert(42) is None
    finally:
        M._APPELS.pop("42", None)
