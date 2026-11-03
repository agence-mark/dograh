"""[.mark] builder partie 2, B2, U3 : l'onglet Tests de l'agent (E47) côté serveur.

Ce qui doit tenir : un test se MODIFIE en entier (même validation, même slug, résultats remis à zéro) par la route et par
l'action ; ``texte_en_tete`` remplace ``merci_en_tete`` sans perte et sans mot du métier dans le code ; la liste de l'onglet
rend sorte, description et dernier résultat ; « depuis la bibliothèque » copie un scénario type en test de l'agent.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder_tests as route
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder.tests_agent import stockage, verdict
from api.services.builder.tests_agent.verdict import ObservationConversation
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur
from api.tests.mark.test_builder_tests_agent import banc  # noqa: F401 -- la fixture du lot

CRITERE = {"type": "texte_absent", "texte": "outil_interne"}
EQUIPE = utilisateur(1, ORG_CLIENT)
AUTRE = utilisateur(2, 8)


def client_pour(user) -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _base(banc, monkeypatch):  # noqa: F811
    monkeypatch.setattr(route, "db_client", banc)


def conv(*lignes):
    return ObservationConversation(texte=" ".join(t for r, t in lignes if r == "agent"), lignes=list(lignes))


# --- texte_en_tete -------------------------------------------------------------------------------------------------------------


def test_texte_en_tete_prend_les_mots_en_parametre_et_ne_connait_aucun_mot_du_code():
    obs = conv(("agent", "Voilà, c'est fait."), ("moi", "ok"), ("agent", "Parfait, je note."), ("agent", "Merci."))
    ok = verdict.evaluer_un({"type": "texte_en_tete", "mots": ["voilà", "parfait"], "max": 2}, obs)
    ko = verdict.evaluer_un({"type": "texte_en_tete", "mots": ["voilà", "parfait"], "max": 1}, obs)
    assert ok.reussi and not ko.reussi and ko.rang == 1
    # « merci » n'est plus une règle du code : sans le mot en paramètre, rien ne le cherche.
    assert verdict.evaluer_un({"type": "texte_en_tete", "mots": ["bonjour"], "max": 0}, obs).reussi


def test_texte_en_tete_sans_mots_est_refuse():
    with pytest.raises(Exception, match="mots"):
        verdict.valider_criteres([{"type": "texte_en_tete", "mots": [], "max": 0}])


def test_l_ancien_merci_en_tete_est_lu_comme_texte_en_tete_sans_perte():
    ancien = {"type": "merci_en_tete", "max": 0}
    assert verdict.valider_criteres([ancien])[0]["type"] == "texte_en_tete"
    assert verdict.valider_criteres([ancien])[0]["mots"] == ["merci"]
    mauvais = conv(("agent", "Merci d'avoir répondu."))
    bon = conv(("agent", "Merci de votre appel, au revoir."), ("agent", "Très bien."))
    assert not verdict.evaluer_un(ancien, mauvais).reussi  # un test déjà stocké sous l'ancien nom est jugé pareil
    assert verdict.evaluer_un(ancien, bon).reussi  # l'exception « de votre appel » est gardée


# --- modification complète -----------------------------------------------------------------------------------------------------


def creer(c, nom="Numéro dit", **plus):
    return c.post(f"/builder/tests/{AGENT}", json={"nom": nom, "replique": "Bonjour, un renseignement.", "criteres": [CRITERE], **plus})


async def test_modifier_un_test_garde_son_slug_valide_comme_a_la_creation_et_remet_les_resultats_a_zero():
    c = client_pour(EQUIPE)
    slug = creer(c).json()["test"]["slug"]
    await stockage.ajouter_un_resultat(ORG_CLIENT, AGENT, slug, {"le": "x", "version": 1, "statut": "ok", "reussis": 1, "total": 1})
    r = c.patch(
        f"/builder/tests/{AGENT}/{slug}",
        json={"nom": "Autre nom", "replique": "Je veux un devis.", "criteres": [{"type": "texte_en_tete", "mots": ["alors"], "max": 0}], "obligatoire": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == slug and r.json()["nom"] == "Autre nom" and r.json()["obligatoire"] is True
    detail = c.get(f"/builder/tests/{AGENT}/{slug}").json()
    assert detail["test"]["replique"] == "Je veux un devis." and detail["resultats"] == []
    assert detail["test"]["criteres"][0]["type"] == "texte_en_tete"


def test_une_modification_invalide_est_refusee_et_ne_touche_a_rien():
    c = client_pour(EQUIPE)
    slug = creer(c).json()["test"]["slug"]
    assert c.patch(f"/builder/tests/{AGENT}/{slug}", json={"criteres": []}).status_code == 422
    assert c.patch(f"/builder/tests/{AGENT}/{slug}", json={"scenario": "autre sorte"}).status_code == 422  # une réplique n'a pas de scénario
    assert c.get(f"/builder/tests/{AGENT}/{slug}").json()["test"]["criteres"] == [CRITERE]


def test_modifier_une_conversation_change_son_scenario_son_personnage_et_ses_tours():
    c = client_pour(EQUIPE)
    r = c.post(f"/builder/tests/{AGENT}", json={"nom": "Conv", "scenario": "Veut un rendez-vous.", "criteres": [CRITERE]})
    slug = r.json()["test"]["slug"]
    assert c.patch(f"/builder/tests/{AGENT}/{slug}", json={"scenario": "Veut annuler.", "ouverture": "Allô", "tours_max": 8, "questions_juge": ["Était-il poli ?"]}).status_code == 200
    test = c.get(f"/builder/tests/{AGENT}/{slug}").json()["test"]
    assert test["scenario"]["but"] == "Veut annuler." and test["scenario"]["tours_max"] == 8 and test["questions_juge"] == ["Était-il poli ?"]
    assert c.patch(f"/builder/tests/{AGENT}/{slug}", json={"replique": "x"}).status_code == 422


def test_modifier_rend_les_donnees_personnelles_fictives_et_un_autre_client_n_y_touche_pas():
    c = client_pour(EQUIPE)
    slug = creer(c).json()["test"]["slug"]
    assert c.patch(f"/builder/tests/{AGENT}/{slug}", json={"replique": "Mon mail est marie.dupont@gmail.com"}).status_code == 200
    assert "gmail" not in str(c.get(f"/builder/tests/{AGENT}/{slug}").json()["test"])
    assert client_pour(AUTRE).patch(f"/builder/tests/{AGENT}/{slug}", json={"nom": "pirate"}).status_code == 404
    assert c.get(f"/builder/tests/{AGENT}/{slug}").json()["test"]["nom"] == "Numéro dit"


def test_la_liste_de_l_onglet_rend_description_genre_et_dernier_resultat():
    c = client_pour(EQUIPE)
    creer(c, description="Vérifie le numéro")
    ligne = c.get(f"/builder/tests/{AGENT}").json()["tests"][0]
    assert ligne["description"] == "Vérifie le numéro" and ligne["genre"] == "replique" and ligne["derniere"] is None


# --- les listes de l'onglet : lues dans l'agent et la bibliothèque, jamais en dur --------------------------------------------------


def test_les_executions_passees_et_les_ressources_sont_lues_dans_les_donnees(monkeypatch):
    from api.services.builder.bibliotheque import service

    c = client_pour(EQUIPE)
    slug = creer(c).json()["test"]["slug"]
    assert c.get(f"/builder/tests/{AGENT}/executions").json() == {"executions": []}

    import asyncio

    asyncio.run(stockage.ajouter_un_resultat(ORG_CLIENT, AGENT, slug, {"le": "2026-11-01T10:00:00", "version": 2, "statut": "ok", "reussis": 3, "total": 3}))
    ligne = c.get(f"/builder/tests/{AGENT}/executions").json()["executions"][0]
    assert (ligne["test"], ligne["reussis"], ligne["version"]) == (slug, 3, 2)

    async def vide(_famille):
        return []

    monkeypatch.setattr(service, "lister", vide)
    r = c.get(f"/builder/tests/{AGENT}/ressources").json()
    assert set(r) == {"etapes", "outils", "issues", "champs", "personnages", "scenarios_types"}
    assert r["etapes"] and r["personnages"] == [] and r["scenarios_types"] == []
    assert client_pour(AUTRE).get(f"/builder/tests/{AGENT}/ressources").status_code == 404


def test_un_test_se_cree_aussi_quand_la_personne_a_une_vraie_adresse_mail():
    """K3 : l'adresse de l'auteur est une clé technique, pas une donnée du test. Avant, tout test créé depuis l'écran
    par une personne dont l'adresse n'est pas en `.test` était refusé (« data that looks real ») ; les tests de la suite
    n'utilisaient que des adresses fictives et ne le voyaient pas."""
    vraie = utilisateur(3, ORG_CLIENT)
    vraie.email = "prenom.nom@gmail.com"
    c = client_pour(vraie)
    r = creer(c, nom="Auteur réel")
    assert r.status_code == 200, r.text
    slug = r.json()["test"]["slug"]
    assert c.patch(f"/builder/tests/{AGENT}/{slug}", json={"obligatoire": True}).status_code == 200
