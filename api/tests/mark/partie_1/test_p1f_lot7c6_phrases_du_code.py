"""[.mark] Lot 7b-C6 (décision d'Evan 25/11 9 h 30, § 8 bis) : les phrases du § 2 passent au modèle ; le code ne dit plus que le total, le numéro, le rendu de monnaie
(motifs réglables du catalogue) et les phrases déjà réglées (numéro dicté relu, numéro affiché gardé, après l'enregistrement).

Garde G3 : ce qui part à la voix est la phrase du modèle ou le texte d'un motif de ``PHRASES_DU_CODE``. Un xfail strict (``raises=AssertionError``) par famille de phrases, posé
au commit 1, retiré par le commit qui ferme la famille. Aucun modèle, aucun appel : on lit les sources.
"""

from __future__ import annotations

import re

import pytest

from api.outils import inventaire_rustines as I

API = I.RACINE_API
MODULE = "phrases_dites_par_le_code.py"

# Les motifs que le code dit encore, mot pour mot, après C6 (liste fermée).
MOTIFS_DU_CODE = frozenset({
    "total_relecture", "total_apres_correction", "total_apres_changement", "rendu_de_monnaie", "numero_retenu",
    "numero_dicte_relu", "numero_affiche_garde", "apres_enregistrement",
})

# Les familles du § 4 du brief : les noms du module d'avant que plus aucun appelant ne doit utiliser.
FAMILLES = {
    "relecture_de_la_commande": ("relecture_complete", "relecture_apres_changement", "ligne_passe_a", "note_de_moitie"),
    "rendu_de_monnaie": ("rendu_de_monnaie",),
    "confirmation_de_la_commande": ("enregistree_avec_delai", "enregistree_retrouvee", "deja_enregistree"),
    "changement_apres_l_enregistrement": ("changement",),
    "annulation_de_la_commande": ("annulation_demandee", "TEXTE_ANNULATION_CONFIRMEE", "TEXTE_ANNULEE_EN_COURS"),
    "relectures_de_la_reservation": ("relecture_de_la_reservation", "relecture_du_changement", "annulation_de_la_reservation"),
    "reservation_faite": ("reservation_enregistree", "reservation_modifiee", "reservation_annulee"),
    "numero_demande": ("quel_numero_je_note", "numero_affiche_propose"),
    "prix_au_poids": ("prix_au_poids",),
}


def _appelants(noms: tuple[str, ...]) -> list[str]:
    """Les lignes des sources (hors tests et hors du module lui-même) qui appellent un nom du module des phrases dites par le code."""
    motif = re.compile(r"\b(?:PHRASES_DITES|PD)\.(?:" + "|".join(noms) + r")\b")
    fautes = []
    for dossier in ("services", "db"):
        for p in sorted((API / dossier).rglob("*.py")):
            if p.name == MODULE or "tests" in p.parts or "__pycache__" in p.parts:
                continue
            for n, ligne in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if motif.search(ligne):
                    fautes.append(f"{p.relative_to(API).as_posix()}:{n}")
    return fautes


def _xfail(famille: str, raison: str):
    return pytest.param(famille, marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"C6 : {raison}"), id=famille)


@pytest.mark.parametrize("famille", [
    pytest.param("relecture_de_la_commande", id="relecture_de_la_commande"),  # fermée par les commits 3b et 4
    pytest.param("rendu_de_monnaie", id="rendu_de_monnaie"),  # fermée par le commit 5
    pytest.param("confirmation_de_la_commande", id="confirmation_de_la_commande"),  # fermée par le commit 5
    pytest.param("changement_apres_l_enregistrement", id="changement_apres_l_enregistrement"),  # fermée par le commit 6
    pytest.param("annulation_de_la_commande", id="annulation_de_la_commande"),  # fermée par le commit 7
    _xfail("relectures_de_la_reservation", "les relectures de la réservation passent au modèle (commit 8)"),
    _xfail("reservation_faite", "réservée, modifiée, annulée passent au modèle (commit 9)"),
    _xfail("numero_demande", "« quel numéro je note » et le numéro qui s'affiche passent au modèle (commit 10)"),
    _xfail("prix_au_poids", "le prix d'un article au poids passe au modèle, vérifié par la barrière (commit 11)"),
])
def test_plus_aucun_appelant_ne_dit_une_phrase_du_paragraphe_2_avec_les_mots_du_code(famille):
    assert _appelants(FAMILLES[famille]) == []


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C6 commit 10 : « Je note le {numero}. » devient le motif numero_retenu du catalogue")
def test_je_note_le_numero_n_est_plus_ecrit_dans_le_resultat_d_un_outil():
    source = (API / "services" / "actions_communes" / "resultat.py").read_text(encoding="utf-8")
    assert "Je note le {" not in source and "je note le {" not in source


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C6 commit 12 : la liste fermée PHRASES_DU_CODE remplace le module des phrases dites par le code")
def test_la_liste_fermee_des_phrases_du_code_est_celle_de_la_decision_du_25_11():
    from api.services.phrases import catalogue

    liste = getattr(catalogue, "PHRASES_DU_CODE", None)
    assert liste is not None and frozenset(liste) == MOTIFS_DU_CODE
    assert not (API / "services" / "commande" / MODULE).exists()
