"""[.mark] Les petits mots qu'on écarte pour comparer des noms : UNE source (plan final Partie 1, lot 1, n° 70).

Avant : trois listes écrites à la main (``articles.py``, ``socle.py``, ``produit_au_poids.py``), chacune un peu différente. Ici, la base commune (les articles)
et, pour chaque emploi, ce qu'il y ajoute. Les ensembles rendus sont ceux d'avant, mot pour mot (``test_p1f_lot1_une_source.py``).
"""

from __future__ import annotations

ARTICLES = frozenset({"de", "du", "des", "la", "le", "les", "l", "un", "une"})

# comparer le morceau dit à la composition d'un article (« A et B » pour un article décrit « avec A et B ») : la liaison et la préposition ne comptent pas
LIAISON_D_UNE_COMPOSITION = ARTICLES | {"sans", "avec", "en", "et"}

# désigner une ligne du panier (« la ligne de la reine », « celle-ci ») : ces mots-là ne désignent rien
RENVOI_A_UNE_LIGNE = ARTICLES | {"ligne", "celle", "celui", "ci"}
