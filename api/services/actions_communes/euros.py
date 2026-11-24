"""[.mark] Le format des euros écrit : UNE fonction (plan final Partie 1, lot 1, n° 94). ``1250`` centimes s'écrit ``12,50 €``.

Avant : quatre copies (message de secours de la caisse, adaptation à la prise, ticket, écran de la salle). Ce qui est DIT à voix haute est ailleurs
(``services/mots_dits.montant_en_lettres``) ; ce que HubRise reçoit (``12.50 EUR``) aussi (``hubrise_traduction.euros``) : trois usages, trois formats voulus.
"""

from __future__ import annotations


def en_euros(centimes: int) -> str:
    return f"{centimes // 100},{centimes % 100:02d} €"
