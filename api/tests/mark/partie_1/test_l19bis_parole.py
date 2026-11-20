"""[.mark] Chantier Partie 1, lot 19 bis, étape B : les petits correctifs de l'audit de Pierre (notes du 20/11), un test vu rouge chacun.

Allergie (A1, A3, A4), commande (C1 à C8), parole (P1 à P8), tours (T1 à T5), preuves (V1 à V10). Tests sur la vraie porte et le vrai moteur (``essai_de``).
"""

from __future__ import annotations

from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, fait  # noqa: F401


# --------------------------------------------------------------------------- A1, A3, A4


async def test_deux_allergies_deux_verifications(essai_de):
    """A1 : « gluten et arachides » : les DEUX allergènes sont vérifiés (avant : seul le premier code trouvé). La salade aux arachides validées est ``present`` ; le blocage est tenu."""
    carte = carte_de("briques/INF1")
    for p in carte["produits"]:
        if p["id"] == "P-SALADE":
            p["allergenes"] = ["arachides"]
    e = await essai_de("briques/INF1", carte=carte)
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salade", ajouter=[{"article": "salade verte", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "gluten et arachides"
    r = await e.tour("je suis allergique au gluten et aux arachides", note_generale="allergique au gluten et aux arachides")
    allergie = r["faits"]["allergie"]
    par_allergene = {a["allergene"]: a["articles"] for a in allergie["allergenes"]}
    assert par_allergene["les arachides"] == [{"article": "Salade verte", "etat": "present"}], allergie
    assert par_allergene["le gluten"] == [{"article": "Salade verte", "etat": "absent_de_la_fiche"}], allergie
    assert not e.p.get("enregistree")


def test_code_dit_au_mot_entier_et_tous_les_codes():
    """A1 : ``codes_dits`` rend tous les codes, au mot entier (« laitue », « semoule », « blettes », « noix de coco » ne sont pas des allergènes) ; un mot non reconnu est signalé."""
    from api.services.restauration.signalements import codes_dits, code_dit

    assert codes_dits("gluten et arachides") == (["gluten", "arachides"], False)
    assert codes_dits("intolérance au lactose et allergie aux arachides") == (["arachides", "lait"], False)  # dans l'ordre des quatorze
    assert codes_dits("laitue")[0] == [] and codes_dits("semoule")[0] == [] and codes_dits("blettes")[0] == [] and codes_dits("noix de coco")[0] == []
    assert codes_dits("gluten et kiwi") == (["gluten"], True)  # un mot d'allergie non reconnu : à confirmer par l'équipe
    assert code_dit("des cacahuètes") == "arachides" and code_dit("laitue") is None


async def test_sans_x_tient_compte_des_choix_obligatoires(essai_de):
    """A3 : Tacos (sans moutarde), sauce obligatoire parmi algérienne (moutarde), ketchup (sans), maison (inconnu) : « sans moutarde » ne le dit pas « sans », il dit « selon le choix »."""
    e = await essai_de("briques/INF2")
    r = await e.lecture(sujet="allergenes", a_eviter="sans moutarde")
    texte = fait(r)
    assert '"sans": []' in texte, texte
    assert '"selon_le_choix": ["Tacos"]' in texte, texte
    assert "ne contient pas de moutarde" not in texte, texte


async def test_allergene_hors_des_quatorze_a_confirmer(essai_de):
    """A4 : « de l'ail dans la salade ? » (hors des quatorze) : jamais « n'en déclare aucun » : inconnu, à confirmer par l'équipe."""
    e = await essai_de("briques/INF1")
    texte = fait(await e.lecture(sujet="allergenes", article="Salade verte", a_eviter="ail"))
    assert '"signalement": "inconnu"' in texte and "n'en déclare aucun" not in texte, texte

