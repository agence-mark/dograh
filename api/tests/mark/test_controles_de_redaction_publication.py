"""[.mark] Lot « façon Tala par motif », T2 et T3 : les contrôles de rédaction à travers la VRAIE publication (R1).

| Test | Ce qu'il prouve |
|---|---|
| prévient par défaut | un montant écrit en dur : la fenêtre « Publier » le montre (à voir, étape + extrait + identifiant de l'étape) et la publication passe |
| éteint | « Éteint » : le contrôle n'est pas joué, aucun défaut |
| bloque | « Bloque » : la garde refuse, une seule fois (le bilan ne le recompte pas), avec le libellé du contrôle |
| même réglage | les positions viennent de ``publication.controles`` du brouillon, comme les autres contrôles ; les défauts de l'organisation s'appliquent |
| poids | seuil dépassé : la ligne est « à relire », la publication passe quand même ; sans seuil : les nombres seuls |
| longueur | un prompt au-delà du plafond du cerveau n'est plus bloquant (T3) ; sans plafond, muette |
| lignes de « Prêt à publier » | un contrôle de rédaction qui prévient a sa ligne conseillée ; éteint, aucune ligne |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.builder.tests_agent import publication
from api.services.publication import controles
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, sans_les_lignes_de_pret
from api.tests.mark.test_builder_tests_agent import banc, un_test  # noqa: F401


def graphe(prompt):
    return {
        "nodes": [
            {"id": "1", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Départ", "prompt": prompt}},
            {"id": "2", "type": "endCall", "position": {"x": 0, "y": 1}, "data": {"name": "Fin", "prompt": "Au revoir."}},
        ],
        "edges": [{"id": "e", "source": "1", "target": "2", "data": {"label": "Fini", "condition": "La personne a fini."}}],
    }


def brouillon(prompt, controles_=None, **reglages):
    configurations = sans_les_lignes_de_pret({"publication": {"controles": controles_ or {}}, **reglages})
    return SimpleNamespace(workflow_json=graphe(prompt), version_number=2, workflow_configurations=configurations)


COUTEUX = "Dis que la visite coûte 45 euros."


async def test_un_montant_en_dur_previent_par_defaut_et_la_publication_passe(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    b = brouillon(COUTEUX)
    vue = await controles.evaluer(wf, b, ORG_CLIENT)
    k1 = next(c for c in vue["controles"] if c["cle"] == "valeur_en_dur")
    assert (k1["position"], k1["statut"]) == ("previent", "alerte")
    defaut = vue["defauts_du_prompt"][0]
    assert (defaut["code"], defaut["etape"], defaut["noeud_id"], defaut["statut"]) == ("valeur_en_dur", "Départ", "1", "avertissement")
    assert "45" in defaut["extrait"]
    assert await publication.verifier_avant_publication(wf, b, ORG_CLIENT) is None


async def test_eteint_le_controle_n_est_pas_joue(banc):  # noqa: F811
    b = brouillon(COUTEUX, {"valeur_en_dur": "eteint"})
    vue = await controles.evaluer(banc.workflows[AGENT], b, ORG_CLIENT)
    assert next(c for c in vue["controles"] if c["cle"] == "valeur_en_dur")["statut"] == "eteint"
    assert vue["defauts_du_prompt"] == []


async def test_bloque_la_garde_refuse_une_seule_fois(banc):  # noqa: F811
    await un_test("a")  # l'agent est suivi : le bilan joue aussi, il ne doit pas recompter K1
    wf = banc.workflows[AGENT]
    b = brouillon(COUTEUX, {"valeur_en_dur": "bloque"})
    refus = await publication.verifier_avant_publication(wf, b, ORG_CLIENT)
    assert refus is not None and refus["is_valid"] is False
    assert [c["cle"] for c in refus["controles_publication"]] == ["valeur_en_dur"]
    messages = [e["message"] for e in refus["errors"] if "45" in e["message"] or "amount" in e["message"]]
    assert len(messages) == 1 and messages[0].startswith("[Valeur écrite en dur]")
    assert refus["controle"] == []  # le bilan ne porte pas K1
    vue = await controles.evaluer(wf, b, ORG_CLIENT)
    assert vue["bloque"] is True


async def test_les_positions_de_l_organisation_s_appliquent_comme_aux_autres_controles(banc):  # noqa: F811
    from api.schemas.publication import Publication
    from api.services.publication import defauts_org

    wf = banc.workflows[AGENT]
    defauts = Publication.model_validate({"controles": {"verbe_ecran": "bloque"}})
    sans_reglage_propre = SimpleNamespace(workflow_json=graphe("Demande de cliquer sur le lien."), version_number=2, workflow_configurations={})

    async def lire(_org):
        return defauts

    original = defauts_org.lire
    defauts_org.lire = lire
    try:
        refus = await publication.verifier_avant_publication(wf, sans_reglage_propre, ORG_CLIENT)
    finally:
        defauts_org.lire = original
    assert refus is not None and "verbe_ecran" in [c["cle"] for c in refus["controles_publication"]]


async def test_le_poids_seuil_depasse_la_publication_passe_quand_meme(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    b = brouillon("A" * 500, cerveau_poids_max=100)
    vue = await controles.evaluer(wf, b, ORG_CLIENT)
    poids = next(c for c in vue["controles"] if c["cle"] == "poids_agent")
    assert (poids["position"], poids["statut"]) == ("previent", "alerte")
    assert vue["poids"]["poids_max"] == 100 and vue["poids"]["etapes"][0]["etape"] == "Départ"
    assert vue["poids"]["etapes"][0]["total"] >= 500
    assert vue["bloque"] is False
    assert await publication.verifier_avant_publication(wf, b, ORG_CLIENT) is None


async def test_sans_seuil_le_poids_montre_les_nombres_seuls(banc):  # noqa: F811
    vue = await controles.evaluer(banc.workflows[AGENT], brouillon("A" * 500), ORG_CLIENT)
    assert next(c for c in vue["controles"] if c["cle"] == "poids_agent")["statut"] == "ok"
    assert vue["poids"]["poids_max"] is None and vue["poids"]["etapes"][0]["total"] >= 500


async def test_le_poids_eteint_n_est_pas_joue(banc):  # noqa: F811
    b = brouillon("A" * 500, {"poids_agent": "eteint"}, cerveau_poids_max=100)
    vue = await controles.evaluer(banc.workflows[AGENT], b, ORG_CLIENT)
    assert next(c for c in vue["controles"] if c["cle"] == "poids_agent")["statut"] == "eteint"
    assert vue["poids"]["actif"] is False


async def test_un_prompt_trop_long_ne_bloque_plus_la_publication(banc):  # noqa: F811
    await un_test("a")  # agent suivi : le bilan bloque par défaut, mais « longueur » n'est plus un blocage
    wf = banc.workflows[AGENT]
    long = " ".join(f"Consigne numéro {n} sur un sujet différent à bien respecter." for n in range(12))
    b = brouillon(long, cerveau_plafond_prompt=100)
    assert await publication.verifier_avant_publication(wf, b, ORG_CLIENT) is None
    sans_plafond = brouillon(long)
    from api.services.builder.controle.service import controler_l_agent

    resultat = await controler_l_agent(wf, ORG_CLIENT, graphe=sans_plafond.workflow_json, configurations=sans_plafond.workflow_configurations)
    assert "longueur" not in {e["code"] for e in resultat["elements"]}


async def test_la_ligne_de_pret_a_publier_d_un_controle_de_redaction(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    vue = await controles.evaluer(wf, brouillon(COUTEUX), ORG_CLIENT)
    ligne = next(l for l in vue["lignes"] if l["id"] == "valeur_en_dur")
    assert (ligne["niveau"], ligne["etat"]) == ("conseille", "a_faire")
    eteint = await controles.evaluer(wf, brouillon(COUTEUX, {"valeur_en_dur": "eteint"}), ORG_CLIENT)
    assert not [l for l in eteint["lignes"] if l["id"] == "valeur_en_dur"]


# --- « Ignorer pour cette version » : écrit au journal, avec la personne, jamais chez un autre client ----------------------------


import pytest  # noqa: E402

from api.tests.mark.equipe_commun import client_http, creer_compte, creer_organisation, entetes  # noqa: E402
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: E402,F401


@pytest.mark.usefixtures("sans_preparation_des_organisations")
async def test_ignorer_un_defaut_est_ecrit_au_journal_et_refuse_chez_un_autre_client(db_session, monkeypatch):
    org = await creer_organisation(db_session, "ign-a")
    autre = await creer_organisation(db_session, "ign-b")
    user, jeton = await creer_compte(db_session, "ign-a@example.com", role="Administrateur", organisations=[org])
    _, jeton_autre = await creer_compte(db_session, "ign-b@example.com", role="Administrateur", organisations=[autre])
    agent = await db_session.create_workflow(name="A", workflow_definition=graphe(COUTEUX), user_id=user.id, organization_id=org)
    ecrits = []

    async def journaliser(utilisateur, action, organisation_id, detail=None):
        ecrits.append((utilisateur.id, action, organisation_id, detail))

    monkeypatch.setattr("api.services.equipe_mark.acces.journaliser", journaliser)
    url = f"/api/v1/builder/publication/{agent.id}/ignorer-un-defaut"
    corps = {"code": "valeur_en_dur", "etape": "Départ", "extrait": "45 euros", "version": 2}
    async with client_http() as c:
        assert (await c.post(url, json=corps, headers=entetes(jeton_autre, autre))).status_code == 404
        assert [e for e in ecrits if e[1] == "publication.ignorer_un_defaut"] == []  # rien n'est écrit pour un agent d'un autre client
        assert (await c.post(url, json={**corps, "code": "longueur"}, headers=entetes(jeton, org))).status_code == 422  # liste fermée
        ok = await c.post(url, json=corps, headers=entetes(jeton, org))
        assert ok.status_code == 200, ok.text
    assert [e for e in ecrits if e[1] == "publication.ignorer_un_defaut"] == [(user.id, "publication.ignorer_un_defaut", org, {"agent": agent.id, **corps})]
