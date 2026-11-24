"""[.mark] Chantier Partie 1, lot 15 : les briques allergènes et régimes (``services/commande/briques/inf*.py``) et la décision D22.

Les allergènes d'un produit ou d'une option sont PROPOSÉS depuis les ingrédients par la table officielle (annexe II du règlement (UE) n° 1169/2011), VALIDÉS par une
personne, et l'agent ne lit que les validés. Une classe par brique (``TestINF1`` à ``TestINF7``) avec sa règle, son test de rendu de la fiche (D66) et son aller-retour en caisse.
Un test = un essai à la fois.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a, oui_au_numero_dicte
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as ALLERGIE


# --------------------------------------------------------------------------- #
# L15-01 : la migration 046 (la fiche disait 044, déjà prise par le code de remise)
# --------------------------------------------------------------------------- #

COLONNES = (
    ("resto_option", "allergenes"), ("resto_option", "allergenes_etat"), ("resto_option", "allergenes_source"),
    ("resto_produit", "allergenes_etat"), ("resto_produit", "allergenes_source"), ("resto_produit", "regimes"), ("resto_produit", "epice"), ("resto_produit", "nutrition"),
    ("resto_reglage", "consigne_allergie"), ("resto_reglage", "halal_restaurant"), ("resto_reglage", "allergies_renvoyees_au_restaurant"),
)


async def test_migration_046_montee_descente(base_prete):
    """Montée, descente, remontée : les colonnes du lot 15 apparaissent et disparaissent ; l'établissement qui renvoie les allergies vers le restaurant est éteint par défaut."""
    from api.db.bases_clients import connexion as schema

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in COLONNES]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        assert await c.fetchval("SELECT column_default FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_reglage' AND column_name='allergies_renvoyees_au_restaurant'") == "false"
        for _ in range(2):
            await descendre_jusqu_a(c, 46)
            assert not any(await presentes(c)) and 46 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 46 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# L15-02 : la table officielle INCO
# --------------------------------------------------------------------------- #


def test_table_inco_quatorze_codes():
    """La table dit les quatorze codes de ``LES_QUATORZE`` et seulement eux, chacun lié à son point de l'annexe II (1 à 14), et cite l'adresse lue."""
    from api.services.restauration.carte_et_allergenes.allergenes_suggeres import table_inco
    from api.services.restauration.carte_et_allergenes.signalements import LES_QUATORZE

    t = table_inco()
    assert set(t["allergenes"]) == set(LES_QUATORZE) and len(t["allergenes"]) == 14
    assert sorted(v["annexe"] for v in t["allergenes"].values()) == list(range(1, 15))
    assert t["adresse"].startswith("https://eur-lex.europa.eu/") and "1169/2011" in t["source"] and t["lu_le"]
    assert all(v["ingredients"] for v in t["allergenes"].values())


# --------------------------------------------------------------------------- #
# L15-03 à L15-06 : la suggestion, la validation, ce que l'agent lit
# --------------------------------------------------------------------------- #

from api.tests.mark.partie_1.aides_briques import article_en_caisse, fait, la_brique_change_la_fiche  # noqa: E402


def test_suggestion_jamais_affirmee():
    """Les ingrédients d'une reine proposent le gluten (la pâte) et le lait (le fromage) ; la liste est PROPOSÉE ; des ingrédients sans allergène ne proposent JAMAIS « aucun » (liste vide)."""
    from api.services.restauration.carte_et_allergenes.allergenes_suggeres import suggerer_les_allergenes

    s = suggerer_les_allergenes([{"nom": "jambon", "retirable": False}, {"nom": "fromage", "retirable": True}, "pâte à pizza"])
    assert s["codes"] == ["gluten", "lait"] and s["proposable"] is True
    rien = suggerer_les_allergenes(["tomate", "basilic", "huile d'olive"])
    assert rien == {"codes": [], "a_preciser": [], "proposable": False}  # jamais un [] proposé comme « aucun allergène »
    assert suggerer_les_allergenes(None)["proposable"] is False


def test_sauce_maison_a_preciser():
    """Un ingrédient composé que la table ne reconnaît pas (« sauce maison ») est rendu « à préciser », jamais « sans allergène » ; « sauce soja » est reconnu (soja)."""
    from api.services.restauration.carte_et_allergenes.allergenes_suggeres import suggerer_les_allergenes

    s = suggerer_les_allergenes(["sauce maison", "salade"])
    assert s["a_preciser"] == ["sauce maison"] and s["codes"] == [] and s["proposable"] is False
    assert suggerer_les_allergenes(["sauce soja"]) == {"codes": ["soja"], "a_preciser": [], "proposable": True}


async def _produit_de_la_carte(e, ref):
    from api.db.bases_clients import restauration

    await e.charger()
    carte = await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
    return next(p for p in carte["produits"] if p["id"] == ref)


async def test_suggestion_pose_une_proposition_sans_toucher_au_valide(essai_de):
    """La carte INF1 : la reine (gluten, lait) et la salade (aucun) sont déjà écrites : jamais touchées ; la tarte (inconnue, « pâte ») reçoit une PROPOSITION (gluten) et la sauce maison est à préciser."""
    from api.db.bases_clients import restauration_allergenes as A

    e = await essai_de("briques/INF1")
    bilan = await A.proposer_les_allergenes(e.monde.c, e.monde.a, "essai")
    assert bilan["deja_ecrits"] == 2 and [x["ref"] for x in bilan["proposes"]] == ["P-TARTE"] and bilan["proposes"][0]["allergenes"] == ["gluten"]
    assert [(x["ref"], x["ingredients"]) for x in bilan["a_preciser"]] == [("P-TARTE", ["sauce maison"])]
    ligne = await e.monde.c.fetchrow("SELECT allergenes, allergenes_etat, allergenes_source FROM mark.resto_produit WHERE site_id = $1 AND ref = 'P-TARTE'", e.monde.a)
    assert (list(ligne["allergenes"]), ligne["allergenes_etat"], ligne["allergenes_source"]) == (["gluten"], "propose", "suggestion")
    reine = await e.monde.c.fetchrow("SELECT allergenes, allergenes_etat FROM mark.resto_produit WHERE site_id = $1 AND ref = 'P-REINE'", e.monde.a)
    assert list(reine["allergenes"]) == ["gluten", "lait"] and reine["allergenes_etat"] == "valide"
    assert (await A.proposer_les_allergenes(e.monde.c, e.monde.a, "essai"))["proposes"][0]["allergenes"] == ["gluten"]  # rejouable, même résultat


async def test_agent_ne_lit_que_les_valides(essai_de):
    """Une proposition n'est jamais lue (la carte rend ``None``, la lecture dit « je ne peux pas vous le confirmer ») ; une fois validée par une personne, elle est dite."""
    from api.db.bases_clients import restauration_allergenes as A

    e = await essai_de("briques/INF1")
    await A.proposer_les_allergenes(e.monde.c, e.monde.a, "essai")
    assert (await _produit_de_la_carte(e, "P-TARTE"))["allergenes"] is None
    lu = await e.lecture(sujet="allergenes", article="Tarte maison", a_eviter="gluten")
    assert '"signalement": "inconnu"' in fait(lu) and '"signalement": "present"' not in fait(lu), fait(lu)
    assert await A.valider_les_allergenes(e.monde.c, e.monde.a, "produit", "P-TARTE", "evan") == "ok"
    assert (await _produit_de_la_carte(e, "P-TARTE"))["allergenes"] == ["gluten"]
    lu = await e.lecture(sujet="allergenes", article="Tarte maison", a_eviter="gluten")
    assert '"signalement": "present"' in fait(lu), fait(lu)


async def test_validation_journalisee(essai_de):
    """Valider = une écriture de personne : le journal dit qui, quoi, quand ; rien à valider sans proposition, un produit inconnu est introuvable."""
    from api.db.bases_clients import restauration_allergenes as A

    e = await essai_de("briques/INF1")
    assert await A.valider_les_allergenes(e.monde.c, e.monde.a, "produit", "P-TARTE", "evan") == "rien_a_valider"
    assert await A.valider_les_allergenes(e.monde.c, e.monde.a, "produit", "P-INCONNU", "evan") == "introuvable"
    await A.proposer_les_allergenes(e.monde.c, e.monde.a, "essai")
    assert await A.valider_les_allergenes(e.monde.c, e.monde.a, "produit", "P-TARTE", "evan") == "ok"
    # la carte vient d'une caisse : l'écrit d'une personne va en SURCOUCHE (un réimport ne l'efface pas), journalisé avec son auteur
    ecrit = await e.monde.c.fetch("SELECT auteur, source, apres FROM mark.resto_journal WHERE site_id = $1 AND objet = 'resto_surcouche' AND apres->>'ref' = 'P-TARTE' ORDER BY id DESC LIMIT 1", e.monde.a)
    assert ecrit and ecrit[0]["auteur"] == "evan" and ecrit[0]["source"] == "mark", ecrit
    assert await e.monde.c.fetchval("SELECT allergenes_ecrits FROM mark.resto_surcouche WHERE site_id = $1 AND objet = 'produit' AND ref = 'P-TARTE'", e.monde.a) is True


async def test_validation_en_direct_marque_valide_par_le_restaurateur(essai_de):
    """Un produit tenu ici (source portail) : la validation s'écrit sur sa ligne, étiquetée ``valide`` / ``restaurateur``, journalisée avec son auteur."""
    from api.db.bases_clients import restauration_allergenes as A

    e = await essai_de("briques/INF1")
    await e.monde.c.execute("UPDATE mark.resto_produit SET source = 'portail' WHERE site_id = $1 AND ref = 'P-TARTE'", e.monde.a)
    await A.proposer_les_allergenes(e.monde.c, e.monde.a, "essai")
    assert await A.valider_les_allergenes(e.monde.c, e.monde.a, "produit", "P-TARTE", "evan") == "ok"
    ligne = await e.monde.c.fetchrow("SELECT allergenes_etat, allergenes_source FROM mark.resto_produit WHERE site_id = $1 AND ref = 'P-TARTE'", e.monde.a)
    assert (ligne["allergenes_etat"], ligne["allergenes_source"]) == ("valide", "restaurateur")
    ecrit = await e.monde.c.fetch("SELECT auteur FROM mark.resto_journal WHERE site_id = $1 AND objet = 'resto_produit' AND apres->>'ref' = 'P-TARTE' ORDER BY id DESC LIMIT 1", e.monde.a)
    assert ecrit[0]["auteur"] == "evan"


async def test_validation_d_une_option_en_surcouche(essai_de):
    """Les allergènes d'une option se valident en surcouche (un réimport ne les efface pas) ; la lecture de l'option les dit."""
    from api.db.bases_clients import restauration_allergenes as A

    e = await essai_de("briques/INF2")
    assert await A.valider_les_allergenes(e.monde.c, e.monde.a, "option", "G-SAUCE-Maison", "evan", ["moutarde"]) == "ok"
    await e.charger()
    lu = await e.lecture(sujet="allergenes", article="Tacos sauce maison", a_eviter="moutarde")
    assert '"signalement": "present"' in fait(lu), fait(lu)


async def test_route_suggestion_cloisonnee(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    """Les routes du lot : la session de l'organisation A les joue chez A (suggestion puis validation, journalisées) ; l'établissement d'une autre organisation ou un inconnu : 404 ;
    une clé d'API n'écrit pas (403)."""
    from api.db.bases_clients import connexion as schema
    from api.tests.mark.banc_a.commun import carte_de
    from api.tests.mark.equipe_commun import client_http
    from api.tests.mark.test_contacts_portail import _cle
    from api.tests.mark.test_restauration_ecran_routes import RACINE, _cas, _importer

    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    c_b = await schema.connecter(cas.base_b)
    try:  # un établissement qui n'existe que chez B (les identifiants des deux bases se recouvrent sinon)
        chez_b = await c_b.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'trois', 'trois', 'Europe/Paris' FROM mark.entreprise LIMIT 1 RETURNING id")
    finally:
        await c_b.close()
    assert chez_b not in cas.sites_a
    async with client_http() as c:
        assert (await _importer(c, cas, carte_de("briques/INF1"))).status_code == 200
        suggestion = await c.post(f"{RACINE}/etablissements/{etab}/allergenes/suggestion", headers=cas.session)
        assert suggestion.status_code == 200 and [x["ref"] for x in suggestion.json()["proposes"]] == ["P-TARTE"], suggestion.text
        assert (await c.post(f"{RACINE}/etablissements/{etab}/allergenes/suggestion", headers=_cle(cas.cle_a))).status_code == 403
        for cible in (chez_b, max(cas.sites_a + cas.sites_b) + 1000):
            assert (await c.post(f"{RACINE}/etablissements/{cible}/allergenes/suggestion", headers=cas.session)).status_code == 404
            assert (await c.post(f"{RACINE}/etablissements/{cible}/allergenes/P-TARTE/valider", json={}, headers=cas.session)).status_code == 404
        assert (await c.post(f"{RACINE}/etablissements/{etab}/allergenes/P-INCONNU/valider", json={}, headers=cas.session)).status_code == 404
        assert (await c.post(f"{RACINE}/etablissements/{etab}/allergenes/P-TARTE/valider", json={"allergenes": ["cacahuete"]}, headers=cas.session)).status_code == 422
        ok = await c.post(f"{RACINE}/etablissements/{etab}/allergenes/P-TARTE/valider", json={}, headers=cas.session)
        assert ok.status_code == 200 and ok.json() == {"ok": True}
    base = await schema.connecter(cas.base_a)
    try:
        assert await base.fetchval("SELECT allergenes_ecrits FROM mark.resto_surcouche WHERE site_id = $1 AND objet = 'produit' AND ref = 'P-TARTE'", etab) is True
        assert await base.fetchval("SELECT count(*) FROM mark.resto_journal WHERE site_id = $1 AND objet = 'resto_surcouche' AND apres->>'ref' = 'P-TARTE'", etab) >= 1
    finally:
        await base.close()
    base_b = await schema.connecter(cas.base_b)
    try:
        assert await base_b.fetchval("SELECT count(*) FROM mark.resto_produit WHERE allergenes_etat = 'propose'") == 0  # rien n'a été écrit chez l'autre organisation
    finally:
        await base_b.close()


def test_routes_du_lot_15_au_registre():
    """Les deux routes sont au registre : écrire = ``agents.modifier``, jamais par clé."""
    from api.services.equipe_mark import registre_routes as registre

    for chemin in ("/restauration/etablissements/{etablissement_id}/allergenes/suggestion", "/restauration/etablissements/{etablissement_id}/allergenes/{ref}/valider"):
        decision, _ = registre.decision_de("POST", chemin)
        assert decision.cle == "agents.modifier" and decision.pour_cle is None, chemin


# --------------------------------------------------------------------------- #
# Les briques INF1 à INF7
# --------------------------------------------------------------------------- #

from api.services.restauration.caisse.prises.hubrise_traduction import commande_vers_hubrise  # noqa: E402


async def _reglage(e, **valeurs) -> None:
    """Ce que l'établissement a écrit (consigne d'allergie, halal, renvoi), posé AVANT le premier geste de l'appel (les réglages sont lus une fois au chargement)."""
    colonnes = ", ".join(valeurs)
    marques = ", ".join(f"${i + 2}" for i in range(len(valeurs)))
    mises_a_jour = ", ".join(f"{c} = EXCLUDED.{c}" for c in valeurs)
    await e.monde.c.execute(f"INSERT INTO mark.resto_reglage (site_id, {colonnes}) VALUES ($1, {marques}) ON CONFLICT (site_id) DO UPDATE SET {mises_a_jour}", e.monde.a, *valeurs.values())


async def _lire(e, article: str, a_eviter: str | None = None) -> str:
    return fait(await e.lecture(sujet="allergenes", article=article, **({"a_eviter": a_eviter} if a_eviter else {})))


class TestINF1:
    def test_inf1_repondre_depuis_la_donnee(self):
        """Une donnée absente est inconnue (jamais « sans ») ; une liste, même vide, permet de dire ce que la fiche dit."""
        from api.services.commande.briques.allergenes_du_produit import brique_inf1_repondre_depuis_la_donnee as r

        assert r(None, "lait") == "inconnu" and r(["lait"], "lait") == "present" and r(["gluten"], "lait") == "absent_de_la_fiche" and r([], "lait") == "absent_de_la_fiche"

    async def test_inf1_un_allergene_seulement_propose_n_est_jamais_dit(self, essai_de):
        """La reine (validée : gluten, lait) le dit ; la salade (validée, aucun) dit « d'après la fiche, non » ; la tarte (inconnue) reste « je ne peux pas vous le confirmer », même proposée."""
        from api.db.bases_clients import restauration_allergenes as A

        e = await essai_de("briques/INF1")
        assert '"signalement": "present"' in await _lire(e, "Pizza reine", "lait")
        assert '"signalement": "absent_de_la_fiche"' in await _lire(e, "Salade verte", "gluten")
        assert '"signalement": "inconnu"' in await _lire(e, "Tarte maison", "gluten")
        await A.proposer_les_allergenes(e.monde.c, e.monde.a, "essai")
        await e.charger()
        assert '"signalement": "inconnu"' in await _lire(e, "Tarte maison", "gluten")  # proposé : jamais dit

    async def test_inf1_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("INF1", essai_de) is False

    async def test_inf1_aller_retour_caisse(self, essai_de):
        """L'information ne part pas dans la commande : le prix et le corps sont ceux d'un article sans allergène, et la caisse retrouve notre prix."""
        e = await essai_de("briques/INF1")
        article = await article_en_caisse(e, "P-REINE-UNIQUE")
        assert not {"allergens", "nutrition"} & set(article) and article["price"] == "11.50 EUR", article


class TestINF2:
    def test_inf2_produit_et_options(self):
        """Le produit et l'option ensemble : présent si l'un le porte (ou si le nom de l'option le dit) ; un inconnu sans présence rend l'ensemble inconnu ; tout connu sans présence : absent de la fiche."""
        from api.services.commande.briques.allergenes_d_une_option import brique_inf2_produit_et_options as r

        assert r(["gluten"], [{"allergenes": ["moutarde"]}], "moutarde") == "present" and r(["moutarde"], [{"allergenes": []}], "moutarde") == "present"
        assert r([], [{"allergenes": None, "signalements_du_nom": ["moutarde"]}], "moutarde") == "present"
        assert r(["gluten"], [{"allergenes": None}], "moutarde") == "inconnu" and r(None, [{"allergenes": []}], "moutarde") == "inconnu"
        assert r(["gluten"], [{"allergenes": []}], "moutarde") == "absent_de_la_fiche"

    async def test_inf2_la_sauce_algerienne_contient_de_la_moutarde(self, essai_de):
        """« La sauce algérienne contient de la moutarde ? » (audit § 7) : oui, d'après la donnée de l'option ; le ketchup (connu, aucun) : d'après la fiche, non ; la sauce maison (sans donnée) : inconnu."""
        e = await essai_de("briques/INF2")
        assert '"signalement": "present"' in await _lire(e, "Tacos sauce algérienne", "moutarde")
        assert '"signalement": "absent_de_la_fiche"' in await _lire(e, "Tacos ketchup", "moutarde")
        assert '"signalement": "inconnu"' in await _lire(e, "Tacos sauce maison", "moutarde")

    async def test_inf2_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("INF2", essai_de) is False

    async def test_inf2_aller_retour_caisse(self, essai_de):
        """L'option choisie part avec son nom et son prix, sans allergène dans le corps ; la caisse retrouve notre prix."""
        e = await essai_de("briques/INF2")
        article = await article_en_caisse(e, "P-TACOS-UNIQUE", 1, [{"option_code": "G-SAUCE-ALGERIENNE", "quantite": 1}])
        assert [o["name"] for o in article["options"]] == ["Sauce algérienne"] and not {"allergens", "nutrition"} & set(article["options"][0]), article


class TestINF3:
    def test_inf3_jamais_sans_etiquette(self):
        """L'étiquette seule fait foi ; pas d'étiquette, pas de « non » ; rien ne se déduit (un végétalien n'est pas dit végétarien sans son étiquette)."""
        from api.services.commande.briques.regime_d_un_article import articles_etiquetes, brique_inf3_jamais_sans_etiquette as r

        assert r(["vegetarien"], "vegetarien") == "etiquete" and r(None, "vegetarien") == "inconnu" and r(["vegetalien"], "vegetarien") == "inconnu" and r([], "vegetarien") == "inconnu"
        assert articles_etiquetes([{"nom": "A", "regimes": ["vegetarien"]}, {"nom": "B"}, {"nom": "C", "regimes": ["halal"]}], "vegetarien") == ["A"]

    async def test_inf3_seulement_les_articles_etiquetes(self, essai_de):
        """« Du végétarien ? » : seulement les deux articles étiquetés ; l'article sans étiquette n'est jamais dit végétarien ; un article précis non étiqueté : « je ne peux pas vous garantir »."""
        e = await essai_de("briques/INF3")
        catalogue = await _lire(e, "du végétarien")
        assert '"articles": ["Burger veggie", "Assiette falafel"]' in catalogue or '"articles": ["Assiette falafel", "Burger veggie"]' in catalogue, catalogue
        assert "Burger classique" not in catalogue
        assert '"etiquete": true' in await _lire(e, "Burger veggie", "végétarien")
        classique = await _lire(e, "Burger classique", "végétarien")
        assert '"renseigne": false' in classique and '"etiquete"' not in classique

    async def test_inf3_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("INF3", essai_de) is False

    async def test_inf3_aller_retour_caisse(self, essai_de):
        """Un régime est une information : la ligne part sans étiquette dans le corps, au prix de la carte."""
        e = await essai_de("briques/INF3")
        article = await article_en_caisse(e, "P-VEGGIE-UNIQUE")
        assert "regimes" not in article and article["price"] == "11.00 EUR", article


class TestINF4:
    def test_inf4_dire_ce_qui_est_ecrit(self):
        """Deux données jamais mélangées : l'étiquette de l'article et la case du restaurant ; rien de plus que ce qui est écrit."""
        from api.services.commande.briques.halal import brique_inf4_dire_ce_qui_est_ecrit as r

        assert r(["halal"], False) == {"article": True, "restaurant": False, "ecrit": True}
        assert r(None, True) == {"article": False, "restaurant": True, "ecrit": True}
        assert r(["vegetarien"], False) == {"article": False, "restaurant": False, "ecrit": False}

    async def test_inf4_c_est_halal_ce_qui_est_ecrit(self, essai_de):
        """Le kebab est étiqueté halal : oui d'après la fiche. Le sandwich ne l'est pas : sans la case du restaurant, « je ne peux pas vous garantir » ; avec elle, seulement « d'après la fiche du restaurant »."""
        e = await essai_de("briques/INF4")
        assert '"etiquete": true' in await _lire(e, "Kebab", "halal")
        sandwich = await _lire(e, "Sandwich poulet", "halal")
        assert '"renseigne": false' in sandwich and '"restaurant"' not in sandwich
        e2 = await essai_de("briques/INF4")
        await _reglage(e2, halal_restaurant=True)
        avec = await _lire(e2, "Sandwich poulet", "halal")
        assert '"restaurant": true' in avec and '"etiquete": false' in avec, avec
        assert '"restaurant": true' in await _lire(e2, "halal")  # sans article : la case du restaurant

    async def test_inf4_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("INF4", essai_de) is False

    async def test_inf4_aller_retour_caisse(self, essai_de):
        e = await essai_de("briques/INF4")
        article = await article_en_caisse(e, "P-KEBAB-UNIQUE")
        assert "regimes" not in article and article["price"] == "9.00 EUR", article


class TestINF5:
    def test_inf5_depuis_le_texte(self):
        from api.services.commande.briques.epice_en_descripteur import brique_inf5_depuis_le_texte as r

        assert r("  fort,   piment ") == "fort, piment" and r(None) is None and r("   ") is None

    async def test_inf5_c_est_fort_depuis_le_texte(self, essai_de):
        """« C'est fort ? » (A32) : le texte écrit par une personne, tel quel ; sans texte, aucun fait d'épice (« je ne peux pas vous le confirmer »)."""
        e = await essai_de("briques/INF5")
        lu = fait(await e.lecture(sujet="article", article="Poulet piquant"))
        assert "fort, piment d'Espelette" in lu, lu
        assert '"epice"' not in fait(await e.lecture(sujet="article", article="Poulet nature"))

    async def test_inf5_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("INF5", essai_de) is False

    async def test_inf5_aller_retour_caisse(self, essai_de):
        e = await essai_de("briques/INF5")
        article = await article_en_caisse(e, "P-PIQUANT-UNIQUE")
        assert "epice" not in article and article["price"] == "12.50 EUR", article


class TestINF6:
    def test_inf6_repeter_et_noter(self):
        """La consigne du restaurant est répétée telle qu'écrite ; l'allergie dite part en note sous l'en-tête du lot 6 ; rien n'est inventé quand l'une manque."""
        from api.services.commande.briques.consigne_d_allergie import brique_inf6_repeter_et_noter as r

        assert r("  Prévenez la cuisine ", "noix") == {"consigne": "Prévenez la cuisine", "note": "Allergie : noix"}
        assert r(None, None) == {"consigne": None, "note": None}

    async def test_inf6_la_consigne_est_un_fait_de_la_lecture(self, essai_de):
        """« Je suis allergique aux noix » : la lecture rend la consigne du restaurant à répéter, avec la réponse de la fiche ; sans consigne écrite, aucun fait inventé."""
        e = await essai_de("briques/INF6")
        sans = await _lire(e, "Gâteau aux noix", "noix")
        assert '"signalement": "present"' in sans and "consigne_du_restaurant" not in sans
        e2 = await essai_de("briques/INF6")
        await _reglage(e2, consigne_allergie="La cuisine manipule des fruits à coque, des traces sont possibles.")
        avec = await _lire(e2, "Gâteau aux noix", "noix")
        assert '"signalement": "present"' in avec and "des traces sont possibles" in avec, avec

    async def test_inf6_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("INF6", essai_de) is False

    async def test_inf6_aller_retour_caisse(self):
        """L'allergie dite arrive à la caisse dans la note de la commande (``customer_notes``), avec la note du modèle."""
        from api.services.commande.briques.consigne_d_allergie import brique_inf6_repeter_et_noter
        from api.services.commande.note import composer_la_note_de_commande

        note = composer_la_note_de_commande([{"texte": "bien cuite"}], {"allergie": "noix"})
        assert brique_inf6_repeter_et_noter(None, "noix")["note"] in note
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": [{"nom": "Gâteau", "code_caisse": "P-GATEAU-UNIQUE", "quantite": 1, "prix_unitaire": 550, "choix": []}], "note": note})
        assert corps["customer_notes"] == "Allergie : noix ; bien cuite", corps


class TestINF7:
    def test_inf7_depuis_la_donnee(self):
        """La donnée est rendue telle quelle (jamais calculée) ; sans donnée, rien."""
        from api.services.commande.briques.nutrition_et_degre import brique_inf7_depuis_la_donnee as r

        n = {"per_100_values": {"per": "100 g", "energy": {"unit": "kcal", "lower": 250}, "protein": "12 g"}}
        assert r(n, None) == {"pour": "100 g", "energie": {"unit": "kcal", "lower": 250}, "nutriments": {"protein": "12 g"}}
        assert r(None, 5.0) == {"degre": 5.0} and r(None, None) is None and r({}, None) is None

    async def test_inf7_combien_de_calories(self, essai_de):
        """« Combien de calories ? » : l'énergie de la donnée ; la bière dit son degré ; l'eau, sans donnée, ne rend aucun fait (« je ne peux pas vous le confirmer »)."""
        e = await essai_de("briques/INF7")
        burger = fait(await e.lecture(sujet="article", article="Burger maison"))
        assert '"unit": "kcal"' in burger and '"lower": 250' in burger, burger
        assert '"degre": 5.0' in fait(await e.lecture(sujet="article", article="Bière blonde"))
        assert '"nutrition"' not in fait(await e.lecture(sujet="article", article="Eau plate"))

    async def test_inf7_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("INF7", essai_de) is False

    async def test_inf7_aller_retour_caisse(self, essai_de):
        e = await essai_de("briques/INF7")
        article = await article_en_caisse(e, "P-BURGER-UNIQUE")
        assert "nutrition" not in article and article["price"] == "13.00 EUR", article


# --------------------------------------------------------------------------- #
# L15-07 : « renvoyer vers le restaurant » ; L15-15 : la brique jamais vue
# --------------------------------------------------------------------------- #


async def test_renvoyer_vers_le_restaurant(essai_de):
    """Éteint par défaut (la réponse vient de la fiche) ; allumé, toute question d'allergène rend « l'équipe vous le confirme » et la donnée n'est plus lue ; la consigne écrite accompagne."""
    from api.db.bases_clients import connexion as schema

    e = await essai_de("briques/INF1")
    assert await e.monde.c.fetchval("SELECT allergies_renvoyees_au_restaurant FROM mark.resto_reglage WHERE site_id = $1", e.monde.a) in (None, False)
    assert '"signalement": "present"' in await _lire(e, "Pizza reine", "lait")
    e2 = await essai_de("briques/INF1")
    await _reglage(e2, allergies_renvoyees_au_restaurant=True, consigne_allergie="Parlez à la cuisine.")
    renvoi = await _lire(e2, "Pizza reine", "lait")
    assert '"signalement": "renvoye_au_restaurant"' in renvoi and '"equipe_confirme": true' in renvoi and "Parlez à la cuisine." in renvoi, renvoi
    assert '"present"' not in renvoi and schema is not None


async def test_briques_jamais_vues_sans_case_nouvelle(essai_de):
    """INF2 (jamais vue sur une carte) : côté code seulement, aucune case nouvelle, aucune conversation : le rendu de la fiche est IDENTIQUE avec et sans ses données (D66)."""
    from api.services.commande.briques import registre
    from api.tests.mark.banc_a.commun import carte_de
    from api.tests.mark.partie_1 import rendu_de_la_fiche as RF

    brique = registre.BRIQUES["INF2"]
    assert brique.vue_sur_carte is False and brique.change_la_fiche_du_modele is False
    avec = await essai_de("briques/INF2")
    sans = await essai_de("briques/INF2-sans", carte=RF.sans_la_brique("INF2", carte_de("briques/INF2")))
    try:
        assert await RF.rendu_de_la_fiche(avec, "INF2") == await RF.rendu_de_la_fiche(sans, "INF2")
    finally:
        await avec.monde.c.close()
        await sans.monde.c.close()


def test_les_sept_briques_sont_au_registre_sans_changer_la_fiche():
    """INF1 à INF7 : inscrites, chacune avec sa règle nommée, déclarée sans effet sur la fiche du modèle (confirmé par ``test_inf*_fiche_du_modele``)."""
    from api.services.commande.briques import registre

    noms = {"INF1": "brique_inf1_repondre_depuis_la_donnee", "INF2": "brique_inf2_produit_et_options", "INF3": "brique_inf3_jamais_sans_etiquette", "INF4": "brique_inf4_dire_ce_qui_est_ecrit",
            "INF5": "brique_inf5_depuis_le_texte", "INF6": "brique_inf6_repeter_et_noter", "INF7": "brique_inf7_depuis_la_donnee"}
    for code, nom in noms.items():
        b = registre.BRIQUES[code]
        assert b.regle.__name__ == nom and b.change_la_fiche_du_modele is False, code


# --------------------------------------------------------------------------- #
# L15-16 à L15-18 : l'allergie, les faits donnés au modèle par le code (Evan, 20/11)
# --------------------------------------------------------------------------- #

from api.tests.mark.partie_1.aides_briques import brique  # noqa: E402


async def test_allergie_donnee_au_modele_meme_sans_lire(essai_de):
    """Conv4 rejouée : le greffier a noté une allergie aux noix, la fiche du modèle ne porte que la note (aucun ``lire``) : le retour porte lui-même les allergènes validés du panier
    (le gâteau aux noix en contient), sans aucune phrase écrite par le code ; donnés une seule fois."""
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "noix"
    r = await e.tour("je suis allergique aux noix, il y en a dans le gâteau ?", note_generale="allergique aux noix")
    allergie = r["faits"]["allergie"]
    assert allergie["allergene"] == "les fruits à coque" and allergie["articles"] == [{"article": "Gâteau aux noix", "etat": "present"}] and allergie["a_confirmer_par_l_equipe"] is False, r
    assert "dit_par_le_code" not in fait(r)  # aucune phrase du code pour l'allergie
    assert all(x.get("operation") != "lire" for x in e.retours[-1].get("resultats") or [])  # le modèle n'a pas lu : le code a donné les faits
    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    # lot 7a (ligne 64) : les faits ne sont notés donnés qu'une fois la parole décidée (en production, après chaque fiche) : le modèle repasse avec eux
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Oui, le gâteau en contient."}).mode != PAROLE.A_DIRE_SEUL
    suivant = await e.tour("et la salade ?", note_generale="allergique aux noix")
    assert "allergie" not in (suivant.get("faits") or {})  # donnés une fois, pas redits à chaque tour


async def test_allergie_inconnue_a_confirmer_par_l_equipe(essai_de):
    """Sans allergène validé (tarte inconnue, ou un allergène que la carte ne connaît pas, ou le choix « renvoyer vers le restaurant ») : le fait dit « à confirmer par l'équipe », jamais « absent »."""
    e = await brique(essai_de, "INF1")
    await e.tour("une tarte", ajouter=[{"article": "tarte maison", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "gluten"
    r = await e.tour("allergique au gluten", note_generale="allergique au gluten")
    allergie = r["faits"]["allergie"]
    assert allergie["articles"] == [{"article": "Tarte maison", "etat": "inconnu"}] and allergie["a_confirmer_par_l_equipe"] is True and "absent_de_la_fiche" not in fait(allergie), allergie
    e2 = await brique(essai_de, "INF1")
    await e2.tour("une reine", ajouter=[{"article": "pizza reine", "quantite": 1}])
    e2.fiche_de_l_appel["allergie"] = "kiwi"  # pas un des quatorze
    autre = (await e2.tour("allergique au kiwi", note_generale="allergique au kiwi"))["faits"]["allergie"]
    assert autre["allergene"] is None and autre["a_confirmer_par_l_equipe"] is True
    e3 = await essai_de("briques/INF1")
    await _reglage(e3, allergies_renvoyees_au_restaurant=True)
    await e3.tour("à emporter", mode_de_retrait="emporter")
    await e3.tour("une reine", ajouter=[{"article": "pizza reine", "quantite": 1}])
    e3.fiche_de_l_appel["allergie"] = "lait"
    renvoi = (await e3.tour("allergique au lait", note_generale="allergique au lait"))["faits"]["allergie"]
    assert renvoi["renvoye_au_restaurant"] is True and renvoi["a_confirmer_par_l_equipe"] is True and "articles" not in renvoi


async def test_pas_d_enregistrement_avec_une_allergie_sans_reponse(essai_de):
    """Une allergie notée au dernier moment (le « oui » de la relecture arrive avec elle) : le « oui » ne vaut pas, les faits sont donnés au modèle, la relecture repart (et garde l'allergie en note) ;
    au tour suivant l'enregistrement est permis. L'allergie part en note de la commande (E22)."""
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    for _ in range(3):
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            break
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = CONV.question_de(e.p)
    assert q.get("type") == "relecture"
    e.fiche_de_l_appel["allergie"] = "noix"  # le greffier la note maintenant
    r = await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    assert not e.p.get("enregistree") and e.p["etape"] != "accordee", r
    assert "allergie_sans_reponse" in fait(r) and r["resultats"][-1]["faits"]["articles"][0]["etat"] == "present", r
    for _ in range(3):  # la relecture repart, avec l'allergie en note
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            break
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = CONV.question_de(e.p)
    assert q.get("type") == "relecture"
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    if not e.p.get("enregistree"):
        await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    if not e.p.get("enregistree"):
        await e.tour("Léa", prenom="Léa")
    await oui_au_numero_dicte(e)
    assert e.p.get("enregistree"), e.retours[-1]
    note = await e.monde.c.fetchval("SELECT note FROM mark.resto_commande WHERE site_id = $1", e.monde.a)
    assert "Allergie : noix" in (note or ""), note


async def test_allergie_article_seulement_cite(essai_de):
    """Conv4 exacte : « je suis allergique aux noix, il y en a dans la reine ? » : la fiche ne porte que la note, le panier est VIDE, la reine n'est nulle part. Le code donne au modèle les articles de la
    CARTE concernés par l'allergène : la reine (fruits à coque validés) figure parmi ceux qui en contiennent, la tarte (donnée inconnue) parmi ceux à confirmer par l'équipe, la salade (aucun, validé) nulle part ;
    au-delà de la borne, le fait dit seulement le nombre. Une allergie hors des quatorze : « à confirmer par l'équipe »."""
    from api.tests.mark.banc_a.commun import carte_de

    carte = carte_de("briques/INF1")
    for p in carte["produits"]:
        if p["id"] == "P-REINE":
            p["allergenes"] = ["fruits_a_coque", "gluten", "lait"]
    e = await essai_de("briques/INF1", carte=carte)
    await e.tour("à emporter", mode_de_retrait="emporter")
    e.fiche_de_l_appel["allergie"] = "noix"
    r = await e.tour("je suis allergique aux noix, il y en a dans la reine ?", note_generale="allergique aux noix")
    assert not e.p.get("lignes")
    allergie = r["faits"]["allergie"]
    assert allergie["allergene"] == "les fruits à coque" and allergie["articles"] == []
    assert allergie["carte"]["contiennent"] == {"noms": ["Pizza reine"]} and allergie["carte"]["a_confirmer_par_l_equipe"] == {"noms": ["Tarte maison"]}, allergie
    assert "Salade verte" not in fait(allergie) and allergie["a_confirmer_par_l_equipe"] is True
    assert ALLERGIE._bornee([f"A{i}" for i in range(ALLERGIE.BORNE_DES_ARTICLES_D_ALLERGIE + 1)]) == {"nombre": ALLERGIE.BORNE_DES_ARTICLES_D_ALLERGIE + 1}
