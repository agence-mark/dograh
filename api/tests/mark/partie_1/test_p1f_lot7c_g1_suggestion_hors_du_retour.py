"""[.mark] Lot 7b-C0, G1 (garde dynamique) : sur les scénarios rapides, aucune suggestion du tour (12 lettres et plus) ne figure dans le retour donné au modèle, un cas par canal.

Les quatre canaux par lesquels le texte d'un module arrive au modèle (fiche de la 7b-C, § 0) : ``faits.refus_de_la_fiche[].explication``, ``faits.heure_a_dire[].explication``,
``question.texte`` et ``texte_a_dire``. Avec R = A, la suggestion reste écrite dans le module comme texte de secours, lu par le repli seul ; le modèle reçoit des faits, jamais la phrase.

Chaque canal a deux tests : le scénario atteint bien le canal (vert, sinon l'échec attendu ne prouverait rien) ; G1 elle-même, en échec attendu strict tant que le canal n'est pas fermé
(la sous-tranche C4 ferme un canal par commit et retire l'échec attendu du sien : un échec attendu qui passe est rouge).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from api.services.commande import moteur, porte
from api.services.commande.moteur import socle as _socle
from api.services.commande.resultat import Resultat
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_reservation as _RESA

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures du classeur, reprises sans import inutile

SEUIL_DE_LETTRES = 12
FERME = "Nous sommes fermés pour le moment, nous rouvrons à dix-huit heures. Pour quel jour et à quelle heure ?"


def _lettres(texte: str) -> int:
    return len(re.findall(r"[^\W\d_]", texte))


def _valeurs(x: Any) -> list[str]:
    """Toutes les chaînes d'un retour, à tous les niveaux."""
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [v for valeur in x.values() for v in _valeurs(valeur)]
    if isinstance(x, (list, tuple)):
        return [v for valeur in x for v in _valeurs(valeur)]
    return []


@pytest.fixture
def suggestions(monkeypatch):
    """Les suggestions de tous les ``Resultat`` rendus par les modules depuis le dernier ``vider`` : la liste se remplit toute seule, ``vider`` la remet à zéro avant le tour joué."""
    notees: list[str] = []
    origine = Resultat.__init__

    def noter(self, *args, **kwargs):
        origine(self, *args, **kwargs)
        notees.append(self.suggestion or "")

    monkeypatch.setattr(Resultat, "__init__", noter)
    return notees


def _du_tour(notees: list[str]) -> list[str]:
    return sorted({s.strip() for s in notees if _lettres(s) >= SEUIL_DE_LETTRES})


def _qui_figurent(suggestions_du_tour: list[str], valeurs: list[str]) -> list[str]:
    return [v for v in valeurs if any(s in v for s in suggestions_du_tour)]


async def _explication(essai_de, suggestions):
    """Client « Une pizza au homard. » : l'article n'existe pas, le module refuse (introuvable) et donne sa phrase."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    suggestions.clear()
    r = await e.tour("une pizza au homard", ajouter=[{"article": "pizza au homard", "quantite": 1}])
    return r, [x["explication"] for x in r["faits"].get("refus_de_la_fiche", []) if "explication" in x], _du_tour(suggestions)


async def _heure_a_dire(essai_de, suggestions, monkeypatch):
    """Client « C'est tout » restaurant fermé, commande pour plus tard permise : le module rend « fermé mais planifiable » avec sa phrase."""
    e = await essai_de("casa-italia")
    await e.dit("deux reines à emporter").fiche(ajouter=[{"article": "regina", "quantite": 2, "variante": "Normale"}], mode_de_retrait="emporter")

    async def ferme(_source, p, _regles, _appelant, confirmer=False):
        return _socle._avec(moteur.Resultat("FERME_PLANIFIABLE", {"raison": "ferme_horaires", "a_planifier": True}, FERME, "heure_voulue"), p)

    monkeypatch.setattr(porte, "mener_a_la_fin", ferme)
    suggestions.clear()
    r = await e.dit("non merci, c'est tout").fiche(c_est_tout=True)
    return r, [x["explication"] for x in r["faits"].get("heure_a_dire", []) if "explication" in x], _du_tour(suggestions)


async def _question(essai_de, suggestions):
    """Client « Une regina. » : la taille manque, le module pose la question avec sa phrase."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    suggestions.clear()
    r = await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    return r, [r["question"]["texte"]] if isinstance(r.get("question"), dict) else [], _du_tour(suggestions)


async def _texte_a_dire(salle, monkeypatch, suggestions):
    """Client « Quatre personnes. » à la réservation : le jour manque, le module rend sa phrase (« Pour quel jour ? »)."""
    essai = EssaiReservation(salle, monkeypatch)
    suggestions.clear()
    r = await essai.tour("quatre personnes", personnes=4)
    return r, [r["texte_a_dire"]] if r.get("texte_a_dire") else [], _du_tour(suggestions)


# ── le scénario atteint le canal (vert) ─────────────────────────────────────────────────────────────────────────────────

async def test_scenario_explication_atteint_le_canal(essai_de, suggestions):
    _, valeurs, du_tour = await _explication(essai_de, suggestions)
    assert valeurs and du_tour, (valeurs, du_tour)


async def test_scenario_heure_a_dire_atteint_le_canal(essai_de, suggestions, monkeypatch):
    _, valeurs, du_tour = await _heure_a_dire(essai_de, suggestions, monkeypatch)
    assert valeurs and FERME in du_tour, (valeurs, du_tour)


async def test_scenario_question_atteint_le_canal(essai_de, suggestions):
    _, valeurs, du_tour = await _question(essai_de, suggestions)
    assert valeurs and du_tour, (valeurs, du_tour)


async def test_scenario_texte_a_dire_atteint_le_canal(salle, monkeypatch, suggestions):
    _, valeurs, du_tour = await _texte_a_dire(salle, monkeypatch, suggestions)
    assert valeurs and du_tour, (valeurs, du_tour)


# ── G1 : aucune suggestion du tour dans le canal (échec attendu strict, un par canal) ───────────────────────────────────

def _a_fermer(canal: str):
    return pytest.mark.xfail(strict=True, reason=f"G1, canal {canal} : la suggestion du module arrive encore au modèle (7b-C4 ferme le canal)")


@_a_fermer("explication")
async def test_g1_canal_explication(essai_de, suggestions):
    """Client « Une pizza au homard. » : le retour ne dit ni la phrase du module ni « pas de pizza » ; le modèle dit le refus avec ses mots, d'après les faits."""
    r, valeurs, du_tour = await _explication(essai_de, suggestions)
    assert not _qui_figurent(du_tour, valeurs), valeurs
    assert not [v for v in _valeurs(r) if "pas de pizza" in v], r


@_a_fermer("heure_a_dire")
async def test_g1_canal_heure_a_dire(essai_de, suggestions, monkeypatch):
    _, valeurs, du_tour = await _heure_a_dire(essai_de, suggestions, monkeypatch)
    assert not _qui_figurent(du_tour, valeurs), valeurs


@_a_fermer("question.texte")
async def test_g1_canal_question_texte(essai_de, suggestions):
    _, valeurs, du_tour = await _question(essai_de, suggestions)
    assert not _qui_figurent(du_tour, valeurs), valeurs


@_a_fermer("texte_a_dire")
async def test_g1_canal_texte_a_dire(salle, monkeypatch, suggestions):
    _, valeurs, du_tour = await _texte_a_dire(salle, monkeypatch, suggestions)
    assert not _qui_figurent(du_tour, valeurs), valeurs
