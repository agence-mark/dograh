"""[.mark] Chantier Partie 1, lot 3 : la porte d'entrée de la commande (``services/commande/porte.py``) et ses briques communes.

Les essais passent par la vraie porte et la vraie source (montage ``porte_essai.py``), sur la carte de Casa Italia du banc A, sans modèle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.services.actions_communes import barrieres as B
from api.services.actions_communes.cases_liees import (
    DEPEND_DE_TOUT,
    LIEES,
    cases_ecartees,
)
from api.services.actions_communes.forme import valeur_dite_par_elle
from api.services.actions_communes.idempotence import cle_d_idempotence
from api.services.actions_communes.plafonds import (
    deux_questions_au_plus,
    plafond_d_operations,
)
from api.services.commande import porte
from api.tests.mark.partie_1.egalite_b12 import CONVERSATIONS, ECARTS_DE_LA_CUISINE, REPONSES, ecarts_de_la_conversation

API = Path(__file__).resolve().parents[3]


async def _a_emporter(e):
    return await e.tour("à emporter", mode_de_retrait="emporter")


async def _une_margherita(e, parole: str = "une margherita normale"):
    """Une Margherita Normale, puis « non merci » à la vente en plus qui suit le premier article (s'il y en a une)."""
    r = await e.tour(parole, ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p.get("question") or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    return r


async def _jusqu_a_la_relecture(e):
    """Une margherita à emporter, puis « non merci, c'est tout » (avec sa réponse à la proposition en attente), jusqu'à la question de relecture."""
    await _a_emporter(e)
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    for _ in range(3):
        q = e.p.get("question") or {}
        if q.get("type") == "relecture":
            break
        cases = {"c_est_tout": True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("type") == "proposition" else {})}
        await e.tour("non merci, c'est tout", **cases)
    assert (e.p.get("question") or {}).get("type") == "relecture", e.retours[-1]
    return e.p["question"]


# --------------------------------------------------------------------------- l'ordre, sans base


def test_ordre_des_cases_comme_au_banc():
    """L'ordre de ``fiche_vers_items`` (banc B5), aux noms de la version finale ; jamais celui où le modèle écrit ses cases."""
    fiche = {"c_est_tout": True, "prenom": "Léa", "ajouter": [{"article": "x", "quantite": 1}], "mode_de_retrait": "emporter", "reponse": {"question_id": "Q-1"},
             "retirer_article": [1], "changer_quantite": [{"ligne": 2}], "annuler_la_commande": True, "vider_le_panier": True, "heure": "midi"}
    assert porte.ordre_des_cases(fiche) == ["vider_le_panier", "annuler_la_commande", "reponse", "retirer_article", "changer_quantite", "ajouter",
                                            "mode_de_retrait", "heure", "prenom", "c_est_tout"]


def test_cases_liees_la_table():
    assert LIEES == (("mode_de_retrait", "adresse", "commune", "consigne_livreur"), ("moyen_de_paiement", "rendu_sur", "part", "moyen_reste"))  # C2 bis : le règlement partagé est du bloc
    assert cases_ecartees(["adresse"]) >= {"mode_de_retrait", "commune", "consigne_livreur", *DEPEND_DE_TOUT}
    assert "ajouter" not in cases_ecartees(["adresse"])
    assert cases_ecartees(["rendu_sur"]) >= {"moyen_de_paiement"} and cases_ecartees([]) == set()


def test_plafond_six_articles_sans_base():
    assert plafond_d_operations({"ajouter": [{"article": "x", "quantite": 1}] * 7})["raison"] == "plafond_d_operations"
    assert plafond_d_operations({"ajouter": [{"article": "x", "quantite": 21}]}) is not None
    assert plafond_d_operations({"ajouter": [{"article": "x", "quantite": 2}] * 6}) is None


def test_deux_questions_au_plus():
    compteur: dict[str, int] = {}
    assert deux_questions_au_plus(compteur, "taille") and deux_questions_au_plus(compteur, "taille")
    assert not deux_questions_au_plus(compteur, "taille")  # la troisième propose la sortie, jamais une quatrième question
    assert deux_questions_au_plus(compteur, "adresse")


def test_telephone_dit_par_elle():
    assert not valeur_dite_par_elle("0612345678", "telephone", ["je voudrais une reine"])
    assert valeur_dite_par_elle("0612345678", "telephone", ["zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit"])
    assert valeur_dite_par_elle("06 12 34 56 78", "telephone", ["0 6 1 2 3 4 5 6 7 8"])


def test_rendu_sur_dit_par_elle():
    assert valeur_dite_par_elle(50, "rendu_sur", ["je paie avec un billet de cinquante"])
    assert not valeur_dite_par_elle(2, "rendu_sur", ["deux reines s'il vous plaît"])


def test_valeur_absente_apres_mise_en_forme():
    assert valeur_dite_par_elle("vingt heures", "heure", ["Vers 20 heures"])
    assert valeur_dite_par_elle("19:00", "heure", ["vers sept heures du soir"])
    assert not valeur_dite_par_elle("Martin", "prenom", ["une reine à emporter"])
    assert valeur_dite_par_elle("Martin", "prenom", ["oui"], ["C'est noté Martin"])  # dit par le code dans l'appel (parade B6)
    assert B.valeur_pas_dans_ses_mots({"prenom": "Martin"}, ["une reine"])["raison"] == "valeur_pas_dans_ses_mots"


def test_fiche_rejouee_cle():
    assert cle_d_idempotence(1, "fiche", {"ajouter": [1], "a_dire": "a"}) == cle_d_idempotence(1, "fiche", {"ajouter": [1], "a_dire": "b"})
    assert cle_d_idempotence(1, "fiche", {"ajouter": [1]}) != cle_d_idempotence(2, "fiche", {"ajouter": [1]})


def test_une_seule_copie_des_aides():
    """La commande et le service lisent leurs arguments par ``actions_communes`` (S11) ; plus aucune copie de ``_texte``, ``_entier``, ``_jsonable``."""
    for f in ("services/commande/porte.py", "services/commande/lire.py", "services/integrations/connectors/actions/service.py",
              "services/integrations/connectors/actions/commande.py"):
        texte = (API / f).read_text(encoding="utf-8")
        assert not any(f"def {n}(" in texte for n in ("_texte", "_entier", "_jsonable")), f
    assert "from api.services.actions_communes.arguments import" in (API / "services/commande/porte.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- la vraie porte


async def test_un_article_un_seul_ajout(essai_de):
    e = await essai_de()
    await e.tour("une regina normale à emporter", mode_de_retrait="emporter", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert e.lignes() == [("Regina Normale", 1, ())], e.retours[-1]


async def test_fiche_rejouee_sans_effet(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    e.dit("une regina normale")
    await e.fiche(ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    r = await e.fiche(ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}], _montrer=False)
    assert e.lignes() == [("Regina Normale", 1, ())] and r["faits"].get("deja_fait") is True


async def test_deux_lignes_identiques_deux_tours(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _une_margherita(e)
    await e.tour("et une autre margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    assert e.lignes() == [("Margherita Normale", 2, ())], e.retours[-1]


async def test_deux_retraits_structures(essai_de):
    """« une napoli sans olives et sans câpres » (note de Pierre) : les deux retraits gardés, par la case structurée ``sans``."""
    e = await essai_de()
    await _a_emporter(e)
    await e.tour("une napoli normale sans olives et sans câpres", ajouter=[{"article": "napoli", "quantite": 1, "variante": "Normale", "sans": ["olives", "câpres"]}])
    lignes = e.p["lignes"]
    assert len(lignes) == 1 and len(lignes[0]["retires"]) == 2, e.retours[-1]


async def test_douze_sans_oignons_structure(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await e.tour("12 campione normales sans oignons", ajouter=[{"article": "campione", "quantite": 12, "variante": "Normale", "sans": ["oignons"]}])
    lignes = e.p["lignes"]
    assert len(lignes) == 1 and lignes[0]["quantite"] == 12 and len(lignes[0]["retires"]) == 1, e.retours[-1]


async def test_mode_et_adresse_une_operation(essai_de):
    e = await essai_de()
    r = await e.tour("en livraison au 12 rue de la République à Senlis", mode_de_retrait="livraison", adresse="12 rue de la République", commune="Senlis")
    assert e.p["mode"] == "livraison" and (e.p.get("adresse") or {}).get("commune") == "Senlis", r
    assert [x["operation"] for x in r["resultats"]] == ["informations"]


async def test_adresse_n_avale_pas_l_article(essai_de):
    """C6 : l'article dit après la question de l'adresse va dans ``ajouter`` ; l'adresse ne prend jamais ses mots."""
    e = await essai_de()
    await e.tour("en livraison", mode_de_retrait="livraison")
    await e.tour("12 rue de la République à Senlis, et une margherita normale", adresse="12 rue de la République", commune="Senlis",
                 ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    assert (e.p.get("adresse") or {}).get("voie") == "12 rue de la République" and e.lignes() == [("Margherita Normale", 1, ())], e.retours[-1]


async def test_valeur_hors_liste_refusee(essai_de):
    e = await essai_de()
    r = await e.tour("en drive", mode_de_retrait="drive")
    assert r["raison"] == "valeur_hors_liste" and e.p["mode"] is None and "emporter" in r["refus"][0]["choix"], r


async def test_case_cachee_refusee(essai_de):
    """B8 point 3 (F1a à F1c) : une case absente des cases montrées dans ce tour est refusée. Seule, la fiche entière est refusée ; avec d'autres
    cases, elle n'écarte qu'elle (clôture, lot B4, M9 : même faute, même traitement qu'une réponse sans question)."""
    e = await essai_de()
    await _a_emporter(e)
    r = await e.tour("annulez ma commande d'hier", annuler_une_commande_enregistree=True)
    assert r["statut"] == "REJETEE" and r["raison"] == "case_sans_objet" and r["fiche_appliquee"] is False, r
    r = await e.tour("c'est Martin, une margherita", prenom="Martin", ajouter=[{"article": "margherita", "quantite": 1}])
    assert r["raison"] == "case_sans_objet" and r["cases_refusees"] == ["prenom"] and len(e.p["lignes"]) == 1, r


async def test_booleen_en_chaine_refuse(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _une_margherita(e)
    r = await e.tour("c'est tout", c_est_tout="true")
    assert r["raison"] == "format", r
    # Lot 19, D30 (run 207 ; décision d'Evan du 20/11) : le refus reste (B8), mais la consigne dit le TYPE attendu ; « refais la fiche sans
    # c_est_tout » invitait le modèle à retirer la case (l'annulation de la conversation 6 renvoyée trois fois en « "true" »).
    assert "c_est_tout en true ou false, sans guillemets" in r["a_faire"] and "sans c_est_tout" not in r["a_faire"], r["a_faire"]
    r = await e.tour("deux margherita", ajouter=[{"article": "margherita", "quantite": "2"}])
    assert r["raison"] == "format" and e.lignes() == [("Margherita Normale", 1, ())], r
    assert "ajouter[].quantite en nombre, sans guillemets" in r["a_faire"], r["a_faire"]


async def test_refus_dit_quoi_refaire(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await e.tour("annulez celle d'hier", annuler_une_commande_enregistree=True)
    assert r["a_faire"].startswith("rien n'est changé : refais la fiche sans annuler_une_commande_enregistree"), r


async def test_plafond_six_articles(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await e.tour("sept pizzas", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}] * 7)
    assert r["raison"] == "plafond_d_operations" and e.p["lignes"] == [], r


async def test_cases_liees_bloc_livraison(essai_de):
    """L'adresse refusée (pas dans ses mots) : mode, commune, consigne non exécutés ; l'article de la même fiche est pris (D8)."""
    e = await essai_de()
    r = await e.tour("en livraison à Senlis, une margherita normale", mode_de_retrait="livraison", adresse="8 avenue Foch", commune="Senlis",
                     ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    assert r["statut"] == "PARTIEL" and "adresse" in r["cases_refusees"], r
    assert e.p["mode"] is None and {"mode_de_retrait", "commune"} <= set(r["cases_non_executees_car_liees"]), r
    assert e.p.get("dits_en_attente") or e.lignes(), "l'article de la même fiche n'est pas perdu"


async def test_cases_liees_paiement(essai_de):
    e = await essai_de()
    q = await _jusqu_a_la_relecture(e)
    r = await e.tour("oui c'est bon, en espèces", reponse={"question_id": q.get("id"), "sens": "accepte"}, moyen_de_paiement="especes", rendu_sur=50)
    assert "rendu_sur" in (r.get("cases_refusees") or []) and "moyen_de_paiement" in (r.get("cases_non_executees_car_liees") or []), r


async def test_c_est_tout_pas_si_refus(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await e.tour("une margherita normale c'est tout, au nom de Martin", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}],
                     heure="dix-neuf heures", c_est_tout=True)
    assert "heure" in r["cases_refusees"] and "c_est_tout" not in r["cases_executees"], r


async def test_reponse_sans_question_id_refusee(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _une_margherita(e)
    await e.tour("c'est tout", c_est_tout=True)
    r = await e.tour("oui", reponse={"question_id": "Q-99", "sens": "accepte"})
    assert r["raison"] == "question_inconnue" and not e.p.get("relecture_acceptee"), r


async def test_un_ajout_pendant_la_relecture_relance_la_relecture(essai_de):
    """B8 point 1, revu au lot 20 (D-A : H2, H4, H8, n10 bouclaient) : un ajout pendant la relecture, sans réponse, n'est plus refusé en entier ; il vaut
    « autre » pour la relecture : l'article est pris et la relecture repart (jamais un accord déduit)."""
    e = await essai_de()
    await _jusqu_a_la_relecture(e)
    avant = e.p["question"]["id"]
    r = await e.tour("et une regina normale", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}], _montrer=False)
    assert r["statut"] != "REJETEE" and r.get("raison") != "reponse_manquante", r
    assert any("Regina" in l["nom"] for l in e.p["lignes"]) and not e.p.get("relecture_acceptee"), e.p
    # B1 (RC9) : la relecture qui repart est la même question (même objet, même numéro) avec son nouveau texte, dit par le code
    assert e.p["question"]["type"] == "relecture" and e.p["question"]["id"] == avant and "Regina" in e.p["question"]["texte"], e.p["question"]


async def test_une_fiche_sans_changement_pendant_la_relecture_reste_refusee(essai_de):
    """B8 point 1 tient pour ce qui ne change pas la commande : une case de fin sans réponse à la relecture reste refusée."""
    e = await essai_de()
    await _jusqu_a_la_relecture(e)
    r = await e.tour("par carte", moyen_de_paiement="carte_bancaire", _montrer=False)
    assert r["raison"] in ("reponse_manquante", "case_sans_objet"), r


async def test_barriere_lit_les_cases_montrees(essai_de):
    """D52 : l'état change entre l'envoi et l'exécution ; la barrière juge contre les cases montrées dans ce tour, jamais un recalcul."""
    e = await essai_de()
    e.dit("en livraison")
    e.montrer()  # état vide : annuler_la_commande n'est pas montrée
    e.p["mode"] = "livraison"  # l'état change après l'envoi : un recalcul ouvrirait annuler_la_commande
    r = await e.fiche(annuler_la_commande=True, _montrer=False)
    assert r["raison"] == "case_sans_objet", r


async def test_annuler_ne_recommence_pas(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _une_margherita(e)
    r = await e.tour("non laissez tomber", annuler_la_commande=True)
    assert e.p.get("annulee") is True and e.p["lignes"] == [] and r["statut"] == "ANNULEE", r


async def test_lire_n_efface_rien_vider_le_panier_vide(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _une_margherita(e)
    from types import SimpleNamespace

    await porte.executer(SimpleNamespace(nom="lire"), {"sujet": "panier"}, e.ctx, 5.0)
    assert e.lignes() == [("Margherita Normale", 1, ())]
    await e.tour("on recommence", vider_le_panier=True, ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert e.lignes() == [("Regina Normale", 1, ())] and not e.p.get("annulee"), e.retours[-1]


async def test_fait_bloquant_marque(essai_de):
    e = await essai_de()
    r = await e.tour("une pizza au caviar à emporter", mode_de_retrait="emporter", ajouter=[{"article": "pizza au caviar", "quantite": 1}])
    assert r["statut"] == "PARTIEL" and r["faits"].get("fait_bloquant"), r


async def test_doute_rend_les_choix(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    assert r["statut"] == "A_PRECISER" and r["question"]["id"].startswith("Q-"), r


async def test_service_numero_invente_refuse(essai_de):
    e = await essai_de()
    e.dit("je voudrais savoir où en est ma commande")
    r = await porte.executer_la_fiche_du_service({"retrouver_une_commande_enregistree": {"telephone": "0611223344", "numero_de_commande": "T12"}, "a_dire": "x"}, e.ctx)
    assert r["raison"] == "valeur_pas_dans_ses_mots", r


async def test_service_un_message_par_appel(essai_de):
    e = await essai_de()
    e.dit("dites au patron que la pizza était froide")
    r1 = await porte.executer_la_fiche_du_service({"laisser_un_message": {"objet": "la pizza était froide"}, "a_dire": "x"}, e.ctx)
    r2 = await porte.executer_la_fiche_du_service({"laisser_un_message": {"objet": "et le livreur en retard"}, "a_dire": "x"}, e.ctx)
    assert r1["statut"] == "FAIT" and r2["raison"] == "message_deja_laisse_dans_cet_appel", (r1, r2)


async def test_non_merci_ne_prend_pas_la_proposition(essai_de):
    """C1 (2636, 2650, 2665) : « non merci, c'est tout » répond à la proposition par un refus ; la proposition n'entre jamais au panier."""
    e = await essai_de()
    await _jusqu_a_la_relecture(e)
    assert e.lignes() == [("Margherita Normale", 1, ())], e.retours


async def test_second_enregistrement_refuse(essai_de):
    e = await essai_de()
    q = await _jusqu_a_la_relecture(e)
    r = await e.tour("oui c'est bon, au nom de Martin, en carte", reponse={"question_id": q["id"], "sens": "accepte"}, prenom="Martin",
                     moyen_de_paiement="carte_bancaire")
    q = e.p.get("question") or {}
    assert q.get("type") == "numero_affiche", r  # C7 : le numéro qui s'affiche est une question numérotée, jamais validée par le « oui » de la relecture
    r = await e.tour("oui, ce numéro", reponse={"question_id": q["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    numero = e.p["enregistree"]["numero"]
    r = await e.tour("c'est tout", c_est_tout=True)
    assert r["raison"] == "deja_fait" and e.p["enregistree"]["numero"] == numero, r


async def test_panne_joint_la_commande(essai_de, monkeypatch):
    """A35 : une panne en pleine commande joint la commande en cours au message de l'équipe ; l'appel continue."""
    from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_COMMANDE

    e = await essai_de()
    await _a_emporter(e)
    await _une_margherita(e)

    async def panne(*a, **k):
        raise RuntimeError("catalogue injoignable")

    monkeypatch.setattr(porte, "executer_la_fiche", panne)
    r = await e.tour("et une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    entrees = [x for x in e.fiche_de_l_appel.get(CLE_RAPPEL) or [] if x.get("origine") == ORIGINE_COMMANDE]
    assert r["faits"] == {"indisponible": True, "transmise_a_l_equipe": True} and len(entrees) == 1 and "argherita" in entrees[0]["objet"], (r, entrees)


def test_action_py_supprime():
    """L03-20 : ``commande/action.py`` n'existe plus et rien ne l'importe (le connecteur passe par la porte)."""
    import re

    assert not (API / "services" / "commande" / "action.py").exists()
    motif = re.compile(r"from api\.services\.commande import [^\n]*\baction\b|api\.services\.commande\.action\b")
    fautifs = [str(f.relative_to(API)) for f in API.rglob("*.py") if ".venv" not in f.parts and motif.search(f.read_text(encoding="utf-8", errors="replace"))]
    assert fautifs == []


def test_banc_a_passe_par_la_fiche():
    """L03-30 (D48) : ``ACTION_DU_NOM_VU`` n'existe plus ; chaque test du banc A envoie une fiche à la porte (aucun ancien outil joué)."""
    from api.tests.mark.banc_a import commun

    assert not hasattr(commun, "ACTION_DU_NOM_VU") and not hasattr(commun, "NOM_VU_DE_L_ACTION")
    banc = API / "tests" / "mark" / "banc_a"
    for f in banc.glob("test_*.py"):
        texte = f.read_text(encoding="utf-8")
        assert "a.jouer(\"" not in texte and "jouer_reel" not in texte and "action.executer" not in texte, f.name
    assert "porte.executer" in (banc / "commun.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("nom", [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=ECARTS_DE_LA_CUISINE[n])) if n in ECARTS_DE_LA_CUISINE else n
                                 for n in CONVERSATIONS])
async def test_egalite_banc_et_fork(essai_de, nom):
    """L03-31 (D67) : les fiches enregistrées en B12 servies à la vraie porte donnent, tour par tour, le même panier et les mêmes refus que le banc."""
    conversation = next(c for c in REPONSES["conversations"] if c["conversation"] == nom)
    from api.tests.mark.partie_1.test_l06_parole import eteindre_la_question_apres_enregistrement

    e = await essai_de()
    eteindre_la_question_apres_enregistrement(e)  # DC10 : la relecture du numéro dicté, absente de l'agent du banc, éteinte comme M108
    ecarts = await ecarts_de_la_conversation(e, conversation)
    assert ecarts == [], chr(10).join(ecarts)
