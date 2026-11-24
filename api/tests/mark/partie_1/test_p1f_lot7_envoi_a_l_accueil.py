"""Lot 7b-A, reprise de l'audit (ligne 87, fiche 7b) : « une margherita, et envoyez-moi la carte par SMS ».

``_outil_de_l_accueil`` passait le statut brut du module (``INDISPONIBLE``, ``DEJA_FAIT``, ``REFUSEE``) à l'``Enveloppe``, qui le refusait : l'erreur partait dans la
branche de panne, le client entendait « je n'arrive pas à faire cela » et l'équipe recevait un rappel avec la commande en cours. Désormais le modèle reçoit un
``REJETEE`` avec une raison rangée, les faits (``deja_parti``, ``panne``) et rien n'est envoyé à l'équipe.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.apres_appel.rappels import CLE_RAPPEL
from api.services.commande import porte
from api.services.restauration.envois_et_sms import sms_restauration as sms_resto
from api.services.restauration.envois_et_sms.sms_restauration import Envoi

from .aides_briques import brique

MOBILE = "+33612345678"


async def _commande_et_envoi(essai_de, monkeypatch, envoi_allume: bool, reponse: Envoi | None):
    e = await brique(essai_de, "INF4")
    await e.tour("une margherita", ajouter=[{"article": "Sandwich poulet", "quantite": 1}])
    if envoi_allume:
        await e.monde.c.execute("INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', 'carte', 'Notre carte', true)", e.monde.a)
    e.ctx.appel = {**(e.ctx.appel or {}), "caller_number": MOBILE}
    e.ctx.organization_id = 7

    async def envoyer_un_sms(*_a, **_k):
        return reponse

    monkeypatch.setattr(sms_resto, "envoyer_un_sms", envoyer_un_sms)
    r = await porte.executer(SimpleNamespace(nom="envoyer_un_sms"), {"quoi": "carte"}, e.ctx, 5.0)
    return e, r


@pytest.mark.parametrize(
    "allume, reponse, raison, faits",
    [
        (False, None, "envoi_indisponible", {}),  # éteint : le réglage par défaut
        (True, Envoi.DEJA_FAIT, "deja_fait", {"envoye": False, "deja_parti": True}),
        (True, Envoi.REFUSEE, "envoi_impossible", {"envoye": False, "deja_parti": False}),
        (True, Envoi.PANNE, "envoi_indisponible", {"envoye": False, "panne": True}),  # le fournisseur est en panne : pas « ce numéro ne peut pas le recevoir »
    ],
    ids=["eteint", "deja_parti", "refuse", "panne_du_fournisseur"],
)
async def test_un_envoi_qui_n_aboutit_pas_est_dit_au_modele_sans_rien_dire_a_l_equipe(essai_de, monkeypatch, allume, reponse, raison, faits):
    e, r = await _commande_et_envoi(essai_de, monkeypatch, allume, reponse)
    assert r["statut"] == "REJETEE" and r["raison"] == raison, r
    assert r["faits"] == faits, r
    assert not (e.ctx.fiche or {}).get(CLE_RAPPEL), "la commande en cours n'est pas jointe au message de l'équipe"
    assert "indisponible" not in r["faits"] and "transmise_a_l_equipe" not in r["faits"], r  # pas la branche de panne
    assert len(e.p["lignes"]) == 1  # la commande continue


async def test_un_envoi_parti_reste_lu(essai_de, monkeypatch):
    e, r = await _commande_et_envoi(essai_de, monkeypatch, True, Envoi.PARTI)
    assert r["statut"] == "LU" and r["faits"] == {"envoye": True}, r
