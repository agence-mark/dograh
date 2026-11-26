"""[.mark] Lot 8, PE-1, Q1 (b) (Pierre, 26/11) : un numéro de question cité par une réponse REFUSÉE n'est jamais redonné à une autre question.

Client (commande) « Oui. » alors qu'aucune question n'attend : le modèle cite ``Q-1``, la réponse est refusée. / Avant : la proposition qui naît ensuite reçoit ``Q-1`` ; un « oui »
rejoué (« je répète ») la prend pour sa réponse et ajoute l'article proposé. / Après : la proposition reçoit un autre numéro, le « oui » rejoué est écarté seul.
Même règle à la réservation (refus 14 : un seul mécanisme, celui du registre commun)."""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.tests.mark.partie_1.aides_de_la_commande import (
    a_emporter,
    premier_article,
    question_posee,
)
from api.tests.mark.partie_1.aides_de_la_reservation import salle
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

MOTS = "une table pour quatre samedi à vingt heures au nom d'Alice"
_ = salle  # la fixture de la salle, reprise sans import nu


def _refusee_pour_son_numero(retour: dict) -> bool:
    return any(x.get("raison") == "question_inconnue" for x in (retour.get("refus") or []) + (retour.get("resultats") or [])) or "question_inconnue" in str(retour)


async def test_commande_le_numero_d_une_reponse_refusee_sans_question_n_est_pas_redonne(essai_de):
    e = await essai_de()
    await a_emporter(e)
    r = await e.tour("oui", reponse={"question_id": "Q-1", "sens": "accepte"})
    assert _refusee_pour_son_numero(r), r
    await premier_article(e)
    q = question_posee(e)
    assert q.get("type") == "proposition" and q["id"] != "Q-1", q


async def test_commande_le_oui_rejoue_ne_prend_pas_la_proposition_nee_apres_le_refus(essai_de):
    """Le scénario du bilan Q1 : « oui » refusé (Q-1), le Coca est proposé, « je répète » rejoue la même fiche : la proposition n'est pas acceptée, rien n'entre."""
    e = await essai_de()
    await a_emporter(e)
    oui = {"reponse": {"question_id": "Q-1", "sens": "accepte"}}
    await e.tour("oui", **oui)
    await premier_article(e)
    avant = e.lignes()
    assert question_posee(e).get("type") == "proposition"
    await e.tour("je répète", **oui)
    assert e.lignes() == avant, (avant, e.lignes())


async def test_commande_le_numero_d_une_reponse_refusee_au_mauvais_numero_n_est_pas_redonne(essai_de):
    """Le même geste au refus de ``reponse`` face à une question posée sous un autre numéro (``question_inconnue`` avec question) : le numéro cité plus haut est brûlé aussi."""
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    q = question_posee(e)
    cite = "Q-" + str(int(q["id"].split("-")[1]) + 5)
    await e.tour("oui", reponse={"question_id": cite, "sens": "accepte"})
    assert (CONV.de(e.p).get("prochain_q") or 0) > int(cite.split("-")[1])


async def test_reservation_le_numero_d_une_reponse_refusee_sans_question_n_est_pas_redonne(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await essai.tour("oui", reponse={"question_id": "Q-1", "sens": "accepte"})
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert r["question"]["type"] == "recapitulatif" and r["question"]["id"] != "Q-1", r["question"]


async def test_reservation_le_numero_d_une_reponse_refusee_au_mauvais_numero_n_est_pas_redonne(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    cite = "Q-" + str(int(r["question"]["id"].split("-")[1]) + 5)
    await essai.tour("oui", reponse={"question_id": cite, "sens": "accepte"})
    assert (CONV.de(essai.etat).get("prochain_q") or 0) > int(cite.split("-")[1])
