"""[.mark] Lot 7b-C6, reprise R2 de l'audit réservation-prix (brief § 7 : jamais le total dans les sources admises de la relecture ; § 8 bis : le total est dit par le code) : une
lecture n'admet à la barrière des chiffres que son prix (``faits["prix"]``, PRX5), jamais le total ni le sous-total du panier.

Avant : Client « C'est tout, ça fait combien ? » (le modèle lit le panier) / dit « Alors trois Margherita à emporter, ça fait trente-deux euros soixante-dix. Cela fait trente-deux
euros soixante-dix, c'est bon pour vous ? » (le total deux fois). Après : la phrase du modèle qui dit le total est retenue, la phrase réglée du code le dit une fois.
Vraie source, vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase
from api.services.mots_dits import montant_en_lettres
from api.services.workflow import parole_de_la_fiche as PF


async def _relecture_apres_la_lecture_du_panier(essai_de):
    e = await essai_de("casa-italia")
    e.voix = False
    r = await e.dit("trois margherita à emporter").fiche(ajouter=[{"article": "margherita", "quantite": 3, "variante": "Normale"}], mode_de_retrait="emporter")
    for _ in range(3):
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            break
        e.dit("non merci, c'est tout, ça fait combien ?")
        lu = await e.lecture(sujet="panier")
        assert lu["faits"].get("total"), lu  # la lecture du panier porte le total : il n'est pas admis pour autant
        r = await e.fiche(c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", r
    return e, r


async def test_apres_la_lecture_du_panier_la_relecture_qui_dit_le_total_est_retenue(essai_de):
    e, r = await _relecture_apres_la_lecture_du_panier(essai_de)
    phrase = f"Alors trois Margherita à emporter, ça fait {montant_en_lettres(e.p['relecture']['total'])}."
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase}).mode == PAROLE.SECOND_PASSAGE
    retenue = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler(phrase)
    assert retenue is not None and retenue.raison == PAROLE.CHIFFRE and retenue.a_dire is None, retenue


def test_seul_le_prix_d_une_lecture_est_admis():
    fiche = {PAROLE.CLE_DU_TOUR: 1}
    PAROLE.admettre_les_valeurs(fiche, {"prix": {"montant": 800, "a_partir_de": False}, "total": 3270, "sous_total": 2970, "lignes": [{"prix_unitaire": 990}]})
    admis = PAROLE.etat_du_tour(fiche).faits_du_refus
    assert not chiffre_dans_la_phrase("Le tacos coûte huit euros.", faits=admis)
    for autre in ("Ça fait trente-deux euros soixante-dix.", "Sans les frais, vingt-neuf euros soixante-dix.", "La margherita est à neuf euros quatre-vingt-dix."):
        assert chiffre_dans_la_phrase(autre, faits=admis), autre


def test_voisin_une_lecture_sans_prix_n_admet_rien():
    fiche = {PAROLE.CLE_DU_TOUR: 1}
    PAROLE.admettre_les_valeurs(fiche, {"total": 3270, "sous_total": 2970})
    assert chiffre_dans_la_phrase("Ça fait trente-deux euros soixante-dix.", faits=PAROLE.etat_du_tour(fiche).faits_du_refus)
