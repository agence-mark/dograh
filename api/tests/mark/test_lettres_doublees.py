"""[.mark] Garantie : une lettre doublée se lit partout, pour toutes les lettres (Evan, 14/10).

« Ulysse = U L Y deux S E » : « deux S » veut dire S S. Evan, 14/10 : « cela doit marcher avec
toutes les doubles lettres », dans un nom, une rue comme une adresse mail, et l'adresse ne doit
jamais compromettre la méthode d'épellation.

| Section | Ce qu'elle tient |
|---|---|
| 1 | Les 25 lettres (W à part) × 8 formes : « deux X », « double X », « 2 X », « avec deux X », virgules, « X X », « trois X » |
| 2 | Les mêmes dans une adresse mail |
| 3 | Les lettres dites par leur nom (« deux elle ») |
| 4 | L'alphabet téléphonique autour (« Y, deux S comme Suzanne ») |
| 5 | La seule limite, assumée : « double V » est la lettre W |

Sur les vrais appels : « P, E, deux R, I, N » (run 926) donnait « Rrin » et « R, O, U, deux S, E,
A, U » (run 922) « Rou » et « Sseau » : ils donnent Perrin et Rousseau.

⛔ Rouge avant d'être vert, mesuré sur `e0a85827` : « U, L, Y, deux S, E » donnait « Uly » et
« Sse » (question n° 274, défaut antérieur au chantier) ; « u l y 2 s e arobase… » donnait
``uly2se@gmail.com`` ; « b o r avec deux s u n arobase… » coupait l'adresse.
"""

from __future__ import annotations

import string

import pytest

from api.services.epellation.lecture import lire

FORMES = [
    ("{x}", "deux {x}", 2),
    ("{x}", "double {x}", 2),
    ("{x}", "2 {x}", 2),
    ("{x}", "avec deux {x}", 2),
    ("{x}", ", deux {x},", 2),
    ("{x}", ", 2 {x},", 2),
    ("{x}", "{x} {x}", 2),
    ("{x}", "trois {x}", 3),
]
LETTRES = [x for x in string.ascii_lowercase if x != "w"]
# « double v » est la lettre W (section 5), jamais V V : seule combinaison retirée.
CAS = [
    (x, forme, fois)
    for x in LETTRES
    for _, forme, fois in FORMES
    if not (x == "v" and forme.startswith("double"))
    # « b o r, deux r » : la lettre doublée suit la même lettre après une virgule, c'est
    # une précision (doublée et à faire confirmer) : testé à part, pas ici.
    and not (x == "r" and forme.startswith(","))
]


def _phrase(x: str, forme: str) -> str:
    return f"c'est b o r {forme.format(x=x)} u n".replace(" ,", ",")


@pytest.mark.parametrize("x,forme,fois", CAS, ids=[f"{x}-{f}" for x, f, _ in CAS])
def test_une_lettre_doublee_dans_un_nom(x, forme, fois):
    assert [e.epele for e in lire(_phrase(x, forme))] == [("Bor" + x * fois + "un")]


@pytest.mark.parametrize("x,forme,fois", CAS, ids=[f"{x}-{f}" for x, f, _ in CAS])
def test_une_lettre_doublee_dans_une_adresse(x, forme, fois):
    phrase = _phrase(x, forme).replace(",", "") + " arobase gmail point com"
    assert [e.epele for e in lire(phrase)] == [f"bor{x * fois}un@gmail.com"]


@pytest.mark.parametrize(
    "nom,lettre",
    [
        ("elle", "l"),
        ("enne", "n"),
        ("emme", "m"),
        ("esse", "s"),
        ("effe", "f"),
        ("erre", "r"),
        ("té", "t"),
        ("pé", "p"),
    ],
)
def test_une_lettre_dite_par_son_nom(nom, lettre):
    assert [e.epele for e in lire(f"c'est b o deux {nom} u n")] == [
        "Bo" + lettre * 2 + "un"
    ]
    assert [e.epele for e in lire(f"c'est b o, deux {nom}, u n")] == [
        "Bo" + lettre * 2 + "un"
    ]


@pytest.mark.parametrize(
    "phrase",
    [
        "U L Y deux S E",
        "U, L, Y, deux S, E",
        "U L Y, 2 S, E",
        "U comme Ursule, L comme Louis, Y, deux S, E",
        "U comme Ursule, L comme Louis, Y comme Yvonne, deux S comme Suzanne, E comme Eugène",
        "u l y, deux s comme Simon, e",
    ],
)
def test_ulysse(phrase):
    assert [e.epele for e in lire(phrase)] == ["Ulysse"]


@pytest.mark.parametrize(
    "phrase,attendu",
    [
        # Relecture n° 7 : des phrases ordinaires après un nom épelé, jamais des lettres.
        ("c'est m a r t i n, 3e étage", ["Martin"]),
        ("c'est d u p o n t, 2e étage porte b", ["Dupont"]),
        ("c'est d u p o n t 2e étage", ["Dupont"]),
        ("c'est r o u x, deux a la maison", ["Roux"]),
        ("c'est d u r a n d, deux elle sont venues", ["Durand"]),
        ("c'est l e r o y, deux à la fois", ["Leroy"]),
        ("il y a, deux ans", []),
        ("f l a m a n t, deux fois", ["Flamant"]),
        # Les vrais appels (question n° 274).
        ("Le nom de ma grand-mère c'est Perrin, P, E, deux R, I, N.", ["Perrin"]),
        ("Rousseau. R, O, U, deux S, E, A, U.", ["Rousseau"]),
    ],
)
def test_jamais_de_lettre_doublee_inventee(phrase, attendu):
    assert [e.epele for e in lire(phrase)] == attendu


@pytest.mark.parametrize(
    "phrase", ["c'est d u p o n t, 2 b", "c'est d u p o n t, 3 a, au deuxième"]
)
def test_une_lettre_doublee_ecrite_en_chiffre_est_a_confirmer(phrase):
    """Relecture n° 8 : « 2 b » après un nom peut être un bâtiment : jamais en silence."""
    (lue,) = lire(phrase)
    assert lue.doutes


def test_la_seule_limite_double_ve_est_la_lettre_w():
    """« double vé » EST la lettre W en français : il ne peut pas dire aussi V V.
    Deux V se disent « deux V » (couvert par la section 1)."""
    assert [e.epele for e in lire("c'est b o r double v u n")] == ["Borwun"]
    assert [
        e.epele for e in lire("c'est b o r double v u n arobase gmail point com")
    ] == ["borwun@gmail.com"]
