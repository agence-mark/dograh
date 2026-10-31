"""[.mark] Builder, lot 5 : le contrôle du prompt par le code (Q12, B31, B34, B49).

* ``regles``  : les règles, PURES (un graphe et ce qu'on sait de l'agent en entrée, des défauts en sortie) ;
* ``service`` : charge l'agent (brouillon sinon publié), ses outils, ses phrases, ses objets, puis applique les règles.

Bloquant = la publication est refusée. Avertissement = dit, jamais bloquant.
"""
