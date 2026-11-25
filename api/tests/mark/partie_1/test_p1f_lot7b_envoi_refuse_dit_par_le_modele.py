"""[.mark] Lot 7b-B, branchement de la ligne 87 : un message demandé qui ne part pas (REFUSEE, déjà parti) entre dans le chemin du fait bloquant : le modèle dit la raison d'après les
faits, le code ne dit rien d'avance et la commande ne bouge pas (R1).

Client « Envoyez-moi la carte. » (ligne fixe). Avant : « C'est déjà parti, ou je ne peux pas l'envoyer à ce numéro » (les deux raisons confondues). Après : le modèle reçoit
``envoye: false, deja_parti: false`` et dit qu'il ne peut pas envoyer à ce numéro ; deuxième demande sur un portable : ``deja_parti: true``, il dit qu'il l'a déjà envoyée.
"""

from __future__ import annotations

import pytest

from api.services.actions_communes import parole as PAROLE
from api.services.restauration.envois_et_sms.sms_restauration import Envoi
from api.services.workflow import parole_de_la_fiche as PF

from .aides_briques import commande_et_envoi as _commande_et_envoi


@pytest.mark.parametrize("reponse, faits", [(Envoi.REFUSEE, {"envoye": False, "deja_parti": False}), (Envoi.DEJA_FAIT, {"envoye": False, "deja_parti": True})], ids=["refuse", "deja_parti"])
async def test_l_envoi_refuse_est_dit_par_le_modele_d_apres_les_faits(essai_de, monkeypatch, reponse, faits):
    e, r = await _commande_et_envoi(essai_de, monkeypatch, True, reponse)
    assert r["faits"] == faits and r["raison"] in ("envoi_impossible", "deja_fait"), r  # la raison et les faits que le modèle reçoit, rien de plus
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Je ne peux pas vous l'envoyer."})
    assert d.mode != PAROLE.A_DIRE_SEUL and not d.a_dire, d  # la parole est au modèle, le code ne dit rien


async def test_r1_l_envoi_refuse_ne_change_pas_la_commande(essai_de, monkeypatch):
    e, _ = await _commande_et_envoi(essai_de, monkeypatch, True, Envoi.PARTI)
    avant = [dict(l) for l in e.p["lignes"]]
    e2, r = await _commande_et_envoi(essai_de, monkeypatch, True, Envoi.REFUSEE)
    assert [l["nom"] for l in e2.p["lignes"]] == [l["nom"] for l in avant] and r["statut"] == "REJETEE", r  # le verdict « la commande a-t-elle changé ? » ne bouge pas
