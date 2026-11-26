"""[.mark] Plan final Partie 1, lot 8b-1a (E2, E3 ; décision d'Evan du 24/11, plan § 17) : la commande est écrite en base au « oui » et part en caisse UNE fois,
à la fin de l'appel ; le SMS de confirmation et ``commande.creee`` partent avec elle.

Sur la vraie porte et la vraie source (``combinaisons.Partie``), la fin jouée par le vrai crochet des modules (``crochets.fin_de_l_appel``), à la voix et au clavier.

| Test | Ce qu'il prouve |
|---|---|
| fini après l'accord | au « oui » : rien en caisse, la ligne est ``retenue`` avec son numéro court ; la fin de l'appel l'envoie une fois |
| fini avant l'accord | rien n'est écrit, rien ne part |
| changée pendant l'appel | un seul envoi, la dernière version (lignes, total) |
| montage tombé puis vraie fin | la fin sans fiche (``None``) ne fait rien ; la vraie fin envoie |
| crochet rejoué | toujours un seul envoi |
| agent sans commande | la fin jouée (quel que soit l'interrupteur) n'ouvre rien et n'envoie rien |
| SMS | « oui » puis fin : un SMS et un ``commande.creee``, à la fin seulement ; « oui » puis annulée : aucun |
| clavier, tour qui finit la partie | l'organisation du tour arrive à la fin : la commande part |
"""

from __future__ import annotations

from collections import Counter

import pytest

from api.db.bases_clients.restauration_commande import commande_complete
from api.services.modules import crochets
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.envois_et_sms import envois
from api.services.restauration.envois_et_sms import sms_restauration as sms_resto
from api.services.restauration.envois_et_sms.sms_restauration import Envoi
from api.services.workflow import text_chat_runner as runner
from api.tests.mark.partie_1 import combinaisons as C
from api.tests.mark.partie_1.porte_essai import ORGANISATION_D_ESSAI

FINS = [pytest.param(False, id="voix"), pytest.param(True, id="clavier")]


async def _partie(faire_monde, monkeypatch, etat: str) -> C.Partie:
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette(etat), etat
    return partie


def _recues(partie: C.Partie) -> list[dict]:
    return list(partie.e.source.prise.recues)


async def _lignes_de_l_appel(partie: C.Partie) -> list[dict]:
    return [dict(r) for r in await partie.e.monde.c.fetch(
        "SELECT numero::text AS numero, numero_court, statut FROM mark.resto_commande WHERE appel_id = $1", str(partie.e.ctx.run_id))]


@pytest.fixture
def evenements(monkeypatch):
    """Le flux du portail (``commande.creee``) et les SMS de l'établissement, enregistrés : jamais un tiers appelé."""
    vus: dict[str, list] = {"flux": [], "sms": []}

    async def emettre(organisation, etablissement, type_, donnees, **_k):
        vus["flux"].append((type_, donnees))

    async def sms(organization_id, destinataire, modele, fiche, cle_unique):
        if cle_unique in {s["cle"] for s in vus["sms"]}:
            return Envoi.DEJA_FAIT
        vus["sms"].append({"a": destinataire, "fiche": fiche, "cle": cle_unique})
        return Envoi.PARTI

    monkeypatch.setattr(flux, "emettre", emettre)
    monkeypatch.setattr(sms_resto, "envoyer_un_sms", sms)
    return vus


@pytest.mark.parametrize("au_clavier", FINS)
async def test_fini_apres_l_accord_la_commande_part_une_fois(faire_monde, monkeypatch, au_clavier):
    partie = await _partie(faire_monde, monkeypatch, "E16")
    numero = str(partie.p["enregistree"]["numero"])
    assert _recues(partie) == []  # « Oui, c'est bon. » : rien en caisse pendant l'appel
    (ligne,) = await _lignes_de_l_appel(partie)
    assert (ligne["numero"], ligne["statut"], ligne["numero_court"]) == (numero, "retenue", partie.p["enregistree"]["numero_court"])

    await partie.e.finir_l_appel(au_clavier=au_clavier)  # … il raccroche
    assert [str(r["numero"]) for r in _recues(partie)] == [numero]
    assert (await _lignes_de_l_appel(partie))[0]["statut"] not in ("retenue", "annulee")


@pytest.mark.parametrize("au_clavier", FINS)
async def test_fini_avant_l_accord_rien_ne_part(faire_monde, monkeypatch, au_clavier):
    partie = await _partie(faire_monde, monkeypatch, "E15")  # accordée, pas encore enregistrée (le numéro qui s'affiche attend)
    await partie.e.finir_l_appel(au_clavier=au_clavier)
    assert _recues(partie) == [] and await _lignes_de_l_appel(partie) == []


@pytest.mark.parametrize("au_clavier", FINS)
async def test_changee_pendant_l_appel_un_seul_envoi_la_derniere_version(faire_monde, monkeypatch, au_clavier):
    partie = await _partie(faire_monde, monkeypatch, "E18")  # enregistrée, puis « une margherita de plus »
    assert _recues(partie) == []
    await partie.e.finir_l_appel(au_clavier=au_clavier)
    (recue,) = _recues(partie)
    base = await commande_complete(partie.e.monde.c, partie.e.monde.a, partie.p["enregistree"]["numero"])
    assert str(recue["numero"]) == str(partie.p["enregistree"]["numero"]) and recue["total"] == base["total"]
    assert C._lignes_de_la_base({"lignes": recue["lignes"]}) == C._lignes_de_la_base(base)
    assert sum(l["quantite"] for l in recue["lignes"]) == sum(C.lignes_de(partie.p).values())  # la dernière version : deux margheritas
    assert Counter(l["statut"] for l in await _lignes_de_l_appel(partie))["retenue"] == 0


async def test_un_montage_tombe_puis_la_vraie_fin_un_seul_envoi(faire_monde, monkeypatch):
    partie = await _partie(faire_monde, monkeypatch, "E16")
    await partie.e.finir_l_appel(fiche=None)  # la fin d'un montage tombé : fiche illisible, ignorée
    assert _recues(partie) == [] and (await _lignes_de_l_appel(partie))[0]["statut"] == "retenue"
    await partie.e.finir_l_appel()  # l'appel coupé après l'accord : la vraie fin (le ``finally``) l'envoie
    assert len(_recues(partie)) == 1


@pytest.mark.parametrize("au_clavier", FINS)
async def test_le_crochet_rejoue_n_envoie_pas_deux_fois(faire_monde, monkeypatch, au_clavier):
    partie = await _partie(faire_monde, monkeypatch, "E16")
    await partie.e.finir_l_appel(au_clavier=au_clavier)
    await partie.e.finir_l_appel(au_clavier=au_clavier)
    assert len(_recues(partie)) == 1


async def test_un_agent_sans_commande_la_fin_jouee_n_envoie_rien(faire_monde, monkeypatch):
    """Audit 8a, exigence 1 : la fin est jouée quel que soit l'interrupteur ; l'envoi se garde sur ce que l'appel a écrit, jamais sur ``run_configs``."""
    from api.services.base_client import rattachement

    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    demandes: list = []

    async def base_de(organisation):
        demandes.append(organisation)
        return partie.e.monde.base

    monkeypatch.setattr(rattachement, "nom_de_la_base", base_de)
    for run_configs in (None, {"commande_sur_catalogue": False}):
        await crochets.fin_de_l_appel(crochets.FinDeLAppel(partie.e.ctx.run_id, {"autre": 1}, ORGANISATION_D_ESSAI, run_configs))
    assert _recues(partie) == [] and demandes == []  # rien d'écrit par l'appel : la base n'est même pas ouverte


async def _allumer_le_sms(partie: C.Partie) -> None:
    await partie.e.monde.c.execute(
        "INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', $2, 'Merci {{prenom}} : {{numero_court}}', true)",
        partie.e.monde.a, envois.COMMANDE_ENREGISTREE)


async def test_oui_puis_fin_un_sms_et_une_commande_creee_a_la_fin_seulement(faire_monde, monkeypatch, evenements):
    monde = await faire_monde("casa-italia")
    partie = C.Partie(monde, monkeypatch)
    partie.e.ctx.organization_id = ORGANISATION_D_ESSAI  # un appel suivi d'une organisation : le portail l'apprend en direct
    await _allumer_le_sms(partie)
    assert await partie.recette("E16")
    assert evenements["sms"] == [] and [t for t, _ in evenements["flux"] if t == "commande.creee"] == []  # rien au « oui »
    await partie.e.finir_l_appel()
    await partie.e.finir_l_appel()
    court = partie.p["enregistree"]["numero_court"]
    assert [s["fiche"]["numero_court"] for s in evenements["sms"]] == [court]
    assert [d["numero_court"] for t, d in evenements["flux"] if t == "commande.creee"] == [court]


async def test_oui_puis_annulee_aucun_sms(faire_monde, monkeypatch, evenements):
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    await _allumer_le_sms(partie)
    assert await partie.recette("E17")  # « Oui. » … « Finalement j'annule. » (DC4 : « oui »)
    await partie.e.finir_l_appel()
    assert evenements["sms"] == [] and _recues(partie) == []
    assert [t for t, _ in evenements["flux"] if t == "commande.creee"] == []


async def test_au_clavier_le_tour_qui_finit_la_partie_donne_son_organisation_a_la_fin(faire_monde, monkeypatch):
    """Audit 8a, exigences 3 et 4 : la fin est jouée par ``execute_text_chat_pending_turn`` AVANT que le résultat du tour soit écrit ; elle lit la fiche du résultat
    et l'organisation que le tour a lue (``workflow.organization_id``), jamais ``None``."""
    from api.services.base_client import rattachement
    from api.services.restauration.caisse.prises import prise as prises

    partie = await _partie(faire_monde, monkeypatch, "E16")
    prise_d_essai, vraie_prise_de = partie.e.source.prise, prises.prise_de
    await partie.e.monde.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test') ON CONFLICT (site_id) DO NOTHING", partie.e.monde.a)
    monkeypatch.setattr(prises, "prise_de", lambda nom: prise_d_essai if nom == "test" else vraie_prise_de(nom))

    async def base_de(organisation):
        return partie.e.monde.base if organisation == ORGANISATION_D_ESSAI else None

    monkeypatch.setattr(rattachement, "nom_de_la_base", base_de)
    resultat = runner.TextChatTurnExecutionResult(
        assistant_text="Merci, à tout de suite.", assistant_created_at="", events=[], usage={}, checkpoint={}, gathered_context=partie.e.fiche_de_l_appel,
        initial_context={}, state="completed", is_completed=True, organization_id=ORGANISATION_D_ESSAI,
    )

    async def executer(**_k):
        return resultat

    monkeypatch.setattr(runner, "_executer_le_tour", executer)
    rendu = await runner.execute_text_chat_pending_turn(workflow_run_id=partie.e.ctx.run_id, workflow_id=1, session_data={}, checkpoint=None)
    assert rendu is resultat and len(_recues(partie)) == 1


def test_le_resultat_d_un_tour_porte_son_organisation():
    assert runner.TextChatTurnExecutionResult.__dataclass_fields__["organization_id"].default is None  # le faux tour des tests 8a (sans organisation) reste accepté
