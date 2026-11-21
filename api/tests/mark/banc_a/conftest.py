"""[.mark] Banc A (18/11) : le contrat de commande rejoué SANS modèle de langage.

Les tests de ce dossier portent le marqueur ``banc_a`` et **échouent aujourd'hui pour ceux qui mesurent une faute du module** : c'est le résultat
attendu, rien n'est corrigé pour les faire passer. Pour ne jamais troubler la suite normale, ils sont ignorés sauf si on les demande :

    .venv/Scripts/python.exe -m pytest api/tests/mark/banc_a -m banc_a        (depuis la racine du fork)
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "banc_a: banc A du contrat de commande (sans modèle) ; rouge attendu, jamais xfail")


# Un prérequis qui manque (lot 19 bis, V7) : joué exprès (``-m banc_a``), le banc ÉCHOUE au lieu de sauter. Un vert fait de tests sautés ne prouve rien.
PREREQUIS_DU_BANC = ("No Postgres",)


def banc_a_demande(config) -> bool:
    return "banc_a" in (config.getoption("-m") or "")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    sortie = yield
    rapport = sortie.get_result()
    if rapport.skipped and banc_a_demande(item.config) and "/banc_a/" in str(item.fspath).replace("\\", "/") and not hasattr(rapport, "wasxfail"):
        raison = str(rapport.longrepr[-1]) if isinstance(rapport.longrepr, tuple) else str(rapport.longrepr)
        if any(p in raison for p in PREREQUIS_DU_BANC):
            rapport.outcome = "failed"
            rapport.longrepr = f"banc A : prérequis manquant, le banc ne saute pas ({raison})"


def pytest_collection_modifyitems(config, items):
    if banc_a_demande(config):
        return
    ici = "banc_a"
    ignore = pytest.mark.skip(reason="banc A : à lancer exprès avec -m banc_a")
    for item in items:
        if f"/{ici}/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(ignore)
