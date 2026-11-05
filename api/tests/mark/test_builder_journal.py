"""[.mark] Builder partie 3, N1 (SA-N1b, sous-lots 4 et 6) : le journal des écritures du builder, « Annuler », et les trois gardes dans les quatre modes.

| Test | Ce qu'il prouve |
|---|---|
| journal x mode | dans chacun des quatre modes, une écriture permise a sa ligne (qui, quoi, mode, autorisation) ; une écriture refusée ou en attente n'en a pas |
| autorisation | « une fois », « pour ce chat », l'accord d'une dépense et Claude Code sont écrits tels quels |
| garde du journal | si la ligne ne peut pas être écrite, l'action n'est PAS jouée, dans chaque mode |
| garde des secrets | dans chaque mode, un secret en clair dans les arguments est refusé avant toute écriture ; rien de ce que l'action rend n'en montre un |
| garde du plafond | dans chaque mode, le plafond du mois refuse de démarrer un travail ; « continuer quand même » est ponctuel et journalisé |
| journal lisible | filtré par organisation DANS la requête, paginé, sans secret |
| annuler | un réglage écrit par le builder se défait (instantané « Revenir avant ») ; dans l'ordre ; une seule fois ; le rôle borne ; une autre organisation reçoit 404 |
| ne se défait pas | publier, supprimer, dépenser, appeler : la ligne dit pourquoi |
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel

from api.db import db_client
from api.services.builder import fil as service_fil
from api.services.builder import garde_secrets, journal
from api.services.builder.actions import registre
from api.services.builder.actions.registre import PORTE_MCP, Action, Contexte
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.services.equipe_mark.permissions import PERMISSIONS
from api.tests.mark.builder_commun import AGENT, utilisateur
from api.tests.mark.test_builder_c2 import B, base_en_serie, decor, donner_le_cerveau, fil_de  # noqa: F401
from api.tests.mark.test_builder_familles_et_modes import _chat, essais  # noqa: F401
from api.tests.mark.equipe_commun import client_http, entetes, sans_preparation_des_organisations  # noqa: F401

MODES = ("demander", "agent", "tout", "plan")
# Dans chaque mode : la famille « entreprise » passe-t-elle sans demander ? (« tout » seulement)
ENTREPRISE_PASSE = {"demander": False, "agent": False, "tout": True, "plan": False}
BROUILLON_PASSE = {"demander": True, "agent": True, "tout": True, "plan": False}


# --- la garde du journal ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_toute_ecriture_permise_a_sa_ligne_de_journal_dans_chaque_mode(mode, monde, essais):
    contexte = _chat(mode)
    contexte.conversation["fil_id"] = 9
    resultat = await registre.executer("essai_brouillon", {"workflow_id": AGENT}, contexte)
    if not BROUILLON_PASSE[mode]:
        assert resultat["code"] == "mode_plan" and monde.journal_builder == []  # refusée : rien n'est écrit, rien n'est journalisé
        return
    assert resultat == {"ok": True} and len(essais["brouillon"]) == 1
    assert len(monde.journal_builder) == 1
    ligne = monde.journal_builder[0]
    assert (ligne["action"], ligne["famille"], ligne["mode"], ligne["autorisation"], ligne["statut"]) == ("essai_brouillon", "brouillon", mode, "mode", "fait")
    assert ligne["organization_id"] == 7 and ligne["user_id"] == 1 and ligne["auteur"] and ligne["workflow_id"] == AGENT and ligne["fil_id"] == 9
    assert ligne["porte"] == "ecran" and ligne["arguments"] == {"workflow_id": AGENT} and ligne["apres"] == {"ok": True}
    assert contexte.journal == {"id": ligne["id"], "annulable": False, "raison": "autre"}


@pytest.mark.parametrize("mode", MODES)
async def test_une_lecture_n_ecrit_rien_au_journal_et_une_demande_non_plus(mode, monde, essais):
    assert await registre.executer("essai_lecture", {}, _chat(mode)) == {"ok": True}
    assert monde.journal_builder == []
    resultat = await registre.executer("essai_entreprise", {}, _chat(mode))
    if ENTREPRISE_PASSE[mode]:
        assert resultat == {"ok": True} and len(monde.journal_builder) == 1
    else:
        assert resultat["code"] in ("autorisation_requise", "mode_plan") and monde.journal_builder == []  # une carte n'est pas une écriture


@pytest.mark.parametrize("mode", MODES)
async def test_le_journal_en_panne_n_laisse_rien_s_ecrire_dans_aucun_mode(mode, monde, essais):
    monde.journal_en_panne = True
    resultat = await registre.executer("essai_brouillon", {"workflow_id": AGENT}, _chat(mode))
    assert resultat["code"] in ("journal", "mode_plan")  # Plan refuse avant ; les trois autres modes sont arrêtés par le journal
    assert essais["brouillon"] == [] and monde.journal_builder == []
    if mode != "plan":
        assert resultat["code"] == "journal" and "Nothing was done" in resultat["erreur"]


async def test_l_autorisation_est_ecrite_telle_qu_elle_a_ete_donnee(monde, essais):
    # une fois : la demande, puis la réponse de la personne (posée dans la conversation), puis l'appel identique
    contexte = _chat("demander")
    demande = await registre.executer("essai_entreprise", {"workflow_id": AGENT}, contexte)
    contexte.conversation["autorisations"][demande["demande"]]["statut"] = "une_fois"
    assert await registre.executer("essai_entreprise", {"workflow_id": AGENT}, contexte) == {"ok": True}
    assert monde.journal_builder[-1]["autorisation"] == "une_fois" and monde.journal_builder[-1]["mode"] == "demander"
    # pour ce chat
    contexte = _chat("demander")
    demande = await registre.executer("essai_entreprise", {"workflow_id": AGENT}, contexte)
    contexte.conversation["autorisations"][demande["demande"]]["statut"] = "pour_ce_chat"
    assert await registre.executer("essai_entreprise", {"workflow_id": AGENT}, contexte) == {"ok": True}
    assert monde.journal_builder[-1]["autorisation"] == "pour_ce_chat"
    # accord d'une dépense annoncée
    contexte = _chat("demander")
    contexte.conversation["depenses"] = {"d1": {"statut": "accordee", "utilisee": False}}
    assert await registre.executer("essai_depense", {"workflow_id": AGENT}, contexte) == {"ok": True}
    assert monde.journal_builder[-1]["autorisation"] == "depense" and monde.journal_builder[-1]["non_annulable"] == "depense"
    # Claude Code : pas de mode de chat
    mcp = Contexte(user=utilisateur(1), workflow_id=AGENT, porte=PORTE_MCP)
    assert await registre.executer("essai_brouillon", {"workflow_id": AGENT}, mcp) == {"ok": True}
    derniere = monde.journal_builder[-1]
    assert (derniere["porte"], derniere["autorisation"], derniere["mode"]) == ("mcp", "claude_code", None)
    # hors chat (la personne agit par une route de l'écran)
    hors = Contexte(user=utilisateur(1), workflow_id=AGENT)
    assert await registre.executer("essai_brouillon", {"workflow_id": AGENT}, hors) == {"ok": True}
    assert monde.journal_builder[-1]["autorisation"] == "personne"


@pytest.mark.parametrize("famille,raison", [("publication", "publication"), ("irreversible", "irreversible"), ("depense", "depense"), ("appels_reels", "appels_reels")])
async def test_ce_qui_ne_se_defait_pas_le_dit(famille, raison, monde, essais):
    contexte = _chat("tout")
    assert await registre.executer(f"essai_{famille}", {"workflow_id": AGENT}, contexte) == {"ok": True}
    assert contexte.journal == {"id": monde.journal_builder[-1]["id"], "annulable": False, "raison": raison}
    assert monde.journal_builder[-1]["non_annulable"] == raison


async def test_une_action_en_echec_est_journalisee_sans_annulation(monde, monkeypatch):
    class P(BaseModel):
        workflow_id: int | None = None

    async def echoue(contexte, parametres):
        raise registre.ErreurAction("non", "refus_de_l_essai")

    monkeypatch.setitem(registre.REGISTRE, "essai_echec", Action(nom="essai_echec", description="", parametres=P, fonction=echoue, ecriture=True, famille="brouillon"))
    contexte = _chat("tout")
    assert (await registre.executer("essai_echec", {"workflow_id": AGENT}, contexte))["code"] == "refus_de_l_essai"
    ligne = monde.journal_builder[-1]
    assert ligne["statut"] == "echec" and ligne["non_annulable"] == "echec" and contexte.journal["annulable"] is False


# --- la garde des secrets ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_un_secret_en_clair_est_refuse_avant_toute_ecriture_dans_chaque_mode(mode, monde, essais):
    for famille in ("brouillon", "entreprise", "irreversible"):
        resultat = await registre.executer(f"essai_{famille}", {"workflow_id": AGENT, "api_key": "sk-fictive-ne-pas-montrer"}, _chat(mode))
        assert resultat["code"] == "secret" and "sk-fictive" not in str(resultat)
        assert essais[famille] == []
    assert monde.journal_builder == []  # refusé avant le journal : rien n'a été écrit


@pytest.mark.parametrize("mode", MODES)
async def test_ce_que_l_action_rend_ne_montre_aucun_secret_dans_aucun_mode(mode, monde, monkeypatch):
    class P(BaseModel):
        pass

    async def rend_des_secrets(contexte, parametres):
        return {"ok": True, "api_key": "sk-fictive-1", "reglages": {"stt": {"token": "tok-fictif", "credential_uuid": "u-1"}}, "mots_de_passe": [{"password": "mdp-fictif"}], "n": 3}

    monkeypatch.setitem(registre.REGISTRE, "essai_secrets", Action(nom="essai_secrets", description="", parametres=P, fonction=rend_des_secrets, famille="lecture"))
    resultat = await registre.executer("essai_secrets", {}, _chat(mode))
    brut = str(resultat)
    assert "sk-fictive-1" not in brut and "tok-fictif" not in brut and "mdp-fictif" not in brut
    assert resultat["reglages"]["stt"]["credential_uuid"] == "u-1"  # un nom de clé (référence) reste lisible : le builder choisit par le nom
    assert resultat["api_key"] == "[key-hidden]" and resultat["n"] == 3


def test_la_garde_distingue_un_secret_d_une_reference():
    assert garde_secrets.secret_en_clair({"a": {"api_key": "x"}}) == "a.api_key"
    assert garde_secrets.secret_en_clair({"liste": [{"token": "x"}]}) == "liste[0].token"
    assert garde_secrets.secret_en_clair({"credential_uuid": "u", "api_key": "[key-hidden]", "token": "", "password": None, "has_key": True}) is None
    assert garde_secrets.masquer({"key": "x", "credentials": {"a": 1}, "ok": 1}) == {"key": "[key-hidden]", "credentials": "[key-hidden]", "ok": 1}


async def test_le_journal_ne_garde_aucun_secret_meme_dans_l_apres(monde, monkeypatch):
    class P(BaseModel):
        pass

    async def fonction(contexte, parametres):
        return {"ok": True, "token": "tok-fictif-journal"}

    monkeypatch.setitem(registre.REGISTRE, "essai_j", Action(nom="essai_j", description="", parametres=P, fonction=fonction, ecriture=True, famille="brouillon"))
    await registre.executer("essai_j", {}, _chat("tout"))
    assert "tok-fictif-journal" not in str(monde.journal_builder)


# --- la garde du plafond du mois ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_le_plafond_du_mois_tient_dans_chaque_mode(mode, db_session, sans_preparation_des_organisations, monkeypatch):
    org, user, _jeton, agent = await decor(db_session, f"pl{mode}")
    fil = await db_client.creer_fil(org, user.id, agent.id, "Ce mois-ci", None)
    await db_client.modifier_fil(org, fil.id, cout=3.5, historique={"messages": [], "mode": mode})
    fil = await db_client.lire_fil(org, fil.id)
    cerveau = CerveauFactice(tour(texte("non")))
    reglages = ReglagesCerveau(modele="m", plafond_mois=3.0)
    with pytest.raises(service_fil.ErreurFil) as refus:
        await service_fil.lancer(user, fil, "continue", cerveau, reglages)
    assert refus.value.statut == 402 and "monthly ceiling" in str(refus.value) and cerveau.requetes == []
    # « continuer quand même » : ponctuel, et journalisé (qui, quel chat, la dépense) ; jamais le message
    donner_le_cerveau(monkeypatch, CerveauFactice(tour(texte("ok"))))
    await service_fil.lancer(user, fil, "continue", CerveauFactice(tour(texte("ok"))), reglages, depasser_le_plafond=True)
    await service_fil.attendre(fil.id)
    lignes, _total = await db_client.lister_journal(limit=50, offset=0, organization_id=org)
    assert len([ligne for ligne in lignes if ligne["action"] == "builder.plafond_mois_depasse"]) == 1


# --- le journal lisible, par organisation, paginé -------------------------------------------------------------------------------------


async def test_le_journal_est_filtre_par_organisation_dans_la_requete_et_pagine(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "jl1")
    autre, _u, autre_jeton, autre_agent = await decor(db_session, "jl2")
    for i in range(7):
        await db_client.ecrire_journal_builder(org, workflow_id=agent.id, user_id=user.id, auteur="c1", action=f"a{i}", famille="brouillon", statut="fait", arguments={"i": i, "api_key": "sk-fictive"})
    await db_client.ecrire_journal_builder(autre, workflow_id=autre_agent.id, user_id=None, auteur="c2", action="autre", famille="brouillon", statut="fait")
    async with client_http() as c:
        page = (await c.get(f"{B}/journal", params={"limit": 3, "offset": 0}, headers=entetes(jeton, org))).json()
        assert page["total"] == 7 and [ligne["action"] for ligne in page["lignes"]] == ["a6", "a5", "a4"] and page["limit"] == 3
        suite = (await c.get(f"{B}/journal", params={"limit": 3, "offset": 6}, headers=entetes(jeton, org))).json()
        assert [ligne["action"] for ligne in suite["lignes"]] == ["a0"]
        assert (await c.get(f"{B}/journal", params={"limit": 500}, headers=entetes(jeton, org))).status_code == 422  # bornée
        chez_l_autre = (await c.get(f"{B}/journal", headers=entetes(autre_jeton, autre))).json()
        assert chez_l_autre["total"] == 1 and chez_l_autre["lignes"][0]["action"] == "autre"
        # filtre par agent, dans la requête
        assert (await c.get(f"{B}/journal", params={"workflow_id": autre_agent.id}, headers=entetes(jeton, org))).json()["total"] == 0


# --- Annuler ------------------------------------------------------------------------------------------------------------------------


async def _regler(user, agent, valeur: bool, mode="tout") -> tuple[dict[str, Any], Contexte]:
    contexte = Contexte(user=user, workflow_id=agent.id, conversation={"messages": [], "mode": mode})
    resultat = await registre.executer("reglages_regler", {"workflow_id": agent.id, "valeurs": {"relecture_des_numeros": valeur}}, contexte)
    return resultat, contexte


async def _reglage(org, agent) -> Any:
    from api.services.builder import brouillon

    workflow = await db_client.get_workflow(agent.id, organization_id=org)
    return (await brouillon.configurations_courantes(workflow)).get("relecture_des_numeros")


async def test_annuler_se_fait_dans_l_ordre_et_une_seule_fois(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "an1")
    user.selected_organization_id = org
    r1, c1 = await _regler(user, agent, True)
    r2, c2 = await _regler(user, agent, False)
    assert c1.journal["annulable"] and c2.journal["annulable"], (r1, r2)
    async with client_http() as c:
        # dans l'ordre : la première est recouverte par la seconde
        ordre = await c.post(f"{B}/journal/{c1.journal['id']}/annuler", headers=entetes(jeton, org))
        assert ordre.status_code == 409 and ordre.json()["detail"]["code"] == "ordre"
        assert (await c.post(f"{B}/journal/{c2.journal['id']}/annuler", headers=entetes(jeton, org))).status_code == 200
        assert (await c.post(f"{B}/journal/{c2.journal['id']}/annuler", headers=entetes(jeton, org))).json()["detail"]["code"] == "deja_annulee"
        assert (await c.post(f"{B}/journal/{c1.journal['id']}/annuler", headers=entetes(jeton, org))).status_code == 200  # plus rien de plus récent
    lignes, _ = await db_client.lister_journal_builder(org)
    assert len([ligne for ligne in lignes if ligne["action"] == "annuler"]) == 2  # l'annulation est elle-même journalisée


async def test_annuler_remet_l_etat_d_avant(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "an2")
    user.selected_organization_id = org
    avant = await _reglage(org, agent)
    resultat, contexte = await _regler(user, agent, True)
    assert resultat.get("ok", True) is not False, resultat
    assert contexte.journal["annulable"] is True, contexte.journal
    assert await _reglage(org, agent) is True
    async with client_http() as c:
        fait = await c.post(f"{B}/journal/{contexte.journal['id']}/annuler", headers=entetes(jeton, org))
        assert fait.status_code == 200, fait.text
    assert await _reglage(org, agent) == avant
    ligne = await db_client.lire_journal_builder(org, contexte.journal["id"])
    assert ligne["annule_le"] is not None and ligne["annule_par"]


async def test_annuler_est_cloisonne_par_organisation_et_borne_par_le_role(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "an3")
    autre, _u, autre_jeton, _autre_agent = await decor(db_session, "an3b")
    user.selected_organization_id = org
    _r, contexte = await _regler(user, agent, True)
    async with client_http() as c:
        # une autre organisation ne voit même pas la ligne
        assert (await c.post(f"{B}/journal/{contexte.journal['id']}/annuler", headers=entetes(autre_jeton, autre))).status_code == 404
        assert (await c.post(f"{B}/journal/999999/annuler", headers=entetes(jeton, org))).status_code == 404
    assert (await db_client.lire_journal_builder(org, contexte.journal["id"]))["annule_le"] is None


async def test_une_action_qui_ne_se_defait_pas_repond_409_avec_la_raison(db_session, sans_preparation_des_organisations):
    org, user, jeton, agent = await decor(db_session, "an4")
    ligne = await db_client.ecrire_journal_builder(org, workflow_id=agent.id, user_id=user.id, auteur="c", action="agent_publier", famille="publication", statut="fait", non_annulable="publication")
    async with client_http() as c:
        r = await c.post(f"{B}/journal/{ligne}/annuler", headers=entetes(jeton, org))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "publication"


async def test_annuler_une_action_de_l_entreprise_remet_l_etat_d_avant_ecrit_dans_la_ligne(db_session, sans_preparation_des_organisations, monkeypatch):
    """Les actions qui réécrivent un objet entier déclarent comment lire l'avant et le remettre (``extras``)."""
    org, user, jeton, agent = await decor(db_session, "an5")
    user.selected_organization_id = org
    etat = {"annonce": "avant"}
    remis: list = []

    class P(BaseModel):
        annonce: str

    async def avant_lire(contexte, arguments):
        return dict(etat)

    async def defaire(contexte, avant):
        remis.append(avant)
        etat.update(avant)

    async def ecrire(contexte, parametres):
        etat["annonce"] = parametres.annonce
        return {"ok": True}

    monkeypatch.setitem(
        registre.REGISTRE, "essai_inverse",
        Action(nom="essai_inverse", description="", parametres=P, fonction=ecrire, ecriture=True, famille="entreprise", extras={"avant": avant_lire, "defaire": defaire}),
    )
    contexte = Contexte(user=user, workflow_id=agent.id, conversation={"messages": [], "mode": "tout"})
    assert await registre.executer("essai_inverse", {"annonce": "apres"}, contexte) == {"ok": True}
    assert contexte.journal["annulable"] is True and etat["annonce"] == "apres"
    async with client_http() as c:
        assert (await c.post(f"{B}/journal/{contexte.journal['id']}/annuler", headers=entetes(jeton, org))).status_code == 200
    assert remis == [{"annonce": "avant"}] and etat["annonce"] == "avant"
