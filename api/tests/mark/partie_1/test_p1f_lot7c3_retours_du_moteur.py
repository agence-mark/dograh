"""[.mark] Lot 7b-C3, commit 5 : les retours du moteur de la réservation (complet, créneaux, déjà fait, introuvable, rien ne change, un choix) ne portent plus de texte (lot 7b-C7, B7) ;
le texte d'avant se refait toujours des faits du résultat (``textes_de_secours``). Le texte du choix se refait de ``candidats[].dit`` : la fonction reçoit le résultat entier (le modèle ne lit pas
``candidats``, E4). « Rien ne change » gagne les faits ``quand_dit`` et ``personnes`` ; « déjà annulée » et « aucune réservation » ne lisent aucun fait."""

from __future__ import annotations

from datetime import datetime, timedelta

from api.services.actions_communes.resultat import Resultat
from api.services.reservation import moteur
from api.services.reservation import textes_de_secours as TS
from api.tests.mark import test_restauration_reservation as RESA
from api.tests.mark.partie_1.aides_secours_de_la_reservation import faits_publics
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

salle, creer, TEL, PARIS = RESA.salle, RESA.creer, RESA.TEL, RESA.PARIS  # la fixture et les aides du classeur, reprises par affectation


def _verifie(r, statut: str, texte: str, secours):
    """C7 (B7) : le moteur ne porte plus de texte ; le texte d'avant se refait toujours de ses seuls faits (il sort avec le catalogue, B9)."""
    assert (r.statut, r.suggestion) == (statut, ""), r
    assert secours(faits_publics(r)) == texte, r


class SourceDuSamedi:
    """Une source dont le seul jour est samedi 14 novembre 2026 et dont les créneaux libres sont ceux qu'on lui donne."""

    def __init__(self, creneaux: list[datetime], heure_dite: bool = True):
        self.creneaux, self.heure_dite = creneaux, heure_dite

    async def resoudre_une_date(self, texte, heure):
        vingt = datetime(2026, 11, 14, 20, 0, tzinfo=PARIS)
        faits = {"jour": "2026-11-14", "jour_dit": "samedi quatorze novembre", "heure_dite": "vingt heures"}
        return Resultat("RETENU", {**faits, "heure_voulue": vingt.isoformat()} if self.heure_dite else faits)

    async def disponibilites(self, jour, personnes):
        return Resultat("OK", {"creneaux": [{"debut": d, "fin": d + timedelta(hours=1)} for d in self.creneaux]})


def _a(heure: int) -> datetime:
    return datetime(2026, 11, 14, heure, 0, tzinfo=PARIS)


async def test_complet_ce_jour_la_et_pour_la_partie_du_jour():
    source = SourceDuSamedi([])
    r = await moteur.disponibilites(source, {}, "samedi", 2)
    _verifie(r, "OK", "Nous sommes complets ce jour-là.", TS.complets_ce_jour)
    source = SourceDuSamedi([_a(12)], heure_dite=False)
    r = await moteur.disponibilites(source, {}, "samedi soir", 2)
    _verifie(r, "OK", "Nous sommes complets ce jour-là, pour le soir.", TS.complets_ce_jour)


async def test_il_y_a_de_la_place_dit_les_heures_des_creneaux():
    r = await moteur.disponibilites(SourceDuSamedi([_a(19), _a(20), _a(21)]), {}, "samedi", 2, "vingt heures")
    _verifie(r, "OK", "Il y a de la place à dix-neuf heures, vingt heures ou vingt et une heures.", TS.il_y_a_de_la_place)


async def test_refus_complet_sans_creneau_puis_avec_les_plus_proches():
    appelant = moteur.Appelant(TEL, None)
    etat = {"brouillon": {}}
    r = await moteur.reserver(SourceDuSamedi([]), etat, appelant, personnes=2, jour="samedi", heure="vingt heures", prenom="Alice")
    _verifie(r, "REFUSEE", "Nous sommes complets ce jour-là.", TS.refus_complet_du_moteur)
    r = await moteur.reserver(SourceDuSamedi([_a(19), _a(21)]), {"brouillon": {}}, appelant, personnes=2, jour="samedi", heure="vingt heures", prenom="Alice")
    _verifie(r, "REFUSEE", "Nous ne pouvons pas à cette heure-là. Je peux vous proposer dix-neuf heures ou vingt et une heures.", TS.refus_complet_du_moteur)


async def test_deja_une_reservation_dans_cet_appel(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    essai.etat["derniere"] = (await creer(salle)).faits["numero"]
    r = await moteur.reserver(essai.source, essai.etat, essai.moteur_appelant, personnes=3)
    _verifie(r, "DEJA_FAIT", "Vous avez déjà une réservation dans cet appel : pour la changer, dites ce qui change.", TS.deja_une_reservation_dans_cet_appel)


async def test_aucune_reservation_a_venir_a_la_recherche_et_a_la_visee(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await moteur.retrouver_une_reservation(essai.source, essai.etat, essai.moteur_appelant, nom="Zoé")
    _verifie(r, "INTROUVABLE", "Je ne trouve pas de réservation à venir.", TS.aucune_reservation_a_venir)
    essai.etat["cible"] = "00000000-0000-0000-0000-000000000000"
    r = await moteur.annuler(essai.source, essai.etat, essai.moteur_appelant)
    _verifie(r, "INTROUVABLE", "Je ne trouve pas de réservation à venir.", TS.aucune_reservation_a_venir)


async def test_une_reservation_trouvee_dit_quand_et_pour_combien(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await creer(salle)
    r = await moteur.retrouver_une_reservation(essai.source, essai.etat, essai.moteur_appelant, nom="Alice")
    _verifie(r, "OK", "Vous avez une réservation samedi quatorze novembre à vingt heures pour deux personnes.", TS.une_reservation_trouvee)


async def test_plusieurs_reservations_le_choix_se_refait_des_candidats(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await creer(salle)
    await creer(salle, appel_id="deux", debut=RESA.SAMEDI_20H.replace(day=15, hour=19), couverts=3)
    r = await moteur.retrouver_une_reservation(essai.source, essai.etat, essai.moteur_appelant, nom="Alice")
    assert (r.statut, r.manque) == ("AMBIGU", "reservation"), r
    assert r.suggestion == "", r  # C7 (B7) : le texte se refait des candidats (« dit »), que la porte donne au modèle (candidats_dits)
    assert TS.plusieurs_a_choisir(r.faits) == "Vous en avez plusieurs : samedi quatorze novembre à vingt heures, pour deux personnes ou dimanche quinze novembre à dix-neuf heures, pour trois personnes. Laquelle ?"


async def test_deja_annulee_au_changement_et_a_l_annulation(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    numero = (await creer(salle)).faits["numero"]
    essai.etat["cible"] = numero
    essai.etat["annulees"] = [numero]
    r = await moteur.annuler(essai.source, essai.etat, essai.moteur_appelant)
    _verifie(r, "DEJA_FAIT", "Cette réservation est déjà annulée.", TS.deja_annulee)
    r = await moteur.modifier(essai.source, essai.etat, essai.moteur_appelant, personnes=4)
    _verifie(r, "DEJA_FAIT", "Cette réservation est déjà annulée.", TS.deja_annulee)


async def test_rien_ne_change_dit_la_reservation_qui_reste(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    essai.etat["cible"] = (await creer(salle)).faits["numero"]
    r = await moteur.modifier(essai.source, essai.etat, essai.moteur_appelant, personnes=2)
    _verifie(r, "DEJA_FAIT", "Rien ne change : votre réservation reste samedi quatorze novembre à vingt heures pour deux personnes.", TS.rien_ne_change)
    assert (r.faits["quand_dit"], r.faits["personnes"]) == ("samedi quatorze novembre à vingt heures", 2)
