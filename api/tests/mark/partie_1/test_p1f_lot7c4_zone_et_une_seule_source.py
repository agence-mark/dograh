"""[.mark] Lot 7b-C4, commit 1 : les refus de la zone de livraison (``restauration_zone``) ne portent plus de texte (C7a) ; C7 B9 : le catalogue de secours de la base est supprimé
(avec le test « une seule source », sans objet), ce que disait chaque texte d'avant est vérifié dans le statut, le manque et les faits. Rien ne change à l'oreille."""

from __future__ import annotations

from api.db.bases_clients import restauration_zone as Z
from api.tests.mark import test_base_client as BASE
from api.tests.mark import test_restauration_classeur_commande as CLASSEUR
from api.tests.mark import test_restauration_zones as ZONES

# Les fixtures du classeur, reprises par affectation (jamais d'import qui ne sert qu'à les enregistrer).
base_essai, base_prete, commerce = BASE.base_essai, BASE.base_prete, CLASSEUR.commerce


async def _zones_de_senlis(commerce):
    """Deux zones autour de Senlis : Chantilly nommée, et un rayon de huit kilomètres."""
    c, a = commerce.c, commerce.a
    await c.execute("UPDATE mark.site SET adresse_insee = $2 WHERE id = $1", a, ZONES.SENLIS)
    await c.execute("DELETE FROM mark.resto_zone WHERE site_id = $1", a)
    for nom, forme, communes, rayon, ordre in (("Chantilly", "communes", [ZONES.CHANTILLY], None, 0), ("Centre", "rayon", [], 8, 1)):
        await c.execute("INSERT INTO mark.resto_zone (site_id, nom, forme, communes, rayon_km, exclues, frais, delai, ordre) VALUES ($1,$2,$3,$4,$5,$6,200,30,$7)", a, nom, forme, communes, rayon, [], ordre)


def _verifie(r, statut: str, manque: str | None = None):
    """Un texte vidé (C7a) : le retour n'en porte plus ; B9 : ce qu'il disait est dans le statut, le manque et les faits."""
    assert (r.statut, r.manque, r.suggestion) == (statut, manque, ""), r


async def test_une_commune_hors_zone_se_dit_avec_les_communes_livrees(commerce):
    await _zones_de_senlis(commerce)
    r = await Z.verifier_adresse(commerce.c, commerce.a, "7 rue Victor Hugo, Compiègne")
    _verifie(r, "HORS_ZONE")
    assert r.faits["commune"]["nom"] == "Compiègne" and "Chantilly" in r.faits["communes_livrees"], r  # « Nous ne livrons pas à Compiègne. Nous livrons … »


async def test_sans_aucune_zone_l_adresse_est_hors_zone(commerce):
    await commerce.c.execute("DELETE FROM mark.resto_zone WHERE site_id = $1", commerce.a)
    r = await Z.verifier_adresse(commerce.c, commerce.a, "7 rue Victor Hugo, Compiègne")
    _verifie(r, "HORS_ZONE")
    assert r.faits == {"raison": "aucune_zone"}  # « Nous ne livrons pas à cette adresse. » : aucune commune dite


async def test_une_adresse_vide_ou_sans_commune_ou_ambigue(commerce):
    await _zones_de_senlis(commerce)
    r = await Z.verifier_adresse(commerce.c, commerce.a, "  ")
    _verifie(r, "ARGUMENT_INVALIDE", "adresse")  # « Je n'ai pas compris l'adresse »
    assert r.faits == {}, r
    r = await Z.verifier_adresse(commerce.c, commerce.a, "rue de Paris")
    _verifie(r, "INTROUVABLE", "commune")  # « Dans quelle commune se trouve l'adresse ? »
    assert r.faits == {}, r
    r = await Z.verifier_adresse(commerce.c, commerce.a, "5 rue de la Mairie, Saint-Just")
    _verifie(r, "AMBIGU", "commune")  # C7 B3 : le modèle pose la question (Evan 25/11 8 h 45) ; « Est-ce Saint-Just (Ain) ou … ? » se lit dans les candidats
    candidats = r.faits["candidats"]
    assert len(candidats) >= 2 and {c["nom"] for c in candidats} == {"Saint-Just"} and candidats[0]["departement"] == "Ain", r
