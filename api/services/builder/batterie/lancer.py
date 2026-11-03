"""[.mark] Batterie du builder : jouer un cas (n essais), corriger la trace, enregistrer et comparer la référence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api.services.builder.batterie import cas as modele_cas
from api.services.builder.batterie.cas import Cas
from api.services.builder.batterie.correcteurs import Juge, Trace, corriger
from api.services.builder.batterie.plateforme import Plateforme
from api.services.builder.cerveau.factice import CerveauFactice, appel, texte, tour

REFERENCE = Path(__file__).resolve().parent / "reference.json"
TOURS_MAX = 12


def cerveau_scripte(cas: Cas) -> CerveauFactice:
    """Le comportement attendu du cas, rejoué sans modèle. Un cas sans script rend un cerveau sans tour (l'essai échoue)."""
    tours = []
    for t in cas.tours:
        tours.append(tour(*[appel(e["appel"], e.get("arguments")) if "appel" in e else texte(e["texte"]) for e in t]))
    return CerveauFactice(*tours)


@dataclass
class Essai:
    reussi: bool
    non_juge: bool = False
    raisons: list[str] = field(default_factory=list)
    trace: str = ""


async def jouer(cas: Cas, cerveau: Any, juge: Juge | None = None, systeme: str = "") -> Essai:
    """Une conversation : le cerveau voit la demande, ses appels sont servis par la plateforme simulée, puis les correcteurs lisent la trace."""
    plateforme, trace = Plateforme(cas), Trace()
    messages: list[dict[str, Any]] = [{"role": "user", "content": cas.demande}]
    for _ in range(TOURS_MAX):
        appels, rendu = [], ""
        try:
            async for evenement in cerveau.tour(systeme=systeme, messages=messages, outils=[]):
                if evenement["type"] == "texte":
                    rendu += evenement["texte"]
                elif evenement["type"] == "appel":
                    appels.append(evenement)
        except AssertionError:
            break  # le script n'a plus de tour : les correcteurs jugent ce qui a eu lieu
        if rendu:
            trace.textes.append(rendu)
        messages.append({"role": "assistant", "content": rendu, "appels": [{"id": a["id"], "nom": a["nom"]} for a in appels]})
        if not appels:
            break
        for a in appels:
            resultat = await plateforme.executer(a["nom"], a["arguments"])
            trace.appels.append({"nom": a["nom"], "arguments": a["arguments"], "resultat": resultat})
            messages.append({"role": "outil", "appel_id": a["id"], "nom": a["nom"], "content": json.dumps(resultat)})
    raisons, non_juge = [], False
    for correcteur in cas.correcteurs:
        verdict, pourquoi = await corriger(correcteur, trace, juge)
        if verdict is None:
            non_juge = True
            raisons.append(pourquoi)
        elif not verdict:
            raisons.append(pourquoi)
    return Essai(reussi=not raisons and not non_juge, non_juge=non_juge, raisons=raisons, trace=trace.en_texte())


async def lancer(
    fabrique_de_cerveau: Callable[[Cas], Any] = cerveau_scripte,
    essais: int = 3,
    juge: Juge | None = None,
    cas_a_jouer: list[Cas] | None = None,
) -> dict[str, dict[str, Any]]:
    """{id du cas: {empreinte, essais, reussis, raisons}}. ``fabrique_de_cerveau`` : un cerveau NEUF par essai."""
    sortie: dict[str, dict[str, Any]] = {}
    for cas in cas_a_jouer if cas_a_jouer is not None else modele_cas.charger():
        resultats = [await jouer(cas, fabrique_de_cerveau(cas), juge) for _ in range(essais)]
        sortie[cas.id] = {
            "empreinte": cas.empreinte,
            "essais": essais,
            "reussis": sum(1 for r in resultats if r.reussi),
            "raisons": sorted({m for r in resultats for m in r.raisons}),
        }
    return sortie


def lire_la_reference(chemin: Path = REFERENCE) -> dict[str, dict[str, Any]]:
    return json.loads(chemin.read_text(encoding="utf-8")).get("cas", {}) if chemin.exists() else {}


def enregistrer_la_reference(resultats: dict[str, dict[str, Any]], chemin: Path = REFERENCE) -> None:
    gardes = {k: {"empreinte": v["empreinte"], "essais": v["essais"], "reussis": v["reussis"]} for k, v in sorted(resultats.items())}
    chemin.write_text(json.dumps({"cas": gardes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def comparer(resultats: dict[str, dict[str, Any]], reference: dict[str, dict[str, Any]]) -> list[str]:
    """Les écarts qui font échouer la comparaison. Vide : aucun cas ne passe moins souvent qu'avant."""
    problemes = []
    for identifiant, ancien in reference.items():
        actuel = resultats.get(identifiant)
        if actuel is None:
            problemes.append(f"{identifiant}: case missing from this run")
        elif actuel["empreinte"] != ancien["empreinte"]:
            problemes.append(f"{identifiant}: the case changed since the reference was recorded (record it again)")
        elif actuel["reussis"] * ancien["essais"] < ancien["reussis"] * actuel["essais"]:
            problemes.append(f"{identifiant}: passes {actuel['reussis']}/{actuel['essais']}, it passed {ancien['reussis']}/{ancien['essais']}")
    problemes.extend(f"{i}: case without a reference (record it)" for i in resultats if i not in reference)
    return problemes
