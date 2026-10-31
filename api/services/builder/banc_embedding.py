"""[.mark] Builder, lot 6 : le banc de recherche de la base de connaissances, qui compare des modèles d'embedding.

Mesure « le bon passage est dans les 3 premiers » sur un corpus de questions posées comme au téléphone, chacune avec son passage
attendu. Aucun appel téléphonique, aucun casque : un ou deux modèles d'embedding, des documents, des questions.

* **Le découpage est celui de la base** (``gen_ai.documents_locaux.decouper``, 128 jetons par défaut comme ``knowledge_base_content``).
* **Les vecteurs viennent de la fabrique existante** (``gen_ai/embedding/factory.build_embedding_service``) : même client, même demande
  de 1 536 dimensions pour un fournisseur compatible OpenAI hébergé ailleurs que chez OpenAI. Un vecteur d'une autre taille est une erreur
  (la base stocke ``vector(1536)``).
* **Le classement est celui de la base** : similarité cosinus, du plus proche au plus loin (``1 - (embedding <=> requête)``).
* **Rejouable** : même corpus, mêmes documents, quand un gros document est ajouté ; la sortie JSON se compare d'une fois sur l'autre.

Corpus (JSON) :

    {"version": 1, "documents": ["chemin.md", ...],
     "questions": [{"question": "...", "passage_attendu": "extrait exact OU identifiant du morceau"}]}

``passage_attendu`` : un extrait exact (le morceau qui le contient est le bon, espaces et casse ignorés) ou ``document#N`` (le morceau N,
compté depuis 0, du document). Un passage attendu introuvable dans le découpage est une erreur du CORPUS, dite avant tout calcul.
Les chemins de documents sont lus depuis le dossier du fichier de corpus.

Modèles : ``text-embedding-3-small`` (OpenAI, défaut) et ``qwen3-embedding-8b`` (Scaleway, compatible OpenAI). ``bge-multilingual-gemma2`` est
REFUSÉ (il ne sait pas rendre 1 536 dimensions : la base ne peut pas le ranger). La clé est lue dans l'environnement, jamais affichée,
jamais écrite dans la sortie (seul le NOM de la variable l'est).

⛔ Zéro vocabulaire métier. ⛔ Aucun appel réel dans les tests : la fabrique d'embedding est injectable.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.services.gen_ai.documents_locaux import decouper
from api.services.tests_rejouables.modele import normaliser

VERSION_DU_CORPUS = 1
TAILLE_DES_MORCEAUX = 128  # knowledge_base_content.DEFAULT_CHUNK_MAX_TOKENS
DIMENSION_DE_LA_BASE = 1536
TOP = 3
LOT_DE_TEXTES = 64
QUESTIONS_MIN, QUESTIONS_MAX = 1, 300

MODELES_REFUSES: dict[str, str] = {
    "bge-multilingual-gemma2": "it cannot return 1536 dimensions (the provider answers HTTP 400): the knowledge base stores vector(1536).",
}

# Ce que l'on sait de chaque modèle visé : fournisseur de la fabrique, adresse, variable d'environnement de la clé.
MODELES_CONNUS: dict[str, dict[str, str | None]] = {
    "text-embedding-3-small": {"fournisseur": "openai", "adresse": None, "variable_cle": "OPENAI_API_KEY"},
    "qwen3-embedding-8b": {"fournisseur": "openai", "adresse": "https://api.scaleway.ai/v1", "variable_cle": "SCALEWAY_API_KEY"},
}
MODELE_PAR_DEFAUT = "text-embedding-3-small"


class ErreurBanc(Exception):
    """Un refus dit en une phrase (corpus, modèle, clé, dimension). Jamais la valeur d'une clé."""


@dataclass(frozen=True)
class ConfigModele:
    modele: str
    fournisseur: str = "openai"
    adresse: str | None = None
    variable_cle: str = "OPENAI_API_KEY"

    def public(self) -> dict[str, Any]:
        """Ce qui peut s'écrire dans la sortie : jamais la clé, seulement le nom de sa variable."""
        return {"modele": self.modele, "fournisseur": self.fournisseur, "adresse": self.adresse, "variable_cle": self.variable_cle}


def lire_le_modele(spec: str) -> ConfigModele:
    """``modele[@adresse][#VARIABLE_CLE]`` -> la configuration (les modèles connus complètent ce qui manque). Refuse le modèle exclu."""
    reste, _, variable = spec.partition("#")
    nom, _, adresse = reste.partition("@")
    nom = nom.strip() or MODELE_PAR_DEFAUT
    if nom in MODELES_REFUSES:
        raise ErreurBanc(f"Model « {nom} » is refused: {MODELES_REFUSES[nom]}")
    connu = MODELES_CONNUS.get(nom, {})
    return ConfigModele(
        modele=nom,
        fournisseur=str(connu.get("fournisseur") or "openai"),
        adresse=adresse.strip() or connu.get("adresse"),
        variable_cle=variable.strip() or str(connu.get("variable_cle") or "OPENAI_API_KEY"),
    )


# --- le corpus ------------------------------------------------------------------------------------------------------------------


@dataclass
class Morceau:
    document: str
    numero: int
    texte: str

    @property
    def identifiant(self) -> str:
        return f"{self.document}#{self.numero}"


@dataclass
class Question:
    question: str
    attendus: set[int]  # indices dans la liste des morceaux


def decouper_les_documents(documents: dict[str, str], max_tokens: int = TAILLE_DES_MORCEAUX) -> list[Morceau]:
    """Le découpage RÉEL de la base, document par document."""
    return [Morceau(nom, n, texte) for nom, contenu in documents.items() for n, texte in enumerate(decouper(contenu.strip(), max_tokens))]


_IDENTIFIANT = re.compile(r"^(?P<document>.+)#(?P<numero>\d+)$")


def lire_le_corpus(chemin: Path | str, max_tokens: int = TAILLE_DES_MORCEAUX) -> tuple[list[Morceau], list[Question]]:
    chemin = Path(chemin)
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        raise ErreurBanc(f"The corpus file cannot be read ({type(erreur).__name__}).") from None
    if not isinstance(brut, dict) or brut.get("version") != VERSION_DU_CORPUS:
        raise ErreurBanc(f"The corpus must be an object with version {VERSION_DU_CORPUS}.")
    noms = brut.get("documents")
    if not isinstance(noms, list) or not noms or not all(isinstance(n, str) and n for n in noms):
        raise ErreurBanc("The corpus needs a non-empty list of documents (paths).")
    documents: dict[str, str] = {}
    for nom in noms:
        fichier = (chemin.parent / nom).resolve()
        try:
            documents[nom] = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise ErreurBanc(f"Document not found: {nom}.") from None
    return preparer(documents, brut.get("questions"), max_tokens)


def preparer(documents: dict[str, str], questions_brutes: Any, max_tokens: int = TAILLE_DES_MORCEAUX) -> tuple[list[Morceau], list[Question]]:
    """Découpe, puis rattache chaque question à ses morceaux attendus. Pur (pas de fichier)."""
    if not isinstance(questions_brutes, list) or not (QUESTIONS_MIN <= len(questions_brutes) <= QUESTIONS_MAX):
        raise ErreurBanc(f"The corpus needs between {QUESTIONS_MIN} and {QUESTIONS_MAX} questions.")
    morceaux = decouper_les_documents(documents, max_tokens)
    if not morceaux:
        raise ErreurBanc("The documents give no chunk.")
    questions: list[Question] = []
    introuvables: list[str] = []
    for i, q in enumerate(questions_brutes, 1):
        texte, attendu = (q.get("question"), q.get("passage_attendu")) if isinstance(q, dict) else (None, None)
        if not (isinstance(texte, str) and texte.strip() and isinstance(attendu, str) and attendu.strip()):
            raise ErreurBanc(f"Question {i}: « question » and « passage_attendu » are required texts.")
        trouves: set[int] = set()
        m = _IDENTIFIANT.match(attendu.strip())
        if m and any(x.document == m["document"] for x in morceaux):
            trouves = {k for k, x in enumerate(morceaux) if x.document == m["document"] and x.numero == int(m["numero"])}
        if not trouves:
            voulu = normaliser(attendu)
            trouves = {k for k, x in enumerate(morceaux) if voulu in normaliser(x.texte)}
        if not trouves:
            introuvables.append(f"{i}: {texte.strip()[:60]}")
        questions.append(Question(texte.strip(), trouves))
    if introuvables:
        raise ErreurBanc("Expected passage not found in the chunks (fix the corpus): " + " | ".join(introuvables[:10]))
    return morceaux, questions


# --- le calcul --------------------------------------------------------------------------------------------------------------------


def similarite(a: list[float], b: list[float]) -> float:
    """La similarité cosinus (``1 - distance cosinus``, comme la requête de la base)."""
    produit = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return produit / (na * nb) if na and nb else 0.0


def classer(vecteur_question: list[float], vecteurs: list[list[float]]) -> list[int]:
    """Les indices des morceaux, du plus proche au plus loin (à égalité, le premier du document)."""
    notes = [(similarite(vecteur_question, v), -k) for k, v in enumerate(vecteurs)]
    return [-k for _note, k in sorted(notes, reverse=True)]


def evaluer(morceaux: list[Morceau], questions: list[Question], vecteurs: list[list[float]], vecteurs_questions: list[list[float]]) -> dict[str, Any]:
    """Le taux de bon passage dans les 3 premiers, le rang de chaque question, les ratées. Pur."""
    rangs = []
    for q, vq in zip(questions, vecteurs_questions):
        ordre = classer(vq, vecteurs)
        rang = next((r for r, k in enumerate(ordre, 1) if k in q.attendus), None)
        rangs.append(
            {
                "question": q.question,
                "rang": rang,
                "dans_les_3": rang is not None and rang <= TOP,
                "passage_attendu": sorted(morceaux[k].identifiant for k in q.attendus),
                "premiers": [morceaux[k].identifiant for k in ordre[:TOP]],
            }
        )
    bons = sum(1 for r in rangs if r["dans_les_3"])
    return {
        "taux_dans_les_3": round(bons / len(rangs), 4),
        "bons": bons,
        "total": len(rangs),
        "rangs": rangs,
        "ratees": [r for r in rangs if not r["dans_les_3"]],
    }


# --- les vecteurs ----------------------------------------------------------------------------------------------------------------------

FabriqueDEmbedding = Callable[[ConfigModele, str], Awaitable[Any]]


async def fabrique_reelle(config: ConfigModele, cle: str):
    """Le service d'embedding de la base (``build_embedding_service``), sans base de données (le banc ne cherche pas dans la base)."""
    from api.services.gen_ai.embedding.factory import build_embedding_service

    return await build_embedding_service(
        db_client=None,  # type: ignore[arg-type] -- ce service ne s'en sert que pour chercher dans la base
        provider=config.fournisseur,
        api_key=cle,
        model=config.modele,
        base_url=config.adresse,
    )


def lire_la_cle(config: ConfigModele, environnement: dict[str, str] | None = None) -> str:
    cle = (environnement if environnement is not None else os.environ).get(config.variable_cle, "").strip()
    if not cle:
        raise ErreurBanc(f"The key of « {config.modele} » is missing: set the environment variable {config.variable_cle}.")
    return cle


def masquer(texte: str, cle: str) -> str:
    return texte.replace(cle, "***") if cle else texte


async def calculer_les_vecteurs(service: Any, textes: list[str]) -> list[list[float]]:
    sortie: list[list[float]] = []
    for debut in range(0, len(textes), LOT_DE_TEXTES):
        sortie.extend(await service.embed_texts(textes[debut : debut + LOT_DE_TEXTES]))
    return sortie


async def banc_d_un_modele(
    config: ConfigModele, morceaux: list[Morceau], questions: list[Question], *, fabrique: FabriqueDEmbedding = fabrique_reelle, environnement: dict[str, str] | None = None
) -> dict[str, Any]:
    cle = lire_la_cle(config, environnement)
    try:
        service = await fabrique(config, cle)
        vecteurs = await calculer_les_vecteurs(service, [m.texte for m in morceaux])
        vecteurs_q = await calculer_les_vecteurs(service, [q.question for q in questions])
    except ErreurBanc:
        raise
    except Exception as erreur:  # noqa: BLE001 -- le message du fournisseur peut contenir la clé : jamais tel quel
        raise ErreurBanc(f"« {config.modele} » failed ({type(erreur).__name__}): {masquer(str(erreur), cle)[:300]}") from None
    if len(vecteurs) != len(morceaux) or len(vecteurs_q) != len(questions):
        raise ErreurBanc(f"« {config.modele} » returned a wrong number of vectors.")
    dimensions = {len(v) for v in [*vecteurs, *vecteurs_q]}
    if dimensions != {DIMENSION_DE_LA_BASE}:
        raise ErreurBanc(f"« {config.modele} » returned vectors of {sorted(dimensions)} dimensions: the base stores {DIMENSION_DE_LA_BASE}.")
    return {**config.public(), "dimension": DIMENSION_DE_LA_BASE, **evaluer(morceaux, questions, vecteurs, vecteurs_q)}


async def comparer(
    configs: list[ConfigModele], morceaux: list[Morceau], questions: list[Question], *, fabrique: FabriqueDEmbedding = fabrique_reelle, environnement: dict[str, str] | None = None
) -> dict[str, Any]:
    """Le banc de un ou deux modèles sur le même corpus. Rend le détail par modèle et la comparaison."""
    if not 1 <= len(configs) <= 2:
        raise ErreurBanc("Give one or two models.")
    resultats = [await banc_d_un_modele(c, morceaux, questions, fabrique=fabrique, environnement=environnement) for c in configs]
    comparaison: dict[str, Any] = {}
    if len(resultats) == 2:
        a, b = resultats
        ecart = round(a["taux_dans_les_3"] - b["taux_dans_les_3"], 4)
        comparaison = {
            "meilleur": None if ecart == 0 else (a if ecart > 0 else b)["modele"],
            "ecart_de_taux": ecart,
            "questions_ou_ils_different": [
                x["question"] for x, y in zip(a["rangs"], b["rangs"]) if x["dans_les_3"] != y["dans_les_3"]
            ],
        }
    return {
        "version": 1,
        "morceaux": len(morceaux),
        "questions": len(questions),
        "taille_des_morceaux": TAILLE_DES_MORCEAUX,
        "modeles": resultats,
        "comparaison": comparaison,
    }


def resume(sortie: dict[str, Any]) -> str:
    """Le résumé lisible (une ligne par modèle, puis les questions ratées)."""
    lignes = [f"{sortie['questions']} questions, {sortie['morceaux']} morceaux."]
    for m in sortie["modeles"]:
        lignes.append(f"{m['modele']} : {m['bons']}/{m['total']} dans les {TOP} premiers ({m['taux_dans_les_3'] * 100:.0f} %)")
        for r in m["ratees"]:
            lignes.append(f"    ratée (rang {r['rang'] or 'absent'}) : {r['question'][:90]}")
    c = sortie["comparaison"]
    if c:
        lignes.append("Égalité." if c["meilleur"] is None else f"Meilleur : {c['meilleur']} (écart {abs(c['ecart_de_taux']) * 100:.0f} points).")
    return "\n".join(lignes)
