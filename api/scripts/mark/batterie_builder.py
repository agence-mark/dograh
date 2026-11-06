"""[.mark] Lance la batterie de non-régression du builder (lot M, pièce 9 de Cognigy, licence MIT) avec le cerveau SCRIPTÉ du dépôt.

    python -m api.scripts.mark.batterie_builder                 compare à la référence (code de sortie 1 si un cas passe moins souvent)
    python -m api.scripts.mark.batterie_builder --enregistrer   enregistre la référence (empreinte par cas)

Aucun appel de modèle, aucune dépense. Rejouer la batterie avec un vrai cerveau passe par ``batterie.lancer.lancer(fabrique)`` et
n'est lancé que sur la phrase d'Evan.
"""

from __future__ import annotations

import asyncio
import sys


async def _principal(argv: list[str]) -> int:
    from api.services.builder.batterie import lancer

    resultats = await lancer.lancer()
    if "--enregistrer" in argv:
        lancer.enregistrer_la_reference(resultats)
        print(f"reference recorded: {len(resultats)} case(s)")
        return 0
    problemes = lancer.comparer(resultats, lancer.lire_la_reference())
    for ligne in problemes:
        print(ligne)
    print("OK" if not problemes else f"{len(problemes)} problem(s)")
    return 1 if problemes else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_principal(sys.argv[1:])))
