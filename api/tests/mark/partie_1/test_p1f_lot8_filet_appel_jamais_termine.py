"""[.mark] Plan final Partie 1, lot 8b-1b (Pierre 27/11 ~4 h, registre T24 (1) ; audit 8b-1a, « à porter dans 8b-1b ») : le filet du rattrapage et l'appel qui plante sans
jamais être noté terminé. La commande « retenue » après le « oui » part quand même, une fois, dès que l'appel ne peut plus être en cours ; une ligne qui ne peut vraiment pas
partir alerte le restaurant une fois, puis le filet la laisse ; l'état des appels se lit en UNE requête par page, jamais une question par ligne.

| Test | Ce qu'il prouve |
|---|---|
| appel jamais noté terminé, plus en cours | la ligne part une fois (rejoué : rien de plus) |
| appel jamais noté terminé, peut-être encore en cours | elle attend (rien ne part pendant un appel vivant, § 17) |
| une lecture par page | trois lignes de trois appels : l'état des appels est lu une fois, jamais appel par appel |
| ne peut pas partir | appel introuvable, au-delà de la limite : une alerte au restaurant, une seule, puis le filet la laisse |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.db import db_client
from api.services.restauration.caisse import rattrapage
from api.services.restauration.caisse.prises.prise import poser_prise_de_test
from api.tests.mark.partie_1 import combinaisons as C

VOIX = "twilio"


class BasePrincipale:
    """Les appels tels que la base principale les connaît (``workflow_runs``), et chaque lecture faite."""

    def __init__(self, monkeypatch, appels: dict[int, tuple[bool, str]]):
        self.appels, self.par_ligne, self.groupees = appels, 0, 0

        async def un(run_id):
            self.par_ligne += 1
            etat = self.appels.get(int(run_id))
            return SimpleNamespace(id=int(run_id), is_completed=etat[0], mode=etat[1]) if etat else None

        async def plusieurs(run_ids):
            self.groupees += 1
            return [(i, *self.appels[i]) for i in run_ids if i in self.appels]

        monkeypatch.setattr(db_client, "get_workflow_run_by_id", un)
        monkeypatch.setattr(db_client, "get_workflow_runs_completion", plusieurs, raising=False)


async def _retenue(faire_monde, monkeypatch) -> C.Partie:
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")  # « Oui, c'est bon. » … puis la ligne coupe et le serveur tombe : ni fin jouée, ni appel noté terminé
    await partie.e.monde.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test') ON CONFLICT (site_id) DO NOTHING", partie.e.monde.a)
    return partie


async def _vieillir(partie: C.Partie, minutes: int) -> None:
    await partie.e.monde.c.execute("UPDATE mark.resto_commande SET maj_le = maj_le - make_interval(mins => $2) WHERE appel_id = $1", str(partie.e.ctx.run_id), minutes)


async def _rattraper(partie: C.Partie, alertes: list | None = None) -> None:
    async def secours(_organisation, sujet, texte):
        (alertes if alertes is not None else []).append((sujet, texte))

    poser_prise_de_test(partie.e.source.prise)
    try:
        await rattrapage.rattrapage_des_envois(bases=[(7, partie.e.monde.base)], secours=secours)
    finally:
        poser_prise_de_test(None)


async def _statut(partie: C.Partie) -> str:
    return await partie.e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE appel_id = $1", str(partie.e.ctx.run_id))


async def test_un_appel_jamais_note_termine_et_qui_ne_peut_plus_etre_en_cours_sa_commande_part_une_fois(faire_monde, monkeypatch):
    """Client « Oui, c'est bon. » puis la ligne coupe et le serveur tombe / avant : la commande reste en attente pour toujours / après : elle part en cuisine par le filet, une fois."""
    partie = await _retenue(faire_monde, monkeypatch)
    BasePrincipale(monkeypatch, {int(partie.e.ctx.run_id): (False, VOIX)})
    await _vieillir(partie, 60)
    await _rattraper(partie)
    assert [str(r["numero"]) for r in partie.e.source.prise.recues] == [str(partie.p["enregistree"]["numero"])]
    assert await _statut(partie) not in ("retenue", "annulee")
    await _rattraper(partie)
    assert len(partie.e.source.prise.recues) == 1


async def test_un_appel_jamais_note_termine_qui_peut_encore_etre_en_cours_sa_commande_attend(faire_monde, monkeypatch):
    """Le dernier « oui » date de dix minutes, l'appel à la voix peut encore durer : rien ne part pendant un appel vivant (§ 17 : à la fin de l'appel)."""
    partie = await _retenue(faire_monde, monkeypatch)
    BasePrincipale(monkeypatch, {int(partie.e.ctx.run_id): (False, VOIX)})
    await _vieillir(partie, 10)
    await _rattraper(partie)
    assert partie.e.source.prise.recues == [] and await _statut(partie) == "retenue"


async def test_l_etat_des_appels_se_lit_en_une_requete_par_page(faire_monde, monkeypatch):
    """Audit 8b-1a (2e passage) : trois lignes « retenue » de trois appels terminés : une seule lecture groupée de la base principale, aucune question appel par appel."""
    partie = await _retenue(faire_monde, monkeypatch)
    c, a, run = partie.e.monde.c, partie.e.monde.a, int(partie.e.ctx.run_id)
    await _vieillir(partie, 60)
    await c.execute(
        "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total, statut, appel_id, maj_le) "
        "SELECT gen_random_uuid(), 'B' || g, $1, 'emporter', 0, 'retenue', ($2 + g)::text, (SELECT maj_le FROM mark.resto_commande WHERE appel_id = $3) "
        "FROM generate_series(1, 2) g", a, run, str(run),
    )
    base = BasePrincipale(monkeypatch, {run: (True, VOIX), run + 1: (False, "textchat"), run + 2: (False, "textchat")})
    await _rattraper(partie)
    assert base.groupees == 1 and base.par_ligne == 0, (base.groupees, base.par_ligne)
    assert [str(r["numero"]) for r in partie.e.source.prise.recues] == [str(partie.p["enregistree"]["numero"])]


async def test_une_ligne_qui_ne_peut_pas_partir_alerte_le_restaurant_une_fois_puis_le_filet_la_laisse(faire_monde, monkeypatch):
    """L'appel est introuvable dans la base principale, la ligne attend depuis bien plus longtemps que tout appel : le restaurant reçoit UNE alerte (la commande jointe, pour la
    saisir à la main) ; au passage suivant, ni seconde alerte ni envoi ; la ligne n'est jamais annulée ni envoyée à l'aveugle."""
    partie = await _retenue(faire_monde, monkeypatch)
    base = BasePrincipale(monkeypatch, {})
    await _vieillir(partie, 24 * 60)
    alertes: list = []
    await _rattraper(partie, alertes)
    assert len(alertes) == 1 and partie.e.source.prise.recues == [] and await _statut(partie) == "retenue", alertes
    lectures = base.groupees
    await _rattraper(partie, alertes)
    assert len(alertes) == 1 and partie.e.source.prise.recues == [] and base.groupees == lectures, (alertes, base.groupees)
