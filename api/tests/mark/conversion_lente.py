"""[.mark] Fonctions de module pour les tests de la conversion dans un processus à part (C11).

Elles doivent vivre dans un module importable : un processus enfant « spawn » ou « forkserver » les retrouve par leur nom.
"""

from __future__ import annotations

import time

from api.services.builder.dossiers import extraction


def lente_03(nom, contenu):
    time.sleep(0.3)
    return extraction.Extraction(pages=[extraction.Page(1, "texte")])


def lente_05(nom, contenu):
    time.sleep(0.5)
    return extraction.Extraction(pages=[extraction.Page(1, "texte")])


def lente_document(*_a, **_k):
    time.sleep(5)
    return {}


def ecrit_apres(chemin: str, secondes: float) -> str:
    time.sleep(secondes)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("fini")
    return "fini"


def leve_une_valeur() -> None:
    raise ValueError("raison lisible")


def leve_autre_chose() -> None:
    raise KeyError("secret-interne")


def double(x: int) -> int:
    return 2 * x
