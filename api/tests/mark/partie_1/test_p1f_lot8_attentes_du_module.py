"""[.mark] Lot 8, 8c-2 (128) : le mécanisme de la phrase d'attente (``outils_mark/attente_par_case.py``) ne lit plus ``gabarits/restauration/attentes.json`` ni les noms de
cases du métier : le module (``Module.attentes``, ``module:fonction`` qui rend ``(familles, famille_de_la_case)``) les fournit, la restauration les pose
(``restauration/attentes.py``). Un JSON illisible n'est plus avalé en silence : une ligne au journal, la phrase de l'outil reste."""

from __future__ import annotations

from loguru import logger

from api.services.outils_mark import attente_par_case as AT


def test_le_mecanisme_ne_connait_plus_le_fichier_du_metier():
    assert not hasattr(AT, "FICHIER") and not hasattr(AT, "familles") and not hasattr(AT, "famille_de_la_case")


def test_la_restauration_pose_ses_familles_par_le_module():
    from api.services.modules.registre import RESTAURATION
    from api.services.restauration import attentes

    assert RESTAURATION.attentes == "api.services.restauration.attentes:attentes"
    familles, case = attentes.attentes()
    assert case("lire", {}) == attentes.LECTURE and familles[attentes.LECTURE]


def test_config_avec_l_attente_par_connecteur():
    from api.services.restauration import attentes

    assert AT.config_avec_l_attente({}, "commande", "lire", {"sujet": "carte"})["phrases_attente"] == attentes.familles()[attentes.LECTURE]
    assert AT.config_avec_l_attente({}, "reservation", "fiche", {"adresse": "8 rue Solférino"})["phrases_attente"] == attentes.familles()[attentes.ZONE]
    assert AT.config_avec_l_attente({"phrase_attente": "Un instant."}, "commande", "fiche", {"ajouter": [{"article": "x"}]}) == {"phrase_attente": "Un instant."}
    assert AT.config_avec_l_attente({"a": 1}, "equipe", "lire", {}) == {"a": 1}  # un connecteur sans famille garde la phrase de son outil
    assert AT.config_avec_l_attente({"a": 1}, None, "lire", {}) == {"a": 1}


def test_un_json_illisible_ecrit_au_journal_et_garde_la_phrase_de_l_outil(tmp_path, monkeypatch):
    from api.services.restauration import attentes

    lignes: list[str] = []
    identifiant = logger.add(lambda message: lignes.append(str(message)), level="WARNING")
    attentes.familles.cache_clear()
    monkeypatch.setattr(attentes, "FICHIER", tmp_path / "absent.json")
    try:
        assert AT.config_avec_l_attente({"phrase_attente": "Un instant."}, "commande", "lire", {}) == {"phrase_attente": "Un instant."}
    finally:
        logger.remove(identifiant)
        monkeypatch.undo()
        attentes.familles.cache_clear()
    assert any("attente" in ligne.lower() for ligne in lignes), lignes
