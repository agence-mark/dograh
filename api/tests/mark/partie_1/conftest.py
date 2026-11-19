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
