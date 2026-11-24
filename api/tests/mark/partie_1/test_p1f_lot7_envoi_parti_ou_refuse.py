"""[.mark] Lot 7b-A, ligne 87 : un message demandé qui ne part pas dit POURQUOI. ``DEJA_FAIT`` : il est déjà parti dans cet appel (la personne l'a reçu) ; ``REFUSEE`` : il ne peut
pas partir (pas de mobile, pas de compte, panne du fournisseur). Avant, les deux se confondaient (« c'est déjà parti, ou je ne peux pas l'envoyer à ce numéro »). Le statut est codé
et testé ici ; son branchement dans le chemin du fait bloquant vient après le préfixe (7b-B)."""

from __future__ import annotations

import pytest

from api.services.restauration.envois_et_sms import envois
from api.services.restauration.envois_et_sms import sms_restauration as sms_resto
from api.services.restauration.envois_et_sms.sms_restauration import Envoi

from .aides_briques import brique

MOBILE = "+33612345678"
FIXE = "+33344556677"


@pytest.fixture
def fournisseur(monkeypatch):
    """Le fournisseur est remplacé : jamais un tiers appelé. ``etat`` : ce que chaque test règle (compte, clé déjà prise, panne)."""
    etat = {"compte": ("sid", "jeton", "+33700000000"), "cle_libre": True, "panne": False, "envoyes": [], "rendues": []}

    async def identifiants(_org):
        return etat["compte"]

    async def une_seule_fois(_cle):
        libre, etat["cle_libre"] = etat["cle_libre"], False
        return libre

    async def oublier(cle):
        etat["rendues"].append(cle)

    async def envoyer(sid, jeton, expediteur, numero, texte):
        if etat["panne"]:
            raise sms_resto.sms.EchecTwilio("panne", True)
        etat["envoyes"].append(numero)

    monkeypatch.setattr(sms_resto, "identifiants_d_envoi", identifiants)
    monkeypatch.setattr(sms_resto, "une_seule_fois", une_seule_fois)
    monkeypatch.setattr(sms_resto, "oublier_une_fois", oublier)
    monkeypatch.setattr(sms_resto.sms, "envoyer", envoyer)
    return etat


async def _envoie(numero=MOBILE):
    return await sms_resto.envoyer_un_sms(7, numero, "Bonjour", {}, "cle")


async def test_un_message_parti_puis_redemande_est_deja_parti(fournisseur):
    assert await _envoie() is Envoi.PARTI and fournisseur["envoyes"] == [MOBILE]
    assert await _envoie() is Envoi.DEJA_FAIT and fournisseur["envoyes"] == [MOBILE]  # rien de plus n'est parti


async def test_un_message_qui_ne_peut_pas_partir_est_refuse_et_n_est_pas_deja_parti(fournisseur):
    assert await _envoie(FIXE) is Envoi.REFUSEE  # pas un mobile
    fournisseur["compte"] = None
    assert await _envoie() is Envoi.REFUSEE  # pas de compte
    fournisseur["compte"], fournisseur["panne"] = ("sid", "jeton", "+33700000000"), True
    assert await _envoie() is Envoi.PANNE and len(fournisseur["rendues"]) == 1  # panne du fournisseur (reprise 4a) : ni refus du numéro, ni déjà parti ; la clé est rendue
    assert not Envoi.REFUSEE and not Envoi.PANNE and not Envoi.DEJA_FAIT and Envoi.PARTI  # les appelants qui lisent « parti ? » ne changent pas


async def test_la_source_dit_parti_deja_parti_ou_refuse(essai_de, monkeypatch):
    """Client « Envoyez-moi la carte. » : OK ; le redemande : DEJA_FAIT ; un numéro qui ne reçoit pas : REFUSEE (et plus la même phrase pour les deux)."""
    e = await brique(essai_de, "INF4")
    await e.monde.c.execute("INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', 'carte', 'Notre carte', true)", e.monde.a)
    reponses = iter([Envoi.PARTI, Envoi.DEJA_FAIT, Envoi.REFUSEE])

    async def envoyer_un_sms(*_a, **_k):
        return next(reponses)

    monkeypatch.setattr(sms_resto, "envoyer_un_sms", envoyer_un_sms)
    r1, r2, r3 = [await e.source.envoyer("carte", MOBILE, "cle", 7) for _ in range(3)]
    assert (r1.statut, r2.statut, r3.statut) == ("OK", "DEJA_FAIT", "REFUSEE"), (r1, r2, r3)
    assert r2.faits == {"envoye": False, "deja_parti": True} and r3.faits == {"envoye": False, "deja_parti": False}, (r2, r3)
    assert r2.suggestion == r3.suggestion == "", (r2, r3)  # aucune phrase du code : le modèle dit la raison d'après les faits


async def test_envoyer_apres_garde_son_contrat_booleen(essai_de, monkeypatch):
    """Les autres appelants (commande enregistrée, réservation) lisent toujours « parti ou non » ; la raison se lit à côté."""
    e = await brique(essai_de, "INF4")
    await e.monde.c.execute("INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', 'carte', 'Notre carte', true)", e.monde.a)

    async def deja_parti(*_a, **_k):
        return Envoi.DEJA_FAIT

    monkeypatch.setattr(sms_resto, "envoyer_un_sms", deja_parti)
    assert await envois.envoyer_et_dire_pourquoi(e.monde.c, 7, e.monde.a, envois.CARTE, MOBILE, {}, "k") is Envoi.DEJA_FAIT
    assert await envois.envoyer_apres(e.monde.c, 7, e.monde.a, envois.CARTE, MOBILE, {}, "k") is False
