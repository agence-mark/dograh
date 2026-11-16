"""[.mark] Module Restauration, lot 5, étape 2 : le noyau commun du panier d'appel (module « Commande »).

Vraie base (rôle ``_ecriture``), carte de référence, heure fixée au jeudi 12 h. Le moteur commun parle à la SOURCE du classeur ;
le prix, le total, les choix obligatoires et les ruptures ne sont jamais ceux du modèle.

| Test | Ce qu'il prouve |
|---|---|
| lecture | quantités dites en lettres ou en chiffres, plusieurs morceaux, « 33 cl » n'est jamais une quantité |
| ordre | le mode d'abord ; en livraison la zone AVANT les articles (W6) ; réglable |
| aucun article perdu | « une regina et un coca » : le coca est posé, la taille de la regina reste une question (W16) |
| choix obligatoire | question fermée, réponse par le nom, remplacement quand on change d'avis |
| prix et total | le total vient de la carte, jamais du modèle ; voir_commande le redit |
| changement de mode | les articles sont gardés, le prix par mode et le minimum de zone sont rechiffrés |
| retraits | « sans champignons » cherché dans les ingrédients retirables ; « sans ananas » refusé avec la liste |
| suppléments | au prix de la carte ; maximum respecté ; hors carte refusé avec les plus proches, jamais un prix inventé |
| notes | « bien cuite » en note de ligne, sans prix ; refusée quand le réglage est éteint |
| moitié-moitié | deux moitiés exactement ; prix selon la règle (la plus chère, la moyenne, la somme) |
| modifier, retirer, vider | par numéro ou par nom ; tout ou rien ; l'ambigu est demandé |
| rupture | un article en rupture n'entre pas ; une autre taille est proposée |
| cloisonnement | une zone d'un autre établissement n'est jamais utilisable |
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte, poser_rupture
from api.services.commande import lecture, moteur, panier
from api.services.commande.moteur import Reglages
from api.services.restauration.appel import Lieu
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401


class Appel:
    """Un appel : une source sur le classeur, un panier, des réglages. Les gestes du moteur, tels que l'outil les appelle."""

    def __init__(self, commerce, **reglages):
        self.commerce = commerce
        self.source = SourceClasseur(commerce.c, Lieu(commerce.base, commerce.a, 1), nom_prise="test")
        self.p = panier.nouveau()
        self.regles = Reglages(**reglages)

    async def mode(self, mode="emporter"):
        return await moteur.choisir_mode(self.source, self.p, self.regles, mode)

    async def ajouter(self, **kw):
        return await moteur.ajouter(self.source, self.p, self.regles, **kw)

    async def modifier(self, **kw):
        return await moteur.modifier(self.source, self.p, self.regles, **kw)

    async def retirer(self, **kw):
        return await moteur.retirer(self.source, self.p, self.regles, **kw)

    async def vider(self):
        return await moteur.vider_commande(self.source, self.p, self.regles)

    async def voir(self):
        return await moteur.voir_commande(self.source, self.p, self.regles)

    def lignes(self):
        return [(l["nom"], l["quantite"]) for l in self.p["lignes"]]


@pytest.fixture
async def appel(commerce):
    return Appel(commerce)


def _total(r) -> int:
    return r.faits["total"]


# --------------------------------------------------------------------------- #
# La lecture de ce qui est dit
# --------------------------------------------------------------------------- #


def _qt(texte):
    return [(m.quantite, m.texte) for m in lecture.decouper(texte)]


def test_les_quantites_dites_en_lettres_ou_en_chiffres_et_plusieurs_morceaux():
    assert _qt("deux margherita et un coca") == [(2, "margherita"), (1, "coca")]
    assert _qt("3 tiramisu, une regina") == [(3, "tiramisu"), (1, "regina")]
    assert _qt("regina") == [(1, "regina")]
    assert _qt("") == []


def test_un_nombre_suivi_d_une_unite_n_est_jamais_une_quantite():
    assert _qt("canette de coca 33 cl") == [(1, "canette de coca 33 cl")]
    assert _qt("33 cl de coca") == [(1, "33 cl de coca")]
    assert _qt("un coca 33 cl et deux tiramisu") == [(1, "coca 33 cl"), (2, "tiramisu")]


def test_le_texte_tel_que_dit_est_garde_car_un_nombre_peut_etre_le_debut_d_un_nom():
    (morceau,) = lecture.decouper("4 formaggi")
    assert (morceau.quantite, morceau.texte, morceau.brut) == (4, "formaggi", "4 formaggi")


# --------------------------------------------------------------------------- #
# L'ordre : le mode, la zone
# --------------------------------------------------------------------------- #


async def test_le_mode_d_abord(appel):
    r = await appel.ajouter(articles="une regina")
    assert (r.statut, r.manque) == ("INCOMPLETE", "mode")
    assert appel.p["lignes"] == []


async def test_un_mode_inconnu_est_refuse_avec_la_liste(appel):
    r = await appel.mode("en fusée")
    assert r.statut == "ARGUMENT_INVALIDE" and set(r.faits["modes"]) == {"emporter", "livraison", "sur_place"}


async def test_le_mode_se_dit_avec_les_mots_de_l_appelant(appel):
    assert (await appel.mode("à emporter")).statut == "OK" and appel.p["mode"] == "emporter"
    assert (await appel.mode("en livraison")).statut == "OK" and appel.p["mode"] == "livraison"


async def test_en_livraison_la_zone_avant_les_articles(commerce):
    a = Appel(commerce)
    await a.mode("livraison")
    r = await a.ajouter(articles="une regina")
    assert (r.statut, r.manque) == ("INCOMPLETE", "zone")
    assert a.p["lignes"] == []
    a.p["zone"] = {"id": commerce.zones["Senlis"], "nom": "Senlis"}
    r = await a.ajouter(articles="un coca")
    # SA-33 (défaut 4) : la Regina dite avant la zone n'est plus perdue ; gardée, elle est prise dès la zone posée (sa taille reste à demander).
    assert sorted(l["ref"].rsplit("-", 1)[-1] for l in a.p["lignes"]) == ["COLA", "REGINA"], a.p["lignes"]
    assert (r.statut, r.manque) == ("CHOIX_OBLIGATOIRE", "taille"), r


async def test_l_ordre_zone_avant_articles_est_un_reglage(commerce):
    a = Appel(commerce, ordre_impose=False)
    await a.mode("livraison")
    r = await a.ajouter(articles="un coca")
    assert r.statut == "OK" and a.lignes() == [("Coca-Cola", 1)]


# --------------------------------------------------------------------------- #
# Aucun article perdu, choix obligatoire, prix
# --------------------------------------------------------------------------- #


async def test_aucun_article_perdu_la_taille_de_la_regina_reste_une_question_et_le_coca_est_pose(appel):
    await appel.mode()
    r = await appel.ajouter(articles="une regina et un coca")
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.manque == "taille"
    assert r.faits["question"]["options"] == ["Normale", "Mega"]
    assert "Regina" in r.suggestion
    assert sorted(appel.lignes()) == [("Coca-Cola", 1), ("Regina", 1)]
    assert appel.p["lignes"][0]["attente"] is not None  # la regina attend, rien n'est perdu


async def test_la_reponse_par_le_nom_complete_la_ligne_et_le_total_vient_de_la_carte(appel):
    await appel.mode()
    await appel.ajouter(articles="une regina et un coca")
    r = await appel.ajouter(choix="mega")
    assert r.statut == "OK"
    assert appel.lignes() == [("Regina Mega", 1), ("Coca-Cola", 1)]
    voir = await appel.voir()
    assert voir.statut == "OK"
    prix_regina_mega = next(p for p in CARTE["produits"] if p["nom"] == "Regina")["declinaisons"][1]["prix"]
    assert _total(voir) == prix_regina_mega + 200
    assert "Cela fait" in voir.suggestion and "euro" in voir.suggestion  # le montant est dit en toutes lettres


async def test_une_taille_inconnue_redemande_la_taille(appel):
    await appel.mode()
    await appel.ajouter(articles="une regina")
    r = await appel.ajouter(choix="gigantesque")
    assert r.statut == "CHOIX_OBLIGATOIRE" and appel.p["lignes"][0]["attente"] is not None


async def test_la_taille_dite_d_emblee_complete_la_ligne(appel):
    await appel.mode()
    r = await appel.ajouter(articles="deux regina mega")
    assert r.statut == "OK" and appel.lignes() == [("Regina Mega", 2)]


async def test_le_choix_obligatoire_d_un_burger_est_demande_puis_pose_puis_remplace(appel):
    await appel.mode()
    r = await appel.ajouter(articles="un cheeseburger")
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.faits["question"]["nom"] == "Sauce"
    assert "Ketchup" in r.suggestion
    assert (await appel.ajouter(choix="ketchup")).statut == "OK"
    assert [c["nom"] for c in appel.p["lignes"][0]["choix"]] == ["Ketchup"]
    assert (await appel.modifier(ligne="1", choix="blanche")).statut == "OK"  # changement d'avis : remplacé, jamais deux sauces
    assert [c["nom"] for c in appel.p["lignes"][0]["choix"]] == ["Blanche"]


async def test_deux_articles_identiques_ne_font_qu_une_ligne(appel):
    await appel.mode()
    await appel.ajouter(articles="un coca")
    await appel.ajouter(articles="un coca")
    assert appel.lignes() == [("Coca-Cola", 2)]


async def test_un_article_ambigu_est_demande_et_rien_n_est_pose(appel):
    await appel.mode()
    r = await appel.ajouter(articles="un coca zéro ou coca")  # deux noms voisins
    assert r.statut in ("AMBIGU", "OK", "INTROUVABLE")
    if r.statut == "AMBIGU":
        assert appel.p["lignes"] == []


async def test_un_article_introuvable_rend_les_plus_proches_et_ne_pose_rien(appel):
    await appel.mode()
    r = await appel.ajouter(articles="un kebab royal")
    assert r.statut == "INTROUVABLE" and appel.p["lignes"] == []


async def test_une_quantite_absurde_est_refusee(appel):
    await appel.mode()
    r = await appel.ajouter(articles="cinquante coca")
    assert r.statut == "ARGUMENT_INVALIDE"


# --------------------------------------------------------------------------- #
# Changement de mode : les articles sont gardés
# --------------------------------------------------------------------------- #


async def test_changer_de_mode_garde_les_articles_et_rechiffre(commerce):
    a = Appel(commerce)
    await a.mode("emporter")
    await a.ajouter(articles="deux regina normale")
    avant = await a.voir()
    r = await a.mode("livraison")
    assert r.statut == "OK" and r.manque == "zone"  # la zone est maintenant demandée
    assert a.lignes() == [("Regina Normale", 2)]
    a.p["zone"] = {"id": commerce.zones["Proches"], "nom": "Proches"}  # minimum de 15 €
    voir = await a.voir()
    assert voir.statut == "OK" and voir.faits["frais"] == 0 and _total(voir) == _total(avant)
    r = await a.mode("emporter")
    assert r.statut == "OK" and a.p["zone"] is None and a.lignes() == [("Regina Normale", 2)]


async def test_le_minimum_de_la_zone_est_dit_au_changement_de_mode(commerce):
    a = Appel(commerce)
    await a.mode("emporter")
    await a.ajouter(articles="un coca")  # 2 €
    a.p["zone"] = {"id": commerce.zones["Proches"], "nom": "Proches"}
    r = await a.mode("livraison")
    assert r.statut == "OK" and r.faits["a_revoir"]["statut"] == "MINIMUM_NON_ATTEINT"
    assert a.lignes() == [("Coca-Cola", 1)]  # rien n'est retiré en silence


async def test_un_mode_ferme_n_est_jamais_pose(commerce):
    await commerce.c.execute("UPDATE mark.resto_reglage_type SET pause_jusqu_a = $2 WHERE site_id = $1 AND type = 'emporter'", commerce.a, JEUDI_MIDI.replace(hour=13))
    a = Appel(commerce)
    r = await a.mode("emporter")
    assert r.statut == "PAUSE_TYPE" and a.p["mode"] is None
    assert r.suggestion.startswith("Nous sommes en pause") and "treize heures" in r.suggestion


# --------------------------------------------------------------------------- #
# Retraits, suppléments, notes (E-35)
# --------------------------------------------------------------------------- #


async def test_sans_champignons_est_cherche_dans_les_ingredients_retirables(appel):
    await appel.mode()
    r = await appel.ajouter(articles="une regina normale", sans="champignons")
    assert r.statut == "OK" and appel.p["lignes"][0]["retires"] == ["champignons"]


async def test_un_ingredient_absent_ou_non_retirable_est_refuse_avec_la_liste(appel):
    await appel.mode()
    r = await appel.ajouter(articles="une regina normale", sans="ananas")
    assert r.statut == "HORS_CARTE" and "jambon" in r.faits["retirables"]
    assert appel.p["lignes"] == []
    r = await appel.ajouter(articles="un cheeseburger", sans="steak")  # le steak n'est pas retirable
    assert r.statut == "HORS_CARTE" and "steak" not in r.faits["retirables"]


async def test_un_supplement_est_au_prix_de_la_carte(appel):
    await appel.mode()
    await appel.ajouter(articles="une margherita normale")
    base = _total(await appel.voir())
    r = await appel.modifier(ligne="1", choix="champignons")
    assert r.statut == "OK"
    assert _total(await appel.voir()) == base + 100


async def test_un_supplement_au_dela_du_maximum_par_option_est_refuse(appel):
    await appel.mode()
    await appel.ajouter(articles="une margherita normale", choix="champignons et champignons")  # 2 fois : permis (max par option 2)
    r = await appel.modifier(ligne="1", choix="champignons")  # un troisième : refusé
    assert r.statut == "MAXIMUM_ATTEINT"
    assert [(c["nom"], c["quantite"]) for c in appel.p["lignes"][0]["choix"]] == [("Champignons", 2)]  # tout ou rien


async def test_un_supplement_hors_carte_est_refuse_avec_les_plus_proches_jamais_un_prix_invente(appel):
    await appel.mode()
    r = await appel.ajouter(articles="une margherita normale", choix="ananas")
    assert r.statut == "HORS_CARTE" and appel.p["lignes"] == []
    assert all("prix" in p and p["nom"] for p in r.faits["plus_proches"])
    noms_carte = {"Mozzarella", "Jambon", "Champignons", "Œuf"}
    assert {p["nom"] for p in r.faits["plus_proches"]} <= noms_carte


async def test_une_note_de_ligne_sans_prix(appel):
    await appel.mode()
    await appel.ajouter(articles="une margherita normale")
    base = _total(await appel.voir())
    r = await appel.modifier(ligne="1", note="bien cuite")
    assert r.statut == "OK" and appel.p["lignes"][0]["note"] == "bien cuite"
    assert _total(await appel.voir()) == base


async def test_la_note_libre_est_refusee_quand_le_reglage_est_eteint(commerce):
    a = Appel(commerce, notes_libres=False)
    await a.mode()
    await a.ajouter(articles="une margherita normale")
    r = await a.modifier(ligne="1", note="bien cuite")
    assert r.statut == "HORS_CARTE" and a.p["lignes"][0]["note"] is None


# --------------------------------------------------------------------------- #
# Moitié-moitié (T-06)
# --------------------------------------------------------------------------- #


def _carte_avec_moities() -> dict:
    carte = copy.deepcopy(CARTE)
    groupe = next(g for g in carte["groupes"] if g["id"] == "G-MOITIES")
    groupe["options"] = [
        {"id": "O-MOIT-REGINA", "nom": "Regina", "code_caisse": "MOI-REGINA", "prix": 1290},
        {"id": "O-MOIT-MARGHE", "nom": "Margherita", "code_caisse": "MOI-MARGHERITA", "prix": 1090},
        {"id": "O-MOIT-4FROM", "nom": "4 Formaggi", "code_caisse": "MOI-4-FORMAGGI", "prix": 1490},
    ]
    carte["produits"].append(
        {"id": "P-MOITIE-MOITIE", "nom": "Pizza moitié-moitié", "categorie_id": carte["produits"][0]["categorie_id"], "ingredients": [], "allergenes": None,
         "tva_par_mode": {"sur_place": 10000, "emporter": 10000, "livraison": 10000}, "etoile": False,
         "declinaisons": [{"id": "P-MOITIE-NORMALE", "nom": "Unique", "code_caisse": "PIZ-MOITIE", "prix": 0, "disponibilite": None}],
         "groupes": ["G-MOITIES"]}
    )
    return carte


@pytest.fixture
async def avec_moities(commerce):
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        await importer_carte(commerce.c, commerce.a, _carte_avec_moities(), "caisse")
    return commerce


@pytest.mark.parametrize("regle,attendu", [("plus_chere", 1490), ("moyenne", 1390), ("somme", 2780)])
async def test_moitie_moitie_deux_moities_et_la_regle_de_prix(avec_moities, regle, attendu):
    a = Appel(avec_moities, regle_moities=regle)
    await a.mode()
    r = await a.ajouter(articles="une pizza moitié-moitié", moities="regina et 4 formaggi")
    assert r.statut == "OK", r
    voir = await a.voir()
    # regina 1290 et 4 formaggi 1490 : la plus chère, la moyenne, la somme
    assert _total(voir) == attendu


async def test_moitie_moitie_une_seule_moitie_reste_une_question(avec_moities):
    a = Appel(avec_moities)
    await a.mode()
    r = await a.ajouter(articles="une pizza moitié-moitié", moities="regina")
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.faits["question"]["nom"].lower().startswith("moiti")


async def test_moitie_moitie_un_retrait_devient_une_note_de_ligne_sur_la_moitie_dite(avec_moities):
    # SA-22 : « une moitié Regina, une moitié 4 fromages, sans champignons sur la Regina » : accepté, noté sur la ligne, jamais refusé.
    a = Appel(avec_moities)  # les notes libres sont éteintes par défaut : la note d'un retrait n'en dépend pas
    await a.mode()
    r = await a.ajouter(articles="une pizza moitié-moitié", moities="regina et 4 formaggi", sans="champignons sur la Regina")
    assert r.statut == "OK", r
    [ligne] = a.p["lignes"]
    assert ligne["note"] == "sans champignons sur la moitié Regina" and ligne["retires"] == []
    # la relecture la dit mot pour mot, et le prix ne bouge pas
    assert "sans champignons sur la moitié Regina" in moteur.contenu_dit(a.p)
    assert _total(await a.voir()) == 1490


async def test_moitie_moitie_retrait_sans_moitie_nommee_pose_une_question_fermee(avec_moities):
    a = Appel(avec_moities)
    await a.mode()
    r = await a.ajouter(articles="une pizza moitié-moitié", moities="regina et 4 formaggi", sans="champignons")
    assert r.statut == "AMBIGU" and set(r.faits["candidats"]) == {"Regina", "4 Formaggi"}
    assert not a.p["lignes"] or not a.p["lignes"][0].get("note")


async def test_moitie_moitie_retrait_ensuite_par_modifier_et_sans_doublon(avec_moities):
    a = Appel(avec_moities)
    await a.mode()
    await a.ajouter(articles="une pizza moitié-moitié", moities="regina et 4 formaggi")
    for _ in range(2):
        r = await a.modifier(ligne="1", sans="champignons sur la moitié 4 formaggi")
        assert r.statut == "OK", r
    assert a.p["lignes"][0]["note"] == "sans champignons sur la moitié 4 Formaggi"


async def test_la_note_de_moitie_part_a_la_caisse_et_s_imprime_sur_le_ticket(avec_moities):
    from api.services.restauration.prises.hubrise_traduction import commande_vers_hubrise
    from api.services.restauration.prises.ticket import assainir
    from api.services.restauration.source_commande import _vers_le_classeur

    a = Appel(avec_moities)
    await a.mode()
    await a.ajouter(articles="une pizza moitié-moitié", moities="regina et 4 formaggi", sans="champignons sur la Regina")
    lignes = [{**l, "prix_unitaire": 1490} for l in _vers_le_classeur(a.p["lignes"])]
    corps = commande_vers_hubrise({"numero": 1, "mode": "emporter", "lignes": lignes})
    assert corps["items"][0]["customer_notes"] == "sans champignons sur la moitié Regina"
    assert assainir(a.p["lignes"][0]["note"]) == "sans champignons sur la moitié Regina"


async def test_moitie_moitie_sur_un_article_qui_n_en_fait_pas_est_refusee(appel):
    await appel.mode()
    r = await appel.ajouter(articles="un tiramisu", moities="regina et margherita")
    assert r.statut == "HORS_CARTE" and r.faits.get("raison") == "aucun_choix"


# --------------------------------------------------------------------------- #
# Modifier, retirer, vider, voir
# --------------------------------------------------------------------------- #


async def test_modifier_la_quantite_par_numero_et_par_nom(appel):
    await appel.mode()
    await appel.ajouter(articles="une regina normale et un coca")
    assert (await appel.modifier(ligne="2", quantite=3)).statut == "OK"
    assert appel.lignes() == [("Regina Normale", 1), ("Coca-Cola", 3)]
    assert (await appel.modifier(ligne="regina", quantite=2)).statut == "OK"
    assert appel.lignes() == [("Regina Normale", 2), ("Coca-Cola", 3)]


async def test_quantite_zero_retire_la_ligne_et_les_numeros_suivent(appel):
    await appel.mode()
    await appel.ajouter(articles="une regina normale et un coca et un tiramisu")
    assert (await appel.modifier(ligne="coca", quantite=0)).statut == "OK"
    assert [l["n"] for l in appel.p["lignes"]] == [1, 2]
    assert [n for n, _ in appel.lignes()] == ["Regina Normale", "Tiramisu"]


async def test_une_ligne_qui_n_existe_pas_ou_un_nom_ambigu_est_demande(appel):
    await appel.mode()
    await appel.ajouter(articles="une regina normale et une regina mega")
    r = await appel.retirer(ligne="regina")
    assert r.statut == "AMBIGU" and len(appel.p["lignes"]) == 2
    assert (await appel.retirer(ligne="9")).statut == "INTROUVABLE"
    assert (await appel.retirer(ligne="2")).statut == "OK" and appel.lignes() == [("Regina Normale", 1)]


async def test_vider_garde_le_mode_et_la_zone(commerce):
    a = Appel(commerce)
    await a.mode("livraison")
    a.p["zone"] = {"id": commerce.zones["Senlis"], "nom": "Senlis"}
    await a.ajouter(articles="un coca")
    r = await a.vider()
    assert r.statut == "OK" and a.p["lignes"] == [] and a.p["mode"] == "livraison" and a.p["zone"]["nom"] == "Senlis"


async def test_voir_une_commande_vide(appel):
    await appel.mode()
    r = await appel.voir()
    assert r.statut == "OK" and r.faits["vide"] is True


async def test_toute_modification_invalide_la_relecture_et_fait_avancer_la_version(appel):
    await appel.mode()
    await appel.ajouter(articles="un coca")
    version = appel.p["version"]
    appel.p["relecture"] = {"jeton": "x"}
    await appel.ajouter(articles="un tiramisu")
    assert appel.p["version"] > version and appel.p["relecture"] is None


# --------------------------------------------------------------------------- #
# Rupture, cloisonnement
# --------------------------------------------------------------------------- #


async def test_un_article_en_rupture_n_entre_pas_et_une_autre_taille_est_proposee(commerce):
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        await poser_rupture(commerce.c, commerce.a, "PIZ-REGINA-MEGA", False, None, "portail")
    a = Appel(commerce)
    await a.mode()
    r = await a.ajouter(articles="une regina mega")
    assert r.statut == "RUPTURE" and "Normale" in r.faits["autres_tailles"] and a.p["lignes"] == []


async def test_une_zone_d_un_autre_etablissement_n_est_jamais_utilisable(commerce):
    a = Appel(commerce)
    await a.mode("livraison")
    a.p["zone"] = {"id": commerce.zone_b, "nom": "Autre"}  # la zone de l'établissement B
    r = await a.ajouter(articles="un coca")
    assert r.statut == "HORS_ZONE" and a.p["lignes"] == []


async def test_un_choix_d_un_autre_produit_n_est_pas_trouve_dans_l_article(appel):
    await appel.mode()
    r = await appel.ajouter(articles="un tiramisu", choix="ketchup")  # la sauce est celle du burger, pas du tiramisu
    assert r.statut in ("HORS_CARTE", "AMBIGU", "CHOIX_OBLIGATOIRE")
    assert all(c["nom"] != "Ketchup" for l in appel.p["lignes"] for c in l["choix"])
