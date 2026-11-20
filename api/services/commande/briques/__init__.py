"""[.mark] Chantier Partie 1, lots 8 à 15 : les briques de carte (E29, D9, méthode § 4 règle 5).

Une capacité de la carte (taille, groupe d'options, quota inclus, formule, prix au poids...) est UNE brique autonome : sa description en données (le champ
du format commun, chargé avec la carte de l'appel), sa règle isolée (une fonction nommée ``brique_<code>_<verbe>``, ``briques/<code>.py``), ses tests, sa
phrase pour le modèle. Le registre (``registre.py``) les inventorie. Aucun mot de restaurant ici : les libellés viennent de la carte.
"""

from api.services.commande.briques import art1, art2, art3, dec1, dec2, dec3, dec4, dec5, opt1, opt2, opt3, opt4, opt5, opt6, opt7, opt8, opt9, opt10, opt11, ret1, ret2, ret3, ret4, ret5, ret6, ret7, ret8, for1, for2, for3, for4, for5, for6, for7, for8, for9, for10, for11, for12, for13, for14, for15, prx1, prx2, prx3, prx4, prx5, prx6, prx7, prx8, prx9, qte1, qte2, qte3, off1, off2, off3, off4, inf1, inf2, inf3, inf4, inf5, inf6, inf7  # noqa: E402,F401  (chaque module s'inscrit au registre)
