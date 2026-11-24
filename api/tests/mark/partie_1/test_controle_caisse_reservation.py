"""[.mark] Correctifs d'avant le banc (23/11), points de Pierre sur la caisse et la réservation, un test par point.

| Test | Ce qu'il prouve |
|---|---|
| 14 place | la place prise entre la relecture et le « oui » : les horaires libres sont DITS (pas ``null``) et la consigne ne prétend pas que « le reste est fait » |
| 14 accord | « oui, mais prenez plutôt le 06… » : rien n'est enregistré avec l'ancien numéro, la relecture est refaite, le « oui » suivant enregistre avec le nouveau |
| 14 retour | le code qui ramène l'appel à la commande après un détour ne redit pas « Demande de l'appelant : … » (une visite de plus) ; un retour vers le principal n'en est pas une |
| 14 kits | un outil sans connecteur (natif, calculatrice, fin d'appel) ajouté par l'équipe à un kit livré n'est plus effacé au démarrage ; une action disparue du catalogue l'est toujours |
| F E30 | « j'annule samedi et je réserve dimanche » : la règle (une réservation par appel) reste, le code dit une phrase et la suite va à l'équipe |
| A5 | une panne (erreur ou coupure) à l'enregistrement après le « oui » laisse la question posée : un second « oui » enregistre la réservation |
"""

from __future__ import annotations

import asyncio

import pytest

from api.db.bases_clients.restauration_reservation import creer_reservation
from api.services.actions_communes import conversation as CONV
from api.services.reservation import moteur
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.partie_1.test_l07_reservation import MOTS
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_reservation import PARIS, SAMEDI_20H, demande, salle  # noqa: F401


@pytest.mark.parametrize("panne", [RuntimeError("base coupée"), asyncio.TimeoutError()])
async def test_a5_oui_apres_une_panne_enregistre_la_reservation(salle, monkeypatch, panne):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r["question"]
    assert q["type"] == "recapitulatif", r
    vrai = moteur.reserver
    pannes = [panne]

    async def reserver_en_panne(*a, **k):
        if pannes and k.get("confirmer"):
            raise pannes.pop()
        return await vrai(*a, **k)

    monkeypatch.setattr(moteur, "reserver", reserver_en_panne)
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert await essai.nombre_de_reservations() == 0 and r["statut"] != "ENREGISTREE", r
    assert (CONV.question_de(essai.etat) or {}).get("id") == q["id"], CONV.question_de(essai.etat)  # la question attend toujours
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE" and await essai.nombre_de_reservations() == 1, r


async def test_14_place_prise_entre_la_relecture_et_le_oui_dit_les_horaires_libres(salle, monkeypatch):
    """Pierre 14 : le refus de la place au « oui » rendait ``horaires_libres: [null]`` (la porte lisait ``heure_dite``, la base rend ``quand_dit``) et la consigne
    « le reste de la fiche est déjà fait (reponse) » : la réponse n'était pas faite."""
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r["question"]
    assert q["type"] == "recapitulatif", r
    for i, (couverts, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):  # quelqu'un d'autre prend la salle
        assert (await creer_reservation(salle.c, salle.a, demande(couverts=couverts, telephone=tel, appel_id=f"p{i}"))).statut == "ENREGISTREE"
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert r["faits"].get("horaires_libres") and all(isinstance(h, str) and h for h in r["faits"]["horaires_libres"]), r
    assert "déjà fait" not in str(r.get("a_faire")) and not str(r.get("a_faire")).startswith(" refusé"), r.get("a_faire")


async def test_14_oui_avec_un_autre_numero_refait_la_relecture_avant_d_enregistrer(salle, monkeypatch):
    """Pierre 14 : la réservation partait avec le numéro affiché (SMS vers lui) PUIS le changement ne disait rien (``A_PRECISER`` sans phrase du code)."""
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r["question"]
    assert q["type"] == "recapitulatif", r
    r = await essai.tour("oui, mais prenez plutôt le 06 98 76 54 32", reponse={"question_id": q["id"], "sens": "accepte"}, telephone="06 98 76 54 32")
    assert await essai.nombre_de_reservations() == 0, r  # l'ancien numéro n'a rien enregistré
    assert r["question"]["type"] == "recapitulatif" and r["question"]["id"] == q["id"], r  # la relecture refaite garde son numéro (RC9)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE" and await essai.nombre_de_reservations() == 1, r
    assert await salle.c.fetchval("SELECT telephone FROM mark.resto_reservation") == "+33698765432"


async def test_14_oui_avec_une_valeur_redite_a_l_identique_enregistre(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    r = await essai.tour("oui, à vingt heures", reponse={"question_id": r["question"]["id"], "sens": "accepte"}, heure="vingt heures")
    assert r["statut"] == "ENREGISTREE" and await essai.nombre_de_reservations() == 1, r


def test_14_retour_du_code_a_la_commande_apres_un_detour_ne_redit_pas_la_demande():
    from api.services.groupe.notes import demande_a_la_premiere_visite, visites_du_collegue

    trace = {"passations": [
        {"de": 299, "vers": 300, "raison": "passer_a_l_agent_commande", "issue": "completed", "demande": "une reine à emporter"},
        {"de": 300, "vers": 301, "raison": "passer_a_l_agent_reservation", "issue": "completed"},
    ]}
    assert demande_a_la_premiere_visite("une reine à emporter", trace, 300, en_cours=False) == "une reine à emporter"  # première visite, tracée
    trace["passations"].append({"de": 301, "vers": 300, "raison": "retour", "issue": "completed"})  # le code ramène l'appel à la commande
    assert visites_du_collegue(trace, 300) == 2
    assert demande_a_la_premiere_visite("une reine à emporter", trace, 300, en_cours=False) is None  # avant : redite comme à une première visite
    assert visites_du_collegue({"passations": [{"de": 300, "vers": 299, "raison": "retour", "issue": "completed"}]}, 299) == 0  # un retour vers le principal n'est pas une visite


def test_14_un_outil_sans_connecteur_d_un_kit_livre_n_est_pas_mort():
    from api.services.outils_mark.kits_livres import outil_mort

    assert outil_mort({"schema_version": 1, "type": "calculator", "config": {}}) is False  # avant : effacé à chaque démarrage
    assert outil_mort({"schema_version": 1, "type": "native", "config": {"name": "end_call"}}) is False
    assert outil_mort({"schema_version": 1, "type": "integration", "config": {"connecteur": "commande", "action": "fiche"}}) is False
    assert outil_mort({"schema_version": 1, "type": "integration", "config": {"connecteur": "commande", "action": "action_disparue"}}) is True


async def test_f_e30_une_nouvelle_reservation_apres_une_annulation_est_dite_et_va_a_l_equipe(salle, monkeypatch):
    """Pierre F : la décision reste (une seule réservation par appel, même après une annulation) ; il lui manquait une phrase du code et une sortie vers l'équipe."""
    from api.services.reservation.porte import CLE_TEXTES_DU_CODE

    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    r = await essai.tour("j'annule", annuler_une_reservation_enregistree=True)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ANNULEE", r
    r = await essai.tour("et plutôt dimanche à vingt heures pour deux au nom de Bob", personnes=2, jour="dimanche", heure="vingt heures", nom="Bob")
    assert await essai.nombre_de_reservations() == 1  # la règle reste : pas de seconde réservation
    # lot 7b, ligne 67 (fiche relue, Q1) : c'est un refus et une promesse, pas un fait accompli : le code ne le dit plus, le modèle le dit et passe à l'équipe
    assert not essai.fiche_de_l_appel[CLE_TEXTES_DU_CODE].get("avant"), essai.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE)
    assert "équipe" in str(r.get("a_faire")), r
