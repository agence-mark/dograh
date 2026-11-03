"""[.mark] Copier un agent d'une organisation à une autre (U2 quinquies E58, E33) : exporter du Labo vers un client, ramener d'un client au Labo.

Un seul module pour les deux sens (``sens`` = ``exporter`` | ``ramener``) :

* ``releve``  : ce que l'agent (et son groupe) emporte, une ligne par élément, avec les choix permis et les équivalents trouvés chez la cible ;
* ``ecriture``: la copie, toujours en brouillon, jamais publiée ; l'original n'est pas touché ;
* ``registre``: le journal des copies (idempotence : rejouée, la même copie n'est pas refaite) et le verrou ;
* ``purge``   : ce qui ne voyage jamais (secrets, identifiants de l'organisation source).

Règles : l'organisation de la source et celle de la cible sont relues côté serveur à chaque requête ; une clé d'API n'exporte ni ne
ramène ; aucune clé n'est copiée (on relie à une clé de la cible par son nom, ou on laisse vide).
"""
