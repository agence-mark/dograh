"""[.mark] Banc A (18/11) : le contrat de commande rejoué SANS modèle de langage.

Les tests de ce dossier portent le marqueur ``banc_a`` et **échouent aujourd'hui pour ceux qui mesurent une faute du module** : c'est le résultat
attendu, rien n'est corrigé pour les faire passer. Pour ne jamais troubler la suite normale, ils sont ignorés sauf si on les demande :

    .venv/Scripts/python.exe -m pytest api/tests/mark/banc_a -m banc_a        (depuis la racine du fork)
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "banc_a: banc A du contrat de commande (sans modèle) ; rouge attendu, jamais xfail")


def pytest_collection_modifyitems(config, items):
    if "banc_a" in (config.getoption("-m") or ""):
        return
    ici = "banc_a"
    ignore = pytest.mark.skip(reason="banc A : à lancer exprès avec -m banc_a")
    for item in items:
        if f"/{ici}/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(ignore)
