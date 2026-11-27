"""[.mark] Lot 8b-3, T35 (Pierre, 27/11 : fermé dans le lot 8) : le filet du rattrapage (E11) relit l'accord avant d'envoyer une ligne ``retenue``.

Double panne : une allergie dite après le « oui » retire l'accord, la base lève à l'annulation de la ligne (elle reste ``retenue``), PUIS l'appel plante : le filet ne doit pas
envoyer la ligne sans nouveau « oui ». Il la passe à ``annulee`` et alerte le restaurant une fois (l'alerte du filet) ; le nouveau « oui » la rouvre sous le même numéro.

| Test | Ce qu'il prouve |
|---|---|
| annulation qui lève, appel planté | rien reçu par la caisse, ligne ``annulee``, une seule alerte au restaurant, rejoué : rien de plus |
| témoin : accord jamais retiré | l'appel planté après le « oui » : le filet envoie comme avant, sans alerte |
| annulation qui lève, nouveau « oui » | la même ligne est rouverte (même numéro), le filet l'envoie une fois, sans alerte |
"""

from __future__ import annotations

from api.db.bases_clients import restauration
from api.tests.mark.partie_1 import aides_de_la_commande as AC
from api.tests.mark.partie_1.test_p1f_lot8_a1_allergie_apres_le_oui import (
    _enregistree,
    _greffier_qui_note_l_allergie,
    _lignes,
)


async def _le_filet(e, alertes: list) -> None:
    """Le filet joué sur l'appel de la partie, noté terminé, dont la ligne a plus d'une heure ; les alertes au restaurant sont recueillies."""
    from api.db.bases_clients.restauration_commun import maintenant
    from api.services.restauration.appel_et_memoire.memoire_de_l_appel import EtatDeLAppel
    from api.services.restauration.caisse import rattrapage
    from api.services.restauration.caisse.prises.prise import poser_prise_de_test

    await e.monde.c.execute("UPDATE mark.resto_commande SET maj_le = $2::timestamptz - interval '60 minutes' WHERE appel_id = $1", str(e.ctx.run_id), await maintenant(e.monde.c))
    await e.monde.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test') ON CONFLICT (site_id) DO NOTHING", e.monde.a)

    async def etats_des_appels(cles: list[str]) -> dict[str, EtatDeLAppel]:
        return {c: EtatDeLAppel(termine=True, au_clavier=False) for c in cles if c == str(e.ctx.run_id)}

    async def secours(_organisation, sujet, texte):
        alertes.append((sujet, texte))

    poser_prise_de_test(e.source.prise)
    try:
        await rattrapage.rattrapage_des_envois(bases=[(7, e.monde.base)], etats_des_appels=etats_des_appels, secours=secours)
    finally:
        poser_prise_de_test(None)


async def _allergie_avec_une_base_qui_leve(e, monkeypatch) -> None:
    """« Ah, et mon fils est allergique aux noix. » pendant que la base lève au changement de statut (l'annulation de la ligne) ; la base revient ensuite."""
    original = restauration.changer_statut

    async def en_panne(*args, **kwargs):
        raise ConnectionError("base indisponible")

    _greffier_qui_note_l_allergie(e)
    monkeypatch.setattr(restauration, "changer_statut", en_panne)
    try:
        await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    finally:
        monkeypatch.setattr(restauration, "changer_statut", original)
    assert not e.p.get("enregistree")  # l'accord est retiré (R1-bis)


async def test_t35_l_annulation_leve_puis_l_appel_plante_le_filet_n_envoie_rien_et_alerte_une_fois(essai_de, monkeypatch):
    """Client « Oui, c'est bon. » / « Ah, et mon fils est allergique aux noix. » / la base tombe pendant la mise de côté / l'appel coupe : avant, le filet envoyait le gâteau
    aux noix sans nouveau « oui » ; après, rien ne part, la ligne est annulée et le restaurant est prévenu une fois."""
    e, numero = await _enregistree(essai_de)
    await _allergie_avec_une_base_qui_leve(e, monkeypatch)
    assert await _lignes(e) == [(numero, "retenue")], await _lignes(e)  # la panne a laissé la ligne : c'est le cas du filet
    alertes: list = []
    await _le_filet(e, alertes)
    assert e.source.prise.recues == [] and await _lignes(e) == [(numero, "annulee")], (e.source.prise.recues, await _lignes(e))
    assert len(alertes) == 1, alertes
    await _le_filet(e, alertes)  # rejoué : rien de plus
    assert e.source.prise.recues == [] and len(alertes) == 1, (e.source.prise.recues, alertes)


async def test_t35_temoin_l_accord_jamais_retire_le_filet_envoie_comme_avant(essai_de):
    e, numero = await _enregistree(essai_de)
    alertes: list = []
    await _le_filet(e, alertes)
    assert [str(x["numero"]) for x in e.source.prise.recues] == [numero] and await _lignes(e) == [(numero, "acceptee")], (e.source.prise.recues, await _lignes(e))
    assert alertes == [], alertes


async def test_t35_un_nouveau_oui_apres_la_panne_rouvre_la_meme_ligne_et_le_filet_l_envoie_une_fois(essai_de, monkeypatch):
    e, numero = await _enregistree(essai_de)
    await _allergie_avec_une_base_qui_leve(e, monkeypatch)
    await AC.jusqu_a_l_enregistrement(e, prenom="Léa", telephone="0612345678")  # la relecture repart, le « oui » est redonné
    assert str(e.p["enregistree"]["numero"]) == numero, e.p.get("enregistree")
    alertes: list = []
    await _le_filet(e, alertes)
    assert [str(x["numero"]) for x in e.source.prise.recues] == [numero] and await _lignes(e) == [(numero, "acceptee")], (e.source.prise.recues, await _lignes(e))
    assert alertes == [], alertes


async def test_t35_r_a_le_client_annule_la_base_tombe_l_appel_plante_l_alerte_ne_parle_pas_d_allergie(essai_de, monkeypatch):
    """Client « Annulez ma commande. » / « Oui. » / la base tombe pendant l'annulation / l'appel coupe : le filet n'envoie rien (la marque est posée aussi par ce chemin) et le restaurant
    lit une raison vraie : avant, le texte de l'alerte parlait d'allergie ; après, il dit seulement que l'accord a été retiré (allergie ou annulation)."""
    from api.services.actions_communes import conversation as CONV

    e, numero = await _enregistree(essai_de)
    await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)
    original = restauration.changer_statut

    async def en_panne(*args, **kwargs):
        raise ConnectionError("base indisponible")

    monkeypatch.setattr(restauration, "changer_statut", en_panne)
    try:
        await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    except ConnectionError:  # le tour peut lever : seule compte la ligne laissée ``retenue``
        pass
    finally:
        monkeypatch.setattr(restauration, "changer_statut", original)
    assert await _lignes(e) == [(numero, "retenue")], await _lignes(e)
    alertes: list = []
    await _le_filet(e, alertes)
    assert e.source.prise.recues == [] and await _lignes(e) == [(numero, "annulee")], (e.source.prise.recues, await _lignes(e))
    assert len(alertes) == 1 and "annulation" in alertes[0][1] + alertes[0][0], alertes


async def test_t35_retente_la_base_tombe_au_tour_de_l_allergie_revient_au_suivant_la_ligne_est_marquee_et_annulee(essai_de, monkeypatch):
    """Coupure courte : la base tombe au tour de l'allergie (ni marque ni annulation), revient au tour suivant : le code retente tout seul, la ligne est marquée puis ``annulee`` ; si
    l'appel plante ensuite, le filet n'envoie rien et n'alerte pas (la ligne n'est plus ``retenue``). Le code ne dit rien de plus au client."""
    from api.db.bases_clients import restauration_liaison as liaison_db

    e, numero = await _enregistree(essai_de)
    original_statut, original_marque = restauration.changer_statut, liaison_db.marquer_l_accord_retire

    async def en_panne(*args, **kwargs):
        raise ConnectionError("base indisponible")

    _greffier_qui_note_l_allergie(e)
    monkeypatch.setattr(restauration, "changer_statut", en_panne)
    monkeypatch.setattr(liaison_db, "marquer_l_accord_retire", en_panne)
    try:
        await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    finally:
        monkeypatch.setattr(restauration, "changer_statut", original_statut)
        monkeypatch.setattr(liaison_db, "marquer_l_accord_retire", original_marque)
    assert await _lignes(e) == [(numero, "retenue")], await _lignes(e)  # la coupure : rien n'a pu être fait
    await e.tour("hum, je réfléchis")  # le tour suivant, la base est revenue
    assert await _lignes(e) == [(numero, "annulee")], await _lignes(e)
    alertes: list = []
    await _le_filet(e, alertes)
    assert e.source.prise.recues == [] and await _lignes(e) == [(numero, "annulee")] and alertes == [], (e.source.prise.recues, await _lignes(e), alertes)


async def test_t35_r1_la_retente_survit_a_une_annulation_du_panier_et_le_filet_n_envoie_rien(essai_de, monkeypatch):
    """« Oui, c'est bon. » / « Ah, et mon fils est allergique aux noix. » (base en panne : ni marque ni annulation) / « Bon, laissez tomber, j'annule. » (base revenue) / l'appel plante :
    avant, la retente s'arrêtait sur l'étape « annulée » (qui ne touche pas la ligne) et le filet envoyait le gâteau ; après, la ligne est annulée en base, rien n'est reçu."""
    from api.db.bases_clients import restauration_liaison as liaison_db

    e, numero = await _enregistree(essai_de)
    original_statut, original_marque = restauration.changer_statut, liaison_db.marquer_l_accord_retire

    async def en_panne(*args, **kwargs):
        raise ConnectionError("base indisponible")

    _greffier_qui_note_l_allergie(e)
    monkeypatch.setattr(restauration, "changer_statut", en_panne)
    monkeypatch.setattr(liaison_db, "marquer_l_accord_retire", en_panne)
    try:
        await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    finally:
        monkeypatch.setattr(restauration, "changer_statut", original_statut)
        monkeypatch.setattr(liaison_db, "marquer_l_accord_retire", original_marque)
    assert await _lignes(e) == [(numero, "retenue")], await _lignes(e)
    await e.tour("bon, laissez tomber, j'annule", annuler_la_commande=True)
    alertes: list = []
    await _le_filet(e, alertes)
    assert e.source.prise.recues == [] and await _lignes(e) == [(numero, "annulee")], (e.source.prise.recues, await _lignes(e))
