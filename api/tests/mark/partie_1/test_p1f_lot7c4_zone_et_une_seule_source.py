"""[.mark] Lot 7b-C4, commit 1 : les textes de la zone de livraison (``restauration_zone``) sont des textes de secours de la base, lus par le repli seul (R = A), et un texte de secours
n'a qu'une source : le catalogue de la base ne recopie aucune phrase du catalogue de la commande. Rien ne change à l'oreille : le texte rendu est celui d'avant, au caractère près."""

from __future__ import annotations

import ast

from api.db.bases_clients import restauration_zone as Z
from api.db.bases_clients import textes_de_secours_commande as TSC
from api.outils import inventaire_rustines as I
from api.services.commande import textes_de_secours as TS
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


def _verifie(r, statut: str, secours, manque: str | None = None, *, vide: bool = True):
    """Un texte vidé (C7a) : le retour n'en porte plus ; la fonction de secours refait le texte d'avant des seuls faits. Un texte de question : le retour le porte encore."""
    assert (r.statut, r.manque) == (statut, manque), r
    assert r.suggestion == ("" if vide else secours(r.faits)), r
    return secours(r.faits)


async def test_une_commune_hors_zone_se_dit_avec_les_communes_livrees(commerce):
    await _zones_de_senlis(commerce)
    r = await Z.verifier_adresse(commerce.c, commerce.a, "7 rue Victor Hugo, Compiègne")
    texte = _verifie(r, "HORS_ZONE", TSC.hors_zone)
    assert texte.startswith("Nous ne livrons pas à Compiègne. Nous livrons ") and r.faits["communes_livrees"], r


async def test_sans_aucune_zone_l_adresse_est_hors_zone(commerce):
    await commerce.c.execute("DELETE FROM mark.resto_zone WHERE site_id = $1", commerce.a)
    r = await Z.verifier_adresse(commerce.c, commerce.a, "7 rue Victor Hugo, Compiègne")
    texte = _verifie(r, "HORS_ZONE", TSC.hors_zone)
    assert texte == "Nous ne livrons pas à cette adresse." and r.faits == {"raison": "aucune_zone"}


async def test_une_adresse_vide_ou_sans_commune_ou_ambigue(commerce):
    await _zones_de_senlis(commerce)
    r = await Z.verifier_adresse(commerce.c, commerce.a, "  ")
    texte = _verifie(r, "ARGUMENT_INVALIDE", TSC.adresse_non_comprise, "adresse")
    assert texte == "Je n'ai pas compris l'adresse, pouvez-vous la répéter ?"
    r = await Z.verifier_adresse(commerce.c, commerce.a, "rue de Paris")
    texte = _verifie(r, "INTROUVABLE", TSC.quelle_commune, "commune")
    assert texte == "Dans quelle commune se trouve l'adresse ?"
    r = await Z.verifier_adresse(commerce.c, commerce.a, "5 rue de la Mairie, Saint-Just")
    _verifie(r, "AMBIGU", TSC.commune_ambigue, "commune", vide=False)
    assert r.suggestion.startswith("Est-ce Saint-Just (") and " ou Saint-Just (" in r.suggestion and r.suggestion.endswith(") ?"), r.suggestion


def _phrases(module) -> set[str]:
    """Les phrases (douze lettres et plus) que renvoient les fonctions d'un catalogue de secours."""
    arbre = ast.parse(I.RACINE_API.joinpath(*module.__name__.split(".")[1:]).with_suffix(".py").read_text(encoding="utf-8"))
    return {n.value for f in ast.walk(arbre) if isinstance(f, ast.FunctionDef) for n in ast.walk(f)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and sum(c.isalpha() for c in n.value) >= 12}


def test_le_catalogue_de_la_base_ne_recopie_aucune_phrase_du_catalogue_de_la_commande():
    """Une seule source par texte : une phrase écrite dans les deux fichiers est un double (la rupture, le moyen refusé, la fermeture, avant la fusion de C1 et C2)."""
    doubles = _phrases(TSC) & _phrases(TS)
    assert not doubles, sorted(doubles)
