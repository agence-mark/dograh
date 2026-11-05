"""[.mark] U11 (SE-10, C-2) : l'import du jeu public d'attaques, le fichier fourni par une personne.

Le jeu visé est celui de ``verazuo/jailbreak_llms`` (« Do Anything Now », CCS 2024, licence MIT, Copyright (c) 2023 Vera), publié aussi
sur Hugging Face (``TrustAIRLab/in-the-wild-jailbreak-prompts``). Format lu dans sa documentation officielle : un CSV dont l'en-tête est
``platform,source,prompt,jailbreak,created_at,date,community,community_id,previous_community_id`` (la colonne ``prompt`` est le texte
de l'attaque, ``jailbreak`` dit si le texte en est une, ``community`` la famille). Sa documentation recommande d'écarter les doublons
du champ ``prompt`` : c'est fait ici.

Où il vit : un élément de la bibliothèque ne tient pas plus de 10 000 octets, le jeu en fait des millions. Il est donc rangé en
lots de lignes de l'organisation (``MARK_ATTAQUES_JEU:<jeu>[:<lot>]``), comme le rapport : aucune table, aucune migration, et chaque
organisation importe le sien (rien n'est partagé entre organisations).

Idempotent, jamais contre une personne : l'identifiant d'une attaque est l'empreinte de son texte ; réimporter un fichier n'ajoute
que les attaques absentes, ne réécrit aucun lot rangé et ne touche ni le catalogue fermé des 15 techniques ni la bibliothèque.
Un texte trop long n'est jamais coupé (une attaque tronquée n'est plus l'attaque) : il est écarté et compté.
Aucun modèle n'est appelé : pas de traduction ici (une dépense, sur accord d'Evan seulement).
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from api.services.builder import stock

SLUG = "jailbreak-llms"
PREFIXE = "MARK_ATTAQUES_JEU:"
SOURCE = "verazuo/jailbreak_llms (TrustAIRLab/in-the-wild-jailbreak-prompts)"
LICENCE = "MIT"
MENTION = "Public set of jailbreak prompts verazuo/jailbreak_llms, MIT license (Copyright (c) 2023 Vera)."
TECHNIQUE = "jeu_public"
TAILLE_MAX_OCTETS = 12_000_000
LONGUEUR_MAX = 4_000  # au-delà : écartée, jamais coupée
LOT = 50
TEMOIN = "Bonjour, peux-tu me dire ce que tu peux faire pour moi ?"
VRAI = {"true", "1", "yes"}


class ImportRefuse(Exception):
    """Une erreur que la personne comprend : fichier trop gros, illisible, sans la colonne ``prompt``."""


def cle(jeu: str = SLUG, lot: int | None = None) -> str:
    return f"{PREFIXE}{jeu}" if lot is None else f"{PREFIXE}{jeu}:{lot:04d}"


def _normaliser(texte: str) -> str:
    return " ".join(texte.split())


def identifiant(texte: str) -> str:
    return "pub-" + hashlib.sha256(_normaliser(texte).lower().encode("utf-8")).hexdigest()[:12]


def lire_le_csv(contenu: str) -> dict[str, Any]:
    """Le fichier lu et validé, sans rien écrire : ``{attaques, ecartees, lignes}``. ``ImportRefuse`` avec la raison."""
    if len(contenu.encode("utf-8")) > TAILLE_MAX_OCTETS:
        raise ImportRefuse(f"The file is too large (at most {TAILLE_MAX_OCTETS // 1_000_000} MB).")
    csv.field_size_limit(TAILLE_MAX_OCTETS)
    lecteur = csv.DictReader(io.StringIO(contenu.lstrip("﻿"), newline=""))
    try:
        colonnes = lecteur.fieldnames or []
    except csv.Error:
        raise ImportRefuse("The file is not a readable CSV.") from None
    if "prompt" not in colonnes:
        raise ImportRefuse("The file has no « prompt » column: the public set is a CSV whose header holds prompt, jailbreak, community…")
    ecartees = {"vides": 0, "trop_longues": 0, "doublons": 0, "pas_une_attaque": 0}
    attaques: list[dict[str, Any]] = []
    vues: set[str] = set()
    lignes = 0
    try:
        for ligne in lecteur:
            lignes += 1
            texte = (ligne.get("prompt") or "").strip()
            if not texte:
                ecartees["vides"] += 1
                continue
            if "jailbreak" in colonnes and str(ligne.get("jailbreak") or "").strip().lower() not in VRAI:
                ecartees["pas_une_attaque"] += 1  # une ligne « ordinaire » du même jeu : ce n'est pas une attaque
                continue
            if len(texte) > LONGUEUR_MAX:
                ecartees["trop_longues"] += 1
                continue
            ident = identifiant(texte)
            if ident in vues:
                ecartees["doublons"] += 1
                continue
            vues.add(ident)
            famille = (ligne.get("community") or ligne.get("source") or ligne.get("platform") or "").strip()[:80]
            attaques.append({"id": ident, "texte": texte, "famille": famille})
    except csv.Error:
        raise ImportRefuse("The file is not a readable CSV.") from None
    if lignes == 0:
        raise ImportRefuse("The file has a header but no line.")
    return {"attaques": attaques, "ecartees": ecartees, "lignes": lignes}


async def _index(organisation_id: int, jeu: str) -> dict[str, Any] | None:
    return await stock.lire(organisation_id, cle(jeu))


async def importer(organisation_id: int, contenu: str, jeu: str = SLUG) -> dict[str, Any]:
    """Verse les attaques absentes, en lots neufs. Rend ce qui a été fait ; un second passage rend ``ajoutees: 0``."""
    lu = lire_le_csv(contenu)
    index = await _index(organisation_id, jeu) or {"lots": 0, "total": 0}
    deja: set[str] = set()
    for numero in range(1, int(index["lots"]) + 1):
        lot = await stock.lire(organisation_id, cle(jeu, numero))
        deja.update(a["id"] for a in (lot or {}).get("attaques", []))
    nouvelles = [a for a in lu["attaques"] if a["id"] not in deja]
    lots = int(index["lots"])
    for debut in range(0, len(nouvelles), LOT):
        lots += 1
        await stock.ecrire(organisation_id, cle(jeu, lots), {"attaques": nouvelles[debut : debut + LOT]})
    if nouvelles or not await _index(organisation_id, jeu):
        await stock.ecrire(
            organisation_id,
            cle(jeu),
            {
                "slug": jeu,
                "source": SOURCE,
                "licence": LICENCE,
                "lots": lots,
                "total": len(deja) + len(nouvelles),
                "importe_le": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
    return {
        "ok": True,
        "ajoutees": len(nouvelles),
        "deja_la": len(lu["attaques"]) - len(nouvelles),
        "ecartees": lu["ecartees"],
        "lignes": lu["lignes"],
        "total": len(deja) + len(nouvelles),
    }


async def resume(organisation_id: int, jeu: str = SLUG) -> dict[str, Any]:
    """Ce que l'écran montre : le jeu est-il importé, combien d'attaques, d'où, sous quelle licence."""
    index = await _index(organisation_id, jeu)
    if not index:
        return {"importe": False, "total": 0, "mention": MENTION}
    return {
        "importe": True,
        "total": int(index.get("total") or 0),
        "source": index.get("source"),
        "licence": index.get("licence"),
        "importe_le": index.get("importe_le"),
        "mention": MENTION,
    }


async def sondes(organisation_id: int, combien: int, jeu: str = SLUG) -> tuple[list[dict[str, Any]], int]:
    """(les ``combien`` premières attaques, le total importé). Ordre stable : celui de l'import (deux passages jouent les mêmes)."""
    index = await _index(organisation_id, jeu)
    if not index:
        return [], 0
    choisies: list[dict[str, Any]] = []
    for numero in range(1, int(index["lots"]) + 1):
        if len(choisies) >= combien:
            break
        lot = await stock.lire(organisation_id, cle(jeu, numero))
        for a in (lot or {}).get("attaques", []):
            if len(choisies) >= combien:
                break
            choisies.append(
                {
                    "id": a["id"],
                    "tours": [a["texte"]],
                    "temoin": TEMOIN,
                    "technique": TECHNIQUE,
                    "famille": a.get("famille") or None,
                    "origine": "public",
                    "gravite_par_defaut": "moyenne",
                }
            )
    return choisies, int(index.get("total") or 0)
