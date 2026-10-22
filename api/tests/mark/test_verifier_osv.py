"""Le seuil de gravité des rapports ``osv-scanner`` (``api/scripts/mark/verifier_osv.py``) ne ment pas.

R7 : un outil neuf s'éprouve sur un cas rouge connu. Rapports factices au format JSON d'osv-scanner
v2 ; le cas rouge réel (``b2211709``, rouge attendu) est au journal de la CI avec l'identifiant du run.
"""

import json

from api.scripts.mark import verifier_osv as vo


def _paquet(nom, version, groupes, dependency_groups=None, fixed=None):
    p = {
        "package": {"name": nom, "version": version, "ecosystem": "PyPI"},
        "groups": [{"ids": [i], "max_severity": note} for i, note in groupes],
        "vulnerabilities": [
            {
                "id": groupes[0][0],
                "affected": [
                    {
                        "package": {"name": nom},
                        "ranges": [{"events": [{"introduced": "0"}, {"fixed": fixed}]}],
                    }
                ],
            }
        ]
        if fixed
        else [],
    }
    if dependency_groups is not None:
        p["dependency_groups"] = dependency_groups
    return p


def _rapport(tmp_path, nom, paquets):
    chemin = tmp_path / nom
    chemin.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "source": {"path": f"/x/{nom}", "type": "lockfile"},
                        "packages": paquets,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return chemin


def test_une_faille_elevee_de_production_est_rouge_avec_sa_version_corrigee(tmp_path):
    r = _rapport(
        tmp_path,
        "constraints.txt",
        [_paquet("pillow", "12.3.0", [("GHSA-aaaa", "9.2")], fixed="13.0.0")],
    )
    code, texte = vo.verifier([r], 7.0)
    assert code == 1
    assert "pillow" in texte and "13.0.0" in texte and "9.2" in texte


def test_une_note_de_7_pile_est_bloquante_et_6_9_ne_l_est_pas(tmp_path):
    r = _rapport(
        tmp_path,
        "a.json",
        [_paquet("x", "1", [("A", "7.0")]), _paquet("y", "1", [("B", "6.9")])],
    )
    code, texte = vo.verifier([r], 7.0)
    assert code == 1 and "| x |" in texte and "| y |" not in texte


def test_sous_le_seuil_c_est_vert(tmp_path):
    r = _rapport(tmp_path, "a.json", [_paquet("x", "1", [("A", "6.3")])])
    code, texte = vo.verifier([r], 7.0)
    assert code == 0 and "aucune faille" in texte


def test_une_faille_de_developpement_seule_est_ignoree(tmp_path):
    r = _rapport(
        tmp_path,
        "package-lock.json",
        [_paquet("vite", "8", [("A", "9.8")], dependency_groups=["dev"])],
    )
    assert vo.verifier([r], 7.0)[0] == 0


def test_dev_et_production_ensemble_reste_bloquant(tmp_path):
    r = _rapport(
        tmp_path,
        "package-lock.json",
        [_paquet("x", "1", [("A", "9.8")], dependency_groups=["dev", "optional"])],
    )
    assert vo.verifier([r], 7.0)[0] == 1


def test_une_faille_sans_note_est_listee_sans_bloquer(tmp_path):
    r = _rapport(tmp_path, "a.json", [_paquet("dompurify", "3.4.11", [("A", "")])])
    code, texte = vo.verifier([r], 7.0)
    assert code == 0 and "Sans note" in texte and "dompurify 3.4.11" in texte


def test_projet_sain_sans_aucun_paquet_a_faille_est_vert(tmp_path):
    r = _rapport(tmp_path, "a.json", [])
    assert vo.verifier([r], 7.0)[0] == 0


def test_rapport_illisible_ou_sans_results_ou_absent_est_un_scan_incomplet(tmp_path):
    (tmp_path / "casse.json").write_text('{"results": [', encoding="utf-8")
    (tmp_path / "vide.json").write_text("{}", encoding="utf-8")
    assert vo.verifier([tmp_path / "casse.json"], 7.0)[0] == 2
    assert vo.verifier([tmp_path / "vide.json"], 7.0)[0] == 2
    assert vo.verifier([tmp_path / "absent.json"], 7.0)[0] == 2
    assert vo.verifier([], 7.0)[0] == 2


def test_un_rapport_illisible_parmi_plusieurs_rend_le_tout_incomplet(tmp_path):
    bon = _rapport(tmp_path, "bon.json", [])
    (tmp_path / "casse.json").write_text("pas du json", encoding="utf-8")
    assert vo.verifier([bon, tmp_path / "casse.json"], 7.0)[0] == 2


def test_le_programme_ecrit_le_resume_et_rend_le_code(tmp_path):
    r = _rapport(tmp_path, "a.json", [_paquet("x", "1", [("A", "9.0")])])
    resume = tmp_path / "resume.md"
    assert vo.main([str(r), "--resume", str(resume)]) == 1
    assert "x" in resume.read_text(encoding="utf-8")
