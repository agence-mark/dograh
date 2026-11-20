"""[.mark] Chantier Partie 1, lot 15 : les briques allergènes et régimes (``services/commande/briques/inf*.py``) et la décision D22.

Les allergènes d'un produit ou d'une option sont PROPOSÉS depuis les ingrédients par la table officielle (annexe II du règlement (UE) n° 1169/2011), VALIDÉS par une
personne, et l'agent ne lit que les validés. Une classe par brique (``TestINF1`` à ``TestINF7``) avec sa règle, son test de rendu de la fiche (D66) et son aller-retour en caisse.
Un test = un essai à la fois.
"""

from __future__ import annotations

from api.tests.mark.partie_1.aides_briques import descendre_jusqu_a
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401


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
    from api.services.restauration.allergenes_suggeres import table_inco
    from api.services.restauration.signalements import LES_QUATORZE

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
    from api.services.restauration.allergenes_suggeres import suggerer_les_allergenes

    s = suggerer_les_allergenes([{"nom": "jambon", "retirable": False}, {"nom": "fromage", "retirable": True}, "pâte à pizza"])
    assert s["codes"] == ["gluten", "lait"] and s["proposable"] is True
    rien = suggerer_les_allergenes(["tomate", "basilic", "huile d'olive"])
    assert rien == {"codes": [], "a_preciser": [], "proposable": False}  # jamais un [] proposé comme « aucun allergène »
    assert suggerer_les_allergenes(None)["proposable"] is False


def test_sauce_maison_a_preciser():
    """Un ingrédient composé que la table ne reconnaît pas (« sauce maison ») est rendu « à préciser », jamais « sans allergène » ; « sauce soja » est reconnu (soja)."""
    from api.services.restauration.allergenes_suggeres import suggerer_les_allergenes

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
