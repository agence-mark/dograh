"""[.mark] Revue serveur, passage 1, corrections R2 (site public) : M2, M7, mineurs 2 et 3.

| Test | Ce qu'il prouve |
|---|---|
| M2 : relais de confiance | derrière un relais déclaré, l'adresse est celle du visiteur (``X-Forwarded-For``) |
| M2 : relais inconnu | un en-tête forgé par une connexion qui n'est pas un relais est ignoré |
| M2 : chaîne forgée | ce que le visiteur écrit à gauche de la chaîne ne compte jamais (on lit de droite à gauche) |
| M2 : sans réglage | aucune confiance par défaut ; réglage lu dans ``MARK_RELAIS_DE_CONFIANCE`` (jamais ``FORWARDED_ALLOW_IPS``) |
| M2 : branché sur la route | deux visiteurs derrière un relais déclaré n'ont pas la même limite ; sans relais déclaré, ils la partagent |
| M7 : évènement limité | au-delà de 60 par minute, jeton et adresse : refus silencieux, le compteur ne bouge plus |
| mineur 2 : plafond rendu | l'échec de la création du run rend la place réservée sur le plafond du mois |
| mineur 3 : un seul avis | la place de l'avis se prend une seule fois ; l'avis rendu peut être redonné |
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from api.db.site_client import mois_de
from api.services.site_mark.adresse import adresse_du_visiteur
from api.tests.mark.equipe_commun import client_http
from api.tests.mark.site_commun import creer_agent_avec_jeton, limiteur_en_memoire

API = "/api/v1"
INIT = f"{API}/public/embed/init"
CLIENT = {"Origin": "https://client.fr"}


def _requete(pair, xff=None):
    entetes = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=pair) if pair else None, headers=entetes)


# ----------------------------------------------------------------------------- M2
def test_m2_un_relais_de_confiance_donne_l_adresse_du_visiteur():
    assert adresse_du_visiteur(_requete("10.0.0.5", "203.0.113.9"), relais=1) == "203.0.113.9"
    assert adresse_du_visiteur(_requete("10.0.0.5", "2001:db8::7"), relais="1") == "2001:db8::7"
    # Deux relais de confiance : le maillon de rang 2 en partant de la droite.
    assert adresse_du_visiteur(_requete("10.0.0.5", "203.0.113.9, 10.0.0.4"), relais=2) == "203.0.113.9"


def test_m2_sans_relais_declare_l_entete_forge_est_ignore():
    r = _requete("198.51.100.1", "203.0.113.200")
    assert adresse_du_visiteur(r, relais=0) == "198.51.100.1"
    assert adresse_du_visiteur(r, relais="") == "198.51.100.1"
    assert adresse_du_visiteur(r, relais="*") == "198.51.100.1"  # « * » n'est pas un nombre : aucune confiance


def test_m2_chaine_forgee_seule_la_droite_compte():
    # Le visiteur a écrit « 1.2.3.4 » ; le relais a ajouté la vraie adresse à droite : « forgé, réel » donne « réel ».
    assert adresse_du_visiteur(_requete("10.0.0.5", "1.2.3.4, 203.0.113.9"), relais=1) == "203.0.113.9"
    assert adresse_du_visiteur(_requete("10.0.0.5", "pas une adresse"), relais=1) == "10.0.0.5"
    assert adresse_du_visiteur(_requete("10.0.0.5"), relais=1) == "10.0.0.5"
    assert adresse_du_visiteur(_requete("10.0.0.5", "203.0.113.9"), relais=2) == "10.0.0.5"  # moins de maillons que de relais
    assert adresse_du_visiteur(_requete(None), relais=1) is None


def test_m2_sans_reglage_aucune_confiance_et_le_reglage_vient_de_l_environnement(monkeypatch):
    monkeypatch.delenv("MARK_RELAIS_DE_CONFIANCE", raising=False)
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")  # la variable d'uvicorn ne donne aucune confiance ici
    r = _requete("10.0.0.5", "1.2.3.4, 203.0.113.9")
    assert adresse_du_visiteur(r) == "10.0.0.5"
    monkeypatch.setenv("MARK_RELAIS_DE_CONFIANCE", "1")
    assert adresse_du_visiteur(r) == "203.0.113.9"
    monkeypatch.setenv("MARK_RELAIS_DE_CONFIANCE", "n'importe quoi")
    assert adresse_du_visiteur(r) == "10.0.0.5"  # une valeur illisible ne donne jamais confiance


async def _deux_visiteurs(db_session, async_session, entetes=("203.0.113.1", "203.0.113.2")):
    _, _, _, jeton = await creer_agent_avec_jeton(
        db_session, async_session, allowed_domains=["client.fr"], reglages_mark={"sessions_par_heure_et_ip": 1}
    )
    codes = []
    with limiteur_en_memoire():
        async with client_http() as c:
            for visiteur in entetes:
                r = await c.post(INIT, json={"token": jeton.token}, headers={**CLIENT, "X-Forwarded-For": visiteur})
                codes.append(r.status_code)
    return codes


async def test_m2_branche_sur_la_route_init(db_session, async_session, monkeypatch):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    monkeypatch.setenv("MARK_RELAIS_DE_CONFIANCE", "1")
    assert await _deux_visiteurs(db_session, async_session) == [200, 200]
    monkeypatch.delenv("MARK_RELAIS_DE_CONFIANCE")
    # Même avec FORWARDED_ALLOW_IPS="*", sans relais déclaré : même limite, l'en-tête forgé ne sert à rien.
    assert await _deux_visiteurs(db_session, async_session) == [200, 429]
    # « forgé, réel » avec 1 relais : le même visiteur réel ne contourne pas la limite en changeant le maillon forgé.
    monkeypatch.setenv("MARK_RELAIS_DE_CONFIANCE", "1")
    forges = ("9.9.9.1, 203.0.113.50", "9.9.9.2, 203.0.113.50")
    assert await _deux_visiteurs(db_session, async_session, forges) == [200, 429]


# ----------------------------------------------------------------------------- M7
async def test_m7_les_evenements_sont_limites_par_jeton_et_adresse_en_silence(db_session, async_session):
    org, _, _, jeton = await creer_agent_avec_jeton(db_session, async_session, allowed_domains=["client.fr"])
    url = f"{API}/public/embed/evenement"
    with limiteur_en_memoire():
        async with client_http() as c:
            codes = [(await c.post(url, json={"token": jeton.token, "evenement": "affiche"}, headers=CLIENT)).status_code for _ in range(65)]
    assert set(codes) == {200}  # refus silencieux : jamais d'erreur pour le widget
    jour = datetime.now(UTC).date()
    lignes = await db_session.lire_evenements(org, jour - timedelta(days=1), jour + timedelta(days=1))
    assert sum(ligne["affiche"] for ligne in lignes) == 60


# ----------------------------------------------------------------------------- mineur 2
async def test_mineur_2_l_echec_du_run_rend_la_place_du_plafond(db_session, async_session):
    _, _, _, jeton = await creer_agent_avec_jeton(
        db_session, async_session, allowed_domains=["client.fr"], reglages_mark={"plafond_conversations_mois": 5}
    )
    with limiteur_en_memoire(), patch.object(db_session, "create_workflow_run", side_effect=RuntimeError("panne")):
        async with client_http() as c:
            r = await c.post(INIT, json={"token": jeton.token}, headers=CLIENT)
    assert r.status_code == 500
    usage = await db_session.lire_usage_mensuel(jeton.id, mois_de(None))
    assert usage is None or usage.conversations == 0


# ----------------------------------------------------------------------------- mineur 3
async def test_mineur_3_la_place_de_l_avis_se_prend_une_seule_fois(db_session, async_session):
    org, user, wf, _ = await creer_agent_avec_jeton(db_session, async_session)
    run = await db_session.create_workflow_run(
        name="r", workflow_id=wf.id, mode="chat", user_id=user.id, organization_id=org
    )
    # (La session de test est partagée : le verrou de ligne n'est pas rejouable en parallèle ici ; la place prise vaut refus.)
    resultats = [await db_session.reserver_avis(run.id, org) for _ in range(3)]
    assert resultats == [True, False, False]
    assert await db_session.reserver_avis(run.id, org + 999) is False  # une autre organisation ne prend rien
    await db_session.rendre_avis(run.id, org)
    assert await db_session.reserver_avis(run.id, org) is True
