"""[.mark] Lot 7b-C3, commit 2 : les manques et les refus de saisie de la base de la réservation ne portent plus de texte (lot 7b-C7, B7) ; le texte d'avant se refait toujours de leurs faits
(``textes_de_secours``). Le numéro illisible porte le fait ``numero_illisible`` (le même nom que la commande) ; les valeurs de ``phrases_du_manque`` sont les constantes de la feuille."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime

from api.db.bases_clients import restauration_reservation as RR
from api.services.reservation import phrases_du_manque as PM
from api.services.reservation import textes_de_secours as TS
from api.tests.mark import test_restauration_reservation as RESA
from api.tests.mark.partie_1.aides_secours_de_la_reservation import faits_publics

salle, demande = RESA.salle, RESA.demande  # la fixture du classeur, reprise par affectation


def _verifie(r, statut: str, manque: str, texte: str, secours):
    """C7 (B7) : la base ne porte plus de texte ; le texte d'avant se refait toujours de ses seuls faits (il sort avec le catalogue, B9)."""
    assert (r.statut, r.manque, r.suggestion) == (statut, manque, ""), r
    assert secours(faits_publics(r)) == texte, r


async def _creer(salle, retire: str | None = None, **plus):
    brouillon = demande(**plus)
    if retire:
        brouillon.pop(retire)
    return await RR.creer_reservation(salle.c, salle.a, brouillon)


async def test_pour_combien_de_personnes(salle):
    _verifie(await _creer(salle, "couverts"), "INCOMPLETE", "couverts", "Pour combien de personnes ?", TS.combien_de_personnes)


async def test_pour_quel_jour_et_quelle_heure(salle):
    _verifie(await _creer(salle, "debut"), "INCOMPLETE", "debut", "Pour quel jour et à quelle heure ?", TS.quel_jour_et_quelle_heure)


async def test_a_quel_nom_je_mets_la_reservation(salle):
    _verifie(await _creer(salle, "prenom"), "INCOMPLETE", "prenom", "À quel nom je mets la réservation ?", TS.a_quel_nom_je_mets_la_reservation)


async def test_nom_trop_long(salle):
    _verifie(await _creer(salle, prenom="A" * 61), "ARGUMENT_INVALIDE", "prenom", "Ce nom est trop long.", TS.nom_trop_long)


async def test_numero_illisible_porte_son_fait(salle):
    r = await _creer(salle, telephone="pas un numéro")
    _verifie(r, "ARGUMENT_INVALIDE", "telephone", "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", TS.numero_illisible)
    assert r.faits == {"numero_illisible": True}


async def test_quel_est_votre_numero(salle):
    _verifie(await _creer(salle, "telephone"), "INCOMPLETE", "telephone", "Quel est votre numéro de téléphone ?", TS.quel_numero)


async def test_note_trop_longue(salle):
    _verifie(await _creer(salle, note="n" * 201), "ARGUMENT_INVALIDE", "note", "Cette note est trop longue.", TS.note_trop_longue)


async def test_modifier_sans_nombre_de_personnes_ni_heure_valides(salle):
    numero = (await _creer(salle)).faits["numero"]
    _verifie(await RR.modifier_reservation(salle.c, salle.a, numero, {"couverts": 0}), "ARGUMENT_INVALIDE", "couverts", "Pour combien de personnes ?", TS.combien_de_personnes)
    sans_fuseau = datetime(2026, 11, 14, 20, 0)
    _verifie(await RR.modifier_reservation(salle.c, salle.a, numero, {"debut": sans_fuseau}), "ARGUMENT_INVALIDE", "debut", "Pour quel jour et à quelle heure ?", TS.quel_jour_et_quelle_heure)


def test_les_phrases_du_manque_sont_les_constantes_de_la_feuille_et_gardent_leur_texte():
    assert PM.PHRASES_DU_MANQUE == {
        "le nombre de personnes": "Pour combien de personnes ?", "le jour": "Pour quel jour ?", "l'heure": "À quelle heure ?", "le nom": "À quel nom ?",
        "le numéro de téléphone": "Quel est votre numéro de téléphone ?", "le nom et le jour de sa réservation d'avant": "À quel nom et pour quel jour était votre réservation ?",
    }
    assert PM.PHRASES_DU_MANQUE == {
        "le nombre de personnes": TS.PERSONNES, "le jour": TS.JOUR, "l'heure": TS.HEURE, "le nom": TS.NOM, "le numéro de téléphone": TS.TELEPHONE,
        "le nom et le jour de sa réservation d'avant": TS.NOM_ET_JOUR_D_AVANT,
    }
    ecrites = {n.value for n in ast.walk(ast.parse(inspect.getsource(PM))) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not ecrites & set(PM.PHRASES_DU_MANQUE.values()), "le catalogue ne recopie plus ses textes : il les lit de la feuille"
