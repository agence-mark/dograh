"""[.mark] Chantier Partie 1 : marqueurs et garde réseau des tests (lot 0, D61 point 9).

- ``garde_noms`` : le contrôle des noms sur le schéma du fork, attendu rouge jusqu'à la fin du lot 2 (registre, § 2).
- ``latence`` : une mesure de temps (les 50 ms par fiche du lot 5), jouée en local seulement ; la CI joue ``-m "not latence"``.
- Aucun test de ce dossier ne joint un fournisseur de modèle (Scaleway ou autre) : la résolution de son nom est refusée.
"""

import socket

import pytest

# Le monde de la carte (banc A) et le montage de la porte (lot 3), fixtures déclarées une fois pour le dossier.
from api.tests.mark.banc_a.commun import base_essai, base_prete, faire_monde  # noqa: F401
from api.tests.mark.partie_1.porte_essai import essai_de  # noqa: F401

FOURNISSEURS_DE_MODELE = (
    "scaleway", "mistral.ai", "openai.com", "anthropic.com", "generativelanguage.googleapis.com",
    "groq.com", "together.xyz", "deepseek.com", "openrouter.ai", "deepinfra.com", "fireworks.ai",
)


class AppelAUnFournisseurDeModele(RuntimeError):
    """Un test a voulu joindre un fournisseur de modèle : interdit (D61, point 9)."""


def pytest_configure(config):
    config.addinivalue_line("markers", "garde_noms: contrôle des noms du fork, rouge jusqu'à la fin du lot 2")
    config.addinivalue_line("markers", "latence: mesure de temps jouée en local, jamais en CI (D61, point 9)")
    config.addinivalue_line("markers", "combinaisons: test des combinaisons, profondeur 1 et défauts connus (clôture A4 ; rouge jusqu'au lot B)")
    config.addinivalue_line("markers", "combinaisons_longues: profondeur 2, fusions, suites tirées (avant chaque déploiement)")
    config.addinivalue_line("markers", "sans_base:test qui n'ouvre aucune base (niveau rapide, joué à chaque commit ; clôture A3)")


FIXTURES_DE_BASE = {"base_essai", "base_prete", "faire_monde", "essai_de", "base_modele"}


def pytest_collection_modifyitems(config, items):
    """Clôture A3 (audit des tests § 5, point 5) : deux niveaux de suite. ``-m sans_base`` joue en quelques secondes ce qui n'ouvre pas de base ;
    la suite complète reste jouée avant chaque déploiement."""
    choisi = str(getattr(config.option, "markexpr", "") or "")
    for item in items:
        if "partie_1" in str(getattr(item, "path", "")) and not FIXTURES_DE_BASE & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.sans_base)
        # Clôture A4 : le test des combinaisons est rouge jusqu'au lot B (critère du lot A) ; joué seulement quand on le demande (``-m combinaisons``),
        # et dans la suite à la fin du lot B (S5 : retirer ces trois lignes).
        if "combinaisons" not in choisi and (item.get_closest_marker("combinaisons") or item.get_closest_marker("combinaisons_longues")):
            item.add_marker(pytest.mark.skip(reason="test des combinaisons : -m combinaisons (rouge jusqu'au lot B, S5)"))


def est_un_fournisseur_de_modele(hote) -> bool:
    h = str(hote or "").lower()
    return any(f in h for f in FOURNISSEURS_DE_MODELE)


@pytest.fixture(autouse=True)
def aucun_appel_a_un_fournisseur_de_modele(monkeypatch):
    vrai = socket.getaddrinfo

    def garde(hote, *a, **k):
        if est_un_fournisseur_de_modele(hote):
            raise AppelAUnFournisseurDeModele(f"un test joint un fournisseur de modèle : {hote}")
        return vrai(hote, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", garde)
