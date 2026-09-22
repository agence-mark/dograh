"""[.mark] Garantie : les deux lecteurs ne coûtent pas le tour de parole.

Ce que ce fichier protège : **un motif ou une requête qui explose**, pas la
vitesse d'une machine. Les plafonds sont donc larges — deux à cinq fois les
mesures du 22/09 sur le poste — et ce qu'on veut voir rougir, c'est une
recherche devenue quadratique, une clé recalculée à l'appel, ou un index lu
sans passer par son cache.

Mesuré le 22/09 (poste d'Evan, à revérifier sur Railway) :

| Geste | Médiane | p95 | Pire |
|---|---|---|---|
| Une rue cherchée | 6,1 ms | 10,6 ms | 51 ms (Paris, 5 871 voies) |
| Une phrase lue pour l'épellation | 0,018 ms | — | — |
| Une commune chargée depuis le fichier | 2 à 9 ms | — | 64 ms (Paris) |

⛔ Ce que ce fichier NE dit pas : ce que ça coûte **sur Railway**, où plusieurs
appels se partagent les cœurs. Cette mesure-là se fait au déploiement.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import pytest

from api.services.epellation.lecture import lire as lire_epellations
from api.services.voies import base as base_voies
from api.services.voies.analyse import analyser

DONNEES = Path(__file__).parent / "donnees"

# Beauvais (726 voies) : une commune ordinaire. Paris (5 871) : le pire cas
# national, et il est dans l'index de test exprès.
BEAUVAIS = "60057"
PARIS = "75056"

PHRASES = [
    "12 rue des Tilleuls",
    "c'est au 6 rue Danton",
    "j'habite 45 avenue du Général de Gaulle",
    "alors c'est 3 impasse du Moulin",
    "l'adresse c'est 26 rue Victor Hugo",
]


@pytest.fixture(autouse=True)
def index_de_test(monkeypatch, tmp_path):
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", DONNEES / "voies")
    monkeypatch.setattr(base_voies, "EXPORT", "test-2026-09-16")
    monkeypatch.setattr(base_voies, "DOSSIER_TRAVAIL", tmp_path / "voies")
    base_voies.voies_de.cache_clear()
    yield
    base_voies.voies_de.cache_clear()


def _durees(faire, combien: int = 20) -> list[float]:
    faire()  # un tour à blanc : ce qui se mesure n'est pas le premier chargement
    mesures = []
    for _ in range(combien):
        debut = time.perf_counter()
        faire()
        mesures.append((time.perf_counter() - debut) * 1000)
    return sorted(mesures)


def test_une_rue_se_cherche_en_quelques_millisecondes():
    voies = base_voies.voies_de(BEAUVAIS)
    mesures = _durees(lambda: [analyser(p, voies, "Beauvais") for p in PHRASES], combien=10)
    par_phrase = [m / len(PHRASES) for m in mesures]
    assert statistics.median(par_phrase) <= 40, par_phrase
    assert max(par_phrase) <= 120, par_phrase


def test_la_plus_grosse_commune_de_france_reste_tenable():
    """Paris, 5 871 voies. ⛔ Si une recherche devenait quadratique, c'est ici
    que ça se verrait d'abord."""
    voies = base_voies.voies_de(PARIS)
    mesures = _durees(lambda: analyser("c'est au 14 rue de la Roquette", voies, "Paris"), combien=10)
    assert statistics.median(mesures) <= 150, mesures


def test_lire_lepellation_ne_coute_presque_rien():
    """Ce lecteur tourne à CHAQUE tour de parole (Q8), donc son coût doit être
    invisible même sur une phrase sans la moindre lettre épelée."""
    phrases = [
        "bonjour, je voudrais faire ramoner mon poêle à granulés avant l'hiver",
        "c'est monsieur Flamand, f l a m a n t",
        "il n'y a pas de problème, je suis disponible toute la semaine",
    ]
    mesures = _durees(lambda: [lire_epellations(p) for p in phrases], combien=200)
    assert statistics.median(mesures) / len(phrases) <= 2, mesures[:5]


def test_une_commune_deja_lue_ne_retouche_pas_le_fichier():
    """🔑 Le cache borné est ce qui rend les tours suivants gratuits. Sans lui,
    chaque tour d'adresse relirait le SQLite — 64 ms pour Paris, à chaque fois.
    """
    base_voies.voies_de(BEAUVAIS)
    mesures = _durees(lambda: base_voies.voies_de(BEAUVAIS), combien=100)
    # Un accès au cache se compte en microsecondes ; une relecture, en millisecondes.
    assert max(mesures) <= 1, mesures[-5:]


def test_les_cles_ne_sont_jamais_recalculees_a_lappel():
    """⛔ Le défaut que ce chiffre protège : recalculer les clés au chargement
    coûtait 1,9 s pour Paris. Elles sont stockées, donc lire Paris est rapide.
    """
    base_voies.voies_de.cache_clear()
    debut = time.perf_counter()
    voies = base_voies.voies_de(PARIS)
    duree = (time.perf_counter() - debut) * 1000
    assert len(voies) > 5000
    assert duree <= 900, f"{duree:.0f} ms pour lire Paris"
