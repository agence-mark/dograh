"""[.mark] Builder, lot 6 : les tests de l'agent et la boucle d'amélioration (Q1, Q2, Q3, B30, B32, B38 à B43).

* ``stockage``    : tests et résultats dans ``organization_configurations`` (aucune migration) ;
* ``verdict``     : les critères et le verdict PAR LE CODE, commun au clavier et à l'appel simulé (parité) ;
* ``creation``    : créer un test (depuis une réplique d'un appel, à la main, depuis la fiche), données fictives ;
* ``jeu``         : jouer un test N fois (réplique rejouée ; conversation libre avec un appelant simulé) ;
* ``juge``        : le juge à part, non bloquant, calibré, plusieurs passes quand c'est serré ;
* ``execution``   : rejouer la suite (B38), résultats, forme rendue à la carte ;
* ``diagnostic``  : classer l'échec avant de corriger (B39) ;
* ``publication`` : la garde de publication (test obligatoire, contrôle du prompt) ;
* ``boucle``      : « À trier » (assigné, statut, origine), historique des corrections et retour arrière ;
* ``mise_a_jour`` : agents existants quand une recette change (B30) ;
* ``export``      : un fichier téléchargeable pour le labo (aucune écriture hors de Dograh).
"""
