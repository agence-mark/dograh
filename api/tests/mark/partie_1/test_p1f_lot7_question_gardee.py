"""[.mark] Lot 7a, n° 7 (``question_gardee``, renvoyé du lot 6) : qui ferme une question est UN seul geste du registre commun (``RC.repondu``), d'après ce que la
table du métier dit (``Table.ferme``) et le résultat de la réponse ; plus de drapeau posé par chaque réponse. À comportement égal : la personne entend la même chose.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.services.actions_communes import registre_des_questions as RC
from api.services.actions_communes.resultat import Resultat
from api.tests.mark import test_restauration_reservation as RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

from .aides_de_la_commande import a_emporter, jusqu_au_recapitulatif, premier_article, question_posee, refuser_la_proposition

salle = RESERVATION.salle
RACINE = Path(__file__).resolve().parents[3] / "services"


def test_plus_aucun_drapeau_question_gardee_dans_les_services():
    """Le mécanisme remplace le drapeau : aucun service ne le pose ni ne le lit."""
    restes = [str(f.relative_to(RACINE)) for f in RACINE.rglob("*.py") if re.search(r"\bquestion_gardee\b", f.read_text(encoding="utf-8"))]
    assert restes == [], restes


def test_la_table_d_un_metier_dit_quand_une_reponse_ferme_sa_question():
    t = RC.Table(ordre=("a",), condition=lambda e, q: True, ferme=lambda q, sens, r, valeurs: sens != "autre")
    p: dict = {}
    q = {"type": "a", "id": "Q-1", "objet": "a"}
    RC.ouvrir(t, p, q)
    assert RC.repondu(t, p, q, "autre", Resultat("OK", {}, "")) is False
    assert (RC.CONV.de(p).get(RC.CLE_DES_QUESTIONS) or {}).get("a"), "la question gardée reste au registre"
    assert RC.repondu(t, p, q, "accepte", Resultat("OK", {}, "")) is True
    assert not (RC.CONV.de(p).get(RC.CLE_DES_QUESTIONS) or {}).get("a")


async def test_non_a_la_relecture_la_garde_et_oui_ensuite_enregistre(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    avant = await jusqu_au_recapitulatif(e)
    await e.tour("non", reponse={"question_id": avant["id"], "sens": "refuse"})
    apres = question_posee(e)
    assert apres.get("type") == "relecture" and apres["id"] == avant["id"], (avant, apres)
    assert not e.p.get("enregistree")
    await e.tour("oui c'est bon", reponse={"question_id": avant["id"], "sens": "accepte"})
    assert question_posee(e).get("type") != "relecture", question_posee(e)


async def test_une_reponse_sans_sens_net_garde_le_doute_et_un_nom_dit_le_ferme(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    q = question_posee(e)
    assert q.get("type") == "ambiguite", q
    await e.tour("euh, la deuxième", reponse={"question_id": q["id"], "sens": "autre"})
    assert question_posee(e).get("id") == q["id"], question_posee(e)
    choix = q["choix"][0]
    await e.tour(choix, reponse={"question_id": q["id"], "sens": "autre", "valeurs": [choix]})
    assert question_posee(e).get("id") != q["id"], question_posee(e)
    assert e.p["lignes"], "l'article choisi est dans la commande"


async def test_reservation_un_choix_non_compris_garde_sa_question_sous_son_numero(salle, monkeypatch):
    """La réservation suit la même table : un « laquelle ? » non compris reste posé sous son numéro ; un choix compris le ferme."""
    from api.db.bases_clients.restauration_reservation import creer_reservation
    from api.tests.mark.partie_1.test_l07_reservation import SAMEDI_20H, TEL

    for numero, debut, personnes in (("a", SAMEDI_20H, 2), ("b", SAMEDI_20H.replace(day=15, hour=19), 3)):
        r = await creer_reservation(salle.c, salle.a, {"debut": debut, "couverts": personnes, "prenom": "Alice", "telephone": TEL, "appel_id": f"avant-{numero}"})
        assert r.statut == "ENREGISTREE", r
    e = EssaiReservation(salle, monkeypatch)
    a = await e.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    q = a["question"]
    b = await e.tour("euh bleu", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["bleu"]})
    assert b["question"]["id"] == q["id"] and "cible" not in e.etat, b
    await e.tour("la deuxième", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["la deuxième"]})
    assert e.etat.get("cible"), e.etat


async def test_ce_que_le_modele_lit_dit_encore_que_la_question_reste_posee(essai_de):
    """Le drapeau ``question_gardee`` était un fait interne qui fuyait dans ``resultats[].faits`` (aucun texte du gabarit ni du contrat n'en parle). L'information utile au modèle
    est portée par le retour : la réponse dite (``recapitulatif``) et la question toujours posée, sous son numéro."""
    from api.services.actions_communes import enveloppe_legere

    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    avant = await jusqu_au_recapitulatif(e)
    r = await e.tour("non", reponse={"question_id": avant["id"], "sens": "refuse"})
    lu = enveloppe_legere.pour_le_modele(r)
    assert (lu.get("question") or {}).get("id") == avant["id"], lu
    assert any((x.get("faits") or {}).get("recapitulatif") == "refuse" for x in lu.get("resultats") or []), lu  # la réponse dite, que le modèle lit toujours
    assert "question_gardee" not in str(lu), lu
