"""[.mark] Module Restauration, lot 2 (D6) : la source d'heure de l'organisation.

| Test | Ce qu'il prouve |
|---|---|
| heure réelle interdite | aucun fichier du module ne lit l'heure réelle (``datetime.now``, ``utcnow``, ``date.today``, ``time.time``, ``now()`` ou ``current_date`` en SQL) ; la seule lecture est celle de ``horloge.py`` |
| le balayeur est éprouvé | le même balayage ROUGIT sur un fichier qui lit l'heure (cas rouge connu) |
| source remplaçable | une heure posée par un test est rendue (aware, UTC) ; retirée, l'heure réelle revient ; une heure sans fuseau est refusée |
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.db.bases_clients import horloge as module_horloge
from api.db.bases_clients.horloge import horloge, remplacer

RACINE = Path(module_horloge.__file__).resolve().parents[2]
# Les fichiers du module Restauration (les lots suivants ajoutent les leurs ici, par un motif).
MOTIFS = [
    "db/bases_clients/restauration*.py",
    "db/bases_clients/capacite.py",
    "db/bases_clients/plages.py",
    "db/bases_clients/annonce_heure.py",
    "db/bases_clients/recherche_liste*.py",
    "db/models_restauration.py",
    "services/restauration/**/*.py",
    "services/commande/*.py",
]
INTERDITS = re.compile(
    r"datetime\.now\(|datetime\.utcnow\(|date\.today\(|time\.time\(|time\.monotonic\(|\bnow\(\)|\bcurrent_date\b|\bcurrent_timestamp\b|\blocaltimestamp\b",
    re.IGNORECASE,
)


def _fichiers_du_module():
    for motif in MOTIFS:
        yield from sorted(RACINE.glob(motif))


def _lectures(chemin: Path) -> list[str]:
    fautes = []
    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
        code = ligne.split("#", 1)[0]
        if INTERDITS.search(code):
            fautes.append(f"{chemin.name}:{numero}: {ligne.strip()}")
    return fautes


def test_aucun_fichier_du_module_ne_lit_l_heure_reelle():
    fichiers = list(_fichiers_du_module())
    fautes = [f for fichier in fichiers for f in _lectures(fichier)]
    assert fautes == [], fautes
    # horloge.py : exactement UNE lecture de l'heure réelle
    assert len([f for f in _lectures(Path(module_horloge.__file__))]) == 1


def test_le_balayeur_rougit_sur_un_fichier_qui_lit_l_heure(tmp_path):
    for ligne in (
        "x = datetime.now(UTC)",
        "y = datetime.utcnow()",
        "d = date.today()",
        "t = time.time()",
        'sql = "SELECT now()"',
        'sql = "WHERE debut < CURRENT_TIMESTAMP"',
        'sql = "jour = current_date"',
    ):
        fichier = tmp_path / "faux.py"
        fichier.write_text(ligne + "\n", encoding="utf-8")
        assert _lectures(fichier), ligne
    propre = tmp_path / "propre.py"
    propre.write_text("maintenant = await heure(connexion)\nlisible = 'le fichier parle de now() dans un commentaire'  # now()\n", encoding="utf-8")
    assert len(_lectures(propre)) == 1  # la chaîne SQL « now() » est vue ; le commentaire seul ne l'est pas
    ok = tmp_path / "ok.py"
    ok.write_text("# datetime.now() dans un commentaire\nx = 1\n", encoding="utf-8")
    assert _lectures(ok) == []


def test_la_source_d_heure_est_remplacable_dans_les_tests_et_toujours_aware():
    reelle = horloge("org-1").maintenant()
    assert reelle.tzinfo is not None and abs(datetime.now(UTC) - reelle) < timedelta(seconds=5)
    fixe = datetime(2026, 11, 15, 12, 0, tzinfo=timezone(timedelta(hours=1)))
    with remplacer("org-1", fixe):
        assert horloge("org-1").maintenant() == fixe
        assert horloge("org-1").maintenant().utcoffset() == timedelta(0)  # rendue en UTC
        assert abs(datetime.now(UTC) - horloge("org-2").maintenant()) < timedelta(seconds=5)  # une autre organisation : réelle
        with pytest.raises(ValueError):
            with remplacer("org-3", datetime(2026, 1, 1)):  # sans fuseau
                horloge("org-3").maintenant()
    assert abs(datetime.now(UTC) - horloge("org-1").maintenant()) < timedelta(seconds=5)
