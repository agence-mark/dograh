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
