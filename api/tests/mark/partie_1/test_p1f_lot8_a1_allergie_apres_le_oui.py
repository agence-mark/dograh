"""[.mark] Lot 8b-3, reprise R1 de l'audit (décision d'Evan du 24/11 17 h 45, ``lot-8-fiche-machee.md`` § 11 : « une allergie dite après le oui rouvre la commande ») :
l'allergie dite au TOUR SUIVANT, quand la commande est déjà enregistrée (ligne ``retenue``), retire l'accord ; le modèle reçoit les faits ; sans nouveau « oui » rien ne part ;
avec lui, c'est le même numéro et un seul envoi.

| Test | Ce qu'il prouve |
|---|---|
| sans nouveau oui | l'allergie notée rouvre la commande, les faits sont rendus au modèle, à la fin la ligne passe ``annulee`` et rien n'est envoyé (E3) |
| avec nouveau oui | le « oui » redonné réécrit la MÊME ligne (même numéro) : un seul envoi à la fin |
"""

from __future__ import annotations

from api.tests.mark.partie_1 import aides_de_la_commande as AC
from api.tests.mark.partie_1.aides_briques import brique


def _greffier_qui_note_l_allergie(e) -> None:
    async def rattraper(delai: float) -> bool:
        e.fiche_de_l_appel["allergie"] = "noix"
        return True

    e.ctx.rattraper = rattraper


async def _enregistree(essai_de):
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    await AC.refuser_la_proposition(e)
    await AC.jusqu_a_l_enregistrement(e, prenom="Léa", telephone="0612345678")
    return e, str(e.p["enregistree"]["numero"])


async def _lignes(e) -> list[tuple[str, str]]:
    return [(r["numero"], r["statut"]) for r in await e.monde.c.fetch("SELECT numero::text AS numero, statut FROM mark.resto_commande WHERE appel_id = $1", str(e.ctx.run_id))]


async def test_une_allergie_au_tour_suivant_rouvre_la_commande_et_sans_nouveau_oui_rien_ne_part(essai_de):
    """Modèle « C'est enregistré, numéro … » / Client « Ah, et mon fils est allergique aux noix. » / avant : la commande reste accordée, le gâteau aux noix part à la fin /
    après : l'accord est retiré, le modèle dit ce qui contient des noix ; sans nouveau « oui » la ligne est annulée à la fin et rien ne part."""
    e, numero = await _enregistree(essai_de)
    _greffier_qui_note_l_allergie(e)
    r = await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    assert not e.p.get("enregistree"), r  # l'accord est retiré
    faits = [x["faits"] for x in r["resultats"] if x["operation"] == "allergie"]  # le blocage d'allergie du métier : ses faits (ce qui en contient) sont dans le retour, le modèle les dit
    assert faits and faits[0]["allergie"] == "noix" and faits[0]["articles"][0]["etat"] == "present", r["resultats"]
    await e.finir_l_appel()
    assert e.source.prise.recues == [] and await _lignes(e) == [(numero, "annulee")], (e.source.prise.recues, await _lignes(e))


async def test_une_allergie_au_tour_suivant_puis_un_nouveau_oui_garde_le_meme_numero_et_un_seul_envoi(essai_de):
    e, numero = await _enregistree(essai_de)
    _greffier_qui_note_l_allergie(e)
    await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    await AC.jusqu_a_l_enregistrement(e, prenom="Léa", telephone="0612345678")  # la relecture repart, le « oui » est redonné
    assert str(e.p["enregistree"]["numero"]) == numero, e.p.get("enregistree")
    await e.finir_l_appel()
    assert [str(x["numero"]) for x in e.source.prise.recues] == [numero] and await _lignes(e) == [(numero, "acceptee")], (e.source.prise.recues, await _lignes(e))


async def _le_filet_sur_un_appel_note_termine(e) -> None:
    """Le filet du rattrapage (E11) joué sur l'appel de la partie, noté terminé, dont la ligne a plus d'une heure : tout ce qui est encore ``retenue`` part."""
    from api.db.bases_clients.restauration_commun import maintenant
    from api.services.restauration.appel_et_memoire.memoire_de_l_appel import (
        EtatDeLAppel,
    )
    from api.services.restauration.caisse import rattrapage
    from api.services.restauration.caisse.prises.prise import poser_prise_de_test

    await e.monde.c.execute("UPDATE mark.resto_commande SET maj_le = $2::timestamptz - interval '60 minutes' WHERE appel_id = $1", str(e.ctx.run_id), await maintenant(e.monde.c))  # l'heure de la base d'essai, pas celle du serveur
    await e.monde.c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test') ON CONFLICT (site_id) DO NOTHING", e.monde.a)

    async def etats_des_appels(cles: list[str]) -> dict[str, EtatDeLAppel]:
        return {c: EtatDeLAppel(termine=True, au_clavier=False) for c in cles if c == str(e.ctx.run_id)}

    poser_prise_de_test(e.source.prise)
    try:
        await rattrapage.rattrapage_des_envois(bases=[(7, e.monde.base)], etats_des_appels=etats_des_appels)
    finally:
        poser_prise_de_test(None)


async def test_r1_bis_une_allergie_au_tour_suivant_annule_la_ligne_au_tour_meme_le_filet_n_envoie_rien(essai_de):
    """Client « Oui, c'est bon. » / « Ah, et mon fils est allergique aux noix. » / le modèle dit que le gâteau contient des noix / l'appel plante (pas de fin d'appel) :
    avant, la ligne restait ``retenue`` et le filet envoyait le gâteau aux noix sans nouveau « oui » ; après, la ligne est ``annulee`` dès le tour de l'allergie, rien ne part."""
    e, numero = await _enregistree(essai_de)
    _greffier_qui_note_l_allergie(e)
    await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    assert await _lignes(e) == [(numero, "annulee")], await _lignes(e)  # au tour même, sans attendre la fin de l'appel
    await _le_filet_sur_un_appel_note_termine(e)
    assert e.source.prise.recues == [] and await _lignes(e) == [(numero, "annulee")], (e.source.prise.recues, await _lignes(e))


async def test_r1_bis_puis_un_nouveau_oui_rouvre_la_meme_ligne_et_un_seul_envoi_par_le_filet_ou_la_fin(essai_de):
    e, numero = await _enregistree(essai_de)
    _greffier_qui_note_l_allergie(e)
    await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    assert await _lignes(e) == [(numero, "annulee")]
    await AC.jusqu_a_l_enregistrement(e, prenom="Léa", telephone="0612345678")  # le nouveau « oui »
    assert str(e.p["enregistree"]["numero"]) == numero and await _lignes(e) == [(numero, "retenue")], await _lignes(e)
    await _le_filet_sur_un_appel_note_termine(e)  # l'appel plante après le nouveau « oui » : le filet envoie, une fois
    assert [str(x["numero"]) for x in e.source.prise.recues] == [numero] and await _lignes(e) == [(numero, "acceptee")], (e.source.prise.recues, await _lignes(e))


async def test_r1_bis_une_base_qui_leve_a_l_annulation_l_accord_est_retire_quand_meme_et_rien_ne_part(essai_de):
    """Panne de base à l'annulation de la ligne : l'exception est journalisée (jamais avalée), mais l'accord est retiré et le blocage d'allergie continue (le modèle reçoit les faits) ;
    à la fin de l'appel la commande n'est plus accordée : rien n'est envoyé."""
    e, numero = await _enregistree(essai_de)
    _greffier_qui_note_l_allergie(e)

    async def en_panne(numero_de_la_ligne):
        raise ConnectionError("base indisponible")

    e.source.annuler_une_commande = en_panne
    r = await e.tour("ah, et mon fils est allergique aux noix", note_generale="allergique aux noix")
    assert not e.p.get("enregistree"), r
    faits = [x["faits"] for x in r["resultats"] if x["operation"] == "allergie"]
    assert faits and faits[0]["allergie"] == "noix", r["resultats"]
    await e.finir_l_appel()
    assert e.source.prise.recues == [], e.source.prise.recues
