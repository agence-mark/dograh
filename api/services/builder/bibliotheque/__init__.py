"""[.mark] Builder, lot 2 : la bibliothèque de recettes (B7, B9, B35, B44).

Stockage sans migration : une ligne par élément dans l'organisation .mark (``MARK_BIBLIO:<famille>:<slug>``).
Lue par toute organisation ; écrite par les seuls membres de l'organisation .mark ; le builder, lui, ne crée
et ne modifie que des **candidats** et **propose** le reste (``propositions``).
"""
