"""Le comparateur de la CI comparée (``api/scripts/mark/comparer_echecs.py``) ne ment jamais.

Réflexe R7 : un outil de vérification maison s'éprouve sur des cas rouges connus. Six rapports
factices (vert, nouveau rouge, rouge déjà présent, tronqué, absent, renommé), puis les lectures
croisées (code de sortie, JUnit, sonde) qui font d'un passage douteux un « passage incomplet ».
La preuve sur un vrai runner (trois cas joués exprès) est au journal du chantier.
"""

import json
from pathlib import Path

import pytest

from api.scripts.mark import comparer_echecs as ce


def _junit(tests: dict[str, str]) -> str:
    """``{"module::test": "ok" | "failure" | "error" | "skipped"}`` -> rapport JUnit de pytest."""
    cas = []
    for identifiant, issue in tests.items():
        classe, nom = identifiant.split("::")
        corps = {
            "ok": "",
            "failure": '<failure message="assert 1 == 2">détail</failure>',
            "error": '<error message="boom">détail</error>',
            "skipped": '<skipped message="raison"/>',
        }[issue]
        cas.append(
            f'<testcase classname="{classe}" name="{nom}" time="0.01">{corps}</testcase>'
        )
    nb = sum(1 for i in tests.values() if i in ("failure", "error"))
    return (
        '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        f'<testsuite name="pytest" errors="0" failures="{nb}" skipped="0" tests="{len(tests)}">'
        + "".join(cas)
        + "</testsuite></testsuites>"
    )


def _passage(
    dossier: Path,
    tests: dict[str, str] | None,
    *,
    code: int | str | None = "auto",
    sonde: dict | None | str = "auto",
    junit_brut: str | None = None,
) -> Path:
    """Écrit un passage. ``None`` = fichier absent ; ``"auto"`` = valeur cohérente avec les tests."""
    dossier.mkdir(parents=True, exist_ok=True)
    if junit_brut is not None:
        (dossier / ce.FICHIER_JUNIT).write_text(junit_brut, encoding="utf-8")
    elif tests is not None:
        (dossier / ce.FICHIER_JUNIT).write_text(_junit(tests), encoding="utf-8")
    if code == "auto":
        rouges = tests and any(i in ("failure", "error") for i in tests.values())
        code = 1 if rouges else 0
    if code is not None:
        (dossier / ce.FICHIER_CODE).write_text(f"{code}\n", encoding="utf-8")
    if sonde == "auto":
        sonde = {
            "plafond_mo": 6144,
            "pic_mo": 812.4,
            "plafond_depasse": False,
            "test_en_cours": "tests/mark/test_x.py::test_a",
            "collecte": len(tests or {}),
            "termine": True,
            "statut_pytest": 0,
        }
    if sonde is not None:
        (dossier / ce.FICHIER_SONDE).write_text(json.dumps(sonde), encoding="utf-8")
    return dossier


SOCLE = {
    "tests.a::test_un": "ok",
    "tests.a::test_deux": "ok",
    "tests.b::test_trois": "ok",
}


def _comparer(
    tmp_path,
    tests_branche: dict | None,
    tests_base: dict | None,
    branche=None,
    base=None,
):
    """``branche`` et ``base`` : options de ``_passage`` propres à chaque passage."""
    b = _passage(tmp_path / "branche", tests_branche, **(branche or {}))
    s = _passage(tmp_path / "base", tests_base, **(base or {}))
    return ce.comparer(ce.lire_passage("branche", b), ce.lire_passage("base", s))


# ---------------------------------------------------------------- les six cas de R7


def test_cas_1_vert(tmp_path):
    v = _comparer(tmp_path, SOCLE, SOCLE)
    assert v.code == ce.VERT
    assert not v.nouveaux and not v.deja_presents


def test_cas_2_nouveau_rouge_nomme(tmp_path):
    branche = {**SOCLE, "tests.b::test_trois": "failure"}
    v = _comparer(tmp_path, branche, SOCLE)
    assert v.code == ce.ROUGE
    assert list(v.nouveaux) == ["tests.b::test_trois"]
    assert "assert 1 == 2" in v.nouveaux["tests.b::test_trois"]
    assert "`tests.b::test_trois`" in ce.rendre(v)


def test_cas_3_rouge_deja_present_liste_sans_bloquer(tmp_path):
    rouge = {**SOCLE, "tests.a::test_deux": "error"}
    v = _comparer(tmp_path, rouge, rouge)
    assert v.code == ce.VERT
    assert list(v.deja_presents) == ["tests.a::test_deux"]
    texte = ce.rendre(v)
    assert (
        "Vert" in texte and "`tests.a::test_deux`" in texte and "non bloquants" in texte
    )


def test_cas_4_rapport_tronque_est_incomplet(tmp_path):
    complet = _junit(SOCLE)
    v = _comparer(
        tmp_path,
        None,
        SOCLE,
        branche={"junit_brut": complet[: len(complet) // 2], "code": 1},
    )
    assert v.code == ce.INCOMPLET
    assert any("tronqué" in r for r in v.branche.raisons)
    assert "incomplet" in ce.rendre(v)


def test_cas_5_rapport_absent_est_incomplet(tmp_path):
    v = _comparer(tmp_path, SOCLE, None, base={"code": None, "sonde": None})
    assert v.code == ce.INCOMPLET
    raisons = " ".join(v.base.raisons)
    assert "rapport JUnit absent" in raisons and "code de sortie" in raisons
    assert v.branche.complet


def test_cas_5_bis_dossier_absent_est_incomplet(tmp_path):
    v = ce.comparer(
        ce.lire_passage("branche", _passage(tmp_path / "branche", SOCLE)),
        ce.lire_passage("base", tmp_path / "n-existe-pas"),
    )
    assert v.code == ce.INCOMPLET


def test_cas_6_test_renomme_est_nouveau_et_l_ancien_disparait(tmp_path):
    base = {**SOCLE, "tests.a::test_un": "failure"}
    branche = {k: v for k, v in SOCLE.items() if k != "tests.a::test_un"}
    branche["tests.a::test_un_renomme"] = "failure"
    v = _comparer(tmp_path, branche, base)
    assert (
        v.code == ce.ROUGE
    )  # le rouge renommé n'est pas « déjà présent » : il est nommé nouveau
    assert list(v.nouveaux) == ["tests.a::test_un_renomme"]
    assert v.disparus == ["tests.a::test_un"]
    assert "supprimés ou renommés" in ce.rendre(v)


# ------------------------------------------------- les règles du plan (D5) et du résumé


def test_un_test_vert_seul_mais_rouge_en_suite_est_nouveau(tmp_path):
    """D5 : le comparateur ne connaît que le résultat dans la suite, jamais le nom du test."""
    branche = {
        **SOCLE,
        "tests.a::test_un": "failure",
    }  # fuite d'un test à l'autre : rouge en suite
    v = _comparer(tmp_path, branche, SOCLE)
    assert v.code == ce.ROUGE and "tests.a::test_un" in v.nouveaux


def test_un_test_corrige_est_liste(tmp_path):
    base = {**SOCLE, "tests.a::test_un": "failure"}
    v = _comparer(tmp_path, SOCLE, base)
    assert v.code == ce.VERT and v.corriges == ["tests.a::test_un"]


def test_un_test_ignore_n_est_pas_un_echec(tmp_path):
    branche = {**SOCLE, "tests.b::test_trois": "skipped"}
    assert _comparer(tmp_path, branche, SOCLE).code == ce.VERT


def test_deux_elements_pour_un_test_dont_le_demontage_echoue(tmp_path):
    """pytest émet un second ``testcase`` quand l'appel passe et que le démontage échoue."""
    branche = _junit(SOCLE).replace(
        "</testsuite>",
        '<testcase classname="tests.a" name="test_un"><error message="teardown">x</error></testcase></testsuite>',
    )
    b = _passage(
        tmp_path / "branche",
        None,
        junit_brut=branche,
        code=1,
        sonde={
            "plafond_mo": 6144,
            "pic_mo": 1,
            "plafond_depasse": False,
            "test_en_cours": "t",
            "collecte": 3,
            "termine": True,
            "statut_pytest": 1,
        },
    )
    s = _passage(tmp_path / "base", SOCLE)
    v = ce.comparer(ce.lire_passage("branche", b), ce.lire_passage("base", s))
    assert v.code == ce.ROUGE and list(v.nouveaux) == ["tests.a::test_un"]


# ---------------------------------------------------- lectures croisées : jamais un vert par défaut


@pytest.mark.parametrize("code", [2, 3, 4, 5, 86, 137])
def test_un_code_de_sortie_hors_0_et_1_est_incomplet_meme_si_le_rapport_est_vert(
    tmp_path, code
):
    v = _comparer(tmp_path, SOCLE, SOCLE, branche={"code": code})
    assert v.code == ce.INCOMPLET
    assert any(f"code {code}" in r for r in v.branche.raisons)


def test_code_0_mais_des_echecs_dans_le_rapport_est_incoherent(tmp_path):
    branche = {**SOCLE, "tests.a::test_un": "failure"}
    v = _comparer(tmp_path, branche, SOCLE, branche={"code": 0})
    assert v.code == ce.INCOMPLET and any("code 0" in r for r in v.branche.raisons)


def test_code_1_mais_aucun_echec_dans_le_rapport_est_incoherent(tmp_path):
    v = _comparer(tmp_path, SOCLE, SOCLE, branche={"code": 1})
    assert v.code == ce.INCOMPLET and any("code 1" in r for r in v.branche.raisons)


def test_plafond_memoire_depasse_nomme_le_test(tmp_path):
    sonde = {
        "plafond_mo": 6144,
        "pic_mo": 6300.0,
        "plafond_depasse": True,
        "test_en_cours": "tests/mark/test_fuite.py::test_veille_sans_fin",
        "collecte": 3,
        "termine": False,
        "statut_pytest": None,
    }
    v = _comparer(
        tmp_path, None, SOCLE, branche={"code": 86, "sonde": sonde, "junit_brut": None}
    )
    assert v.code == ce.INCOMPLET
    texte = ce.rendre(v)
    assert "tests/mark/test_fuite.py::test_veille_sans_fin" in texte
    assert "plafond mémoire" in texte


def test_moins_de_tests_relus_que_de_tests_collectes_est_incomplet(tmp_path):
    sonde = {
        "plafond_mo": 6144,
        "pic_mo": 10,
        "plafond_depasse": False,
        "test_en_cours": "x",
        "collecte": 50,
        "termine": True,
        "statut_pytest": 0,
    }
    v = _comparer(tmp_path, SOCLE, SOCLE, branche={"sonde": sonde})
    assert v.code == ce.INCOMPLET
    assert any("50 tests collectés" in r for r in v.branche.raisons)


def test_session_non_terminee_est_incomplete(tmp_path):
    sonde = {
        "plafond_mo": 6144,
        "pic_mo": 10,
        "plafond_depasse": False,
        "test_en_cours": "tests/z.py::test_z",
        "collecte": 3,
        "termine": False,
        "statut_pytest": None,
    }
    v = _comparer(tmp_path, SOCLE, SOCLE, branche={"sonde": sonde})
    assert v.code == ce.INCOMPLET and any(
        "non terminée" in r for r in v.branche.raisons
    )


def test_une_erreur_de_collecte_devenue_un_cas_rouge_est_un_echec_nouveau(tmp_path):
    """``--continue-on-collection-errors`` : le fichier qui n'importe plus ressort comme un test rouge."""
    branche = {**SOCLE, "tests.cassé::tests.cassé": "error"}
    b = _passage(
        tmp_path / "branche",
        branche,
        sonde={
            "plafond_mo": 6144,
            "pic_mo": 1,
            "plafond_depasse": False,
            "test_en_cours": "t",
            "collecte": 3,
            "termine": True,
            "statut_pytest": 1,
        },
    )
    s = _passage(tmp_path / "base", SOCLE)
    v = ce.comparer(ce.lire_passage("branche", b), ce.lire_passage("base", s))
    assert v.code == ce.ROUGE and "tests.cassé::tests.cassé" in v.nouveaux


def test_base_incomplete_et_branche_rouge_affiche_les_echecs_de_la_branche_sans_les_comparer(
    tmp_path,
):
    branche = {**SOCLE, "tests.b::test_trois": "failure"}
    v = _comparer(tmp_path, branche, SOCLE, base={"code": 137})
    texte = ce.rendre(v)
    assert v.code == ce.INCOMPLET
    assert "Passage « base » incomplet" in texte and "`tests.b::test_trois`" in texte


# ------------------------------------------------------------------------- le programme


def test_le_programme_rend_le_code_du_verdict_et_ecrit_le_resume(tmp_path):
    _passage(tmp_path / "branche", {**SOCLE, "tests.a::test_un": "failure"})
    _passage(tmp_path / "base", SOCLE)
    resume = tmp_path / "resume.md"
    code = ce.main(
        [
            "--branche",
            str(tmp_path / "branche"),
            "--base",
            str(tmp_path / "base"),
            "--mode-base",
            "base jouée en parallèle (abc1234)",
            "--resume",
            str(resume),
        ]
    )
    assert code == ce.ROUGE
    texte = resume.read_text(encoding="utf-8")
    assert "base jouée en parallèle (abc1234)" in texte and "tests.a::test_un" in texte


def test_le_programme_rend_2_sur_un_passage_absent(tmp_path):
    _passage(tmp_path / "branche", SOCLE)
    assert (
        ce.main(
            ["--branche", str(tmp_path / "branche"), "--base", str(tmp_path / "rien")]
        )
        == ce.INCOMPLET
    )


def test_la_liste_trop_longue_est_tronquee_avec_son_compte(tmp_path):
    base = {f"tests.m::test_{i}": "ok" for i in range(300)}
    branche = {k: "failure" for k in base}
    v = _comparer(tmp_path, branche, base)
    texte = ce.rendre(v)
    assert (
        v.code == ce.ROUGE
        and "Échecs nouveaux, bloquants" in texte
        and "(300)" in texte
    )
    assert "et 100 autres" in texte
