"""[.mark] Lot 7b, préfixe (Q1 = A) : le code ne dit plus RIEN avant la phrase du modèle. Le refus au chiffre ou au lieu (hors zone, minimum, règle d'une ligne, règle d'un article)
est donné au modèle en faits, avec ses chiffres ; il le dit avec ses mots et la barrière des chiffres le laisse passer.

Avant : « Nous ne livrons pas à Compiègne. Nous livrons Senlis, Chantilly et Gouvieux. » dit mot pour mot par le code, puis le modèle sans chiffre.
Après : le modèle dit « Compiègne n'est pas dans notre zone, on livre Senlis, Chantilly et Gouvieux. Vous préférez venir les chercher ? ».
"""

from __future__ import annotations

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase
from api.services.actions_communes.du import faits_du_refus
from api.services.commande import porte as PORTE
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.aides_briques import brique, fait


def _rien_dit_avant(e, r) -> None:
    """Le code n'a rien rangé à dire avant la phrase du modèle, et le retour ne dit pas qu'il l'a dit."""
    assert not (e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("prefixe"), e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE)
    assert not r.get("dit_avant_ta_phrase") and not r.get("regle_dite_par_le_code") and "le code vient de" not in str(r.get("a_faire")), r


async def test_hors_zone_le_modele_dit_le_refus_avec_les_communes(essai_de):
    """Client « Deux reines, livrées à Compiègne » : le code ne dit rien avant ; le modèle repasse avec les communes livrées en faits."""
    e = await essai_de("casa-italia")
    e.dit("Deux reines normales, livrées au 8 rue Solférino à Compiègne")
    e.montrer()
    r = await e.fiche(ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}], mode_de_retrait="livraison", adresse="8 Rue Solférino", commune="Compiègne", _montrer=False)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est entendu. Livraison ou retrait ?"})
    assert d.mode == PAROLE.SECOND_PASSAGE and not hasattr(d, "prefixe"), d
    _rien_dit_avant(e, r)
    refus = r["faits"]["refus_de_la_fiche"][0]
    dite = "Compiègne n'est pas dans notre zone, on livre Senlis, Chantilly et Gouvieux. Vous préférez venir les chercher ?"
    assert refus["faits"]["communes_livrees"] and all(c in fait(r) for c in ("Senlis", "Chantilly", "Gouvieux")), fait(r)
    assert not chiffre_dans_la_phrase(dite, faits=faits_du_refus(r)), "une phrase du modèle sans chiffre est dite"


async def test_minimum_le_modele_dit_le_minimum_et_ce_qui_manque(essai_de):
    """Client « une margherita » en livraison à Chantilly, minimum 50 € : le modèle dit « cinquante euros minimum, il vous manque trente-neuf euros dix » ; les chiffres sont
    dans les faits (``minimum_de_la_commande``), la barrière les laisse passer, et le code ne les dit pas avant."""
    e = await essai_de("casa-italia", minimum=5000)
    await e.tour("en livraison au 9 avenue du Bouteiller à Chantilly", mode_de_retrait="livraison", commune="Chantilly", adresse="9 avenue du Bouteiller")
    cases = {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}
    r = await e.tour("une margherita normale", **cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Parfait, une margherita.", **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, (d, r)
    _rien_dit_avant(e, r)
    assert r["faits"]["minimum_de_la_commande"] == {"commune": "Chantilly", "minimum": 5000, "manque": 3910,  # F3 (C7 B6) : les montants aussi en lettres
                                                     "minimum_dit": "cinquante euros", "manque_dit": "trente-neuf euros dix"}, r["faits"]
    assert PORTE.A_FAIRE_DU_MINIMUM in r["a_faire"], r["a_faire"]
    dite = "Pour Chantilly il faut cinquante euros minimum, il vous manque trente-neuf euros dix ; vous ajoutez quelque chose ?"
    assert not chiffre_dans_la_phrase(dite, faits=faits_du_refus(r)), "les chiffres du minimum sont portés par les faits"
    assert chiffre_dans_la_phrase("Il vous manque quarante euros.", faits=faits_du_refus(r)), "un autre montant reste retenu"


async def test_regle_d_une_ligne_limitee_par_un_prix_est_donnee_au_modele(essai_de):
    """FOR3 : un dessert à 3,50 € dans la formule complète est refusé ; la règle (« le dessert se choisit parmi ceux à deux euros ») est un fait que le modèle dit."""
    e = await brique(essai_de, "FOR3")
    r = await e.tour("la formule complète avec un tiramisu", ajouter=[{"article": "formule complète", "quantite": 1, "composition": ["tacos", "tiramisu"]}])
    assert "hors_sous_ensemble" in fait(r) and not e.p["lignes"], fait(r)
    _rien_dit_avant(e, r)
    assert r["faits"]["regle_de_la_ligne"]["prix_max"] == 200, r["faits"]  # fait brut (reprise 7b-B, § 2) : le modèle écrit la phrase
    assert not chiffre_dans_la_phrase("Le dessert se choisit parmi ceux à deux euros.", faits=faits_du_refus(r))


async def test_regle_d_un_article_est_donnee_une_fois_par_appel_au_modele(essai_de):
    """FOR13 : « C'est servi avec 1 soupe, 1 salade et 1 riz. » est un fait que le modèle dit, une seule fois par appel."""
    e = await brique(essai_de, "FOR13")
    r = await e.tour("des brochettes yakitori", ajouter=[{"article": "brochettes yakitori", "quantite": 1}])
    _rien_dit_avant(e, r)
    assert r["faits"]["regles_a_dire"] == [{"servi_avec": ["1 soupe", "1 salade", "1 riz"]}], r["faits"]
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté."})
    assert d.mode == PAROLE.SECOND_PASSAGE, d
    r2 = await e.tour("et encore une", ajouter=[{"article": "brochettes yakitori", "quantite": 1}])
    assert "regles_a_dire" not in r2["faits"], r2["faits"]  # une seule fois par appel
