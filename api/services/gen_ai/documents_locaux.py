"""[.mark] Un document texte de la base de connaissances, traité sur place (lot C d'agent-leger-greffier).

Pourquoi : l'amont confie la conversion et le découpage de TOUT document au service de l'éditeur
(MPS, ``services.dograh.com``), que notre patch n° 60 coupe. Sans ce module, aucun document
n'entre dans la base de connaissances de notre fork, dans aucun des deux modes.

Ce qu'il fait, et seulement ça : un fichier **texte** (``.txt``, ``.md``) est lu ici, sans rien
envoyer à personne ; il rend la même forme que la réponse du MPS (``full_text``, ``chunks``,
``docling_metadata``), donc la suite de l'ingestion (vectorisation, rangement) ne change pas.
Le découpage suit les paragraphes (un bloc séparé par une ligne vide, une question et sa
réponse dans une FAQ), regroupés tant qu'ils tiennent sous ``max_tokens``. Un autre format
(PDF, Word) part au MPS comme avant : coupé chez nous, il échoue en le disant.

⛔ Aucun mot de métier : le découpage ne connaît que les lignes vides et la taille.
"""

from __future__ import annotations

import os

EXTENSIONS_TEXTE = (".txt", ".md", ".markdown")
TRAITE_PAR = "mark-local"


def est_un_texte(filename: str, mime_type: str | None) -> bool:
    extension = os.path.splitext(filename or "")[1].lower()
    return extension in EXTENSIONS_TEXTE or (mime_type or "").startswith("text/")


def jetons_estimes(texte: str) -> int:
    """Une estimation, pas un compte : environ 1,3 jeton par mot en français."""
    return max(1, round(len(texte.split()) * 1.3))


def paragraphes(texte: str) -> list[str]:
    blocs, courant = [], []
    for ligne in texte.replace("\r\n", "\n").split("\n"):
        if ligne.strip():
            courant.append(ligne.rstrip())
        elif courant:
            blocs.append("\n".join(courant))
            courant = []
    if courant:
        blocs.append("\n".join(courant))
    return blocs


def decouper(texte: str, max_tokens: int) -> list[str]:
    """Les paragraphes regroupés tant qu'ils tiennent sous ``max_tokens``. Un paragraphe
    plus long reste seul (jamais coupé au milieu d'une phrase)."""
    morceaux, courant = [], []
    for bloc in paragraphes(texte):
        candidat = "\n\n".join([*courant, bloc])
        if courant and jetons_estimes(candidat) > max_tokens:
            morceaux.append("\n\n".join(courant))
            courant = [bloc]
        else:
            courant.append(bloc)
    if courant:
        morceaux.append("\n\n".join(courant))
    return morceaux


def traiter_un_texte(chemin: str, retrieval_mode: str, max_tokens: int) -> dict:
    """La réponse du MPS, fabriquée sur place pour un fichier texte."""
    with open(chemin, encoding="utf-8", errors="replace") as fichier:
        texte = fichier.read().strip()
    metadonnees = {"processed_by": TRAITE_PAR}
    if retrieval_mode != "chunked":
        return {"full_text": texte, "chunks": [], "docling_metadata": metadonnees}
    return {
        "full_text": None,
        "docling_metadata": metadonnees,
        "chunks": [
            {
                "chunk_text": morceau,
                "contextualized_text": morceau,
                "chunk_index": index,
                "chunk_metadata": {"processed_by": TRAITE_PAR},
                "token_count": jetons_estimes(morceau),
            }
            for index, morceau in enumerate(decouper(texte, max_tokens))
        ],
    }
