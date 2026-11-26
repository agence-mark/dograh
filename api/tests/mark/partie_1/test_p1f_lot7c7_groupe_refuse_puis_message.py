"""[.mark] Lot 7b-C7, B11 (refus 16 : « une promesse a son action ») : de bout en bout, un groupe trop grand refusé, le client dit oui à l'offre du message, la réservation rend la main
(``rendre_la_main``), l'appel passe à l'étape du service, qui laisse le message : la demande de rappel est écrite dans la fiche de l'appel, rien n'est réservé."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.apres_appel.rappels import CLE_RAPPEL
from api.services.groupe import passations as PASSATIONS
from api.services.reservation.lire import A_FAIRE_DU_GROUPE
from api.services.service_client import action as service
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_reservation as _RESA
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.partie_1.test_l07_reservation import MOTS

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle

ACCUEIL, RESERVATION, SERVICE = 299, 301, 302


def _passer(fiche, de, vers, raison):
    """Une passation du code : refusée ou non, puis tracée comme le moteur le fait."""
    assert PASSATIONS.refus_de_passation(fiche, {}, de=de, vers=vers, raison=raison) is None, f"la passation {de} vers {vers} est refusée"
    PASSATIONS.tracer_passation(fiche, de=de, vers=vers, raison=raison, refusee=False, issue="completed")


async def test_un_groupe_refuse_le_oui_au_message_rend_la_main_et_le_service_laisse_le_message(salle, monkeypatch):
    """Client « On sera vingt-cinq. » / la réservation refuse et le modèle offre le message (``a_faire``) / Client « Oui. » / la main passe au service / le message part pour de bon."""
    essai = EssaiReservation(salle, monkeypatch)
    refus = await essai.tour(MOTS, personnes=25, jour="samedi", heure="vingt heures", nom="Alice")
    assert refus["raison"] == "groupe_trop_grand" and refus["a_faire"] == A_FAIRE_DU_GROUPE and "message" in refus["a_faire"], refus
    assert await essai.nombre_de_reservations() == 0

    fiche = essai.fiche_de_l_appel
    essai.dit("oui, laissez un message")
    _passer(fiche, RESERVATION, ACCUEIL, PASSATIONS.RAISON_RETOUR)               # rendre_la_main : la réservation rend l'appel
    _passer(fiche, ACCUEIL, SERVICE, "passer_a_l_agent_service")                 # l'accueil confie la personne au service
    ctx = SimpleNamespace(fiche=fiche, appel={"caller_number": "+33612345678"}, reglages={}, organization_id=None, run_id=None)
    laisse = await service.laisser_un_message({"objet": "groupe de vingt-cinq samedi à vingt heures", "prenom": "Alice", "nom": "Martin"}, ctx)

    assert laisse["statut"] == "OK", laisse
    demandes = fiche[CLE_RAPPEL]
    assert len(demandes) == 1 and demandes[0]["objet"] == "groupe de vingt-cinq samedi à vingt heures" and demandes[0]["mode"] == "rappel", demandes
    assert await essai.nombre_de_reservations() == 0, "rien n'a été réservé"
    assert [p["vers"] for p in PASSATIONS.passations_de(fiche)] == [ACCUEIL, SERVICE]
