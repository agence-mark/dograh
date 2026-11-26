"""[.mark] Lot 8, PE-3 (Q10, point d'étape 7b-C du 26/11) : quand le jour est à préciser et que le nom est la chose suivante à demander, une seule question pour les deux.

Décision : ``bilan-point-d-etape-7b-c.md:278``. Le code donne le fait (``a_demander_ensemble`` : la valeur fermée du manque suivant) et une consigne ; le modèle compose la question.
Ordre réel des manques (``etat_pour_le_modele.ce_qui_manque_ensuite``) : personnes, jour, HEURE, nom, numéro. Le nom n'est donc le manque suivant le jour que si l'heure est dite.
Client « Une table pour deux jeudi à vingt heures. » (numéro masqué, deux jeudis possibles) / avant : « Ce jeudi ou le suivant ? » puis « À quel nom ? » / après : « À quel nom, et c'est ce
jeudi ou le suivant ? ». Sans l'heure (« Vous avez de la place jeudi pour deux ? ») : le manque suivant est l'heure, rien ne change.
"""

from __future__ import annotations

from api.services.actions_communes.resultat import Resultat
from api.services.reservation import etat_pour_le_modele as E
from api.tests.mark import test_base_client as _BASE
from api.tests.mark.partie_1 import aides_de_la_reservation as _RESA
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures de la base et de la salle, reprises sans import nu

DEUX_JEUDIS = [{"jour": "2026-11-19", "jour_dit": "jeudi dix-neuf novembre"}, {"jour": "2026-11-26", "jour_dit": "jeudi vingt-six novembre"}]
TEL = "+33612345678"


async def _jeudi_ambigu(texte, heure):
    return Resultat("AMBIGU", {"candidats": DEUX_JEUDIS}, "", "jour")


def _essai(salle, monkeypatch, appelant=None) -> EssaiReservation:
    essai = EssaiReservation(salle, monkeypatch, appelant=appelant)
    monkeypatch.setattr(essai.source, "resoudre_une_date", _jeudi_ambigu)
    return essai


async def test_jour_a_preciser_et_nom_ensuite_une_seule_question_pour_les_deux(salle, monkeypatch):
    essai = _essai(salle, monkeypatch)
    r = await essai.tour("une table pour deux jeudi à vingt heures", personnes=2, jour="jeudi", heure="vingt heures")
    assert r["resultats"][0]["manque"] == "jour", r
    assert r["faits"]["a_demander_ensemble"] == [E.LE_NOM], r
    assert r.get("a_faire"), r


async def test_voisin_sans_l_heure_le_manque_suivant_est_l_heure_rien_n_est_regroupe(salle, monkeypatch):
    """« Vous avez de la place jeudi pour deux ? » : l'heure manque aussi, la question du jour reste seule (``ce_qui_manque_ensuite`` : l'heure)."""
    essai = _essai(salle, monkeypatch)
    r = await essai.tour("vous avez de la place jeudi pour deux", personnes=2, jour="jeudi")
    assert "a_demander_ensemble" not in r["faits"] and not r.get("a_faire"), r


async def test_voisin_le_nom_deja_dit_le_manque_suivant_est_le_numero_rien_n_est_regroupe(salle, monkeypatch):
    essai = _essai(salle, monkeypatch)
    r = await essai.tour("une table pour deux jeudi à vingt heures au nom de Paul", personnes=2, jour="jeudi", heure="vingt heures", nom="Paul")
    assert "a_demander_ensemble" not in r["faits"] and not r.get("a_faire"), r


async def test_voisin_numero_affiche_et_nom_deja_dit_aucun_manque_ensuite(salle, monkeypatch):
    essai = _essai(salle, monkeypatch, appelant=TEL)
    r = await essai.tour("une table pour deux jeudi à vingt heures au nom de Paul", personnes=2, jour="jeudi", heure="vingt heures", nom="Paul")
    assert "a_demander_ensemble" not in r["faits"], r


# ── R3 (reprise de l'audit du 27/11) : le regroupement ne vaut que pour AMBIGU et INCOMPLETE ──────────────────────────────────────
# Décision de Pierre (27/11) : Q10 regroupe nom + jour seulement quand l'heure est dite. Une date illisible ou passée (INTROUVABLE, manque « jour ») garde son bloc propre.


async def _date_illisible(texte, heure):
    return Resultat("INTROUVABLE", {}, "", "jour")


async def test_r3_une_date_illisible_ou_passee_avec_l_heure_dite_ne_regroupe_rien(salle, monkeypatch):
    essai = _essai(salle, monkeypatch)
    monkeypatch.setattr(essai.source, "resoudre_une_date", _date_illisible)
    r = await essai.tour("une table pour deux hier à vingt heures", personnes=2, jour="hier", heure="vingt heures")
    assert r["resultats"][0]["manque"] == "jour" and r["resultats"][0]["statut_du_module"] == "INTROUVABLE", r
    assert "a_demander_ensemble" not in r["faits"], r


async def test_r3_le_jour_absent_avec_l_heure_dite_regroupe_le_nom_et_le_jour(salle, monkeypatch):
    """« Une table pour deux à vingt heures » (numéro masqué) : aucun jour dit, l'heure l'est : une seule question, le nom et le jour."""
    essai = _essai(salle, monkeypatch)
    r = await essai.tour("une table pour deux à vingt heures", personnes=2, heure="vingt heures")
    assert r["resultats"][0]["manque"] == "jour", r
    assert r["faits"]["a_demander_ensemble"] == [E.LE_NOM], r
    assert r.get("a_faire"), r
