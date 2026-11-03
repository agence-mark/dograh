"""[.mark] Builder partie 2, U10 / S1 : plafond par mois, limite par adresse, durée maximale, contexte à l'initialisation.

| Test | Ce qu'il prouve |
|---|---|
| valeurs par défaut | 500 conversations, 1 500 minutes, 600 s (de 60 à 3 600), 10 sessions par heure et par adresse ; hors bornes = défaut |
| plafond en conversations | la conversation au-dessus du plafond est refusée proprement (403, code ``monthly_cap_reached``) |
| plafond en minutes | le premier plafond atteint arrête, même s'il reste des conversations |
| dernière place disputée | cinq réservations simultanées pour une place : une seule passe |
| passage de mois | un mois nouveau repart de zéro, sans tâche de nuit ; le même mois reste plein |
| limite par adresse | la 11e session de la même adresse sur le même jeton en une heure est refusée (429) ; une autre adresse ou un autre jeton passe |
| l'adresse n'est pas gardée | la clé du limiteur ne contient pas l'adresse |
| durée en trois temps | consigne à T - marge ; phrase de fin seulement après la phrase en cours ; coupure dure à T + grâce |
| jamais au milieu d'une phrase | un bot qui parle sans fin n'est jamais coupé avant T + grâce |
| contexte de /init | la page ne choisit pas son établissement ; le run porte le canal « site » et la durée maximale |
| l'ancien script | un jeton sans site ni réglages : ``/config/{token}`` et ``/init`` répondent comme avant |
"""

import asyncio
import time
from datetime import datetime, UTC
from types import SimpleNamespace


from api.services.site_mark import plafond
from api.services.site_mark.demarrage import lancer_la_duree_du_widget
from api.services.site_mark.duree_max import MinuteurDuree
from api.services.site_mark.limite_ip import _empreinte, autoriser_session
from api.services.site_mark.reglages import ReglagesMark
from api.tests.mark.equipe_commun import client_http
from api.tests.mark.site_commun import (
    creer_agent_avec_jeton,
    limiteur_en_memoire,
)

INIT = "/api/v1/public/embed/init"
ORIGINE = {"Origin": "https://client.fr"}


# ----------------------------------------------------------------------------- défauts
def test_valeurs_par_defaut_et_bornes():
    d = ReglagesMark.depuis(None)
    assert (d.plafond_conversations_mois, d.plafond_minutes_mois, d.duree_max_s, d.sessions_par_heure_et_ip) == (
        500,
        1500,
        600,
        10,
    )
    assert ReglagesMark.depuis({"duree_max_s": 30}).duree_max_s == 600  # sous 60 : défaut
    assert ReglagesMark.depuis({"duree_max_s": 3601}).duree_max_s == 600  # au-dessus de 3 600 : défaut
    assert ReglagesMark.depuis({"duree_max_s": 60}).duree_max_s == 60
    assert ReglagesMark.depuis({"duree_max_s": 3600}).duree_max_s == 3600
    assert ReglagesMark.depuis({"plafond_conversations_mois": "beaucoup"}).plafond_conversations_mois == 500
    assert ReglagesMark.depuis({"plafond_minutes_mois": True}).plafond_minutes_mois == 1500
    assert ReglagesMark.depuis("n'importe quoi").sessions_par_heure_et_ip == 10  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- plafond
async def _init(client, jeton, contexte=None, ip_entete=None):
    corps = {"token": jeton.token}
    if contexte is not None:
        corps["context_variables"] = contexte
    return await client.post(INIT, json=corps, headers=ORIGINE)


async def test_plafond_en_conversations_refus_propre(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(
        db_session, async_session, reglages_mark={"plafond_conversations_mois": 2}
    )
    with limiteur_en_memoire():
        async with client_http() as c:
            premiere = await _init(c, jeton)
            seconde = await _init(c, jeton)
            troisieme = await _init(c, jeton)
    assert premiere.status_code == 200, premiere.text
    assert seconde.status_code == 200
    assert troisieme.status_code == 403
    assert troisieme.json()["detail"]["code"] == "monthly_cap_reached"


async def test_plafond_en_minutes_le_premier_atteint_arrete(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(
        db_session, async_session, reglages_mark={"plafond_conversations_mois": 100, "plafond_minutes_mois": 10}
    )
    await plafond.verser_la_duree(jeton.id, 10 * 60)  # les 10 minutes sont parlées
    with limiteur_en_memoire():
        async with client_http() as c:
            reponse = await _init(c, jeton)
    assert reponse.status_code == 403
    assert reponse.json()["detail"]["code"] == "monthly_cap_reached"


async def test_derniere_place_disputee_une_seule_reservation_passe(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(db_session, async_session)
    reglages = ReglagesMark.depuis({"plafond_conversations_mois": 1})
    resultats = await asyncio.gather(*[plafond.reserver(jeton.id, reglages) for _ in range(5)])
    assert sorted(resultats) == [False, False, False, False, True]


async def test_passage_de_mois_repart_de_zero_sans_tache_de_nuit(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(db_session, async_session)
    reglages = ReglagesMark.depuis({"plafond_conversations_mois": 1})
    fin_janvier = datetime(2027, 1, 31, 23, 59, tzinfo=UTC)
    debut_fevrier = datetime(2027, 2, 1, 0, 1, tzinfo=UTC)
    assert await plafond.reserver(jeton.id, reglages, fin_janvier)
    assert not await plafond.reserver(jeton.id, reglages, fin_janvier)  # le même mois reste plein
    assert await plafond.reserver(jeton.id, reglages, debut_fevrier)  # le mois suivant repart de zéro
    assert not await plafond.reserver(jeton.id, reglages, debut_fevrier)


async def test_le_total_a_vie_reste_lisible_sur_le_jeton(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(db_session, async_session)
    with limiteur_en_memoire():
        async with client_http() as c:
            assert (await _init(c, jeton)).status_code == 200
    relu = await db_session.get_embed_token_by_id(jeton.id)
    assert relu.usage_count == 1


# ----------------------------------------------------------------------------- limite par adresse
async def test_la_onzieme_session_de_la_meme_adresse_est_refusee(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(db_session, async_session)
    _, _, _, autre_jeton = await creer_agent_avec_jeton(db_session, async_session)
    with limiteur_en_memoire() as limiteur:
        for _ in range(10):
            assert await autoriser_session(jeton.id, "203.0.113.7", 10)
        assert not await autoriser_session(jeton.id, "203.0.113.7", 10)  # la 11e
        assert await autoriser_session(jeton.id, "203.0.113.8", 10)  # une autre adresse
        assert await autoriser_session(autre_jeton.id, "203.0.113.7", 10)  # un autre jeton
        assert {w for _, _, w in limiteur.appels} == {3600.0}  # fenêtre d'une heure


async def test_init_repond_429_quand_la_limite_par_adresse_est_atteinte(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(
        db_session, async_session, reglages_mark={"sessions_par_heure_et_ip": 2}
    )
    with limiteur_en_memoire():
        async with client_http() as c:
            codes = [(await _init(c, jeton)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_l_adresse_n_est_pas_dans_la_cle_du_limiteur():
    with limiteur_en_memoire() as limiteur:
        await autoriser_session(7, "198.51.100.23", 10)
    cle = limiteur.appels[0][0]
    assert "198.51.100.23" not in cle and _empreinte(7, "198.51.100.23") in cle


async def test_le_limiteur_de_l_amont_accepte_une_fenetre_d_une_heure():
    from unittest.mock import AsyncMock

    from api.services.call_concurrency.rate_limiter import RateLimiter

    limiteur = RateLimiter()
    redis = AsyncMock()
    redis.eval.return_value = 1
    limiteur._get_redis = AsyncMock(return_value=redis)
    avant = time.time()
    assert await limiteur.acquire_token(1, 10, scope_key="x", window_seconds=3600.0)
    args = redis.eval.await_args.args
    assert args[2] == "rate_limit:x"
    assert avant - 3600.5 <= float(args[4]) <= time.time() - 3599.5  # début de fenêtre = il y a une heure
    assert args[7] == 3601  # la clé expire avec la fenêtre
    # Défaut inchangé : une seconde.
    await limiteur.acquire_token(1, 1)
    assert redis.eval.await_args.args[7] == 2


# ----------------------------------------------------------------------------- durée en trois temps
class Faux:
    def __init__(self):
        self.t0 = time.monotonic()
        self.bot_parle = False
        self.fini = False
        self.journal: list[tuple[str, float]] = []

    def vu(self, nom):
        self.journal.append((nom, time.monotonic() - self.t0))

    async def consigne(self):
        self.vu("consigne")

    async def phrase(self):
        self.vu("phrase_de_fin")
        self.fini = True

    async def couper(self):
        self.vu("coupure")
        self.fini = True

    def minuteur(self, duree=0.6, marge=0.3, grace=0.4):
        return MinuteurDuree(
            duree,
            consigne=self.consigne,
            phrase_de_fin=self.phrase,
            couper=self.couper,
            bot_parle=lambda: self.bot_parle,
            termine=lambda: self.fini,
            marge_consigne_s=marge,
            grace_coupure_s=grace,
            pas_s=0.02,
        )


async def test_duree_trois_temps_consigne_phrase_de_fin_apres_la_phrase_en_cours():
    f = Faux()
    f.bot_parle = True

    async def fin_de_phrase():
        await asyncio.sleep(0.75)  # le bot parle encore à T = 0,6 s
        f.bot_parle = False

    asyncio.create_task(fin_de_phrase())
    m = f.minuteur()
    await m.derouler()
    noms = [n for n, _ in f.journal]
    assert noms == ["consigne", "phrase_de_fin"]  # pas de coupure : la fin a mis fin à l'appel
    t = dict(f.journal)
    assert 0.25 <= t["consigne"] < 0.5  # T - 0,3 s
    assert t["phrase_de_fin"] >= 0.74  # après la phrase en cours, pas à T


async def test_duree_la_coupure_dure_tombe_a_t_plus_la_grace_si_l_appel_court_encore():
    f = Faux()

    async def phrase_qui_ne_termine_rien():
        f.vu("phrase_de_fin")  # dite, mais l'appel ne se termine pas

    f.phrase = phrase_qui_ne_termine_rien  # type: ignore[assignment]
    m = f.minuteur()
    await m.derouler()
    assert [n for n, _ in f.journal] == ["consigne", "phrase_de_fin", "coupure"]
    assert dict(f.journal)["coupure"] >= 0.95  # T + grâce = 1,0 s


async def test_duree_un_bot_qui_parle_sans_fin_n_est_jamais_coupe_avant_t_plus_la_grace():
    f = Faux()
    f.bot_parle = True
    m = f.minuteur()
    await m.derouler()
    assert [n for n, _ in f.journal] == ["consigne", "coupure"]  # jamais de phrase de fin sur une phrase en cours
    assert dict(f.journal)["coupure"] >= 0.95


async def test_duree_un_appel_deja_termine_ne_declenche_rien():
    f = Faux()
    f.fini = True
    await f.minuteur().derouler()
    assert f.journal == []


# ----------------------------------------------------------------------------- branchement du pipeline
async def test_le_pipeline_ne_branche_le_minuteur_que_sur_un_run_de_widget_vocal():
    moteur = SimpleNamespace(call_monitor=SimpleNamespace(user_aggregator=None), is_call_disposed=lambda: True)
    assert lancer_la_duree_du_widget(moteur, SimpleNamespace(annotations=None)) is None
    assert lancer_la_duree_du_widget(moteur, SimpleNamespace(annotations={"embed": {"source": "autre"}})) is None
    assert (
        lancer_la_duree_du_widget(
            moteur, SimpleNamespace(annotations={"embed": {"source": "embed_widget", "modality": "text"}})
        )
        is None
    )
    tache = lancer_la_duree_du_widget(
        moteur,
        SimpleNamespace(annotations={"embed": {"source": "embed_widget", "embed_token_id": 1, "duree_max_s": 600}}),
    )
    assert tache is not None
    await asyncio.wait_for(tache, timeout=5)  # l'appel est déjà fini : la tâche s'arrête seule


# ----------------------------------------------------------------------------- /init
async def test_init_ecarte_le_contexte_mark_et_pose_le_canal_et_la_duree(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(db_session, async_session, reglages_mark={"duree_max_s": 900})
    with limiteur_en_memoire():
        async with client_http() as c:
            reponse = await _init(
                c,
                jeton,
                {"page_url": "https://client.fr/x", "etablissement_id": "creil", "called_number": "+33344000001"},
            )
    assert reponse.status_code == 200, reponse.text
    run = await db_session.get_workflow_run(reponse.json()["workflow_run_id"], organization_id=jeton.organization_id)
    assert run.initial_context["page_url"] == "https://client.fr/x"
    assert run.initial_context["canal_mark"] == "site"
    assert "etablissement_id" not in run.initial_context and "called_number" not in run.initial_context
    assert run.annotations["embed"]["duree_max_s"] == 900
    assert run.annotations["embed"]["embed_token_id"] == jeton.id


async def test_l_ancien_script_par_jeton_marche_toujours(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(db_session, async_session, settings={"buttonText": "Appeler"})
    async with client_http() as c:
        config = await c.get(f"/api/v1/public/embed/config/{jeton.token}", headers=ORIGINE)
    assert config.status_code == 200
    assert config.json()["button_text"] == "Appeler"
    with limiteur_en_memoire():
        async with client_http() as c:
            init = await _init(c, jeton)
    assert init.status_code == 200
    assert init.json()["widget_type"] == "voice"
