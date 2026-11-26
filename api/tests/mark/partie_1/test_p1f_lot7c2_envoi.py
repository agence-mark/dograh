"""[.mark] Lot 7b-C2, source de la commande : le message demandé qui ne part pas (éteint ou sans mobile : un seul texte, aucun fait à ajouter) et la question de la zone vient du catalogue des manques.

Le texte rendu est inchangé au caractère près et se refait des faits seuls (``textes_de_secours_commande``)."""

from __future__ import annotations

import pytest

from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.commande.phrases_du_manque import Manque, phrase_du_manque
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.envois_et_sms.sms_restauration import Envoi
from api.services.restauration.source_commande import SourceClasseur

MOBILE = "+33612345678"


@pytest.fixture
def source():
    return SourceClasseur(None, Lieu("base", 1, 1), nom_prise="test")


def _envoi_allume(monkeypatch, allume):
    async def envoi_actif(*_):
        return allume

    monkeypatch.setattr("api.services.restauration.source_commande.envois.liaison_db.envoi_actif", envoi_actif)


async def test_envoi_eteint_dit_qu_il_est_eteint(source, monkeypatch):
    _envoi_allume(monkeypatch, None)
    r = await source.envoyer("carte", MOBILE, "cle", 7)
    assert (r.statut, r.faits, r.suggestion) == ("INDISPONIBLE", {}, "")
    assert TSC.envoi_indisponible(r.faits) == "Je ne peux pas envoyer de message pour le moment."


async def test_envoi_sans_mobile_dit_qu_il_n_y_a_pas_de_mobile(source, monkeypatch):
    _envoi_allume(monkeypatch, object())
    r = await source.envoyer("carte", None, "cle", 7)
    assert (r.statut, r.faits, r.suggestion) == ("INDISPONIBLE", {}, "")
    assert TSC.envoi_indisponible(r.faits) == "Je ne peux pas envoyer de message pour le moment."


async def test_message_parti_dit_c_est_envoye(source, monkeypatch):
    _envoi_allume(monkeypatch, object())

    async def envoyer_et_dire_pourquoi(*_):
        return Envoi.PARTI

    monkeypatch.setattr("api.services.restauration.source_commande.envois.envoyer_et_dire_pourquoi", envoyer_et_dire_pourquoi)
    r = await source.envoyer("carte", MOBILE, "cle", 7)
    assert (r.statut, r.faits, r.suggestion) == ("OK", {"envoye": True}, "")
    assert TSC.envoye(r.faits) == "C'est envoyé."


@pytest.mark.parametrize("envoi, statut, faits", [
    (Envoi.PANNE, "INDISPONIBLE", {"envoye": False, "panne": True}),
    (Envoi.DEJA_FAIT, "DEJA_FAIT", {"envoye": False, "deja_parti": True}),
    (Envoi.REFUSEE, "REFUSEE", {"envoye": False, "deja_parti": False}),
])
async def test_les_autres_refus_de_l_envoi_ne_bougent_pas(source, monkeypatch, envoi, statut, faits):
    """Voisins : la panne, le déjà-parti et le refus n'ont aucune phrase (le modèle dit), avant comme après."""
    _envoi_allume(monkeypatch, object())

    async def envoyer_et_dire_pourquoi(*_):
        return envoi

    monkeypatch.setattr("api.services.restauration.source_commande.envois.envoyer_et_dire_pourquoi", envoyer_et_dire_pourquoi)
    r = await source.envoyer("carte", MOBILE, "cle", 7)
    assert (r.statut, r.faits, r.suggestion) == (statut, faits, "")


def test_la_question_de_la_zone_n_est_plus_dans_la_source():
    """C7 B5 (Evan 25/11 8 h 45) : la source ne garde plus la question de la zone ; le manque (``zone``, ``adresse``) la porte, le modèle la pose ; le catalogue du manque reste jusqu'à B9."""
    assert not hasattr(SourceClasseur, "question_de_la_zone") and phrase_du_manque(Manque.ADRESSE_ET_COMMUNE) == "Quelle est l'adresse de livraison ?"
