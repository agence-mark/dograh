"""[.mark] Builder partie 3, N1 (SA-N1b, sous-lot 5) : tout ce que l'écran permet pour l'entreprise, le builder le permet.

| Test | Ce qu'il prouve |
|---|---|
| inventaire écran / builder | chaque route d'ÉCRITURE de l'entreprise (établissements, phrases, annonce, vocabulaire, listes, équipe, campagnes, téléphonie) a son action du builder, ou figure dans ``RESTE_A_FAIRE`` (pour SA-N2-N3a) ; une route neuve sans décision fait échouer |
| famille et permission | chaque action est rangée dans sa famille, avec la permission de rôle de l'écran pour le même geste |
| arguments d'essai | chaque action valide ses arguments, est refusée à Claude Code (écran seulement) et passe dans « Tout permettre » |
| appels réels | démarrer, reprendre une campagne et l'appel de test demandent une carte tant que le mode n'est pas « Tout permettre », jamais en « Plan » |
| secrets | la téléphonie se lit par le nom, jamais les identifiants ; le lien d'invitation n'est jamais rendu au builder |
| annuler | l'annonce d'ouverture se défait d'un clic (état d'avant dans la ligne du journal), vraie base |
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute

from api.app import app
from api.db import db_client
from api.services.builder.actions import registre
from api.services.builder.actions.familles_actions import FAMILLE_DES_ACTIONS, permission_de
from api.services.builder.actions.registre import Contexte
from api.services.equipe_mark.permissions import PERMISSIONS
from api.tests.mark.builder_commun import AGENT, utilisateur
from api.tests.mark.test_builder_c2 import B, decor
from api.tests.mark.equipe_commun import client_http, entetes, sans_preparation_des_organisations  # noqa: F401

PREFIXE = "/api/v1"

# Route d'écriture de l'écran -> l'action du builder qui la rejoue.
ROUTE_VERS_ACTION = {
    ("PUT", "/organizations/etablissements"): "etablissements_remplacer",
    ("PATCH", "/organizations/etablissements/{identifiant}"): "etablissement_modifier",
    ("POST", "/organizations/etablissements/{identifiant}/etat"): "etablissement_fermer_ou_rouvrir",
    ("PUT", "/organizations/phrases"): "phrases_organisation_ecrire",
    ("PUT", "/organizations/annonce-ouverture"): "annonce_regler",
    ("PUT", "/organizations/lexique"): "lexique_ecrire",
    ("PUT", "/organizations/listes-valeurs"): "listes_valeurs_cocher",
    ("POST", "/equipe-mark/invitations"): "equipe_inviter",
    ("POST", "/campaign/create"): "campagne_creer",
    ("PATCH", "/campaign/{campaign_id}"): "campagne_modifier",
    ("POST", "/campaign/{campaign_id}/pause"): "campagne_pause",
    ("POST", "/campaign/{campaign_id}/start"): "campagne_demarrer",
    ("POST", "/campaign/{campaign_id}/resume"): "campagne_reprendre",
    ("POST", "/telephony/initiate-call"): "appel_de_test_lancer",
}

# Ce qui reste à faire, écrit (pour SA-N2-N3a : inventaire scripté, ce qui manque se construit) : une écriture de l'écran sans action du
# builder, avec la raison. Les secrets ne se saisissent jamais par le builder (garde des secrets).
RESTE_A_FAIRE = {
    ("POST", "/organizations/etablissements/controle-horaires"): "contrôle seulement (lecture) : à exposer comme lecture",
    ("POST", "/organizations/etablissements/copier"): "copie d'une fiche : à construire",
    ("POST", "/organizations/etablissements/reprise"): "reprise des fiches : à construire",
    ("POST", "/organizations/etablissements/{identifiant}/appliquer-a-tous"): "recopier un réglage dans tous les établissements : à construire",
    ("POST", "/organizations/etablissements/agent"): "lecture des établissements d'un agent (POST de lecture) : à exposer comme lecture",
    ("POST", "/organizations/lexique/budget"): "calcul seulement (lecture)",
    ("POST", "/organizations/lexique/import"): "import de vocabulaire : à construire",
    ("PUT", "/equipe-mark/roles/{role_id}"): "rôles de l'équipe : décision d'Evan (droits)",
    ("POST", "/equipe-mark/roles"): "rôles de l'équipe : décision d'Evan (droits)",
    ("DELETE", "/equipe-mark/roles/{role_id}"): "rôles de l'équipe : décision d'Evan (droits)",
    ("PUT", "/equipe-mark/membres/{user_id}/role"): "changer le rôle d'un membre : décision d'Evan (droits)",
    ("DELETE", "/equipe-mark/membres/{user_id}"): "retirer un membre : décision d'Evan (droits)",
    ("DELETE", "/equipe-mark/invitations/{invitation_id}"): "annuler une invitation : à construire",
    ("POST", "/campaign/{campaign_id}/redial"): "rappeler les appels échoués (appels réels) : à construire",
    ("PATCH", "/equipe-mark/moi"): "profil de la personne : son geste à elle, jamais celui du builder",
    ("POST", "/equipe-mark/moi/mot-de-passe"): "mot de passe de la personne : jamais le builder (garde des secrets)",
    ("POST", "/telephony/inbound/{workflow_id}"): "rappel d'un fournisseur (exempté, jamais une écriture de l'écran)",
}


def _routes_d_ecriture_de_l_entreprise() -> set[tuple[str, str]]:
    prefixes = ("/organizations/etablissements", "/organizations/phrases", "/organizations/annonce-ouverture", "/organizations/lexique", "/organizations/listes-valeurs",
                "/equipe-mark", "/campaign", "/telephony/initiate-call")
    trouvees = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        chemin = route.path[len(PREFIXE):] if route.path.startswith(PREFIXE) else route.path
        if not chemin.startswith(prefixes):
            continue
        for methode in route.methods or []:
            if methode in {"POST", "PUT", "PATCH", "DELETE"}:
                trouvees.add((methode, chemin))
    return trouvees


def test_chaque_route_d_ecriture_de_l_entreprise_a_son_action_ou_une_ligne_au_reste_a_faire():
    ecriture = _routes_d_ecriture_de_l_entreprise()
    sans_decision = sorted(r for r in ecriture if r not in ROUTE_VERS_ACTION and r not in RESTE_A_FAIRE)
    assert not sans_decision, f"Écritures de l'écran sans action du builder ni ligne « reste à faire » : {sans_decision}"
    # chaque route annoncée existe vraiment, et chaque action annoncée est au registre
    inconnues = sorted(r for r in ROUTE_VERS_ACTION if r not in ecriture)
    assert not inconnues, f"Routes citées qui n'existent plus : {inconnues}"
    manquantes = sorted(a for a in ROUTE_VERS_ACTION.values() if a not in registre.REGISTRE)
    assert not manquantes, manquantes


def test_les_actions_de_l_entreprise_ont_leur_famille_et_la_permission_de_l_ecran():
    attendu = {
        "etablissements_remplacer": ("entreprise", "agents.modifier"),
        "phrases_organisation_ecrire": ("entreprise", "agents.modifier"),
        "annonce_regler": ("entreprise", "agents.modifier"),
        "lexique_ecrire": ("entreprise", "agents.modifier"),
        "listes_valeurs_cocher": ("entreprise", "agents.modifier"),
        "campagne_creer": ("entreprise", "agents.modifier"),
        "campagne_pause": ("entreprise", "agents.modifier"),
        "equipe_inviter": ("entreprise", "equipe.gerer"),
        "equipe_lister": ("lecture", "equipe.gerer"),
        "campagne_demarrer": ("appels_reels", "agents.publier"),  # comme /campaign/{id}/start
        "campagne_reprendre": ("appels_reels", "agents.publier"),
        "appel_de_test_lancer": ("appels_reels", "tests.jouer"),  # comme /telephony/initiate-call
        "telephonie_lister": ("lecture", None),
    }
    for nom, (famille, permission) in attendu.items():
        assert FAMILLE_DES_ACTIONS[nom] == famille, nom
        assert permission_de(nom, famille) == permission, nom
        assert permission is None or permission in PERMISSIONS


ARGUMENTS = {
    "etablissements_lire": {}, "etablissements_remplacer": {"catalogue": {"etablissements": []}},
    "etablissement_modifier": {"identifiant": "e1", "modifications": {}},
    "etablissement_fermer_ou_rouvrir": {"identifiant": "e1", "etat": {"etat_force": "FERME"}},
    "phrases_organisation_lire": {}, "phrases_organisation_ecrire": {"catalogue": {}},
    "annonce_lire": {}, "annonce_regler": {"reglages": {}}, "lexique_lire": {}, "lexique_ecrire": {"vocabulaire": {}},
    "listes_valeurs_lire": {}, "listes_valeurs_cocher": {"modification": {"valeurs": []}},
    "equipe_lister": {}, "equipe_inviter": {"email": "a@exemple.test", "role_id": 1},
    "campagnes_lister": {}, "campagne_lire": {"campagne_id": 1}, "campagne_creer": {"name": "c", "workflow_id": AGENT, "source_type": "csv", "source_id": "k"},
    "campagne_modifier": {"campagne_id": 1, "modifications": {"name": "x"}}, "campagne_pause": {"campagne_id": 1},
    "campagne_demarrer": {"campagne_id": 1}, "campagne_reprendre": {"campagne_id": 1},
    "telephonie_lister": {}, "appel_de_test_lancer": {"workflow_id": AGENT},
}


def test_chaque_action_de_l_entreprise_a_ses_arguments_d_essai():
    nouvelles = set(ROUTE_VERS_ACTION.values()) | {n for n, f in FAMILLE_DES_ACTIONS.items() if n.endswith("_lire") and n in ARGUMENTS} | {"equipe_lister", "campagnes_lister", "telephonie_lister"}
    assert nouvelles <= set(ARGUMENTS), sorted(nouvelles - set(ARGUMENTS))
    assert set(ARGUMENTS) <= set(registre.REGISTRE)


@pytest.mark.parametrize("nom", sorted(ARGUMENTS))
async def test_chaque_action_passe_en_tout_permettre_et_n_est_pas_a_claude_code(nom, monde, monkeypatch):
    appels = []

    async def espion(contexte, parametres):
        appels.append(parametres)
        return {"ok": True, "vu": nom}

    monkeypatch.setitem(registre.REGISTRE, nom, dataclasses.replace(registre.REGISTRE[nom], fonction=espion, extras={}))
    contexte = Contexte(user=utilisateur(1), workflow_id=AGENT, conversation={"mode": "tout", "messages": []})
    assert await registre.executer(nom, ARGUMENTS[nom], contexte) == {"ok": True, "vu": nom} and len(appels) == 1
    assert registre.REGISTRE[nom].mcp is False
    # la porte Claude Code ne les connaît pas
    assert nom not in {n for n, a in registre.REGISTRE.items() if a.mcp}


@pytest.mark.parametrize("mode", ["demander", "agent", "plan"])
@pytest.mark.parametrize("nom", ["campagne_demarrer", "campagne_reprendre", "appel_de_test_lancer"])
async def test_appeler_de_vraies_personnes_demande_une_carte_sauf_en_tout_permettre(nom, mode, monde, monkeypatch):
    appels = []

    async def espion(contexte, parametres):
        appels.append(1)
        return {"ok": True}

    monkeypatch.setitem(registre.REGISTRE, nom, dataclasses.replace(registre.REGISTRE[nom], fonction=espion))
    contexte = Contexte(user=utilisateur(1), workflow_id=AGENT, conversation={"mode": mode, "messages": []})
    resultat = await registre.executer(nom, ARGUMENTS[nom], contexte)
    assert resultat["code"] == ("mode_plan" if mode == "plan" else "autorisation_requise") and appels == []
    assert monde.journal_builder == []  # rien n'a été fait, rien n'est journalisé


async def test_le_role_borne_l_entreprise_meme_en_tout_permettre(monde, monkeypatch):
    monde.permissions_des_comptes = {1: ["agents.modifier"]}  # pas « equipe.gerer », pas « tests.jouer », pas « agents.publier »
    contexte = Contexte(user=utilisateur(1), workflow_id=AGENT, conversation={"mode": "tout", "messages": []})
    for nom in ("equipe_inviter", "equipe_lister", "appel_de_test_lancer", "campagne_demarrer"):
        assert (await registre.executer(nom, ARGUMENTS[nom], contexte))["code"] == "droits", nom


# --- secrets ------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["demander", "agent", "tout", "plan"])
async def test_la_telephonie_se_lit_par_le_nom_jamais_les_identifiants(mode, monde, monkeypatch):
    comptes = [SimpleNamespace(id=3, name="Compte principal", provider="twilio", credentials={"auth_token": "tok-fictif-tel", "account_sid": "sid-fictif"}, is_default_outbound=True, inactive=False)]

    async def liste(organization_id):
        return comptes

    monkeypatch.setattr(db_client, "list_telephony_configurations", liste)
    resultat = await registre.executer("telephonie_lister", {}, Contexte(user=utilisateur(1), conversation={"mode": mode, "messages": []}))
    assert resultat["comptes"] == [{"id": 3, "nom": "Compte principal", "fournisseur": "twilio", "par_defaut_sortant": True, "inactif": False}]
    assert "tok-fictif-tel" not in str(resultat) and "sid-fictif" not in str(resultat)


async def test_le_lien_d_invitation_n_est_jamais_rendu_au_builder(monde, monkeypatch):
    async def inviter(corps, user):
        return SimpleNamespace(model_dump=lambda mode="json": {"id": 1, "email": corps.email, "role_nom": "Membre", "lien": "https://x.test/rejoindre/jeton-fictif", "envoye": False})

    monkeypatch.setattr("api.routes.equipe_mark.inviter", inviter)
    contexte = Contexte(user=utilisateur(1), conversation={"mode": "tout", "messages": []})
    resultat = await registre.executer("equipe_inviter", ARGUMENTS["equipe_inviter"], contexte)
    assert resultat["ok"] is True and "jeton-fictif" not in str(resultat) and "lien" not in resultat["invitation"]
    assert "jeton-fictif" not in str(monde.journal_builder)


# --- annuler, vraie base ---------------------------------------------------------------------------------------------------------------


async def test_l_annonce_d_ouverture_se_defait_d_un_clic_avec_l_etat_d_avant(db_session, sans_preparation_des_organisations):

    org, user, jeton, agent = await decor(db_session, "ent1")
    user.selected_organization_id = org
    contexte = Contexte(user=user, workflow_id=agent.id, conversation={"mode": "tout", "messages": []})
    avant = (await registre.executer("annonce_lire", {}, contexte))
    assert avant["ok"] is True, avant
    nouveau = {k: v for k, v in avant.items() if k != "ok"}
    cle = "annonce_pause"
    nouveau[cle] = "Nous reprenons dans un instant."
    fait = await registre.executer("annonce_regler", {"reglages": nouveau}, contexte)
    assert fait["ok"] is True, fait
    assert contexte.journal["annulable"] is True
    ligne = contexte.journal["id"]
    apres = {k: v for k, v in (await registre.executer("annonce_lire", {}, contexte)).items() if k != "ok"}
    assert apres[cle] == "Nous reprenons dans un instant."
    async with client_http() as c:
        assert (await c.post(f"{B}/journal/{ligne}/annuler", headers=entetes(jeton, org))).status_code == 200
    retour = {k: v for k, v in (await registre.executer("annonce_lire", {}, contexte)).items() if k != "ok"}
    assert retour == {k: v for k, v in avant.items() if k != "ok"}
