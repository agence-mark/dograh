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

from api.services.actions_communes.enveloppe_legere import pour_le_modele

from api.services.commande import etat_pour_le_modele as ETAT_COMMANDE
from api.services.commande import moteur, porte
from api.services.commande.moteur import articles
from api.services.commande.moteur import socle as _socle
from api.services.commande.resultat import Resultat
from api.services.phrases.catalogue import MOTIFS, PHRASES_DU_CODE
from api.services.reservation import etat_pour_le_modele as ETAT_RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_reservation as _RESA

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures du classeur, reprises sans import inutile

SEUIL_DE_LETTRES = 12
FERME = "Nous sommes fermés pour le moment, nous rouvrons à dix-huit heures. Pour quel jour et à quelle heure ?"
INTROUVABLE = "Je ne trouve pas de pizza au homard dans notre carte."


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


# C6 n° 12 (décision d'Evan 25/11 9 h 30) : les phrases que le code peut dire mot pour mot sont les variantes des motifs de la liste fermée ``PHRASES_DU_CODE``
_DU_PLAN = [re.compile("^" + re.sub(r"\\{[a-z_]+\\}", ".*", re.escape(v)) + "$") for m in sorted(PHRASES_DU_CODE) for v in MOTIFS[m].variantes_defaut]


def _hors_du_plan(valeurs: list[str]) -> list[str]:
    """Les valeurs d'un retour moins les phrases que le plan permet au code de dire mot pour mot (``PHRASES_DU_CODE``, C6 n° 12)."""
    return [v for v in valeurs if not any(m.match(v.strip()) for m in _DU_PLAN)]


def _fuites(r: dict, du_tour: list[str]) -> list[str]:
    """G1 sur le retour ENTIER (audit C0) : une suggestion du tour sous n'importe quelle clé (``pourquoi``, ``dit``…) est une fuite, pas seulement dans son canal."""
    return _qui_figurent(du_tour, _hors_du_plan(_valeurs(pour_le_modele(r))))  # la copie que le modèle lit : le constat caché (``CLE_DU``) n'en fait pas partie


def _fuites_de_l_etat(etat: str | None, du_tour: list[str]) -> list[str]:
    """G1 sur l'état que le modèle lit à chaque tour (5e canal, audit C4) : même règle que pour le retour, une suggestion du tour n'y figure pas."""
    return _qui_figurent(du_tour, (etat or "").splitlines())


async def _explication(essai_de, suggestions, monkeypatch):
    """Client « Une pizza au homard. » : l'article n'existe pas, le module refuse (introuvable) et donne sa phrase. Depuis C7a le module n'écrit plus cette phrase : le scénario la lui
    fait écrire (comme ``_heure_a_dire`` avec ``FERME``), sinon G1 ne pourrait plus échouer et ne prouverait rien."""
    origine = articles._r
    monkeypatch.setattr(articles, "_r", lambda statut, faits, suggestion, *reste: origine(statut, faits, suggestion or (INTROUVABLE if statut == "INTROUVABLE" else ""), *reste))
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    suggestions.clear()
    r = await e.tour("une pizza au homard", ajouter=[{"article": "pizza au homard", "quantite": 1}])
    return r, [x["explication"] for x in r["faits"].get("refus_de_la_fiche", []) if "explication" in x], _du_tour(suggestions), ETAT_COMMANDE.texte(e.fiche_de_l_appel)


async def _heure_a_dire(essai_de, suggestions, monkeypatch):
    """Client « C'est tout » restaurant fermé, commande pour plus tard permise : le module rend « fermé mais planifiable » avec sa phrase."""
    e = await essai_de("casa-italia")
    await e.dit("deux reines à emporter").fiche(ajouter=[{"article": "regina", "quantite": 2, "variante": "Normale"}], mode_de_retrait="emporter")

    async def ferme(_source, p, _regles, _appelant, confirmer=False):
        return _socle._avec(moteur.Resultat("FERME_PLANIFIABLE", {"raison": "ferme_horaires", "a_planifier": True}, FERME, "heure_voulue"), p)

    monkeypatch.setattr(porte, "mener_a_la_fin", ferme)
    suggestions.clear()
    r = await e.dit("non merci, c'est tout").fiche(c_est_tout=True)
    return r, [x["explication"] for x in r["faits"].get("heure_a_dire", []) if "explication" in x], _du_tour(suggestions), ETAT_COMMANDE.texte(e.fiche_de_l_appel)


async def _question(essai_de, suggestions):
    """Client « Une regina. » : la taille manque, le module pose la question avec sa phrase."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    suggestions.clear()
    r = await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    return r, [r["question"]["texte"]] if isinstance(r.get("question"), dict) and r["question"]["texte"] else [], _du_tour(suggestions), ETAT_COMMANDE.texte(e.fiche_de_l_appel)


async def _texte_a_dire(salle, monkeypatch, suggestions):
    """Client « Quatre personnes. » à la réservation : le jour manque, le module rend sa phrase (« Pour quel jour ? »)."""
    essai = EssaiReservation(salle, monkeypatch)
    suggestions.clear()
    r = await essai.tour("quatre personnes", personnes=4)
    return r, [r["texte_a_dire"]] if r.get("texte_a_dire") else [], _du_tour(suggestions), ETAT_RESERVATION.texte(essai.fiche_de_l_appel)


# ── le scénario atteint le canal (vert) ─────────────────────────────────────────────────────────────────────────────────

async def test_scenario_explication_atteint_le_canal(essai_de, suggestions, monkeypatch):
    """Le refus est bien dans ``refus_de_la_fiche`` (ses faits, sans phrase) et le module a écrit une suggestion dans le tour (le scénario la lui fait écrire : le canal n'est creux que si elle existe)."""
    r, valeurs, du_tour, _ = await _explication(essai_de, suggestions, monkeypatch)
    assert r["faits"]["refus_de_la_fiche"] and INTROUVABLE in du_tour and not valeurs, (r["faits"], du_tour)


async def test_scenario_heure_a_dire_atteint_le_canal(essai_de, suggestions, monkeypatch):
    r, valeurs, du_tour, _ = await _heure_a_dire(essai_de, suggestions, monkeypatch)
    assert r["faits"]["heure_a_dire"] and FERME in du_tour and not valeurs, (r["faits"], du_tour)


async def test_scenario_question_atteint_le_canal(essai_de, suggestions):
    r, valeurs, du_tour, _ = await _question(essai_de, suggestions)
    assert r["question"]["type"] == "variante" and du_tour and not valeurs, (r["question"], du_tour)  # la question est posée, sans phrase


async def test_scenario_texte_a_dire_atteint_le_canal(salle, monkeypatch, suggestions):
    r, valeurs, du_tour, _ = await _texte_a_dire(salle, monkeypatch, suggestions)
    assert r["manque"] and du_tour and not valeurs, (r, du_tour)  # le manque est un fait (« jour »), sa phrase est dans le constat caché


# ── G1 : aucune suggestion du tour dans le canal (échec attendu strict, un par canal) ───────────────────────────────────

async def test_g1_canal_explication(essai_de, suggestions, monkeypatch):
    """Client « Une pizza au homard. » : le retour ne dit ni la phrase du module ni « pas de pizza » ; le modèle dit le refus avec ses mots, d'après les faits."""
    r, _, du_tour, etat = await _explication(essai_de, suggestions, monkeypatch)
    assert not _fuites(r, du_tour), _fuites(r, du_tour)
    assert not _fuites_de_l_etat(etat, du_tour), _fuites_de_l_etat(etat, du_tour)
    assert not [v for v in _valeurs(r) if "pas de pizza" in v], r


async def test_g1_canal_heure_a_dire(essai_de, suggestions, monkeypatch):
    r, _, du_tour, etat = await _heure_a_dire(essai_de, suggestions, monkeypatch)
    assert not _fuites(r, du_tour), _fuites(r, du_tour)
    assert not _fuites_de_l_etat(etat, du_tour), _fuites_de_l_etat(etat, du_tour)


async def test_g1_canal_question_texte(essai_de, suggestions):
    r, _, du_tour, etat = await _question(essai_de, suggestions)
    assert not _fuites(r, du_tour), _fuites(r, du_tour)
    assert not _fuites_de_l_etat(etat, du_tour), _fuites_de_l_etat(etat, du_tour)


async def test_g1_canal_texte_a_dire(salle, monkeypatch, suggestions):
    r, _, du_tour, etat = await _texte_a_dire(salle, monkeypatch, suggestions)
    assert not _fuites(r, du_tour), _fuites(r, du_tour)
    assert not _fuites_de_l_etat(etat, du_tour), _fuites_de_l_etat(etat, du_tour)
