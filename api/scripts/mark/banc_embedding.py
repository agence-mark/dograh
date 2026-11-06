"""[.mark] builder-agent-vocal, lot 6 : le banc de recherche de la base de connaissances (outil du banc, hors appel).

Compare un ou deux modèles d'embedding sur un corpus de questions : taux de « bon passage dans les 3 premiers », rang de chaque question,
questions ratées. Chaque lancement appelle le fournisseur d'embedding (dépense minime, mais réelle) : à lancer sur instruction d'Evan.
La clé est lue dans l'ENVIRONNEMENT (jamais affichée, jamais écrite dans la sortie).

    python -m api.scripts.mark.banc_embedding --corpus CORPUS.json \\
        --modele text-embedding-3-small --modele qwen3-embedding-8b [--sortie RESULTAT.json] [--max-tokens 128]

``--modele`` : ``nom[@adresse][#VARIABLE_CLE]`` ; text-embedding-3-small (variable OPENAI_API_KEY) et qwen3-embedding-8b (Scaleway,
variable SCALEWAY_API_KEY) sont connus. ``bge-multilingual-gemma2`` est refusé. Sans ``--modele`` : text-embedding-3-small.

Code de sortie : 0 fait, 2 refus (corpus, modèle, clé, dimension).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from api.services.builder import banc_embedding as banc


async def _lancer(args: argparse.Namespace) -> int:
    configs = [banc.lire_le_modele(s) for s in (args.modele or [banc.MODELE_PAR_DEFAUT])]
    morceaux, questions = banc.lire_le_corpus(args.corpus, args.max_tokens)
    sortie = await banc.comparer(configs, morceaux, questions)
    if args.sortie:
        Path(args.sortie).write_text(json.dumps(sortie, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(banc.resume(sortie))
    if args.sortie:
        print(f"Détail : {args.sortie}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--corpus", required=True, help="le fichier de corpus (JSON)")
    p.add_argument("--modele", action="append", help="nom[@adresse][#VARIABLE_CLE] ; une ou deux fois")
    p.add_argument("--sortie", help="écrit le détail en JSON")
    p.add_argument("--max-tokens", type=int, default=banc.TAILLE_DES_MORCEAUX)
    args = p.parse_args(argv)
    try:
        return asyncio.run(_lancer(args))
    except banc.ErreurBanc as erreur:
        print(f"Refusé : {erreur}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
