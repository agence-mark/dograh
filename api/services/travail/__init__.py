"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8, D9, D10, D12, D13) : le cerveau de fond.

Un agent dont « Travail en arrière-plan » est allumé reçoit un outil de plus, ``confier_le_travail``.
Quand son cerveau de conversation l'appelle, l'outil **rend tout de suite** (« lancé ») : le micro de
l'appelant n'est jamais coupé et le cerveau de conversation parle librement (« je regarde ça »).
La demande part en **job** au worker de fond (``WorkerDeFond``, sous-classe de ``BackendLLMWorker``
de Pipecat, enfant du worker d'appel) qui travaille avec **son propre contexte** et **ses propres
outils**. Son résultat revient en message ``[Résultat du travail : …]`` poussé à l'agent qui a la
main, **gardé** tant que le robot ou l'appelant parle.

Modules :

- ``reglages``  : les cinq réglages par agent (``travail_*``), jamais d'exception ;
- ``fabrique``  : le service de modèle du cerveau de fond (même fabrique que les autres cerveaux) ;
- ``worker``    : ``WorkerDeFond`` et son observateur (jetons, outils appelés) ;
- ``outils``    : les outils du fond (catalogue moins transferts et fin d'appel) et son moteur muet ;
- ``retour``    : la remise gardée du résultat ;
- ``agent``     : ``TravailDeLAgent`` (l'état d'un agent qui travaille) et l'outil « confier » ;
- ``clavier``   : le même travail au clavier (dans le tour, remis au tour suivant).

⛔ Pipecat n'est pas touché (R2) : tout est sous-classe ou code ici. ⛔ Aucun mot de métier : ce que
le fond fait vient de la demande du cerveau de conversation et des outils réglés à l'écran.
⛔ Éteint par défaut : sans réglage, aucun outil, aucun worker, rien dans la requête.
"""
