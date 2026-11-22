"""[.mark] SA-18, lot A (C2) : le panier de l'appel reste sérialisable après l'enregistrement.

Le panier vit dans la fiche de l'appel, que la session clavier (et tout enregistrement de fiche) écrit en JSON. La source de
commande rend l'heure annoncée en ``datetime`` ; elle ne doit jamais entrer telle quelle dans le panier (erreur 500 après chaque
commande enregistrée aux essais du 17/11 : « Object of type datetime is not JSON serializable »).

Lot 4 de la partie 1 (D49) : réécrit sur la fiche (articles structurés, ``commande_sur_la_fiche`` ; réponse à la proposition par
``repondre_a_la_proposition`` ; la fin du contrat). Les tests de l'ancien chemin texte sont supprimés, chacun avec le test qui reprend son sens.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.services.commande import moteur, panier
from api.tests.mark import commande_sur_la_fiche as F
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE
from api.tests.mark.test_restauration_commande_finaliser import Appel


async def test_le_panier_enregistre_s_ecrit_en_json(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.confirmer()
    assert r.statut == "ENREGISTREE", r
    json.dumps(a.p)  # la fiche de l'appel s'écrit
    assert isinstance(a.p["enregistree"]["heure_annoncee"], str)  # ISO, jamais un objet date


async def test_un_second_oui_rend_la_meme_heure_en_texte(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    premier = await a.confirmer()
    second = await a.confirmer()
    assert second.statut == "DEJA_FAIT" and second.faits["numero"] == premier.faits["numero"]
    json.dumps(second.faits)


# --------------------------------------------------------------------------- #
# C3 : la réponse à « quelle taille ? » ne crée jamais de doublon
# --------------------------------------------------------------------------- #


async def _en_attente_de_la_taille(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await a.ajouter("regina")
    assert r.statut == "CHOIX_OBLIGATOIRE" and r.manque == "taille", r
    return a


async def test_la_taille_dite_au_pluriel_est_reconnue(commerce):
    a = await _en_attente_de_la_taille(commerce)
    r = await F.repondre(a.source, a.p, a.regles, "Normales")
    assert r.statut == "OK", r
    assert [l["nom"] for l in a.p["lignes"]] == ["Regina Normale"]


# test_l_article_renvoye_avec_la_taille_regle_la_ligne_en_attente : supprimé au lot 4 (D49), au contrat la taille répond à la question par ``reponse`` et ``ajouter`` additionne (E3) ; une fiche sans réponse pendant la question est refusée : sens repris par partie_1/test_l03_porte.py::test_reponse_manquante_refusee.


# test_un_ajout_complet_du_meme_article_remplace_la_ligne_en_attente : supprimé au lot 4 (D49), même raison (E3) ; sens repris par partie_1/test_l03_porte.py::test_reponse_manquante_refusee.


# test_la_question_reposee_ne_multiplie_pas_les_lignes_en_attente : supprimé au lot 4 (D49), même raison (E3) ; sens repris par partie_1/test_l03_porte.py::test_reponse_manquante_refusee et test_un_article_un_seul_ajout.


async def test_un_autre_article_garde_la_ligne_en_attente(commerce):
    a = await _en_attente_de_la_taille(commerce)
    r = await a.ajouter("coca")
    assert r.statut in ("OK", "CHOIX_OBLIGATOIRE"), r
    assert len(a.p["lignes"]) == 2  # le Coca s'ajoute, la Regina attend toujours sa taille


# --------------------------------------------------------------------------- #
# C5 : le oui à l'offre en plus (la réponse à la proposition, M44)
# --------------------------------------------------------------------------- #


async def test_le_oui_a_l_offre_en_plus_ajoute_l_article_propose(commerce):
    a = await Appel(commerce).pret(A("regina", 1, "Normale"))
    r = await a.finaliser()
    assert r.manque == "vente_en_plus", r
    nom = r.faits["proposition"]["nom"]
    r = await moteur.repondre_a_la_proposition(a.source, a.p, a.regles, a.appelant, "accepte")
    assert r.manque != "vente_en_plus", r
    assert any(l["nom"].startswith(nom) or nom in l["nom"] for l in a.p["lignes"]), a.p["lignes"]
    assert len(a.p["lignes"]) == 2


async def test_le_non_a_l_offre_en_plus_n_ajoute_rien(commerce):
    a = await Appel(commerce).pret(A("regina", 1, "Normale"))
    assert (await a.finaliser()).manque == "vente_en_plus"
    r = await moteur.repondre_a_la_proposition(a.source, a.p, a.regles, a.appelant, "refuse")
    assert r.manque == "relecture", r  # la proposition de la fin mène à la suite de la fin : le récapitulatif
    assert len(a.p["lignes"]) == 1


async def test_un_en_plus_sans_offre_en_cours_est_ignore(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret(A("regina", 1, "Normale"))
    await moteur.repondre_a_la_proposition(a.source, a.p, a.regles, a.appelant, "accepte")
    assert len(a.p["lignes"]) == 1  # aucune proposition en cours : rien n'est ajouté
    r = await a.finaliser()
    assert r.manque in ("relecture", "reponse_a_la_relecture"), r  # le récapitulatif (déjà dit s'il l'a été)


# test_les_articles_dits_a_finaliser_sont_ajoutes : supprimé au lot 4 (D49), la fin n'a plus de case ``articles`` : ``ajouter`` est la seule case qui additionne (E3) ; sens repris par partie_1/test_l03_porte.py::test_un_article_un_seul_ajout.


# --------------------------------------------------------------------------- #
# C4 : les deux moitiés d'un article (la case ``moities`` de la fiche)
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


async def test_deux_moities_dites_dans_les_articles_font_une_seule_ligne(carte_avec_deux_moities, commerce):
    # les tournures (« moitié Regina moitié Pescatore »…) sont lues par le modèle (D1) ; le code reçoit les deux moitiés dans leur case
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await a.ajouter(A("pizza moitié-moitié", moities=["Regina", "Pescatore"]))
    assert r.statut == "OK", r
    assert len(a.p["lignes"]) == 1 and panier.a_completer(a.p) == []
    ligne = a.p["lignes"][0]
    assert ligne["ref"] == "P-DEUX-MOITIES"
    assert sorted(c["nom"] for c in ligne["choix"]) == ["Pescatore", "Regina"]


async def test_une_moitie_inconnue_ne_cree_aucune_ligne(carte_avec_deux_moities, commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    for _ in range(3):
        r = await a.ajouter(A("pizza moitié-moitié", moities=["Regina", "Zorglub"]))
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
    r = await a.finaliser()  # sans mode, la fin le demande d'abord
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
    r = await a.finaliser()
    assert r.manque == "relecture", r
    assert "on retire" not in r.suggestion and "on ajoute" not in r.suggestion, r.suggestion
    assert r.suggestion.startswith("Coca-Cola passe à deux"), r.suggestion


async def test_la_relecture_ne_parle_pas_d_ecran(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.jusqu_a_la_relecture()
    assert "affiche" not in r.suggestion
    numero = await a.finaliser(confirmer=True, prenom="Alice", moyen="carte")  # après son accord : le numéro qui s'affiche, proposé
    assert numero.manque == "confirmer_numero" and "affiche" not in numero.suggestion and "pour vous joindre en cas de problème" in numero.suggestion


def test_un_appelant_presse_n_entend_ni_offert_ni_remise():
    source = SimpleNamespace(libelles_des_modes={"emporter": "à emporter"}, libelles_des_moyens={"carte": "par carte"})
    chiffre = moteur.Resultat(
        "OK", {"total": 1490, "remises": [{"ref": "R1", "nom": "Une boisson offerte"}], "offerts": [{"quantite": 1, "nom": "Coca-Cola"}]}
    )

    def relecture(presse: bool) -> str:
        p = panier.nouveau()
        p.update(
            mode="emporter", presse=presse,
            lignes=[{"n": 1, "ref": "X", "nom": "Regina Normale", "code": "C", "quantite": 1, "choix": [], "retires": [], "note": None, "attente": None}],
        )
        return moteur.recapituler(source, p, chiffre).suggestion

    assert "offert" in relecture(False)
    assert "offert" not in relecture(True)


# test_ce_qui_est_dit_pendant_l_offre_en_plus_n_est_pas_redemande : supprimé au lot 4 (D49), la porte garde les cases de fin dites (``fin_dite``) et les repasse à chaque fin ; sens repris par banc_a/test_c11_c12_c13_reglement_hors_zone_recherche.py::test_c11_1_2639_le_reglement_dit_d_emblee_n_est_pas_redemande.


async def test_un_numero_dit_en_lettres_est_lu(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret(A("regina", 1, "Normale"))
    await a.jusqu_a_la_relecture()
    r = await a.confirmer(telephone="0 six douze trente-quatre cinquante-six soixante-dix-huit")
    assert r.manque == "confirmer_numero_dicte", r  # DC10 : le numéro dicté est relu, il attend son « oui »
    moteur.repondre_au_numero_dicte(a.p, "accepte")
    r = await a.confirmer()
    assert r.statut == "ENREGISTREE", r  # le numéro est pris
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


# test_un_non_mis_dans_les_articles_de_finaliser_n_est_pas_un_article : supprimé au lot 4 (D49), la fin n'a plus de case ``articles`` ; « non » répond à la proposition : sens repris par partie_1/test_l03_porte.py::test_non_merci_ne_prend_pas_la_proposition.


async def test_le_mode_choisi_sans_article_dit_que_les_articles_manquent(commerce):
    """Après le mode, un panier vide le dit (manque « articles ») : le modèle enchaîne sur les articles déjà dits au lieu de les croire pris."""
    a = Appel(commerce)
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert (r.statut, r.manque, r.suggestion) == ("OK", "articles", "")  # M13 : la phrase est celle de ``phrases_du_manque``
    await a.ajouter("coca")
    r = await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    assert r.manque != "articles"  # des articles sont pris : rien ne manque


async def test_deux_moities_et_un_autre_article_dans_la_meme_phrase(carte_avec_deux_moities, commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    await a.ajouter(A("pizza moitié-moitié", moities=["Regina", "Pescatore"]), "regina")
    assert [l["ref"] for l in a.p["lignes"]][0] == "P-DEUX-MOITIES" and len(a.p["lignes"]) == 2


# test_finaliser_ne_double_jamais_les_articles_deja_au_panier : supprimé au lot 4 (D49), la fin n'a plus de case ``articles`` (E3) ; sens repris par partie_1/test_l03_porte.py::test_un_article_un_seul_ajout.


async def test_le_oui_a_la_proposition_redit_avec_son_nom_ne_l_ajoute_qu_une_fois(commerce):
    a = Appel(commerce)
    await a.pret(A("regina", 1, "Normale"))
    r = await a.finaliser()
    nom = r.faits["proposition"]["nom"]
    await moteur.repondre_a_la_proposition(a.source, a.p, a.regles, a.appelant, "accepte", variante=nom)
    assert sum(l["quantite"] for l in a.p["lignes"] if l["nom"].startswith(nom)) == 1


async def test_le_oui_avec_une_autre_option_de_la_proposition_la_prend_a_sa_place(commerce):
    """M73 (appels 2560, 2568) : « oui, mais plutôt X », X parmi les options de la proposition : X remplace l'article proposé, une seule fois."""
    a = Appel(commerce)
    await a.pret(A("regina", 1, "Normale"))
    r = await a.finaliser()
    nom = r.faits["proposition"]["nom"]
    options = [c for c in a.p["proposition_en_plus"]["choix"] or [] if c != nom]  # les options de la proposition, gardées par le code
    if not options:
        pytest.skip("le catalogue d'essai ne propose pas d'autre option")
    await moteur.repondre_a_la_proposition(a.source, a.p, a.regles, a.appelant, "accepte", variante=options[0])
    noms = [l["nom"] for l in a.p["lignes"]]
    assert options[0] in noms and nom not in noms, noms  # noms exacts : « Coca-Cola Zéro » commence par « Coca-Cola »
    assert sum(l["quantite"] for l in a.p["lignes"] if l["nom"] == options[0]) == 1


async def test_un_article_et_son_choix_dits_ensemble_dans_une_phrase_de_plusieurs_articles(commerce):
    a = Appel(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await a.ajouter(A("regina", 1, "Normale"), A("tiramisu", supplements=["classic"]))
    assert r.statut == "OK", r
    tiramisu = next(l for l in a.p["lignes"] if l["nom"].startswith("Tiramisu"))
    assert [c["nom"] for c in tiramisu["choix"]] == ["Classic"] and panier.a_completer(a.p) == []
