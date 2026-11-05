"""[.mark] Le juge v1 sur clé d'API : une passe par critère, vote sur 3 passes si c'est serré.

Chaque passe rend UN verdict fermé (``verdicts.py``) ; une réponse hors forme est écartée, jamais corrigée. Si la confiance est sous
``SEUIL_DE_CONFIANCE`` (ou la réponse inutilisable), jusqu'à ``PASSES_MAX`` passes et vote à la majorité. Aucune réponse valable :
« non vérifiable », qui compte comme raté. Le cerveau est injecté (les tests passent un cerveau factice).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from typing import Any

from api.services.builder import consignes
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau
from api.services.builder.tests_agent.jeu import completer
from api.services.builder.tests_agent.juge import PASSES_MAX, SEUIL_DE_CONFIANCE
from api.services.juge import verdicts as v

# RA-B (R6, audit 06) : une erreur passagère du modèle est réessayée avant de passer le reste de la grille en « non vérifiable »
# (sinon « À améliorer » se remplit de faux signaux) : 3 essais au plus, avec attente. Une erreur définitive n'est pas réessayée.
ATTENTES_DE_REESSAI_S = (1.0, 3.0)

FORMAT = (
    'Réponds UNIQUEMENT par un objet JSON : {"critere": "<le critère>", "verdict": "reussi|rate|non_verifiable", '
    '"replique": <numéro de la réplique citée>, "preuve": "<citation exacte de cette réplique>", "confiance": <0 à 1>}. '
    "Pas de réplique à citer : non_verifiable, avec en preuve la raison."
)


def _dossier_texte(lignes: list[tuple[str, str]], outils: list[dict[str, Any]], fiche: dict[str, Any]) -> str:
    texte = "\n".join(f"{i + 1}. {'AGENT' if r == 'agent' else 'APPELANT'} : {t}" for i, (r, t) in enumerate(lignes))
    morceaux = [f"Transcription numérotée :\n{texte}"]
    if outils:
        morceaux.append("Outils appelés : " + json.dumps(outils, ensure_ascii=False)[:2000])
    if fiche:
        morceaux.append("Fiche finale : " + json.dumps(fiche, ensure_ascii=False, default=str)[:2000])
    return "\n\n".join(morceaux)


def lire_un_verdict(texte: str, critere: str, lignes: list[tuple[str, str]]) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", texte, flags=re.S)
    if not m:
        return None
    try:
        brut = json.loads(m.group(0))
        if isinstance(brut, dict):
            brut["critere"] = critere
        return v.verifier_un(brut, lignes, [critere])
    except (json.JSONDecodeError, v.VerdictRefuse):
        return None


async def _systeme() -> str:
    return await consignes.consigne_juge()


async def juger_critere(
    cerveau: Cerveau, systeme: str, critere: str, lignes: list[tuple[str, str]], dossier: str
) -> dict[str, Any]:
    valides: list[dict[str, Any]] = []
    for _ in range(PASSES_MAX):
        demande = f"{dossier}\n\nCritère à juger : {critere}\n\n{FORMAT}"
        texte = await completer(cerveau, systeme, [{"role": "user", "content": demande}])
        un = lire_un_verdict(texte, critere, lignes)
        if un is not None:
            valides.append(un)
            if un["confiance"] >= SEUIL_DE_CONFIANCE and len(valides) == 1:
                return {**un, "passes": 1}
    if not valides:
        return {
            "critere": critere,
            "verdict": "non_verifiable",
            "replique": None,
            "preuve": "No valid answer from the judge.",
            "confiance": 0.0,
            "passes": PASSES_MAX,
        }
    compte = Counter(x["verdict"] for x in valides)
    (premier, n), *reste = compte.most_common()
    gagnant = premier if not reste or n > reste[0][1] else "non_verifiable"  # égalité : pas de majorité, non vérifiable
    retenu = next((x for x in valides if x["verdict"] == gagnant), valides[0])
    if gagnant == "non_verifiable" and retenu["verdict"] != "non_verifiable":
        retenu = {**retenu, "verdict": "non_verifiable", "preuve": "No majority between the passes."}
    return {**retenu, "passes": len(valides), "serre": True}


async def _juger_critere_avec_reessais(
    cerveau: Cerveau, systeme: str, critere: str, lignes: list[tuple[str, str]], dossier: str
) -> dict[str, Any]:
    for attente in (*ATTENTES_DE_REESSAI_S, None):
        try:
            return await juger_critere(cerveau, systeme, critere, lignes, dossier)
        except ErreurCerveau as erreur:
            if attente is None or not erreur.reessayable:
                raise
            await asyncio.sleep(attente)
    raise AssertionError("unreachable")  # pragma: no cover


async def juger(
    cerveau: Cerveau,
    lignes: list[tuple[str, str]],
    criteres: list[str],
    *,
    outils: list[dict[str, Any]] | None = None,
    fiche: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Les verdicts de tous les critères. Une erreur du cerveau rend ce qui est jugé et marque le reste « non vérifiable »."""
    systeme = await _systeme()
    dossier = _dossier_texte(lignes, outils or [], fiche or {})
    rendus: list[dict[str, Any]] = []
    erreur: str | None = None
    for critere in criteres:
        if erreur is not None:
            rendus.append({"critere": critere, "verdict": "non_verifiable", "replique": None, "preuve": erreur, "confiance": 0.0, "passes": 0})
            continue
        try:
            rendus.append(await _juger_critere_avec_reessais(cerveau, systeme, critere, lignes, dossier))
        except ErreurCerveau as e:
            erreur = f"The judge brain failed: {e.code}."
            rendus.append({"critere": critere, "verdict": "non_verifiable", "replique": None, "preuve": erreur, "confiance": 0.0, "passes": 0})
    return {"verdicts": rendus, "reussi": v.reussi(rendus)}
