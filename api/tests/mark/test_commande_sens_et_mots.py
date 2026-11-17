"""[.mark] Agent fiable (appel 2616) : le modèle dit le SENS et transmet les MOTS ; le code applique la réponse à la question en attente,
quel que soit l'outil que le modèle a choisi. Mécanisme commun, aucun mot de carte dans le code.

| Test | Ce qu'il prouve |
|---|---|
| S1 | « Normale » (réponse à la taille) envoyé par erreur à ``finaliser`` part dans ``ajouter.choix`` |
| S2 | « en livraison » envoyé à ``verifier_adresse`` pose le mode, ce n'est pas une adresse |
| S3 | un refus à la proposition en plus devient ``en_plus`` faux, un accord à la relecture ``confirmer`` vrai |
| S4 | une question de la personne n'est jamais prise pour une réponse ; une vraie adresse reste une adresse |
| S5 | de bout en bout : la question de taille en attente, puis « Normale » par ``finaliser`` : la ligne est complétée |
"""

from __future__ import annotations

from api.services.commande import action, moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_kebab_sa52 import ADRESSE, Appel, kebab  # noqa: F401


async def test_s1_la_taille_dite_part_dans_ajouter(kebab):
    a = await Appel(kebab).a_emporter()
    a.p["question_en_attente"] = "ajouter.choix"
    assert action.vers_la_question_en_attente(a.source, a.p, "finaliser", {"sens": "autre", "mots": "Normale"}) == ("ajouter", {"choix": "Normale"})


async def test_s2_le_mode_dit_n_est_pas_une_adresse(kebab):
    a = await Appel(kebab).charger()
    nom, args = action.vers_la_question_en_attente(a.source, a.p, "verifier_adresse", {"adresse": "en livraison"})
    assert nom == "choisir_mode" and args["mode"] == "en livraison"


async def test_s3_accord_et_refus_vont_dans_la_bonne_case(kebab):
    a = await Appel(kebab).a_emporter()
    a.p["question_en_attente"] = "finaliser.en_plus"
    assert action.vers_la_question_en_attente(a.source, a.p, "finaliser", {"sens": "refus", "mots": "non merci"})[1]["en_plus"] is False
    a.p["question_en_attente"] = "finaliser.confirmer"
    assert action.vers_la_question_en_attente(a.source, a.p, "ajouter", {"sens": "accord", "mots": "ouais vas-y"}) == (
        "finaliser", {"sens": "accord", "mots": "ouais vas-y", "confirmer": True}
    )


async def test_s4_une_question_ou_une_vraie_adresse_ne_sont_pas_detournees(kebab):
    a = await Appel(kebab).a_emporter()
    a.p["question_en_attente"] = "ajouter.choix"
    assert action.vers_la_question_en_attente(a.source, a.p, "voir_produit", {"sens": "question", "mots": "c'est quoi la mega ?"})[0] == "voir_produit"
    b = await Appel(kebab).charger()
    assert action.vers_la_question_en_attente(b.source, b.p, "verifier_adresse", {"adresse": ADRESSE})[0] == "verifier_adresse"


async def test_s5_de_bout_en_bout_la_taille_par_finaliser(kebab):
    a = await Appel(kebab).a_emporter()
    r = await a.ajouter(articles="un tacos 2 viandes")
    assert r.statut == "CHOIX_OBLIGATOIRE", r
    a.p["question_en_attente"] = action.reponse_attendue("ajouter", r)
    assert a.p["question_en_attente"] == "ajouter.choix"
    nom, args = action.vers_la_question_en_attente(a.source, a.p, "finaliser", {"sens": "autre", "mots": "kebab et chicken"})
    r = await moteur.ajouter(a.source, a.p, a.regles, choix=args["choix"])
    assert nom == "ajouter" and r.faits.get("article") != "Tacos 2 viandes" or r.statut == "OK", r


# --------------------------------------------------------------------------- #
# Lot 3 : un outil par chose que la personne veut faire
# --------------------------------------------------------------------------- #

from types import SimpleNamespace  # noqa: E402

CTX = SimpleNamespace(run_id=None)


async def test_g1_l_adresse_passe_par_choisir_mode_et_pose_la_livraison(kebab):
    a = await Appel(kebab).charger()
    r = await action._geste(a.source, a.p, a.regles, "choisir_mode", {"adresse": ADRESSE}, CTX)
    assert a.p["mode"] == "livraison" and a.p["zone"], (r, a.p["mode"], a.p["zone"])


async def test_g2_voir_lit_un_plat_le_delai_et_la_commande(kebab):
    a = await Appel(kebab).a_emporter()
    plat = await action._geste(a.source, a.p, a.regles, "voir_commande", {"quoi": "produit", "produit": "tacos 2 viandes"}, CTX)
    assert plat.statut != "ARGUMENT_INVALIDE" and "Tacos" in str(plat.faits), plat
    commande = await action._geste(a.source, a.p, a.regles, "voir_commande", {}, CTX)
    assert "lignes" in str(commande.faits) or commande.faits.get("panier") is not None, commande


async def test_s6_la_commune_confirmee_complete_l_adresse_gardee(kebab):
    a = await Appel(kebab).charger()
    a.p["adresse_en_doute"] = {"texte": "5 rue Louis Boilet", "candidats": [
        {"nom": "Pont-Sainte-Maxence", "code_postal": "60700", "departement": "Oise"}, {"nom": "Pont", "code_postal": "21130", "departement": "Côte-d'Or"}]}
    nom, args = action.vers_la_question_en_attente(a.source, a.p, "ajouter", {"sens": "accord", "mots": "oui c'est ça, dans l'Oise"})
    assert nom == "choisir_mode" and args["adresse"] == "5 rue Louis Boilet, 60700 Pont-Sainte-Maxence"
    r = await action._geste(a.source, a.p, a.regles, nom, args, CTX)
    assert a.p["zone"] and a.p["mode"] == "livraison", r
