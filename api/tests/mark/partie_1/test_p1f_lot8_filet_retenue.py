"""[.mark] Plan final Partie 1, lot 8b-1a (E11 ; § 17 « appel coupé après l'accord : elle part ») : le filet du rattrapage pour une commande « retenue » dont la fin
de l'appel n'a jamais été jouée (serveur redémarré pendant l'appel).

| Test | Ce qu'il prouve |
|---|---|
| appel terminé sans crochet | la ligne « retenue » part au passage suivant du rattrapage, une fois (rejoué : rien de plus) |
| appel encore en cours | elle ne part pas |
| délai réglé | le délai est un réglage du module (``filet_retenue_min``) : une ligne plus récente que lui attend, quel que soit l'état de l'appel |
"""

from __future__ import annotations

import pytest

from api.db.bases_clients.restauration_reglage import PAR_DEFAUT_DU_MODULE
from api.services.restauration.caisse import rattrapage
from api.services.restauration.caisse.prises.prise import poser_prise_de_test
from api.tests.mark.partie_1 import combinaisons as C


async def _retenue(faire_monde, monkeypatch) -> C.Partie:
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")  # « Oui, c'est bon. » … puis le serveur redémarre : la fin de l'appel n'est jamais jouée
    await partie.e.monde.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test') ON CONFLICT (site_id) DO NOTHING", partie.e.monde.a)
    return partie


async def _vieillir(partie: C.Partie, minutes: int) -> None:
    await partie.e.monde.c.execute("UPDATE mark.resto_commande SET maj_le = maj_le - make_interval(mins => $2) WHERE appel_id = $1", str(partie.e.ctx.run_id), minutes)


async def _rattraper(partie: C.Partie, *, termine: bool) -> None:
    vus: list[str] = []

    async def appel_termine(cle: str) -> bool:
        vus.append(cle)
        return termine

    poser_prise_de_test(partie.e.source.prise)
    try:
        await rattrapage.rattrapage_des_envois(bases=[(7, partie.e.monde.base)], appel_termine=appel_termine)
    finally:
        poser_prise_de_test(None)


async def _statut(partie: C.Partie) -> str:
    return await partie.e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE appel_id = $1", str(partie.e.ctx.run_id))


async def test_un_appel_termine_sans_crochet_sa_commande_part_au_passage_suivant(faire_monde, monkeypatch):
    partie = await _retenue(faire_monde, monkeypatch)
    await _vieillir(partie, 60)
    await _rattraper(partie, termine=True)
    assert [str(r["numero"]) for r in partie.e.source.prise.recues] == [str(partie.p["enregistree"]["numero"])]
    assert await _statut(partie) not in ("retenue", "annulee")
    await _rattraper(partie, termine=True)
    assert len(partie.e.source.prise.recues) == 1


async def test_un_appel_encore_en_cours_sa_commande_ne_part_pas(faire_monde, monkeypatch):
    partie = await _retenue(faire_monde, monkeypatch)
    await _vieillir(partie, 60)
    await _rattraper(partie, termine=False)
    assert partie.e.source.prise.recues == [] and await _statut(partie) == "retenue"


@pytest.mark.parametrize("reglage, age, part", [(None, 0, False), (30, 10, False), (30, 40, True)])
async def test_le_delai_du_filet_est_un_reglage_du_module(faire_monde, monkeypatch, reglage, age, part):
    assert isinstance(PAR_DEFAUT_DU_MODULE["filet_retenue_min"], int) and PAR_DEFAUT_DU_MODULE["filet_retenue_min"] > 0
    partie = await _retenue(faire_monde, monkeypatch)
    if reglage is not None:
        await partie.e.monde.c.execute("UPDATE mark.resto_reglage SET filet_retenue_min = $2 WHERE site_id = $1", partie.e.monde.a, reglage)
    await _vieillir(partie, age)
    await _rattraper(partie, termine=True)
    assert (len(partie.e.source.prise.recues) == 1) is part
