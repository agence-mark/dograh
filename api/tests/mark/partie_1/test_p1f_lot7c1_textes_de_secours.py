"""[.mark] Lot 7b-C1 : le texte de secours de chaque refus de la commande se fait des seuls faits que le modèle reçoit.

Un test par texte de secours (``services/commande/textes_de_secours.py``) : le vrai moteur refuse, et ``r.suggestion == TS.nom(faits vus par le modèle)``. Un fait qui manque au refus
(le texte lit une valeur que le modèle ne reçoit pas) ou une fonction absente rend le test rouge. Le texte rendu reste celui d'avant, au caractère près.
"""

from __future__ import annotations

import pytest

from api.services.commande import panier as P, porte, textes_de_secours as TS
from api.services.commande import moteur
from api.services.commande.briques import formule as FO
from api.services.commande.moteur import articles
from api.tests.mark.partie_1.aides_briques import brique
from api.tests.mark import test_restauration_commande_panier as _PANIER
from api.tests.mark import test_restauration_classeur_commande as _CLASSEUR
from api.tests.mark import test_base_client as _BASE
from api.tests.mark.commande_sur_la_fiche import article as A

base_essai, base_prete, commerce = _BASE.base_essai, _BASE.base_prete, _CLASSEUR.commerce  # les fixtures du classeur, reprises sans import inutile


@pytest.fixture
async def appel(commerce):
    a = _PANIER.Appel(commerce)
    await a.mode()
    return a


def le_texte_de_secours_suffit(r, texte_de_secours, attendu: str | None = None) -> None:
    """Le texte du module est celui que fait la fonction de secours des faits publics du refus (et, s'il est donné, celui d'avant)."""
    assert r.suggestion, r
    assert r.suggestion == texte_de_secours(porte.faits_vus_par_le_modele(r)), (r.suggestion, r.faits)
    if attendu is not None:
        assert r.suggestion == attendu


# ── commit 1 : choisir, ajouter, retirer (articles.py) ──────────────────────────────────────────────────────────────────

async def test_question_d_un_choix_de_taille(appel):
    r = await appel.ajouter("regina")
    assert r.statut == "CHOIX_OBLIGATOIRE"
    le_texte_de_secours_suffit(r, TS.question_d_un_choix, "Quelle taille pour votre Regina : Normale ou Mega ?")


async def test_question_d_un_choix_d_un_groupe_obligatoire(appel):
    r = await appel.ajouter("cheeseburger")
    assert r.faits["question"]["nom"] == "Sauce"
    le_texte_de_secours_suffit(r, TS.question_d_un_choix)


async def test_question_d_un_choix_au_nom_de_la_carte_et_non_de_la_ligne(appel):
    """La ligne s'appelle « Regina Mega » une fois sa taille choisie : la question d'un groupe garde le nom de l'article de la carte."""
    r = await appel.ajouter(A("regina", 1, "Mega"))
    if r.statut == "CHOIX_OBLIGATOIRE":
        assert r.faits["article_de_la_carte"] == "Regina"
        le_texte_de_secours_suffit(r, TS.question_d_un_choix)


async def test_maximum_atteint_par_option(appel):
    await appel.ajouter(A("margherita", 1, "Normale", supplements=["champignons", "champignons"]))
    r = await appel.modifier(ligne="1", choix="champignons")
    assert r.statut == "MAXIMUM_ATTEINT" and r.faits["maximum_atteint"] == r.faits["maximum_par_option"]
    le_texte_de_secours_suffit(r, TS.maximum_atteint)


KETCHUP, MAYO = {"code": "A", "nom": "Ketchup", "rupture": False}, {"code": "B", "nom": "Mayonnaise", "rupture": False}


def _groupe(maximum: int, par_option: int) -> dict:
    return {"id": "g", "nom": "Sauces", "role": "sauce", "min": 0, "max": maximum, "max_par_option": par_option, "options": [KETCHUP, MAYO]}


def test_maximum_atteint_du_groupe():
    """Le groupe a la place d'une seule sauce : c'est son maximum que le refus dit, pas celui de l'option."""
    ligne = {"choix": [{"option_code": "A", "nom": "Ketchup", "quantite": 1, "choix": []}]}
    r = articles._choisir(ligne, (), _groupe(1, 3), MAYO, 1)
    assert r is not None and r.statut == "MAXIMUM_ATTEINT" and r.faits["maximum_atteint"] == 1
    le_texte_de_secours_suffit(r, TS.maximum_atteint, "Sauces : pas plus de un ; Mayonnaise n'est pas pris.")


def test_option_en_rupture():
    r = articles._choisir({"choix": []}, (), _groupe(2, 2), {**MAYO, "rupture": True}, 1)
    assert r.statut == "RUPTURE"
    le_texte_de_secours_suffit(r, TS.n_est_plus_disponible, "Mayonnaise n'est plus disponible.")


async def test_un_article_qui_ne_se_prend_pas_avec_des_choix(appel):
    r = await appel.ajouter(A("tiramisu", moities=["regina", "margherita"]))
    assert r.faits["raison"] == "aucun_choix"
    le_texte_de_secours_suffit(r, TS.ne_se_prend_pas_avec_des_choix)


async def test_une_option_hors_carte_dit_la_plus_proche(appel):
    r = await appel.ajouter(A("margherita", 1, "Normale", supplements=["mozza"]))
    assert r.statut == "HORS_CARTE" and r.faits["plus_proches"] and "choix_possibles" not in r.faits
    le_texte_de_secours_suffit(r, TS.option_hors_carte)
    assert "Le plus proche" in r.suggestion


async def test_une_option_hors_carte_sans_proche_dit_ce_qui_se_choisit(appel):
    r = await appel.ajouter(A("margherita", 1, "Normale", supplements=["viande"]))
    assert r.statut == "HORS_CARTE" and not r.faits["plus_proches"]
    assert 0 < len(r.faits["choix_possibles"]) <= 4
    le_texte_de_secours_suffit(r, TS.option_hors_carte)
    assert "Ce qui se choisit" in r.suggestion


async def test_une_option_ambigue_est_une_question_des_candidats(appel):
    r = await appel.ajouter(A("margherita", 1, "Normale", supplements=["jambon cru"]))
    assert r.statut == "AMBIGU" and r.faits["candidats"]
    le_texte_de_secours_suffit(r, TS.vous_voulez_dire)


async def test_un_mot_choix_de_deux_etapes_demande_l_etape(essai_de):
    e = await brique(essai_de, "FOR2")
    article = await e.source.article("F-MIDI", "emporter")
    double = {**article, "groupes": [*article["groupes"], {**article["groupes"][0], "id": "Entrée 2", "nom": "Entrée 2"}]}
    double["groupes"][-1]["options"] = [{**o, "code": o["code"] + "-2"} for o in double["groupes"][-1]["options"]]
    r, _ = moteur.placer_les_choix(double, {"nom": "Formule midi", "choix": []}, "nems", None)
    assert r.statut == "INCOMPLETE" and r.faits["etapes"] == ["Entrée", "Entrée 2"]
    le_texte_de_secours_suffit(r, TS.pour_quelle_etape, "Pour quelle étape : Entrée ou Entrée 2 ?")


async def test_un_mot_hors_de_la_ligne_de_la_formule_est_refuse_avec_son_mot(essai_de):
    e = await brique(essai_de, "FOR3")
    article = await e.source.article("F-COMPLETE", "emporter")
    r, _ = moteur.placer_les_choix(article, {"nom": "Formule complète", "choix": []}, "tiramisu", None)
    assert r.faits["raison"] == "hors_sous_ensemble"
    le_texte_de_secours_suffit(r, TS.pas_dans_la_formule, "Je n'ai pas « tiramisu » dans Formule complète.")


def test_un_retrait_sur_deux_plats_demande_lequel():
    plat = lambda code, nom: {"code": code, "nom": nom, "retirables": ["olives"]}  # noqa: E731
    article = {"groupes": [{"id": "e1", "nom": "Plat", "role": FO.ROLE_ETAPE, "options": [plat("P1", "Pizza"), plat("P2", "Pâtes")]}]}
    ligne = {"nom": "Formule", "choix": [{"option_code": c, "nom": n, "quantite": 1, "choix": [], "etape": "e1"} for c, n in (("P1", "Pizza"), ("P2", "Pâtes"))]}
    r = articles.retirer_sur_le_plat(article, ligne, "olives")
    assert r.statut == "AMBIGU"
    le_texte_de_secours_suffit(r, TS.sur_lequel, "Sur lequel : Pizza ou Pâtes ?")


# ── commit 2 : retraits, notes, code de remise (articles.py) ────────────────────────────────────────────────────────────
from api.services.commande.moteur.socle import Reglages  # noqa: E402


def _etape_de_boissons(**en_plus):
    option = lambda code, nom, alt=None, decl=(): {"code": code, "nom": nom, "produit": nom, "alternative": alt, "declinaisons_du_produit": list(decl)}  # noqa: E731
    return {"id": "e1", "nom": "Boisson", "role": FO.ROLE_ETAPE, "options": [option("B", "Coca Bouteille", 0), option("C", "Coca Canette", 1), option("F", "Fanta", 1)],
            "alternatives": [{"quantite": 1, "codes": ["B"]}, {"quantite": 3, "codes": ["C", "F"]}], **en_plus}


def _formule(etape, taille=None):
    article = {"formule": True, "groupes": [etape], "declinaisons": [{"code": "M", "taille": taille}]}
    ligne = {"nom": "Menu partage", "code": "M", "choix": [{"option_code": c, "nom": c, "quantite": 1, "choix": [], "etape": etape["id"]} for c in ("B", "C")]}
    return article, ligne


def test_un_melange_d_alternatives_dit_les_alternatives():
    article, ligne = _formule(_etape_de_boissons())
    r = articles.a_la_taille_de_la_formule(article, ligne)
    assert r.faits["raison"] == "alternatives_melangees"
    le_texte_de_secours_suffit(r, TS.melange_refuse, "Menu partage : soit un Coca Bouteille, soit trois Coca Canette ou Fanta.")


def test_une_valeur_sans_la_taille_dit_ce_qui_l_a():
    etape = _etape_de_boissons(alternatives=None)
    etape["options"][0]["declinaisons_du_produit"] = [{"nom": "Maxi", "vendable": True, "rupture": False, "code": "BM"}]
    article, ligne = _formule(etape, {"nom": "Maxi", "declinaisons": {"Boisson": "Maxi"}})
    r = articles.a_la_taille_de_la_formule(article, ligne)
    assert r.faits["raison"] == "choix_sans_la_taille"
    le_texte_de_secours_suffit(r, TS.valeur_parmi_les_choix, "C : Coca Bouteille ?")


def test_une_note_refusee_quand_les_notes_libres_sont_eteintes():
    r = articles._noter({}, "sans stress", Reglages(notes_libres=False))
    assert r.faits["raison"] == "notes_non_acceptees"
    le_texte_de_secours_suffit(r, TS.notes_non_acceptees, "Je ne peux pas noter cette demande.")
    r = articles.noter_la_commande(P.nouveau(), Reglages(notes_libres=False), "pour Léa")
    le_texte_de_secours_suffit(r, TS.notes_non_acceptees, "Je ne peux pas noter cette demande.")


def test_un_retrait_sans_ingredient_demande_quoi():
    r = articles._noter_un_retrait_par_moitie({}, "sur la Reine", ["Reine", "4 fromages"])
    le_texte_de_secours_suffit(r, TS.quoi_retirer, "Qu'est-ce qu'il faut retirer ?")


def test_un_retrait_sans_moitie_demande_laquelle_sans_doublon():
    r = articles._noter_un_retrait_par_moitie({}, "olives", ["Reine", "Reine", "4 fromages"])
    assert r.statut == "AMBIGU"
    le_texte_de_secours_suffit(r, TS.sur_quelle_moitie, "Sans olives sur quelle moitié : Reine ou 4 fromages ?")


def test_un_retrait_ambigu_ou_hors_carte_dit_les_retirables():
    article = {"retirables": ["Olives noires", "Olives vertes", "Oignons"], "declinaisons": [], "groupes": []}
    r = articles._appliquer_les_retraits(article, {"nom": "Reine", "retires": [], "choix": []}, "olives")
    assert r.statut == "AMBIGU"
    le_texte_de_secours_suffit(r, TS.vous_voulez_retirer, "Vous voulez retirer : Olives noires ou Olives vertes ?")
    r = articles._appliquer_les_retraits(article, {"nom": "Reine", "retires": [], "choix": []}, "oignons")
    assert r is None


def test_un_ingredient_decrit_mais_non_retirable_dit_ce_qu_on_peut_retirer():
    article = {"declinaisons": [], "groupes": [], "retirables": ["Oignons", "Olives"], "ingredients": ["Tomate", "Oignons", "Olives"]}
    r = articles._appliquer_les_retraits(article, {"nom": "Reine", "retires": [], "choix": []}, "tomate")
    assert r.statut == "HORS_CARTE" and r.faits["retirables"] == ["Oignons", "Olives"]
    le_texte_de_secours_suffit(r, TS.ne_se_retire_pas, "On ne peut pas retirer « tomate » de Reine. On peut retirer : Oignons et Olives.")


class _SourceDeCodes:
    def __init__(self, codes):
        self.codes_de_remise = _lire(codes)


def _lire(codes):
    async def lire():
        return codes
    return lire


CODES = [{"code": "BIENVENUE", "ref": "R1", "nom": "Bienvenue 10 %", "phrase": None}]


async def test_un_code_inconnu_est_refuse_en_une_phrase():
    p = P.nouveau()
    r = await articles.poser_le_code_de_remise(_SourceDeCodes(CODES), p, Reglages(), "FAUX", False)
    assert r.faits["raison"] == "code_inconnu"
    le_texte_de_secours_suffit(r, TS.code_inconnu, "Je ne connais pas ce code.")


async def test_un_code_bon_sans_remise_encore_applicable_dit_le_code_et_l_offre():
    p = P.nouveau()
    r = await articles.poser_le_code_de_remise(_SourceDeCodes(CODES), p, Reglages(), "BIENVENUE", False)
    assert r.statut == "OK" and r.faits["appliquee"] is False
    le_texte_de_secours_suffit(r, TS.code_de_remise_bon, "Le code BIENVENUE est bon, Bienvenue dix pour cent s'appliquera dès que votre commande y donne droit.")


# ── commit 3 : trouver l'article, la ligne, la quantité (articles.py) ───────────────────────────────────────────────────
@pytest.mark.parametrize("dit, attendu", [
    ("pizza au homard", "Je ne trouve pas « pizza au homard »."),
    ("quatre fromagez", "Je ne trouve pas « quatre fromagez ». Le plus proche : 4 Formaggi ou Formaggio."),
])
async def test_un_article_introuvable_dit_les_plus_proches_quand_il_y_en_a(appel, dit, attendu):
    r = await appel.ajouter(A(dit, 1, "Normale"))
    assert r.statut == "INTROUVABLE"
    le_texte_de_secours_suffit(r, TS.article_introuvable, attendu)


async def test_un_mot_de_rangement_demande_lequel(appel):
    r = await appel.ajouter(A("pizzas", 1))
    assert r.statut == "INCOMPLETE" and r.faits["rangements"]
    le_texte_de_secours_suffit(r, TS.quel_rangement, "Nous avons Pizzas base tomate, Pizzas base crème et Pizzas Eccellenza : qu'est-ce que je vous mets ?")


def test_un_seul_rangement_dit_ses_premiers_elements_entre_autres():
    r = articles._question_de_rangement("pizzas", [{"nom": "Pizzas", "exemples": ["Reine", "Margherita"]}])
    assert r.faits["exemples"] == ["Reine", "Margherita"]
    le_texte_de_secours_suffit(r, TS.quel_rangement, "Nous avons Reine et Margherita, entre autres : qu'est-ce que je vous mets ?")


async def test_un_article_pas_servi_maintenant_se_distingue_d_un_introuvable_sans_proches(appel, monkeypatch):
    async def rien(*_a, **_k):
        return None
    monkeypatch.setattr(articles, "_article_de_la_carte", rien)
    r = await appel.ajouter(A("margherita", 1, "Normale"))
    assert r.statut == "INTROUVABLE" and r.faits["pas_servi_maintenant"] is True
    le_texte_de_secours_suffit(r, TS.pas_servi_maintenant, "« margherita » n'est pas disponible en ce moment.")


async def test_une_quantite_trop_haute_dit_le_plafond(appel):
    r = await appel.ajouter(A("margherita", 99999, "Normale"))
    assert r.statut == "ARGUMENT_INVALIDE" and r.faits["quantite_max"] == articles.lecture.QUANTITE_MAX
    le_texte_de_secours_suffit(r, TS.beaucoup_combien_exactement, "99999, c'est beaucoup : je vous mets combien exactement ?")


async def test_une_taille_en_rupture_dit_celles_qui_restent(appel, monkeypatch):
    vrai = articles._article_de_la_carte

    async def mega_en_rupture(*a, **k):
        article = await vrai(*a, **k)
        for d in article["declinaisons"]:
            d["rupture"] = d["nom"] == "Mega"
        return article
    monkeypatch.setattr(articles, "_article_de_la_carte", mega_en_rupture)
    r = await appel.ajouter(A("margherita", 1, "Mega"))
    assert r.statut == "RUPTURE" and r.faits["autres_tailles"] == ["Normale"]
    le_texte_de_secours_suffit(r, TS.taille_en_rupture, "Margherita Mega n'est plus disponible. Il reste : Normale.")


async def test_une_ligne_qui_n_est_plus_au_catalogue_le_dit(appel, monkeypatch):
    await appel.ajouter(A("margherita", 1, "Normale"))

    async def rien(*_a, **_k):
        return None
    monkeypatch.setattr(articles, "_article_de_la_carte", rien)
    r = await appel.modifier(ligne="1", quantite=2)
    assert r.statut == "INTROUVABLE"
    le_texte_de_secours_suffit(r, TS.plus_au_catalogue, "Margherita Normale n'est plus au catalogue.")


async def test_changer_une_ligne_d_une_commande_vide(appel):
    r = await appel.modifier(ligne="1", quantite=2)
    assert r.statut == "INTROUVABLE" and r.faits["panier_vide"] is True
    le_texte_de_secours_suffit(r, TS.commande_vide, "Il n'y a encore rien dans la commande.")


async def test_une_ligne_qui_n_existe_pas_et_une_ligne_non_dite_et_un_nom_inconnu(appel):
    await appel.ajouter(A("margherita", 1, "Normale"))
    await appel.ajouter(A("margherita", 1, "Mega"))
    r = await appel.modifier(ligne="9", quantite=2)
    le_texte_de_secours_suffit(r, TS.pas_de_ligne, "Il n'y a pas de ligne 9.")
    r = await appel.modifier(quantite=2)
    assert r.statut == "INCOMPLETE" and r.manque == "ligne"
    le_texte_de_secours_suffit(r, TS.quelle_ligne, "Laquelle voulez-vous changer ?")
    r = await appel.modifier(ligne="margherita", quantite=2)
    assert r.statut == "AMBIGU"
    le_texte_de_secours_suffit(r, TS.laquelle)
    r = await appel.modifier(ligne="xylophone", quantite=2)
    le_texte_de_secours_suffit(r, TS.pas_dans_la_commande, "Je ne trouve pas « xylophone » dans la commande.")


async def test_une_quantite_invalide_et_rien_a_changer(appel):
    await appel.ajouter(A("margherita", 1, "Normale"))
    r = await appel.modifier(ligne="1", quantite=-1)
    le_texte_de_secours_suffit(r, TS.combien_exactement, "Combien exactement ?")
    r = await appel.modifier(ligne="1", quantite=99999)
    assert r.faits["quantite_max"] == articles.lecture.QUANTITE_MAX
    le_texte_de_secours_suffit(r, TS.combien_exactement)
    r = await appel.modifier(ligne="1")
    assert r.manque == "modification"
    le_texte_de_secours_suffit(r, TS.que_change_t_on, "Qu'est-ce que je change ?")


# ── commit 4 : l'ouverture, l'heure annoncée, l'adresse (prealables.py) ─────────────────────────────────────────────────
def _etat_ferme(phrase=None):
    async def etat(_mode):
        return {"ouvert": False, "statut": "FERME", "phrase": phrase, "raison": "ferme", "reprise": None, "prochaine_ouverture": None, "planifiee_permise": False}
    return etat


async def test_une_fermeture_sans_phrase_de_la_source_dit_le_secours_de_la_commande(appel, monkeypatch):
    monkeypatch.setattr(appel.source, "etat", _etat_ferme())
    r = await moteur.etat_ouverture(appel.source, appel.p, appel.regles, "emporter")
    assert r.statut == "FERME"
    le_texte_de_secours_suffit(r, TS.pas_de_commande_en_ce_moment, "Nous ne prenons pas de commande en ce moment.")
    r = await moteur.heure_annoncee(appel.source, appel.p, appel.regles, "emporter")
    le_texte_de_secours_suffit(r, TS.pas_de_commande_en_ce_moment)


async def test_la_phrase_de_fermeture_de_la_source_reste_le_secours(appel, monkeypatch):
    """La source écrit sa phrase (C2) : elle passe avant le texte du moteur ; elle n'est plus une valeur des faits (commit 5), le secours n'est lu que par le repli."""
    monkeypatch.setattr(appel.source, "etat", _etat_ferme("Les livraisons sont terminées."))
    r = await moteur.heure_annoncee(appel.source, appel.p, appel.regles, "emporter")
    assert r.suggestion == "Les livraisons sont terminées."
    from api.services.commande.moteur import prealables
    assert prealables.annoncer_la_fermeture({}, {"phrase": None}) == TS.pas_de_commande_en_ce_moment({})


async def test_l_heure_annoncee_dit_ce_sera_pret(appel, monkeypatch):
    async def annonce(_mode, _zone):
        return {"prete": "2026-11-25T20:00:00+01:00", "texte": "à vingt heures", "minutes": 20}
    monkeypatch.setattr(appel.source, "annonce", annonce)
    r = await moteur.heure_annoncee(appel.source, appel.p, appel.regles, "emporter")
    assert r.statut == "OK"
    le_texte_de_secours_suffit(r, TS.ce_sera_pret, "Ce sera prêt à vingt heures.")


def test_le_minimum_de_l_adresse_se_lit_de_la_zone_quand_rien_n_est_pris():
    from api.services.commande.moteur import prealables

    faits = {"zone": {"nom": "Senlis", "minimum": 1500}}
    assert prealables._minimum_de_l_adresse(faits, P.nouveau()) == TS.minimum_de_l_adresse(faits) == "Le minimum de commande pour cette adresse est de quinze euros."
    assert prealables._minimum_de_l_adresse({"zone": {"minimum": 0}}, P.nouveau()) == ""


# ── commit 5 (comportement) : les phrases de fermeture sortent des faits, les clés de l'état n'ont plus qu'une liste ────
PHRASE_DE_FERMETURE = "Les livraisons sont terminées pour aujourd'hui. Nous reprenons à dix-huit heures."


def _valeurs(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _valeurs(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _valeurs(v)
    else:
        yield x


def _etat_ferme_a_la_main(**en_plus):
    async def etat(_mode):
        return {"ouvert": False, "statut": "FERME", "phrase": PHRASE_DE_FERMETURE, "raison": "ferme", "reprise": None, "reprise_dite": "dix-huit heures",
                "prochaine_ouverture": None, "planifiee_permise": False, **en_plus}
    return etat


async def test_la_phrase_de_fermeture_n_est_dans_aucun_fait_de_l_ouverture(appel, monkeypatch):
    monkeypatch.setattr(appel.source, "etat", _etat_ferme_a_la_main())
    r = await moteur.etat_ouverture(appel.source, appel.p, appel.regles)
    faits = porte.faits_vus_par_le_modele(r)
    assert not [v for v in _valeurs(faits) if isinstance(v, str) and "reprenons" in v], faits
    for mode in faits["modes"]:
        assert "phrase" not in mode and mode["reprise_dite"] == "dix-huit heures" and {"ouvert", "raison", "reprise"} <= set(mode), mode
    r = await moteur.etat_ouverture(appel.source, appel.p, appel.regles, "emporter")
    assert r.suggestion == PHRASE_DE_FERMETURE  # le secours reste la phrase de la source
    assert not [v for v in _valeurs(porte.faits_vus_par_le_modele(r)) if isinstance(v, str) and "reprenons" in v]


async def test_un_mode_ferme_planifiable_ne_met_pas_la_phrase_dans_les_faits_et_dit_l_heure_gardee(appel, monkeypatch):
    monkeypatch.setattr(appel.source, "etat", _etat_ferme_a_la_main(planifiee_permise=True))
    r = await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")
    assert r.statut == "FERME_PLANIFIABLE"
    faits = porte.faits_vus_par_le_modele(r)
    assert "fermeture" not in faits and not [v for v in _valeurs(faits) if isinstance(v, str) and "reprenons" in v], faits
    assert faits["reprise_dite"] == "dix-huit heures" and faits["raison"] == "ferme"
    assert PHRASE_DE_FERMETURE in r.suggestion  # le texte de secours est celui d'avant


async def test_une_heure_gardee_se_dit_en_fait(appel, monkeypatch):
    async def quand_dit(_h):
        return "demain à dix-neuf heures"
    monkeypatch.setattr(appel.source, "etat", _etat_ferme_a_la_main(planifiee_permise=True))
    monkeypatch.setattr(appel.source, "quand_dit", quand_dit, raising=False)
    appel.p["heure_voulue"] = "2026-11-26T19:00:00+01:00"
    r = await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")
    assert r.statut == "FERME_PLANIFIABLE"
    faits = porte.faits_vus_par_le_modele(r)
    assert faits["heure_voulue_dite"] == "demain à dix-neuf heures" and "fermeture" not in faits
    assert r.suggestion.startswith(TS.commande_pour(faits)) and "Commande pour demain à dix-neuf heures." in r.suggestion


def test_les_cles_de_l_etat_sont_posees_a_un_seul_endroit():
    import inspect
    from api.services.commande.moteur import mode_et_adresse, prealables

    assert prealables.CLES_DE_L_ETAT == ("raison", "reprise", "reprise_dite", "prochaine_ouverture", "planifiee_permise")
    for module in (prealables, mode_et_adresse):
        assert '("raison", "reprise", "prochaine_ouverture", "planifiee_permise")' not in inspect.getsource(module)


# ── commit 6 : un mode fermé qui se planifie (mode_et_adresse.py) ───────────────────────────────────────────────────────
from datetime import datetime, timezone  # noqa: E402


async def test_la_proposition_du_debut_dit_l_ouverture_en_fait(appel, monkeypatch):
    async def quand_dit(_h):
        return "dix-huit heures"
    monkeypatch.setattr(appel.source, "etat", _etat_ferme_a_la_main(planifiee_permise=True, prochaine_ouverture=datetime(2026, 11, 25, 17, tzinfo=timezone.utc)))
    monkeypatch.setattr(appel.source, "quand_dit", quand_dit, raising=False)
    r = await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")
    assert (r.statut, r.manque) == ("FERME_PLANIFIABLE", "heure_proposee")
    faits = porte.faits_vus_par_le_modele(r)
    assert faits["heure_proposee_dite"] == "dix-huit heures"
    assert r.suggestion == f"{PHRASE_DE_FERMETURE} {TS.preparer_pour_l_ouverture(faits)}" == f"{PHRASE_DE_FERMETURE} Voulez-vous que je prépare votre commande pour dix-huit heures ?"


async def test_sans_ouverture_connue_le_jour_et_l_heure_se_demandent(appel, monkeypatch):
    await appel.ajouter("coca")
    monkeypatch.setattr(appel.source, "etat", _etat_ferme_a_la_main(planifiee_permise=True))
    r = await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")
    assert r.statut == "FERME_PLANIFIABLE" and r.manque is None
    assert r.suggestion == f"{PHRASE_DE_FERMETURE} {TS.quel_jour_et_quelle_heure(porte.faits_vus_par_le_modele(r))}" == f"{PHRASE_DE_FERMETURE} Pour quel jour et à quelle heure ?"


# ── commit 7 : le numéro, le prénom, la fin à une heure fermée (enregistrement.py) ──────────────────────────────────────
from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES  # noqa: E402
from api.services.commande.moteur import enregistrement  # noqa: E402
from api.services.commande.moteur.socle import Appelant  # noqa: E402
from api.services.commande.phrases_du_manque import Manque, phrase_du_manque  # noqa: E402


async def test_un_numero_illisible_dit_le_secours_et_porte_son_fait(appel):
    r = await enregistrement.identifier(appel.source, appel.p, appel.regles, Appelant(), telephone="abc", prenom=None)
    assert (r.statut, r.manque) == ("ARGUMENT_INVALIDE", "telephone")
    assert porte.faits_vus_par_le_modele(r)["numero_illisible"] is True
    le_texte_de_secours_suffit(r, TS.numero_pas_compris, "Je n'ai pas bien compris le numéro : vous pouvez le redire ?")


async def test_a_la_fin_un_numero_illisible_dit_le_meme_secours(appel):
    await appel.ajouter("coca")
    await appel.mode()
    r = await enregistrement.finaliser(appel.source, appel.p, appel.regles, Appelant(), telephone="abc")
    assert r.statut == "ARGUMENT_INVALIDE"
    le_texte_de_secours_suffit(r, TS.numero_pas_compris)


async def test_le_numero_qui_manque_se_demande_par_la_phrase_du_manque(appel):
    r = await enregistrement.identifier(appel.source, appel.p, appel.regles, Appelant(), telephone=None, prenom="Paul")
    assert r.manque == "telephone" and r.suggestion == phrase_du_manque(Manque.TELEPHONE) == "Quel est votre numéro de téléphone ?"


async def test_le_prenom_qui_manque_se_demande_par_la_phrase_du_manque(appel):
    appel.p["client"]["telephone"] = "0612345678"
    r = await enregistrement.identifier(appel.source, appel.p, appel.regles, Appelant(), telephone=None, prenom=None)
    assert r.manque == "prenom" and r.suggestion == phrase_du_manque(Manque.PRENOM) == "À quel nom je mets la commande ?"


async def test_le_numero_affiche_se_propose_avec_la_phrase_du_code_ou_le_reglage(appel):
    from dataclasses import replace
    regles = replace(appel.regles, question_numero_affiche=None)
    r = await enregistrement.identifier(appel.source, appel.p, regles, Appelant(telephone_affiche="+33612345678"), telephone=None, prenom="Paul")
    assert r.manque == "confirmer_numero" and r.suggestion == PHRASES_DITES.numero_affiche_propose() == "Je note le numéro qui s'affiche, c'est bon ?"
    assert PHRASES_DITES.numero_affiche_propose("Je note le 06, ça vous va ?") == "Je note le 06, ça vous va ?"
    assert PHRASES_DITES.quel_numero_je_note() == "Quel numéro je note ?"


async def test_la_fin_a_une_heure_fermee_propose_l_ouverture_puis_demande_le_jour(appel, monkeypatch):
    async def quand_dit(_h):
        return "dix-huit heures"
    await appel.ajouter("coca")
    await appel.mode()
    monkeypatch.setattr(appel.source, "etat", _etat_ferme_a_la_main(planifiee_permise=True, prochaine_ouverture=datetime(2026, 11, 25, 17, tzinfo=timezone.utc)))
    monkeypatch.setattr(appel.source, "quand_dit", quand_dit, raising=False)
    r = await enregistrement.finaliser(appel.source, appel.p, appel.regles, Appelant(telephone_affiche="+33612345678"))
    assert (r.statut, r.manque) == ("FERME_PLANIFIABLE", "heure_proposee")
    faits = porte.faits_vus_par_le_modele(r)
    assert faits["heure_proposee_dite"] == "dix-huit heures" and "reprenons" not in str(faits)
    assert r.suggestion == f"{PHRASE_DE_FERMETURE} Je vous la prépare pour dix-huit heures ?"
    monkeypatch.setattr(appel.source, "etat", _etat_ferme_a_la_main(planifiee_permise=True))
    r = await enregistrement.finaliser(appel.source, appel.p, appel.regles, Appelant(telephone_affiche="+33612345678"))
    assert (r.statut, r.manque) == ("FERME_PLANIFIABLE", "heure_voulue")
    assert r.suggestion.endswith("Pour quel jour et à quelle heure ?")  # la fermeture déjà dite au premier passage ne se redit pas
