"""[.mark] Module Restauration, lot 3 : la règle d'import d'une carte vers la portée (propre, exception, jamais enseigne).

| Test | Ce qu'il prouve |
|---|---|
| sans enseigne | tout ce qui est importé est propre à l'établissement ; rien n'est écrit en « enseigne » même si le fichier le déclare |
| avec enseigne | un objet dont la ``ref`` est déjà dans l'enseigne est importé en exception (remplace la ligne d'enseigne), le reste en carte propre |
| l'enseigne n'est jamais touchée | la carte d'enseigne déclarée à la main reste telle quelle, l'autre établissement la voit inchangée |
| idempotent | le même import rejoué ne change rien ; la version de la carte ne monte pas |
| la règle mord | sans la règle (``importer_carte`` nu), l'objet de l'enseigne est dupliqué en propre : le test le voit |
"""

from __future__ import annotations

import copy

from api.db.bases_clients.restauration_carte import carte_du_restaurant, importer_carte, version_carte
from api.services.restauration.caisse.prises.import_carte import importer_selon_la_portee, marquer_la_portee
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, resto  # noqa: F401


async def _portees(c, table, site):
    return {r["ref"]: r["portee"] for r in await c.fetch(f"SELECT ref, portee FROM mark.{table} WHERE site_id IS NOT DISTINCT FROM $1", site)}


def test_la_marque_est_pure_et_ne_cree_jamais_d_enseigne():
    carte = copy.deepcopy(CARTE)
    carte["categories"][0]["portee"] = "enseigne"  # un fichier qui se déclare enseigne
    avant = copy.deepcopy(carte)
    marquee = marquer_la_portee(carte, None)
    assert carte == avant  # l'argument n'est pas modifié
    toutes = [o["portee"] for o in marquee["categories"] + marquee["produits"] + marquee["groupes"] + marquee["formules"]]
    toutes += [d["portee"] for p in marquee["produits"] for d in p["declinaisons"]] + [o["portee"] for g in marquee["groupes"] for o in g["options"]]
    assert set(toutes) == {"etablissement"}


async def test_sans_enseigne_tout_est_propre_a_l_etablissement(resto):  # noqa: F811
    c = resto.c
    carte = copy.deepcopy(CARTE)
    carte["produits"][0]["portee"] = "enseigne"
    bilan = await importer_selon_la_portee(c, resto.a, carte, "caisse")
    assert bilan["ajoutes"] > 0
    for table in ("resto_categorie", "resto_produit", "resto_declinaison", "resto_groupe_choix", "resto_option", "resto_formule"):
        assert set((await _portees(c, table, resto.a)).values()) <= {"etablissement"}, table
        assert await _portees(c, table, None) == {}, table  # aucune ligne d'enseigne créée par l'import


async def test_un_objet_de_l_enseigne_est_importe_en_exception_le_reste_en_propre(resto):  # noqa: F811
    c = resto.c
    produit = CARTE["produits"][0]["id"]
    categorie = CARTE["categories"][0]["id"]
    await c.execute("INSERT INTO mark.resto_categorie (site_id, portee, ref, nom, source) VALUES (NULL, 'enseigne', $1, 'Catégorie d''enseigne', 'mark')", categorie)
    await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom, categorie_ref, source) VALUES (NULL, 'enseigne', $1, 'Produit d''enseigne', $2, 'mark')", produit, categorie)
    await importer_selon_la_portee(c, resto.a, CARTE, "caisse")
    produits = await _portees(c, "resto_produit", resto.a)
    assert produits[produit] == "exception" and all(p == "etablissement" for ref, p in produits.items() if ref != produit)
    assert (await _portees(c, "resto_categorie", resto.a))[categorie] == "exception"
    # l'établissement voit SA ligne (la caisse), l'autre voit l'enseigne, intacte
    vu_a = {p["id"]: p["nom"] for p in (await carte_du_restaurant(c, resto.a))["produits"]}
    vu_b = {p["id"]: p["nom"] for p in (await carte_du_restaurant(c, resto.b))["produits"]}
    assert vu_a[produit] == CARTE["produits"][0]["nom"] and vu_b == {produit: "Produit d'enseigne"}
    assert await _portees(c, "resto_produit", None) == {produit: "enseigne"}
    assert await c.fetchval("SELECT nom FROM mark.resto_produit WHERE site_id IS NULL AND ref = $1", produit) == "Produit d'enseigne"


async def test_le_meme_import_rejoue_ne_change_rien(resto):  # noqa: F811
    c = resto.c
    await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom, source) VALUES (NULL, 'enseigne', $1, 'E', 'mark')", CARTE["produits"][0]["id"])
    await importer_selon_la_portee(c, resto.a, CARTE, "caisse")
    version = await version_carte(c, resto.a)
    rejoue = await importer_selon_la_portee(c, resto.a, CARTE, "caisse")
    assert (rejoue["ajoutes"], rejoue["changes"], rejoue["retires"]) == (0, 0, 0)
    assert await version_carte(c, resto.a) == version


async def test_la_regle_mord_sans_elle_l_objet_de_l_enseigne_est_ecrit_en_propre(resto):  # noqa: F811
    c = resto.c
    produit = CARTE["produits"][0]["id"]
    await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom, source) VALUES (NULL, 'enseigne', $1, 'E', 'mark')", produit)
    await importer_carte(c, resto.a, CARTE, "caisse")  # import nu : pas de règle
    assert (await _portees(c, "resto_produit", resto.a))[produit] == "etablissement"  # ≠ exception : c'est ce que la règle corrige
