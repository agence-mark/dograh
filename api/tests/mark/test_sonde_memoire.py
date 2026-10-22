"""La sonde mémoire de la CI comparée (``sonde_memoire.py``) arrête net et nomme le test.

Le plafond, la lecture de ``VmRSS`` et le fichier d'état se prouvent avec une lecture et une sortie
injectées (aucune dépendance à ``/proc``). Le dernier test joue la vraie sonde dans un pytest fils,
sous Linux seulement : c'est la chaîne du runner (fil, ``os._exit``, code 86, fichier d'état).
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from api.tests.mark import sonde_memoire as sm

ICI = Path(__file__).resolve().parent


def _sonde(tmp_path, lectures, plafond=100.0):
    sorties: list[int] = []
    suite = iter(lectures)
    sonde = sm.Sonde(
        plafond_mo=plafond,
        fichier=str(tmp_path / "sonde.json"),
        lire=lambda: next(suite),
        sortir=sorties.append,
    )
    return sonde, sorties


def test_lecture_de_vmrss_en_mo(tmp_path):
    statut = tmp_path / "status"
    statut.write_text(
        "Name:\tpython\nVmPeak:\t  999999 kB\nVmRSS:\t  204800 kB\nThreads:\t3\n",
        encoding="utf-8",
    )
    assert sm.lire_rss_mo(str(statut)) == 200.0


def test_lecture_impossible_rend_none(tmp_path):
    assert sm.lire_rss_mo(str(tmp_path / "absent")) is None
    mauvais = tmp_path / "status"
    mauvais.write_text("VmRSS:\t  beaucoup kB\n", encoding="utf-8")
    assert sm.lire_rss_mo(str(mauvais)) is None


def test_la_sonde_ne_s_active_que_sous_linux():
    assert sm.actif("linux") is True
    assert sm.actif("win32") is False
    assert sm.actif("darwin") is False


def test_hors_linux_le_plugin_ne_demarre_rien(monkeypatch):
    monkeypatch.setattr(sm, "actif", lambda plateforme=None: False)
    monkeypatch.setattr(sm, "_SONDE", None)
    sm.pytest_configure(config=None)
    assert sm._SONDE is None  # rien de lancé, rien d'écrit


def test_sous_le_plafond_rien_ne_s_arrete_et_le_pic_est_retenu(tmp_path):
    sonde, sorties = _sonde(tmp_path, [40.0, 90.0, 60.0])
    assert [sonde.echantillonner() for _ in range(3)] == [False, False, False]
    assert sorties == [] and sonde.pic_mo == 90.0 and not sonde.plafond_depasse


def test_au_dela_du_plafond_arret_net_avec_le_test_nomme_dans_le_fichier(tmp_path):
    sonde, sorties = _sonde(tmp_path, [40.0, 150.0])
    sonde.test_en_cours = "tests/mark/test_fuite.py::test_veille_sans_fin"
    sonde.collecte = 8512
    assert sonde.echantillonner() is False
    assert sonde.echantillonner() is True
    assert sorties == [sm.CODE_SORTIE_PLAFOND]
    etat = json.loads((tmp_path / "sonde.json").read_text(encoding="utf-8"))
    assert etat["plafond_depasse"] is True
    assert etat["test_en_cours"] == "tests/mark/test_fuite.py::test_veille_sans_fin"
    assert (
        etat["pic_mo"] == 150.0
        and etat["collecte"] == 8512
        and etat["termine"] is False
    )


def test_une_lecture_impossible_n_arrete_rien(tmp_path):
    sonde, sorties = _sonde(tmp_path, [None])
    assert sonde.echantillonner() is False and sorties == []


def test_le_fichier_d_etat_est_ecrit_atomiquement(tmp_path):
    sonde, _ = _sonde(tmp_path, [])
    sonde.ecrire()
    assert not (tmp_path / "sonde.json.tmp").exists()
    assert (
        json.loads((tmp_path / "sonde.json").read_text(encoding="utf-8"))["termine"]
        is False
    )


def test_le_comparateur_lit_l_etat_de_la_sonde_comme_elle_l_ecrit(tmp_path):
    """Le contrat entre les deux fichiers : ce que la sonde écrit est ce que le comparateur exige."""
    from api.scripts.mark import comparer_echecs as ce

    sonde, _ = _sonde(tmp_path, [150.0])
    sonde.test_en_cours = "tests/z.py::test_z"
    sonde.collecte = 1
    sonde.echantillonner()
    (tmp_path / ce.FICHIER_SONDE).write_text(
        (tmp_path / "sonde.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / ce.FICHIER_CODE).write_text("86", encoding="utf-8")
    passage = ce.lire_passage("branche", tmp_path)
    assert not passage.complet
    assert any(
        "tests/z.py::test_z" in r and "plafond mémoire" in r for r in passage.raisons
    )


@pytest.mark.skipif(
    not sm.actif(), reason="/proc n'existe que sous Linux : la CI joue ce test"
)
def test_vraie_sonde_dans_un_pytest_fils_tue_le_processus_et_nomme_le_test(tmp_path):
    (tmp_path / "test_fuite.py").write_text(
        textwrap.dedent(
            """
            import time

            def test_petit():
                assert True

            def test_gros_et_long():
                morceau = b"x" * (400 * 1024 * 1024)  # 400 Mo réellement touchés
                time.sleep(30)  # la sonde doit tuer le processus bien avant
                assert morceau
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    fichier = tmp_path / "sonde.json"
    env = {
        **os.environ,
        "PYTHONPATH": str(ICI),
        "MARK_SONDE_PLAFOND_MO": "250",
        "MARK_SONDE_FICHIER": str(fichier),
    }
    fin = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "sonde_memoire",
            "-p",
            "no:cacheprovider",
            "-c",
            str(tmp_path / "pytest.ini"),
            "--rootdir",
            str(tmp_path),
            str(tmp_path / "test_fuite.py"),
            "-q",
        ],
        check=False,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert fin.returncode == sm.CODE_SORTIE_PLAFOND, fin.stdout + fin.stderr
    etat = json.loads(fichier.read_text(encoding="utf-8"))
    assert etat["plafond_depasse"] is True and etat["termine"] is False
    assert etat["test_en_cours"].endswith("test_fuite.py::test_gros_et_long")
    assert etat["collecte"] == 2
    # Le message sur stderr n'est pas vérifié : sans ``-s`` pytest capture le descripteur 2 et
    # ``os._exit`` ne le vide pas. Le fichier d'état est la trace qui compte.


@pytest.mark.skipif(
    not sm.actif(), reason="/proc n'existe que sous Linux : la CI joue ce test"
)
def test_vraie_sonde_session_normale_ecrit_termine(tmp_path):
    (tmp_path / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    fichier = tmp_path / "sonde.json"
    env = {**os.environ, "PYTHONPATH": str(ICI), "MARK_SONDE_FICHIER": str(fichier)}
    fin = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "sonde_memoire",
            "-p",
            "no:cacheprovider",
            "-c",
            str(tmp_path / "pytest.ini"),
            "--rootdir",
            str(tmp_path),
            str(tmp_path / "test_ok.py"),
            "-q",
        ],
        check=False,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert fin.returncode == 0, fin.stdout + fin.stderr
    etat = json.loads(fichier.read_text(encoding="utf-8"))
    assert etat["termine"] is True and etat["plafond_depasse"] is False
    assert etat["collecte"] == 1 and etat["statut_pytest"] == 0 and etat["pic_mo"] > 0
