"""[.mark] builder-agent-vocal, lot 1 : le moteur (flux, cartes, opérations, plafond, compactage, interdits, conception, correction).

Cerveau FACTICE : aucun appel réel, aucune dépense. Ce qui doit tenir : le flux rend texte, actions, résultats,
cartes et opérations dans l'ordre ; une action interdite est refusée et ne change rien ; le plafond arrête la
conversation ; les vieux tours sont résumés et l'état est RELU SUR LE DISQUE ; rien ne se construit avant
l'approbation du document de conception ; les opérations s'enregistrent en UN brouillon ; la correction a un plafond
de tours et ne dit « vérifié » que sur une suite entièrement verte.
"""

from __future__ import annotations

import dataclasses

import pytest

from api.services.builder import conception, contexte, correction, fiche, moteur
from api.services.builder.actions import registre
from api.services.builder.actions.registre import Contexte
from api.services.builder.bibliotheque import service as bibliotheque
from api.services.builder.cerveau.appel import ErreurCerveau
from api.services.builder.cerveau.factice import CerveauFactice, appel, texte, tour
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur

REGLAGES = ReglagesCerveau(modele="factice")

CONCEPTION = {
    "objectif": "Prendre une demande",
    "reussite": "La demande est notée",
    "hypotheses": ["Les jours fériés sont fermés"],
    "donnees": [{"nom": "numero", "si_absente": "Proposer un rappel"}],
    "outils": [{"nom": "noter", "reponses": ["ok", "erreur"], "si_indisponible": "Proposer un rappel"}],
}


def contexte_d_action(identifiant: int = 1) -> Contexte:
    return Contexte(user=utilisateur(identifiant), workflow_id=AGENT)


async def jouer(cerveau, message="Bonjour", ctx=None, reglages=REGLAGES) -> list[dict]:
    return [e async for e in moteur.conversation(ctx or contexte_d_action(), message, cerveau, reglages)]


def genres(evenements) -> list[str]:
    return [e["type"] for e in evenements]


async def approuver_la_conception(monde):
    await conception.ecrire(ORG_CLIENT, AGENT, conception.Conception.model_validate(CONCEPTION))
    await conception.decider(ORG_CLIENT, AGENT, True, "evan")


# --- le flux ------------------------------------------------------------------------------------------------------


async def test_le_flux_rend_texte_depense_et_fin_et_range_l_historique(monde):
    evenements = await jouer(CerveauFactice(tour(texte("Bonjour, "), texte("je suis là."))))
    assert genres(evenements) == ["texte", "texte", "depense", "fin"]
    assert evenements[-1] == {"type": "fin", "raison": "fin"}
    conv = await contexte.charger(ORG_CLIENT, AGENT)
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["content"] == "Bonjour, je suis là."
    assert conv["depense"]["jetons"] == 150 and "en_cours_depuis" not in conv


async def test_une_action_est_executee_son_resultat_rendu_au_cerveau_et_la_carte_envoyee(monde):
    cerveau = CerveauFactice(
        tour(texte("J'écris le document."), appel("conception_ecrire", CONCEPTION, "c1")),
        tour(texte("C'est écrit, j'attends votre approbation.")),
    )
    evenements = await jouer(cerveau)
    assert genres(evenements) == ["texte", "action", "depense", "carte", "resultat", "texte", "depense", "fin"]
    carte = next(e for e in evenements if e["type"] == "carte")["carte"]
    assert carte["type"] == "conception" and carte["revision"] == 1
    assert (await conception.lire(ORG_CLIENT, AGENT)).etat == "propose"  # jamais approuvé par le builder
    # Le second tour reçoit le résultat de l'action, rattaché à son appel.
    messages = cerveau.requetes[1]["messages"]
    assert messages[-1]["role"] == "outil" and messages[-1]["appel_id"] == "c1"
    assert '"ok": true' in messages[-1]["content"]


async def test_les_actions_interdites_sont_refusees_et_ne_changent_rien(monde):
    await bibliotheque.creer("moules-etape", "a", "A", {"t": 1}, "alice")
    cerveau = CerveauFactice(
        tour(
            appel("publish_workflow", {"workflow_id": AGENT}, "i1"),
            appel("delete_workflow", {"workflow_id": AGENT}, "i2"),
            appel("bibliotheque_marquer_recette", {"famille": "moules-etape", "slug": "a"}, "i3"),
            appel("bibliotheque_accepter_proposition", {"id": "x"}, "i4"),
            appel("action_qui_n_existe_pas", {}, "i5"),
        ),
        tour(texte("Je ne peux pas.")),
    )
    evenements = await jouer(cerveau)
    resultats = {e["id"]: e for e in evenements if e["type"] == "resultat"}
    assert all(resultats[i]["ok"] is False for i in ("i1", "i2", "i3", "i4", "i5"))
    assert all(resultats[i]["resultat"].get("interdit") for i in ("i1", "i2", "i3", "i4"))
    assert not resultats["i5"]["resultat"].get("interdit")
    assert (await bibliotheque.lire_element("moules-etape", "a")).statut.value == "candidat"
    assert not monde.brouillons and not monde.ecritures_de_reglages  # rien n'a bougé


def test_aucune_action_interdite_n_est_dans_le_registre():
    assert not (set(registre.REGISTRE) & registre.INTERDITES)
    for nom in registre.INTERDITES:
        with pytest.raises(ValueError):
            registre.enregistrer(registre.Action(nom=nom, description="", parametres=registre.BaseModel, fonction=None))
    # Aucune action de passage en Recette, de rejet, d'acceptation ou de publication n'existe, sous aucun nom.
    for nom in registre.REGISTRE:
        assert not any(mot in nom for mot in ("publi", "supprim", "delete", "recette", "rejet", "accept", "retour"))


async def test_une_erreur_du_cerveau_est_rendue_puis_la_conversation_se_ferme_proprement(monde):
    evenements = await jouer(CerveauFactice(ErreurCerveau("cle_refusee", "Key refused")))
    assert genres(evenements) == ["erreur", "fin"] and evenements[0]["code"] == "cle_refusee"
    conv = await contexte.charger(ORG_CLIENT, AGENT)
    assert conv["messages"][0]["content"] == "Bonjour" and "en_cours_depuis" not in conv


async def test_un_seul_tour_de_conversation_a_la_fois_par_agent(monde):
    conv = await contexte.charger(ORG_CLIENT, AGENT)
    conv["en_cours_depuis"] = __import__("time").time()
    await contexte.enregistrer(ORG_CLIENT, AGENT, conv)
    evenements = await jouer(CerveauFactice())
    assert evenements == [{"type": "erreur", "code": "en_cours", "message": "The builder is already working on this agent."}]


# --- le plafond de dépense ------------------------------------------------------------------------------------------


async def test_le_plafond_de_jetons_arrete_la_conversation_et_tient_d_un_message_a_l_autre(monde):
    reglages = ReglagesCerveau(modele="f", plafond_jetons=1000)
    premier = await jouer(CerveauFactice(tour(texte("a"), entree=600, sortie=500)), reglages=reglages)
    assert premier[-1] == {"type": "fin", "raison": "fin"}
    cerveau = CerveauFactice()
    second = await jouer(cerveau, "Encore", reglages=reglages)
    assert second[0]["code"] == "plafond" and second[-1] == {"type": "fin", "raison": "plafond"}
    assert cerveau.requetes == []  # aucun appel au cerveau une fois le plafond atteint


async def test_le_plafond_de_depense_compte_les_prix_du_cerveau(monde):
    reglages = ReglagesCerveau(modele="f", plafond_depense=1.0, prix_entree_par_million=10.0, prix_sortie_par_million=30.0)
    # 100 000 entrées + 50 000 sorties = 1 $ + 1,5 $ : le plafond de 1 $ est dépassé au premier tour.
    evenements = await jouer(
        CerveauFactice(tour(texte("a"), appel("fiche_lire", {}, "x"), entree=100_000, sortie=50_000)), reglages=reglages
    )
    assert evenements[-1] == {"type": "fin", "raison": "plafond"}
    depense = next(e for e in evenements if e["type"] == "depense")
    assert depense["cout"] == pytest.approx(2.5)


async def test_un_cerveau_qui_boucle_sur_les_actions_s_arrete_au_plafond_de_tours(monde):
    reglages = ReglagesCerveau(modele="f", tours_outils_max=3)
    cerveau = CerveauFactice(*[tour(appel("fiche_lire", {}, f"x{i}")) for i in range(5)])
    evenements = await jouer(cerveau, reglages=reglages)
    assert evenements[-1] == {"type": "fin", "raison": "tours"} and len(cerveau.requetes) == 3


# --- le compactage et l'état relu sur le disque ------------------------------------------------------------------


async def test_les_vieux_tours_sont_resumes_et_l_etat_est_relu_sur_le_disque(monde):
    await fiche.ecrire(ORG_CLIENT, AGENT, {"horaires": fiche.ChampFiche(valeur="9h-18h", source="audit.pdf p.2")})
    await fiche.valider(ORG_CLIENT, AGENT, "evan")
    await approuver_la_conception(monde)
    conv = contexte.conversation_vide()
    for i in range(12):
        conv["messages"] += [{"role": "user", "content": f"demande {i} " + "x" * 900}, {"role": "assistant", "content": f"réponse {i} " + "y" * 900, "appels": []}]
    await contexte.enregistrer(ORG_CLIENT, AGENT, conv)

    reglages = ReglagesCerveau(modele="f", fenetre=4000)
    cerveau = CerveauFactice(tour(texte("Résumé : on a parlé des horaires.")), tour(texte("Voilà.")))
    evenements = await jouer(cerveau, "Où en est-on ?", reglages=reglages)
    assert evenements[-1] == {"type": "fin", "raison": "fin"}

    # 1er appel = le résumé (sans outils) ; 2e = la conversation, avec l'état relu sur le disque devant le message.
    assert cerveau.requetes[0]["outils"] == [] and "résumes" in cerveau.requetes[0]["systeme"]
    requete = cerveau.requetes[1]
    assert requete["messages"][0]["role"] == "user"  # on ne coupe jamais au milieu d'un échange
    dernier = requete["messages"][-1]["content"]
    assert "Résumé : on a parlé des horaires." in dernier
    assert "validée par evan" in dernier and "9h-18h" in dernier and "audit.pdf p.2" in dernier
    assert "Document de conception (approuve" in dernier and "Où en est-on ?" in dernier
    assert "Changements en attente : 0 opération(s)" in dernier
    conv = await contexte.charger(ORG_CLIENT, AGENT)
    assert conv["resume"].startswith("Résumé") and len(conv["messages"]) < 24
    assert "État actuel" not in conv["messages"][-2]["content"]  # l'état est envoyé, jamais rangé dans l'historique


async def test_si_le_cerveau_ne_peut_pas_resumer_un_resume_sans_cerveau_prend_le_relais(monde):
    conv = contexte.conversation_vide()
    for i in range(12):
        conv["messages"] += [{"role": "user", "content": f"demande {i} " + "x" * 900}, {"role": "assistant", "content": "r" * 900, "appels": []}]
    await contexte.enregistrer(ORG_CLIENT, AGENT, conv)
    cerveau = CerveauFactice(ErreurCerveau("indisponible", "down"), tour(texte("Voilà.")))
    await jouer(cerveau, reglages=ReglagesCerveau(modele="f", fenetre=4000))
    assert "Demande : demande 0" in (await contexte.charger(ORG_CLIENT, AGENT))["resume"]


# --- rien ne se construit avant l'approbation ---------------------------------------------------------------------------

AJOUT = [
    {"op": "ajouter_noeud", "id": "3", "type": "agentNode", "nom": "Accueil", "prompt": "Dis bonjour."},
    {"op": "ajouter_liaison", "source": "1", "target": "3", "label": "Ok", "condition": "toujours"},
]


async def test_sans_document_approuve_aucune_construction(monde):
    cerveau = CerveauFactice(
        tour(appel("brouillon_operation", {"operations": AJOUT}, "o1"), appel("brouillon_enregistrer", {}, "o2")), tour(texte("Refusé."))
    )
    evenements = await jouer(cerveau)
    resultats = {e["id"]: e for e in evenements if e["type"] == "resultat"}
    assert resultats["o1"]["ok"] is False and resultats["o1"]["resultat"]["code"] == "conception"
    assert resultats["o2"]["ok"] is False and not monde.brouillons
    # Écrit mais seulement « proposé » : toujours refusé.
    await conception.ecrire(ORG_CLIENT, AGENT, conception.Conception.model_validate(CONCEPTION))
    refus = await registre.executer("brouillon_operation", {"operations": AJOUT}, contexte_d_action())
    assert refus["ok"] is False
    # Renvoyé avec une note : refusé aussi, et la note est dite.
    await conception.decider(ORG_CLIENT, AGENT, False, "evan", "Il manque les urgences")
    refus = await registre.executer("brouillon_operation", {"operations": AJOUT}, contexte_d_action())
    assert refus["ok"] is False and "Il manque les urgences" in refus["erreur"]
    assert not monde.brouillons


async def test_toute_reecriture_du_document_retire_l_approbation(monde):
    await approuver_la_conception(monde)
    await registre.executer("conception_ecrire", {**CONCEPTION, "objectif": "Autre chose"}, contexte_d_action())
    assert (await conception.lire(ORG_CLIENT, AGENT)).etat == "propose"
    refus = await registre.executer("brouillon_operation", {"operations": AJOUT}, contexte_d_action())
    assert refus["ok"] is False


async def test_le_document_de_conception_exige_les_cas_d_absence_et_de_panne(monde):
    sans_repli = {**CONCEPTION, "donnees": [{"nom": "numero"}]}
    assert (await registre.executer("conception_ecrire", sans_repli, contexte_d_action()))["ok"] is False
    sans_indisponible = {**CONCEPTION, "outils": [{"nom": "noter", "reponses": ["ok"]}]}
    assert (await registre.executer("conception_ecrire", sans_indisponible, contexte_d_action()))["ok"] is False


async def test_les_operations_sont_envoyees_a_l_ecran_une_par_une_et_enregistrees_en_un_seul_brouillon(monde):
    await approuver_la_conception(monde)
    cerveau = CerveauFactice(
        tour(appel("brouillon_operation", {"operations": AJOUT[:1]}, "o1")),
        tour(appel("brouillon_operation", {"operations": AJOUT[1:]}, "o2")),
        tour(appel("brouillon_enregistrer", {}, "o3")),
        tour(texte("Brouillon enregistré.")),
    )
    evenements = await jouer(cerveau)
    operations = [e["operation"]["op"] for e in evenements if e["type"] == "operation"]
    assert operations == ["ajouter_noeud", "ajouter_liaison"]
    assert not monde.brouillons or len(monde.brouillons) == 1
    brouillon = monde.brouillons[AGENT]
    assert brouillon.status == "draft" and brouillon.version_number == 2  # UNE version brouillon pour les deux tours
    assert {n["id"] for n in brouillon.workflow_json["nodes"]} == {"1", "2", "3"}
    assert len(brouillon.workflow_json["edges"]) == 2
    assert monde.workflows[AGENT].released_definition.version_number == 1  # le publié n'a pas bougé
    carte = next(e for e in evenements if e["type"] == "carte")["carte"]
    assert carte["type"] == "changements" and carte["nombre_operations"] == 2
    assert (await registre.executer("brouillon_voir", {}, contexte_d_action()))["en_attente"] == []


async def test_un_graphe_invalide_n_est_pas_enregistre_et_les_operations_restent_pour_correction(monde):
    await approuver_la_conception(monde)
    ctx = contexte_d_action()
    pendante = {"op": "ajouter_liaison", "id": "boucle", "source": "2", "target": "1", "label": "x", "condition": "y"}
    assert (await registre.executer("brouillon_operation", {"operations": [pendante]}, ctx))["ok"] is True
    resultat = await registre.executer("brouillon_enregistrer", {}, ctx)
    # Une liaison qui part de la fin est refusée par la validation du graphe : rien n'est enregistré.
    assert resultat["ok"] is False and not monde.brouillons
    assert len((await registre.executer("brouillon_voir", {}, ctx))["en_attente"]) == 1
    assert (await registre.executer("brouillon_jeter", {}, ctx))["ok"] is True
    assert (await registre.executer("brouillon_voir", {}, ctx))["en_attente"] == []


async def test_une_operation_sur_un_noeud_inconnu_est_refusee_sans_rien_ranger(monde):
    await approuver_la_conception(monde)
    mauvaise = {"op": "modifier_prompt", "id": "99", "prompt": "x"}
    resultat = await registre.executer("brouillon_operation", {"operations": [AJOUT[0], mauvaise]}, contexte_d_action())
    assert resultat["ok"] is False and "Operation 2" in resultat["erreur"]
    assert (await registre.executer("brouillon_voir", {}, contexte_d_action()))["en_attente"] == []


async def test_les_changements_d_un_autre_brouillon_en_cours_de_route_bloquent_l_enregistrement(monde):
    await approuver_la_conception(monde)
    ctx = contexte_d_action()
    await registre.executer("brouillon_operation", {"operations": AJOUT}, ctx)
    await monde.save_workflow_draft(AGENT, workflow_definition=monde.workflows[AGENT].released_definition.workflow_json)  # quelqu'un d'autre enregistre
    resultat = await registre.executer("brouillon_enregistrer", {}, ctx)
    assert resultat["ok"] is False and "changed" in resultat["erreur"]


async def test_un_agent_d_une_autre_organisation_est_introuvable(monde):
    monde.ajouter_agent(organization_id=8, identifiant=77)
    ctx = Contexte(user=utilisateur(1), workflow_id=77)
    for nom, args in (("fiche_lire", {}), ("brouillon_voir", {}), ("reglages_lire", {}), ("conception_lire", {})):
        resultat = await registre.executer(nom, args, ctx)
        if nom in ("brouillon_voir", "reglages_lire"):
            assert resultat["ok"] is False
    assert (await registre.executer("brouillon_voir", {}, ctx))["code"] == "introuvable"


# --- la correction en plusieurs tours ---------------------------------------------------------------------------------


def remplacer_les_tests(monkeypatch, *reponses):
    """Le point d'entrée du lot 6 est remplacé par des suites jouées d'avance (verte ou non)."""
    suites = list(reponses)
    appels = []

    async def fausse_suite(contexte, parametres):
        appels.append(1)
        return suites.pop(0)

    monkeypatch.setitem(registre.REGISTRE, "tests_rejouer", dataclasses.replace(registre.REGISTRE["tests_rejouer"], fonction=fausse_suite, disponible=True))
    return appels


async def lancer_la_correction(cerveau, reglages=REGLAGES):
    return [e async for e in correction.corriger(contexte_d_action(), cerveau, reglages)]


async def test_la_correction_rejoue_toute_la_suite_apres_chaque_correction_et_ne_dit_verifie_que_sur_du_vert(monde, monkeypatch):
    echec = {"ok": False, "echecs": [{"test": "t1", "raison": "dit un nom d'outil"}]}
    appels = remplacer_les_tests(monkeypatch, echec, echec, {"ok": True, "echecs": []})
    cerveau = CerveauFactice(tour(texte("Je corrige.")), tour(texte("Je corrige encore.")))
    evenements = await lancer_la_correction(cerveau)
    rapport = next(e for e in evenements if e["type"] == "rapport")
    assert rapport["etat"] == "verifie" and rapport["tours"] == 2 and len(appels) == 3
    assert genres(evenements).count("fin") == 1
    assert "t1" in cerveau.requetes[0]["messages"][-1]["content"]  # le cerveau reçoit les échecs


async def test_la_correction_s_arrete_au_plafond_de_tours_et_dit_non_verifie(monde, monkeypatch):
    echec = {"ok": False, "echecs": [{"test": "t1"}]}
    appels = remplacer_les_tests(monkeypatch, *[echec] * 4)
    cerveau = CerveauFactice(*[tour(texte("Je corrige.")) for _ in range(3)])
    evenements = await lancer_la_correction(cerveau, ReglagesCerveau(modele="f", tours_correction_max=2))
    rapport = next(e for e in evenements if e["type"] == "rapport")
    assert (rapport["etat"], rapport["tours"]) == ("non_verifie", 2) and len(appels) == 3
    assert rapport["echecs_restants"] == [{"test": "t1"}] and len(cerveau.requetes) == 2


async def test_la_correction_s_arrete_au_plafond_de_depense(monde, monkeypatch):
    remplacer_les_tests(monkeypatch, {"ok": False, "echecs": [{"test": "t1"}]})
    reglages = ReglagesCerveau(modele="f", plafond_jetons=1000)
    cerveau = CerveauFactice(tour(texte("Je corrige."), entree=900, sortie=300))
    evenements = await lancer_la_correction(cerveau, reglages)
    # Le premier tour dépasse le plafond ; il n'y en a pas de second et le rapport ne ment pas.
    assert next(e for e in evenements if e["type"] == "rapport")["etat"] == "non_verifie"
    assert len(cerveau.requetes) == 1


async def test_tant_que_les_tests_ne_sont_pas_disponibles_la_correction_ne_depense_rien(monde):
    cerveau = CerveauFactice()
    evenements = await lancer_la_correction(cerveau)
    assert evenements[0]["etat"] == "tests_non_disponibles" and cerveau.requetes == []
    resultat = await registre.executer("tests_rejouer", {}, contexte_d_action())
    assert resultat["disponible"] is False


async def test_la_correction_ne_publie_jamais(monde, monkeypatch):
    remplacer_les_tests(monkeypatch, {"ok": False, "echecs": [{"test": "t"}]}, {"ok": True})
    cerveau = CerveauFactice(tour(appel("publish_workflow", {"workflow_id": AGENT}, "p1")), tour(texte("Refusé, je corrige autrement.")))
    evenements = await lancer_la_correction(cerveau)
    assert next(e for e in evenements if e["type"] == "resultat")["resultat"]["interdit"] is True
    assert monde.workflows[AGENT].released_definition.version_number == 1 and not monde.brouillons
