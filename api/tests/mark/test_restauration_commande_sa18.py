"""[.mark] SA-18, lot A (C2) : le panier de l'appel reste sérialisable après l'enregistrement.

Le panier vit dans la fiche de l'appel, que la session clavier (et tout enregistrement de fiche) écrit en JSON. La source de
commande rend l'heure annoncée en ``datetime`` ; elle ne doit jamais entrer telle quelle dans le panier (erreur 500 après chaque
commande enregistrée aux essais du 17/11 : « Object of type datetime is not JSON serializable »).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.services.commande import moteur, panier
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE
from api.tests.mark.test_restauration_commande_finaliser import Appel


async def test_le_panier_enregistre_s_ecrit_en_json(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.finaliser(confirmer=True)
    assert r.statut == "ENREGISTREE", r
    json.dumps(a.p)  # la fiche de l'appel s'écrit
    assert isinstance(a.p["enregistree"]["heure_annoncee"], str)  # ISO, jamais un objet date


async def test_un_second_oui_rend_la_meme_heure_en_texte(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    premier = await a.finaliser(confirmer=True)
    second = await a.finaliser(confirmer=True)
    assert second.statut == "DEJA_FAIT" and second.faits["numero"] == premier.faits["numero"]
    json.dumps(second.faits)


# --------------------------------------------------------------------------- #
# C3 : la réponse à « quelle taille ? » ne crée jamais de doublon
# --------------------------------------------------------------------------- #


async def _en_attente_de_la_taille(commerce, articles="une regina"):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await moteur.ajouter(a.source, a.p, a.regles, articles=articles)
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.manque == "taille", r
    return a


async def test_la_taille_dite_au_pluriel_est_reconnue(commerce):
    a = await _en_attente_de_la_taille(commerce)
    r = await moteur.ajouter(a.source, a.p, a.regles, choix="Normales")
    assert r.statut == "OK", r
    assert [l["nom"] for l in a.p["lignes"]] == ["Regina Normale"]


async def test_l_article_renvoye_avec_la_taille_regle_la_ligne_en_attente(commerce):
    a = await _en_attente_de_la_taille(commerce)
    r = await moteur.ajouter(a.source, a.p, a.regles, articles="une regina", choix="Normale")
    assert r.statut == "OK", r
    assert [(l["nom"], l["quantite"]) for l in a.p["lignes"]] == [("Regina Normale", 1)]  # une seule ligne, jamais de doublon en attente
    assert panier.a_completer(a.p) == []


async def test_un_ajout_complet_du_meme_article_remplace_la_ligne_en_attente(commerce):
    a = await _en_attente_de_la_taille(commerce)
    r = await moteur.ajouter(a.source, a.p, a.regles, articles="une regina normale")
    assert r.statut == "OK", r
    assert [(l["nom"], l["quantite"]) for l in a.p["lignes"]] == [("Regina Normale", 1)]


async def test_la_question_reposee_ne_multiplie_pas_les_lignes_en_attente(commerce):
    a = await _en_attente_de_la_taille(commerce)
    for _ in range(3):
        r = await moteur.ajouter(a.source, a.p, a.regles, articles="une regina")
        assert r.statut == "CHOIX_OBLIGATOIRE"
    assert len(a.p["lignes"]) == 1 and a.p["lignes"][0]["attente"]


async def test_un_autre_article_garde_la_ligne_en_attente(commerce):
    a = await _en_attente_de_la_taille(commerce)
    r = await moteur.ajouter(a.source, a.p, a.regles, articles="un coca")
    assert r.statut in ("OK", "CHOIX_OBLIGATOIRE"), r
    assert len(a.p["lignes"]) == 2  # le Coca s'ajoute, la Regina attend toujours sa taille


# --------------------------------------------------------------------------- #
# C5 : le oui à l'offre en plus, et les articles dits à `finaliser`
# --------------------------------------------------------------------------- #


async def test_le_oui_a_l_offre_en_plus_ajoute_l_article_propose(commerce):
    a = await Appel(commerce).pret("une regina normale")
    r = await a.finaliser()
    assert r.manque == "vente_en_plus", r
    nom = r.faits["proposition"]["nom"]
    r = await a.finaliser(en_plus=True)
    assert r.manque != "vente_en_plus", r
    assert any(l["nom"].startswith(nom) or nom in l["nom"] for l in a.p["lignes"]), a.p["lignes"]
    assert len(a.p["lignes"]) == 2


async def test_le_non_a_l_offre_en_plus_n_ajoute_rien(commerce):
    a = await Appel(commerce).pret("une regina normale")
    assert (await a.finaliser()).manque == "vente_en_plus"
    r = await a.finaliser(en_plus=False)
    assert r.manque == "prenom", r
    assert len(a.p["lignes"]) == 1


async def test_un_en_plus_sans_offre_en_cours_est_ignore(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret("une regina normale")
    r = await a.finaliser(en_plus=True)
    assert r.manque == "prenom" and len(a.p["lignes"]) == 1


async def test_les_articles_dits_a_finaliser_sont_ajoutes(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await a.finaliser(articles="une regina normale")
    assert r.manque == "prenom", r
    assert [l["nom"] for l in a.p["lignes"]] == ["Regina Normale"]
    json.dumps(a.p)


# --------------------------------------------------------------------------- #
# C4 : « <article> moitié A moitié B » dit dans les articles
# --------------------------------------------------------------------------- #

PRODUIT_DEUX_MOITIES = {
    "id": "P-DEUX-MOITIES", "nom": "Pizza moitié-moitié", "categorie_id": "pizzas-tomate", "description": None, "ingredients": [],
    "allergenes": None, "tva_par_mode": {"sur_place": 10000, "emporter": 10000, "livraison": 10000}, "etoile": False,
    "declinaisons": [{"id": "P-DEUX-MOITIES-MEGA", "nom": "Mega", "code_caisse": "PIZ-MOITIE-MOITIE-MEGA", "prix": 0, "disponibilite": None}],
    "groupes": ["G-MOITIES"],
}


@pytest.fixture
def carte_avec_deux_moities(monkeypatch):
    """La carte de référence + un article « deux moitiés » dont le groupe propose Regina et Pescatore (comme la carte de Casa Italia)."""
    groupes = []
    for g in CARTE["groupes"]:
        if g.get("role") == "moities":
            options = [
                {"id": f"G-MOITIES-{c}", "groupe_id": g["id"], "nom": nom, "code_caisse": f"MOI-{c}", "prix": prix, "par_defaut": False, "retirable": False}
                for c, nom, prix in (("REGINA", "Regina", 2090), ("PESCATORE", "Pescatore", 2190))
            ]
            g = {**g, "options": options, "s_applique_a": None}
        groupes.append(g)
    monkeypatch.setitem(CARTE, "produits", [*CARTE["produits"], PRODUIT_DEUX_MOITIES])
    monkeypatch.setitem(CARTE, "groupes", groupes)


@pytest.mark.parametrize("phrase", ["une pizza moitié Regina moitié Pescatore", "pizza moitié Regina et moitié Pescatore", "une moitié Regina, moitié Pescatore", "une moitié-moitié Regina Pescatore"])
async def test_deux_moities_dites_dans_les_articles_font_une_seule_ligne(carte_avec_deux_moities, commerce, phrase):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await moteur.ajouter(a.source, a.p, a.regles, articles=phrase)
    assert r.statut == "OK", r
    assert len(a.p["lignes"]) == 1 and panier.a_completer(a.p) == []
    ligne = a.p["lignes"][0]
    assert ligne["ref"] == "P-DEUX-MOITIES"
    assert sorted(c["nom"] for c in ligne["choix"]) == ["Pescatore", "Regina"]


async def test_une_moitie_inconnue_ne_cree_aucune_ligne(carte_avec_deux_moities, commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    for _ in range(3):
        r = await moteur.ajouter(a.source, a.p, a.regles, articles="une pizza moitié Regina moitié Zorglub")
        assert r.statut != "OK"
    assert a.p["lignes"] == []  # rien n'est posé sur un refus, jamais de ligne qui s'accumule


# --------------------------------------------------------------------------- #
# C13 : jamais un mode que l'établissement n'a pas réglé
# --------------------------------------------------------------------------- #


async def _eteindre(commerce, type_):
    await commerce.c.execute(
        "INSERT INTO mark.resto_reglage_type (site_id, type, ouvert) VALUES ($1, $2, false) ON CONFLICT (site_id, type) DO UPDATE SET ouvert = false",
        commerce.a, type_,
    )


async def test_un_mode_eteint_n_est_jamais_propose(commerce):
    await _eteindre(commerce, "sur_place")
    a = Appel(commerce)
    assert a.source.modes == ("emporter", "livraison", "sur_place")  # avant lecture des réglages : la liste d'origine
    await a.source.charger_les_modes()
    assert a.source.modes == ("emporter", "livraison")
    r = await moteur.ajouter(a.source, a.p, a.regles, articles="une regina")
    assert (r.statut, r.manque) == ("INCOMPLETE", "mode")
    assert r.faits["modes"] == ["emporter", "livraison"] and "sur place" not in r.suggestion
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "sur place")
    assert r.statut == "ARGUMENT_INVALIDE" and "sur_place" not in r.faits["modes"]


async def test_un_type_sans_ligne_ou_ouvert_reste_propose(commerce):
    a = Appel(commerce)  # la fiche de test ne règle que l'emporter et la livraison, ouverts : aucun type éteint
    await a.source.charger_les_modes()
    assert a.source.modes == ("emporter", "livraison", "sur_place")


async def test_tous_les_types_eteints_garde_la_liste_d_origine(commerce):
    for type_ in ("emporter", "livraison", "sur_place"):
        await _eteindre(commerce, type_)
    a = Appel(commerce)
    await a.source.charger_les_modes()
    assert a.source.modes == ("emporter", "livraison", "sur_place")  # jamais une liste vide : le refus se dit par l'état fermé


# --------------------------------------------------------------------------- #
# C6 : la relecture après une correction, au téléphone, et à un appelant pressé
# --------------------------------------------------------------------------- #


async def test_la_relecture_apres_une_correction_ne_dit_que_ce_qui_change_meme_apres_un_aller_retour_json(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    a.p.update(json.loads(json.dumps(a.p)))  # la fiche s'écrit entre deux tours : tuples devenus listes
    await moteur.modifier(a.source, a.p, a.regles, ligne="coca", quantite=2)
    r = await a.finaliser(prenom="Alice", moyen="carte")
    assert r.manque == "relecture", r
    assert "on retire" not in r.suggestion and "on ajoute" not in r.suggestion, r.suggestion
    assert r.suggestion.startswith("Coca-Cola passe à deux"), r.suggestion


async def test_la_relecture_ne_parle_pas_d_ecran(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.jusqu_a_la_relecture()
    assert "affiche" not in r.suggestion and "depuis lequel vous appelez" in r.suggestion


def test_un_appelant_presse_n_entend_ni_offert_ni_remise():
    source = SimpleNamespace(libelles_des_modes={"emporter": "à emporter"}, libelles_des_moyens={"carte": "par carte"})
    chiffre = moteur.Resultat(
        "OK", {"total": 1490, "remises": [{"ref": "R1", "nom": "Une boisson offerte"}], "offerts": [{"quantite": 1, "nom": "Coca-Cola"}]}
    )
    paiement = {"moyens": [{"moyen": "carte", "montant": 1490}], "rendu_sur": None, "monnaie": 0}

    def relecture(presse: bool) -> str:
        p = panier.nouveau()
        p.update(
            mode="emporter", presse=presse,
            lignes=[{"n": 1, "ref": "X", "nom": "Regina Normale", "code": "C", "quantite": 1, "choix": [], "retires": [], "note": None, "attente": None}],
        )
        return moteur._ecrire_la_relecture(source, p, chiffre, paiement, False).suggestion

    assert "offert" in relecture(False)
    assert "offert" not in relecture(True)


async def test_ce_qui_est_dit_pendant_l_offre_en_plus_n_est_pas_redemande(commerce):
    """Prénom, numéro et règlement dits dans l'appel qui reçoit l'offre en plus sont gardés (essais du 17/11 : le moyen de paiement était perdu)."""
    a = await Appel(commerce).pret("une regina normale")
    r = await a.finaliser(prenom="Alice", moyen="carte", telephone="06 12 34 56 78")
    assert r.manque == "vente_en_plus", r
    r = await a.finaliser(en_plus=False)
    assert r.manque == "relecture", r  # ni le prénom, ni le numéro, ni le règlement ne sont redemandés


async def test_un_numero_dit_en_lettres_est_lu(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret("une regina normale")
    r = await a.finaliser(prenom="Alice", telephone="0 six douze trente-quatre cinquante-six soixante-dix-huit")
    assert r.manque == "paiement", r  # le numéro est pris : on passe au règlement
    assert a.p["client"]["telephone"] == "+33612345678"


def test_la_taille_dite_avec_le_mot_taille_retient_l_article():
    """« Regina taille normale » rendait AMBIGU avec « Regina » pour seul candidat (essais du 17/11) ; la variante dite est lue."""
    from api.db.bases_clients.recherche_liste import Element
    from api.db.bases_clients.recherche_liste_moteur import chercher_dans_l_index, construire_index

    elements = [Element("P-REGINA", "Regina", (), "Pizzas", ("Normale", "Mega")), Element("P-MARGHERITA", "Margherita", (), "Pizzas", ("Normale", "Mega"))]
    index = construire_index(elements)
    for dit in ("Regina taille normale", "une Regina en taille normale", "Regina format mega", "regina normale"):
        r = chercher_dans_l_index(index, dit)
        assert (r["statut"], r["retenu"]) == ("RETENU", "P-REGINA"), (dit, r)


async def test_un_non_mis_dans_les_articles_de_finaliser_n_est_pas_un_article(commerce):
    """Essai du 17/11 : le modèle met la réponse « non » dans ``articles`` ; le catalogue ne la connaît pas, la commande continue."""
    a = await Appel(commerce, vente_en_plus=False).pret("une regina normale")
    r = await a.finaliser(articles="Non")
    assert r.manque == "prenom" and len(a.p["lignes"]) == 1, r


async def test_le_mode_choisi_sans_article_dit_que_les_articles_manquent(commerce):
    """Après le mode, un panier vide le dit (manque « articles ») : le modèle enchaîne sur les articles déjà dits au lieu de les croire pris."""
    a = Appel(commerce)
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert (r.statut, r.manque, r.suggestion) == ("OK", "articles", "Qu'est-ce que je vous mets ?")
    await moteur.ajouter(a.source, a.p, a.regles, articles="un coca")
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    assert r.manque != "articles"  # des articles sont pris : rien ne manque


async def test_deux_moities_et_un_autre_article_dans_la_meme_phrase(carte_avec_deux_moities, commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    await moteur.ajouter(a.source, a.p, a.regles, articles="une moitié-moitié Regina Pescatore et une Regina")
    assert [l["ref"] for l in a.p["lignes"]][0] == "P-DEUX-MOITIES" and len(a.p["lignes"]) == 2


async def test_finaliser_ne_double_jamais_les_articles_deja_au_panier(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    await moteur.ajouter(a.source, a.p, a.regles, articles="deux regina normale")
    avant = [(l["ref"], l["quantite"]) for l in a.p["lignes"]]
    await moteur.finaliser(a.source, a.p, a.regles, a.appelant, articles="deux regina normale", prenom="Alice", moyen="carte")
    assert [(l["ref"], l["quantite"]) for l in a.p["lignes"]] == avant


async def test_le_oui_a_la_proposition_redit_avec_son_nom_ne_l_ajoute_qu_une_fois(commerce):
    a = Appel(commerce)
    await a.pret("une regina normale")
    r = await a.finaliser()
    nom = r.faits["proposition"]["nom"]
    await a.finaliser(articles=nom, en_plus=True, prenom="Alice", moyen="carte")
    assert sum(l["quantite"] for l in a.p["lignes"] if l["nom"].startswith(nom)) == 1


async def test_un_article_et_son_choix_dits_ensemble_dans_une_phrase_de_plusieurs_articles(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await moteur.ajouter(a.source, a.p, a.regles, articles="une regina normale et un tiramisu classic")
    assert r.statut == "OK", r
    tiramisu = next(l for l in a.p["lignes"] if l["nom"].startswith("Tiramisu"))
    assert [c["nom"] for c in tiramisu["choix"]] == ["Classic"] and panier.a_completer(a.p) == []
