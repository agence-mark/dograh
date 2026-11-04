"""[.mark] Builder partie 2, V5 : ce que l'éditeur du widget (maquette) lit et écrit sur de vraies données.

| Test | Ce qu'il prouve |
|---|---|
| couleurs | chaque couleur de la maquette a sa donnée ; une retouche ne touche aucune autre ; le texte par défaut est lisible sur son fond ; raccrocher est rouge |
| textes | les six textes de V5 existent, ont leur défaut français, sont bornés |
| déclenchement | les quatre choix de la maquette (+ l'ancien « clic ») sont acceptés, les autres refusés |
| modes | « voix et écrit » par défaut (comportement d'avant), « voix seule » enregistrée, lue par le widget, valeur inconnue refusée |
| affichage | coupé : la page ne reçoit plus le widget ; remis : il revient ; autre organisation : 404 |
| expiration du jeton | date écrite, passée refusée, vide = jamais, jeton expiré = widget absent |
| régénérer la clé | l'ancienne clé est refusée, la nouvelle sert ; autre organisation : 404 |
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from api.schemas.apparence_widget import ApparenceWidget, TEXTES_DEFAUT, sur_couleur
from api.services.site_mark import config_site
from api.services.site_mark.reglages import ReglagesMark
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.mark.site_commun import creer_agent

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

API = "/api/v1"
ORIGINE = {"Origin": "https://client.fr"}
NOUVEAUX_TEXTES = ("titre", "avis_titre", "avis_passer", "case_rappel", "case_publication", "ecrire")


# ----------------------------------------------------------------------------- couleurs et textes
def test_toutes_les_couleurs_de_la_maquette_ont_leur_donnee():
    resolues = ApparenceWidget().couleurs_resolues()
    assert len(resolues) == 18
    assert resolues["raccrocher"] == "#dc2626" and resolues["raccrocher_texte"] == "#ffffff"
    assert resolues["bulle_agent"] == "#f1f1f1" and resolues["bulle_agent_texte"] == "#0f1c2e"
    assert resolues["boutons_texte"] == "#ffffff"  # blanc sur le bleu .mark
    assert resolues["champ_saisie_texte"] == "#0f1c2e"


def test_le_texte_par_defaut_est_le_plus_lisible_sur_son_fond():
    assert sur_couleur("#ffffff") == "#111111"
    assert sur_couleur("#1b5fb0") == "#ffffff"
    jaune = ApparenceWidget(couleur_base="#ffe600").couleurs_resolues()
    assert jaune["boutons_texte"] == "#111111" and jaune["rond_accroche_texte"] == "#111111"


def test_retoucher_le_texte_d_un_bouton_ne_touche_ni_son_fond_ni_les_autres():
    base = ApparenceWidget().couleurs_resolues()
    retouche = ApparenceWidget(couleurs={"boutons_texte": "#00ff00"}).couleurs_resolues()
    assert retouche["boutons_texte"] == "#00ff00"
    assert {k: v for k, v in retouche.items() if k != "boutons_texte"} == {k: v for k, v in base.items() if k != "boutons_texte"}
    # Une retouche de fond ne déplace pas le texte retouché, et les textes non retouchés suivent leur fond.
    autre = ApparenceWidget(couleurs={"boutons": "#ffe600", "boutons_texte": "#00ff00"}).couleurs_resolues()
    assert autre["boutons_texte"] == "#00ff00"
    assert ApparenceWidget(couleurs={"boutons": "#ffe600"}).couleurs_resolues()["boutons_texte"] == "#111111"


def test_les_six_textes_de_v5_ont_leur_defaut_et_leurs_bornes():
    textes = ApparenceWidget().textes.model_dump()
    for cle in NOUVEAUX_TEXTES:
        assert textes[cle] == TEXTES_DEFAUT[cle] and textes[cle]
    assert ApparenceWidget(textes={"titre": "Showroom de Beauvais"}).textes.titre == "Showroom de Beauvais"
    for cle in NOUVEAUX_TEXTES:
        with pytest.raises(ValidationError):
            ApparenceWidget(textes={cle: ""})
        with pytest.raises(ValidationError):
            ApparenceWidget(textes={cle: "x" * 201})


@pytest.mark.parametrize("valeur", ["clic", "survol", "delai", "toujours", "jamais"])
def test_les_choix_de_declenchement_de_la_maquette_sont_acceptes(valeur):
    assert ApparenceWidget(declenchement=valeur).declenchement == valeur


def test_un_declenchement_inconnu_est_refuse():
    with pytest.raises(ValidationError):
        ApparenceWidget(declenchement="toujours-et-partout")


# ----------------------------------------------------------------------------- modes
def test_les_modes_valent_voix_et_ecrit_par_defaut_et_une_valeur_inconnue_aussi():
    assert ReglagesMark.depuis(None).modes == "voix_et_ecrit"
    assert ReglagesMark.depuis({"modes": "voix"}).modes == "voix"
    assert ReglagesMark.depuis({"modes": "telepathie"}).modes == "voix_et_ecrit"
    assert ReglagesMark.depuis({"modes": "voix"}).en_json()["modes"] == "voix"


# ----------------------------------------------------------------------------- routes
async def _acces(db_session, nom, organisations):
    role = await db_session.creer_role(
        nom=f"Portail-{nom}", labo_ouvert=True, tous_les_clients=False, permissions=["agents.modifier"], organisations=list(organisations)
    )
    user, jeton = await creer_compte(db_session, f"{nom}@example.com", organisations=organisations)
    await db_session.poser_membre(user.id, role)
    return jeton


async def _agent_de_site(c, h, db_session, async_session, org, domaines=("client.fr",)):
    """Un site, un agent de site posé sur « / » : rend (site, agent, emplacement)."""
    site = (await c.post(f"{API}/organizations/sites", headers=h, json={"nom": "Client", "allowed_domains": list(domaines)})).json()
    _, _, agent = await creer_agent(db_session, async_session, organisation_id=org)
    assert (await c.put(f"{API}/organizations/agents-site/{agent.id}/canal", headers=h, json={"canal": "site"})).status_code == 200
    place = await c.put(f"{API}/organizations/agents-site/{agent.id}/emplacement", headers=h, json={"site_id": site["id"], "chemins": ["/"]})
    assert place.status_code == 200, place.text
    return site, agent, place.json()


async def _config(c, cle):
    return await c.get(f"{API}/public/embed/site/{cle}/config", params={"chemin": "/"}, headers=ORIGINE)


async def test_l_emplacement_dit_le_nom_de_l_agent(db_session, async_session):
    config_site.vider_le_cache()
    org = await creer_organisation(db_session, "v5-nom")
    h = entetes(await _acces(db_session, "v5nom", [org]), org)
    async with client_http() as c:
        _, agent, emplacement = await _agent_de_site(c, h, db_session, async_session, org)
    assert emplacement["agent_nom"] == agent.name and emplacement["widget_actif"] is True


async def test_les_modes_s_enregistrent_et_le_widget_les_lit(db_session, async_session):
    config_site.vider_le_cache()
    org = await creer_organisation(db_session, "v5-modes")
    h = entetes(await _acces(db_session, "v5modes", [org]), org)
    async with client_http() as c:
        site, agent, _ = await _agent_de_site(c, h, db_session, async_session, org)
        base = f"{API}/organizations/agents-site/{agent.id}/reglages"
        assert (await c.get(base, headers=h)).json()["modes"] == "voix_et_ecrit"
        assert (await _config(c, site["cle"])).json()["modes"] == "voix_et_ecrit"
        assert (await c.put(base, headers=h, json={"modes": "voix"})).json()["modes"] == "voix"
        config_site.vider_le_cache(site["cle"])
        assert (await _config(c, site["cle"])).json()["modes"] == "voix"
        assert (await c.put(base, headers=h, json={"modes": "telepathie"})).status_code == 422
        # Un autre réglage n'efface pas le mode.
        autre = await c.put(base, headers=h, json={"duree_max_s": 900})
    assert autre.json()["modes"] == "voix"


async def test_couper_l_affichage_retire_le_widget_de_la_page_et_le_remettre_le_rend(db_session, async_session):
    config_site.vider_le_cache()
    org = await creer_organisation(db_session, "v5-affichage")
    h = entetes(await _acces(db_session, "v5aff", [org]), org)
    async with client_http() as c:
        site, agent, _ = await _agent_de_site(c, h, db_session, async_session, org)
        route = f"{API}/organizations/agents-site/{agent.id}/affichage"
        assert (await _config(c, site["cle"])).json()["actif"] is True
        coupe = await c.put(route, headers=h, json={"actif": False})
        assert coupe.status_code == 200 and coupe.json()["widget_actif"] is False
        assert (await _config(c, site["cle"])).json() == {"actif": False}  # le cache est vidé : effet au prochain chargement
        remis = await c.put(route, headers=h, json={"actif": True})
        assert remis.json()["widget_actif"] is True
        assert (await _config(c, site["cle"])).json()["actif"] is True


async def test_l_expiration_du_jeton_s_ecrit_se_vide_et_un_jeton_expire_n_affiche_rien(db_session, async_session):
    config_site.vider_le_cache()
    org = await creer_organisation(db_session, "v5-expire")
    h = entetes(await _acces(db_session, "v5exp", [org]), org)
    async with client_http() as c:
        site, agent, emplacement = await _agent_de_site(c, h, db_session, async_session, org)
        base = f"{API}/organizations/agents-site/{agent.id}/reglages"
        assert (await c.get(base, headers=h)).json()["jeton_expire_le"] is None
        demain = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
        assert (await c.put(base, headers=h, json={"jeton_expire_le": demain})).json()["jeton_expire_le"] == demain
        hier = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        assert (await c.put(base, headers=h, json={"jeton_expire_le": hier})).status_code == 422
        assert (await c.put(base, headers=h, json={"jeton_expire_le": "bientôt"})).status_code == 422
        assert (await c.put(base, headers=h, json={"jeton_expire_le": ""})).json()["jeton_expire_le"] is None
        # Un jeton arrivé à échéance n'affiche plus rien.
        await db_session.update_embed_token(emplacement["embed_token_id"], org, expires_at=datetime.now(UTC) - timedelta(hours=1))
        config_site.vider_le_cache(site["cle"])
        assert (await _config(c, site["cle"])).json() == {"actif": False}


async def test_regenerer_la_cle_refuse_l_ancienne_et_sert_la_nouvelle(db_session, async_session):
    config_site.vider_le_cache()
    org = await creer_organisation(db_session, "v5-cle")
    h = entetes(await _acces(db_session, "v5cle", [org]), org)
    async with client_http() as c:
        site, _, _ = await _agent_de_site(c, h, db_session, async_session, org)
        assert (await _config(c, site["cle"])).status_code == 200
        neuf = await c.post(f"{API}/organizations/sites/{site['id']}/regenerer-cle", headers=h)
        assert neuf.status_code == 200
        assert neuf.json()["cle"] != site["cle"] and neuf.json()["cle"] in neuf.json()["script"]
        assert (await _config(c, site["cle"])).status_code == 404
        assert (await _config(c, neuf.json()["cle"])).json()["actif"] is True


async def test_les_nouvelles_routes_refusent_une_autre_organisation(db_session, async_session):
    org_a = await creer_organisation(db_session, "v5-a")
    org_b = await creer_organisation(db_session, "v5-b")
    h_a = entetes(await _acces(db_session, "v5a", [org_a]), org_a)
    h_b = entetes(await _acces(db_session, "v5b", [org_b]), org_b)
    async with client_http() as c:
        site, agent, _ = await _agent_de_site(c, h_a, db_session, async_session, org_a)
        affichage = await c.put(f"{API}/organizations/agents-site/{agent.id}/affichage", headers=h_b, json={"actif": False})
        cle = await c.post(f"{API}/organizations/sites/{site['id']}/regenerer-cle", headers=h_b)
        reglage = await c.put(f"{API}/organizations/agents-site/{agent.id}/reglages", headers=h_b, json={"modes": "voix"})
        encore = await _config(c, site["cle"])  # rien n'a bougé chez A
    assert affichage.status_code == 404 and cle.status_code == 404 and reglage.status_code == 404
    assert encore.json()["actif"] is True
