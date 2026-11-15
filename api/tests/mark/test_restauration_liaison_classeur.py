"""[.mark] Module Restauration, lot 9, étape 2 : la couche d'accès de la liaison à la caisse (``restauration_liaison``), sur une vraie base.

| Test | Ce qu'il prouve |
|---|---|
| liaison | posée, relue ; l'état ne change qu'avec un code de la liste fermée ; ``marquer_la_liaison`` dit si l'état a CHANGÉ |
| accès | seule la référence du jeton est gardée ; jamais lisible par le rôle du portail |
| état de la caisse | écrit, relu avec sa source « caisse » ; ``True`` seulement si quelque chose change ; retiré = le portail fait foi |
| anti-doublon | un message déjà vu n'est pas nouveau ; un traitement échoué est oublié pour la nouvelle tentative |
| commande | ``ref_fournisseur`` écrit pour CET établissement seulement ; jamais écrasé par du vide |
| tickets | un ticket par commande ; l'imprimante n'est connue que par l'empreinte de son jeton |
| cloisonnement | le numéro d'un autre établissement ne crée pas de ticket et ne reçoit pas de ref |
"""

from __future__ import annotations

import pytest

from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as lia
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce  # noqa: F401


async def test_la_liaison_se_pose_et_dit_si_l_etat_change(commerce):
    c, a = commerce.c, commerce.a
    assert await lia.liaison(c, a) is None
    await lia.poser_liaison(c, a, "hubrise", "w8xvp-0", "ok")
    assert (await lia.liaison(c, a))["point_de_vente"] == "w8xvp-0"
    assert await lia.marquer_la_liaison(c, a, "ok") is False
    assert await lia.marquer_la_liaison(c, a, "rompue", "jeton_refuse") is True
    assert (await lia.liaison(c, a))["derniere_erreur"] == "jeton_refuse"
    with pytest.raises(ValueError):
        await lia.marquer_la_liaison(c, a, "erreur", "Le serveur HubRise a dit : boom")  # jamais un texte de fournisseur
    assert await lia.marquer_la_liaison(c, commerce.b, "ok") is False  # pas de liaison chez B : rien


async def test_l_acces_ne_garde_que_la_reference_et_le_portail_ne_le_lit_pas(commerce):
    c, a = commerce.c, commerce.a
    await lia.poser_liaison(c, a, "hubrise", "w8xvp-0", "ok")
    await lia.poser_acces(c, a, "uuid-du-coffre")
    assert await lia.acces(c, a) == "uuid-du-coffre" and await lia.acces(c, commerce.b) is None
    colonnes = {r["column_name"] for r in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'resto_liaison_acces'")}
    assert colonnes == {"site_id", "credential_uuid", "maj_le"}  # aucun champ de jeton


async def test_l_etat_de_la_caisse_s_ecrit_et_dit_s_il_a_change(commerce):
    c, a = commerce.c, commerce.a
    etat = {"mode": "deborde", "minutes_en_plus": 15, "reprise": None, "temps_preparation": 20}
    assert await lia.poser_etat_de_la_caisse(c, a, etat) is True
    lu = await restauration.etat_caisse(c, a)
    assert (lu["mode"], lu["minutes_en_plus"], lu["temps_preparation"], lu["source"]) == ("deborde", 15, 20, "caisse")
    assert await lia.poser_etat_de_la_caisse(c, a, etat) is False
    assert await restauration.etat_caisse(c, commerce.b) is None
    with pytest.raises(ValueError):
        await lia.poser_etat_de_la_caisse(c, a, {"mode": "ferme"})
    await lia.retirer_l_etat_de_la_caisse(c, a)
    assert await restauration.etat_caisse(c, a) is None


async def test_un_message_deja_vu_n_est_pas_nouveau_et_un_echec_est_oublie(commerce):
    c, a = commerce.c, commerce.a
    assert await lia.noter_le_message(c, "hubrise", "ev-1", a, "order.update") is True
    assert await lia.noter_le_message(c, "hubrise", "ev-1", a, "order.update") is False
    await lia.marquer_le_message_traite(c, "hubrise", "ev-1")
    await lia.oublier_le_message(c, "hubrise", "ev-1")  # déjà traité : jamais oublié
    assert await lia.noter_le_message(c, "hubrise", "ev-1", a, None) is False
    assert await lia.noter_le_message(c, "hubrise", "ev-2", None, None) is True  # point de vente inconnu : noté quand même
    await lia.oublier_le_message(c, "hubrise", "ev-2")
    assert await lia.noter_le_message(c, "hubrise", "ev-2", None, None) is True


async def test_la_ref_fournisseur_est_ecrite_pour_cet_etablissement_seulement(commerce):
    c, a, b = commerce.c, commerce.a, commerce.b
    r = await restauration.enregistrer_commande(c, a, brouillon(), "relu")
    numero = r.faits["numero"]
    assert await lia.poser_ref_fournisseur(c, b, numero, "8qknnxn") is False  # un autre établissement : rien
    assert await lia.poser_ref_fournisseur(c, a, numero, "8qknnxn") is True
    assert await lia.poser_ref_fournisseur(c, a, numero, "8qknnxn") is False
    assert await lia.poser_ref_fournisseur(c, a, numero, None) is False  # jamais écrasé par du vide
    assert await lia.commande_par_ref_fournisseur(c, a, "8qknnxn") == numero
    assert await lia.commande_par_ref_fournisseur(c, b, "8qknnxn") is None


async def test_un_ticket_par_commande_et_l_imprimante_n_est_connue_que_par_l_empreinte(commerce):
    c, a, b = commerce.c, commerce.a, commerce.b
    numero = (await restauration.enregistrer_commande(c, a, brouillon(), "relu")).faits["numero"]
    assert await lia.creer_le_ticket(c, b, numero) is False  # pas une commande de B
    assert await lia.creer_le_ticket(c, a, numero) is True
    assert await lia.creer_le_ticket(c, a, numero) is False  # jamais deux tickets
    await lia.poser_imprimante(c, a, "jeton-secret-de-l-imprimante")
    stocke = await c.fetchval("SELECT jeton_empreinte FROM mark.resto_imprimante WHERE site_id = $1", a)
    assert "secret" not in stocke and stocke == lia.empreinte("jeton-secret-de-l-imprimante")
    assert (await lia.imprimante_par_jeton(c, "jeton-secret-de-l-imprimante"))["site_id"] == a
    assert await lia.imprimante_par_jeton(c, "autre") is None
