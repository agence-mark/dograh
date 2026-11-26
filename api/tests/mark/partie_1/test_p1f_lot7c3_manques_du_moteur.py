"""[.mark] Lot 7b-C3, commit 4 : les questions de manque du moteur de la réservation ne portent plus de texte (lot 7b-C7, B7) ; le texte d'avant se refait toujours des faits du résultat que lit le modèle
(``textes_de_secours``). Le moteur n'importe pas ``phrases_du_manque`` (il importerait ``etat_pour_le_modele``, qui importe le moteur) : il lit la feuille, qui porte aussi les textes du catalogue.
Le numéro illisible porte le fait ``numero_illisible``, le même nom que la base."""

from __future__ import annotations

from api.db.bases_clients import restauration_reservation as RR
from api.services.actions_communes.resultat import Resultat
from api.services.reservation import moteur
from api.services.reservation import textes_de_secours as TS
from api.tests.mark import test_restauration_reservation as RESA
from api.tests.mark.partie_1.aides_secours_de_la_reservation import faits_publics
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

salle, creer, TEL = RESA.salle, RESA.creer, RESA.TEL  # la fixture et les aides du classeur, reprises par affectation


def _verifie(r, statut: str, manque: str, texte: str, secours):
    """C7 (B7) : le moteur ne porte plus de texte ; le texte d'avant se refait toujours de ses seuls faits (il sort avec le catalogue, B9)."""
    assert (r.statut, r.manque, r.suggestion) == (statut, manque, ""), r
    assert secours(faits_publics(r)) == texte, r


class SourceSansJour:
    """Une source dont la date est retenue sans jour lisible : le seul moyen d'atteindre le « pour quel jour ? » d'un jour introuvable."""

    async def resoudre_une_date(self, texte, heure):
        return Resultat("RETENU", {})


async def test_pour_combien_de_personnes_a_la_reservation_et_aux_disponibilites(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await moteur.reserver(essai.source, essai.etat, essai.moteur_appelant, jour="samedi")
    _verifie(r, "INCOMPLETE", "personnes", "Pour combien de personnes ?", TS.combien_de_personnes)
    r = await moteur.disponibilites(essai.source, essai.etat, "samedi", None)
    _verifie(r, "INCOMPLETE", "personnes", "Pour combien de personnes ?", TS.combien_de_personnes)


async def test_pour_quel_jour_a_la_reservation_aux_disponibilites_et_au_jour_introuvable(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await moteur.reserver(essai.source, essai.etat, essai.moteur_appelant, personnes=2)
    _verifie(r, "INCOMPLETE", "jour", "Pour quel jour ?", TS.quel_jour)
    r = await moteur.disponibilites(essai.source, essai.etat, None, 2)
    _verifie(r, "INCOMPLETE", "jour", "Pour quel jour ?", TS.quel_jour)
    r = await moteur.disponibilites(SourceSansJour(), {}, "samedi", 2)
    _verifie(r, "INTROUVABLE", "jour", "Pour quel jour ?", TS.quel_jour)


async def test_a_quel_nom_je_mets_la_reservation(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await moteur.reserver(essai.source, essai.etat, essai.moteur_appelant, personnes=2, jour="samedi", heure="vingt heures")
    _verifie(r, "INCOMPLETE", "prenom", "À quel nom je mets la réservation ?", TS.a_quel_nom_je_mets_la_reservation)


async def test_quel_est_votre_numero_quand_il_ne_s_affiche_pas(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await moteur.reserver(essai.source, essai.etat, essai.moteur_appelant, personnes=2, jour="samedi", heure="vingt heures", prenom="Alice")
    _verifie(r, "INCOMPLETE", "telephone", "Quel est votre numéro de téléphone ?", TS.quel_numero)


async def test_numero_illisible_porte_son_fait(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await moteur.reserver(essai.source, essai.etat, essai.moteur_appelant, personnes=2, jour="samedi", heure="vingt heures", prenom="Alice", telephone="pas un numéro")
    _verifie(r, "ARGUMENT_INVALIDE", "telephone", "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", TS.numero_illisible)
    assert r.faits == {"numero_illisible": True}


async def test_sous_quel_nom_et_quel_jour_sans_reservation_visee_et_sans_numero_affiche(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await moteur.modifier(essai.source, essai.etat, essai.moteur_appelant, jour="dimanche")
    _verifie(r, "INCOMPLETE", "nom_et_jour_de_la_reservation", "Sous quel nom, et pour quel jour ?", TS.sous_quel_nom_et_quel_jour)
    r = await moteur.retrouver_une_reservation(essai.source, essai.etat, essai.moteur_appelant)
    _verifie(r, "INCOMPLETE", "nom_et_jour_de_la_reservation", "Sous quel nom, et pour quel jour ?", TS.sous_quel_nom_et_quel_jour)
    assert r.faits == {"raison": "numero_masque"}


async def test_a_quelle_heure_pour_un_changement_de_jour_seul(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    essai.etat["cible"] = (await creer(salle)).faits["numero"]
    r = await moteur.modifier(essai.source, essai.etat, essai.moteur_appelant, jour="dimanche")
    _verifie(r, "INCOMPLETE", "heure", "À quelle heure ?", TS.quelle_heure)


async def test_qu_est_ce_que_je_change_quand_rien_n_est_dit(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    essai.etat["cible"] = (await creer(salle)).faits["numero"]
    r = await moteur.modifier(essai.source, essai.etat, essai.moteur_appelant)
    _verifie(r, "INCOMPLETE", "changement", "Qu'est-ce que je change : l'heure, le nombre de personnes ?", TS.que_change_je)
    assert RR and TEL
