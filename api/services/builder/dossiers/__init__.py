"""[.mark] Builder, lot 3 : les dossiers d'audit déposés, la fiche qu'on en tire et la base de connaissances proposée.

* ``extraction`` : le texte d'un PDF, d'un Word, d'un Markdown ou d'un texte, page par page, sur place ;
* ``site``       : la lecture d'un site, pages publiques seulement (aucune adresse interne : SSRF) ;
* ``depot``      : ce qui est déposé (fichier gardé par ``services/storage.py``, texte extrait, statut de lecture) ;
* ``classement`` : chaque fait de la fiche classé en objet, base de connaissances ou règle du prompt (B47) ;
* ``base``       : les documents de base de connaissances proposés, validés par une personne, rattachés.

⛔ Aucun mot de métier : ces modules ne connaissent que des fichiers, des pages et des sources.
"""
