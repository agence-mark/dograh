"""[.mark] Lot 7b-C7a : les faits que portait seulement un texte de secours sont dans ce que le modèle lit (un fait brut, jamais une phrase).

Un test par fait (F1, F2, F7, F8, F9), chacun vu rouge avant son commit, avec son voisin (la règle 9 de ``regles-zero-aller-retour``)."""

from __future__ import annotations

from api.services.actions_communes.enveloppe_legere import pour_le_modele
from api.services.commande import moteur
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as A_
from api.tests.mark.partie_1.test_p1f_lot7c3_allergie_secours import Source as SourceAllergie, fiche, option
from api.tests.mark import test_commande_kebab_sa52 as _KEBAB

base_essai, base_prete, kebab = _KEBAB.base_essai, _KEBAB.base_prete, _KEBAB.kebab  # les fixtures du kebab, reprises sans import inutile


def _ambigu(*candidats: dict) -> dict:
    return {"resultats": [{"statut_du_module": "AMBIGU", "manque": "commune", "faits": {"candidats": list(candidats)}}]}


# ── F1 : le département des communes homonymes ──────────────────────────────────────────────────────────────────────────

def test_f1_deux_communes_homonymes_portent_leur_departement():
    """« À Nointel. » : le modèle demande « Nointel dans l'Oise ou dans le Val-d'Oise ? » ; sans le département il ne peut que dire « lequel des deux ? »."""
    vu = pour_le_modele(_ambigu({"nom": "Nointel", "departement": "Oise", "insee": "60471"}, {"nom": "Nointel", "departement": "Val-d'Oise", "insee": "95446"}))
    candidats = vu["resultats"][0]["faits"]["candidats"]
    assert [c["departement"] for c in candidats] == ["Oise", "Val-d'Oise"]


def test_f1_voisin_le_code_insee_et_le_code_postal_restent_retires():
    vu = pour_le_modele(_ambigu({"nom": "Nointel", "departement": "Oise", "insee": "60471", "code_postal": "60840"}))
    assert vu["resultats"][0]["faits"]["candidats"] == [{"nom": "Nointel", "departement": "Oise"}]


# ── F2 : le minimum de la zone, dit en fait au retour de l'adresse ──────────────────────────────────────────────────────

async def _adresse_retenue(kebab_, *, minimum: int, en_attente: bool = False):
    await kebab_.c.execute("UPDATE mark.resto_zone SET minimum = $2 WHERE site_id = $1", kebab_.a, minimum)
    a = await _KEBAB.Appel(kebab_).charger()
    await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    if en_attente:
        a.p["dits_en_attente"] = [{"article": "tacos"}]
    return await moteur.verifier_adresse(a.source, a.p, a.regles, _KEBAB.ADRESSE)


async def test_f2_adresse_retenue_panier_vide_le_minimum_est_un_fait_dit(kebab):
    """Client « Au 12 rue de la République à Senlis. » / le modèle dit « Il y a quinze euros minimum pour la livraison ; qu'est-ce que je vous mets ? »."""
    r = await _adresse_retenue(kebab, minimum=1500)
    assert r.statut == "RETENU" and r.faits["minimum_dit"] == "quinze euros", r.faits


async def test_f2_voisin_panier_commence_ou_zone_sans_minimum_pas_de_minimum_dit(kebab):
    r = await _adresse_retenue(kebab, minimum=1500, en_attente=True)
    assert r.statut == "RETENU" and "minimum_dit" not in r.faits, r.faits
    r = await _adresse_retenue(kebab, minimum=0)
    assert r.statut == "RETENU" and "minimum_dit" not in r.faits, r.faits


# ── F7 et F8 : ce qui reste à confirmer, dit en fait ────────────────────────────────────────────────────────────────────

def test_f7_un_allergene_inconnu_selon_le_choix_porte_options_a_confirmer(monkeypatch):
    """Client « Il y a des fruits à coque dans le tiramisu ? » / avant le modèle dit « Je ne peux pas vous le garantir. » / après « Ça dépend du parfum, et je ne peux pas vous le garantir. »."""
    monkeypatch.setattr(A_, "_options_obligatoires", lambda f: [option("sauce maison", None)])
    r = A_._signalement_dit(SourceAllergie(), fiche([]), None, "lait")
    assert r.faits["signalement"] == "inconnu" and r.faits["options_a_confirmer"] is True, r.faits


def test_f7_voisin_hors_liste_et_sans_fiche_ne_portent_pas_options_a_confirmer():
    assert "options_a_confirmer" not in A_._signalement_dit(SourceAllergie(), fiche(["lait"]), None, "kiwi").faits
    assert "options_a_confirmer" not in A_._signalement_dit(SourceAllergie(), fiche(None), None, "lait").faits


async def _regime(articles_etiquetes, *, halal_restaurant=False, regime="végétarien", code="vegetarien"):
    class Source(SourceAllergie):
        async def catalogue(self, _mode):
            return {"articles": [{"nom": n, "regimes": [code]} for n in articles_etiquetes]}

        async def regles_d_information(self):
            return {"halal_restaurant": halal_restaurant}
    return await A_._regime_du_catalogue(Source(), {"mode": "emporter"}, regime)


async def test_f8_des_articles_etiquetes_portent_autres_a_confirmer():
    """Client « Vous avez du végétarien ? » / modèle « La Margherita et la Veggie sont végétariennes ; pour le reste je ne peux pas le garantir. »."""
    r = await _regime(["Margherita", "Veggie"])
    assert r.faits["articles"] == ["Margherita", "Veggie"] and r.faits["autres_a_confirmer"] is True, r.faits


async def test_f8_voisin_la_case_halal_du_restaurant_seule_n_a_rien_a_confirmer():
    r = await _regime([], halal_restaurant=True, regime="halal", code="halal")
    assert r.faits.get("restaurant") is True and "autres_a_confirmer" not in r.faits, r.faits
