"""[.mark] passages-fiables, lot H : créer et rejouer un test depuis un run (outil du banc, hors appel).

Avec l'environnement de l'API (``api/.env``) ; chaque rejeu appelle le vrai modèle de l'agent visé
(dépense : à lancer sur instruction d'Evan, sur une COPIE d'agent, jamais sur 139-145 ni 223-243) :

    # créer un test depuis un run (lecture seule du run)
    python -m api.scripts.mark.tests_rejouables creer --run 2146 --organisation 12 --rang 3 \\
        --nom numero-invente-2146 --critere '{"type":"texte_absent","texte":"06 12"}' --dossier DOSSIER

    # rejouer un test (3 fois par défaut)
    python -m api.scripts.mark.tests_rejouables rejouer --test FICHIER.json --agent 250 [--essais 3]

    # jouer une suite (un dossier de tests)
    python -m api.scripts.mark.tests_rejouables suite --dossier DOSSIER --agent 250 [--essais 3]

Code de sortie : 0 tout à 100 %, 1 au moins un essai raté, 2 refus ou fichier illisible.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from api.services.tests_rejouables.modele import (
    ESSAIS_PAR_DEFAUT,
    ErreurTestRejouable,
    ecrire_test,
    lire_test,
    nom_de_fichier,
)


async def _creer(args: argparse.Namespace) -> int:
    from api.services.tests_rejouables.creation import creer_depuis_un_run

    try:
        critere = json.loads(args.critere)
    except json.JSONDecodeError as e:
        raise ErreurTestRejouable(f"--critere n'est pas du JSON ({e})") from None
    test = await creer_depuis_un_run(
        args.run, args.organisation, args.rang, critere, args.nom, args.description or ""
    )
    chemin = ecrire_test(test, Path(args.dossier) / nom_de_fichier(args.nom))
    print(
        f"Test écrit : {chemin} ({len(test.historique)} message(s) d'historique, "
        f"étape {(test.etape or {}).get('nom') or 'première'}). "
        "Relis-le : il contient la conversation du run."
    )
    return 0


async def _rejouer(args: argparse.Namespace) -> int:
    from api.services.tests_rejouables.rejeu import rejouer, rendre

    resultat = await rejouer(lire_test(args.test), args.agent, args.essais)
    print(rendre([resultat]))
    return 0 if resultat.vert else 1


async def _suite(args: argparse.Namespace) -> int:
    from api.services.tests_rejouables.rejeu import jouer_suite, rendre

    resultats = await jouer_suite(args.dossier, args.agent, args.essais)
    print(rendre(resultats))
    if any(r.erreur for r in resultats):
        return 2
    return 0 if all(r.vert for r in resultats) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sous = p.add_subparsers(dest="commande", required=True)
    c = sous.add_parser("creer", help="un test depuis un run")
    c.add_argument("--run", type=int, required=True)
    c.add_argument("--organisation", type=int, required=True, help="l'organisation du run (vérifiée)")
    c.add_argument("--rang", type=int, required=True, help="rang (de 1) de la réplique fautive de la personne")
    c.add_argument("--critere", required=True, help="le critère, en JSON")
    c.add_argument("--nom", required=True)
    c.add_argument("--description")
    c.add_argument("--dossier", required=True)
    c.set_defaults(fonction=_creer)
    r = sous.add_parser("rejouer", help="rejouer un test")
    r.add_argument("--test", required=True)
    r.add_argument("--agent", type=int, required=True, help="la COPIE d'agent jouée")
    r.add_argument("--essais", type=int, default=ESSAIS_PAR_DEFAUT)
    r.set_defaults(fonction=_rejouer)
    s = sous.add_parser("suite", help="jouer un dossier de tests")
    s.add_argument("--dossier", required=True)
    s.add_argument("--agent", type=int, required=True, help="la COPIE d'agent jouée")
    s.add_argument("--essais", type=int, default=ESSAIS_PAR_DEFAUT)
    s.set_defaults(fonction=_suite)
    args = p.parse_args(argv)
    try:
        return asyncio.run(args.fonction(args))
    except ErreurTestRejouable as e:
        print(f"Refusé : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
