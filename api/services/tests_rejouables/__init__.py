"""[.mark] passages-fiables, lot H : les tests rejouables (outil du banc, hors appel).

Un test = un tour fautif d'un vrai run, la conversation jusqu'à lui, l'étape et la fiche de l'appel à ce
moment, et ce qu'on attend de l'agent. On le rejoue sur la session clavier (``text_chat_runner``), qui
repart de cet état, 3 fois par défaut : le résultat est un taux de réussite. Rien ici ne tourne dans le
chemin d'un appel réel.

* ``modele``   : le fichier de test, les critères, leur évaluation (pur, sans base) ;
* ``creation`` : un test depuis un run (lecture seule du run, organisation vérifiée) ;
* ``rejeu``    : le rejeu sur une copie d'agent, et la suite (un dossier de tests).
"""
