"""[.mark] Lot H : le fichier d'un test rejouable et l'évaluation de ses critères (pur, sans base).

Forme du fichier (JSON, ``version`` 1) :

    {
      "version": 1,
      "nom": "slug-du-test",
      "description": "une phrase",
      "organisation_id": 12,                 # l'agent rejoué doit être de cette organisation (null : pas de contrôle)
      "source": {"run_id": 2146, "rang": 3}, # d'où il vient (rien d'autre n'en dépend)
      "etape": {"id": "n3", "nom": "Collecte", "agent": null},   # où en était l'appel (null : première étape)
      "historique": [{"role": "assistant", "texte": "..."}, {"role": "user", "texte": "..."}],
      "fiche": {...},                        # la fiche de l'appel (gathered_context) à ce moment
      "replique": "ce que la personne dit au tour fautif",
      "critere": {...}
    }

Critères (champ ``type``) :

* ``etape``        : ``attendue`` = nom ou identifiant de l'étape d'ARRIVÉE (porte ou passage attendu) ;
* ``outil``        : ``nom`` de l'outil appelé pendant le tour, ``arguments`` (facultatif) comparés selon
  ``mode`` (``egalite`` : identiques ; ``inclusion`` : ceux du critère sont tous dans l'appel, défaut) ;
  ``appele: false`` = l'outil ne doit PAS être appelé ;
* ``texte_present`` / ``texte_absent`` : ``texte`` cherché dans la réplique de l'agent (casse, accents et
  espaces ne comptent pas).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VERSION = 1
ESSAIS_PAR_DEFAUT = 3
# Les agents du banc de référence et de la production : jamais rejoués (la copie d'agent est la règle).
AGENTS_PROTEGES = frozenset(range(139, 146)) | frozenset(range(223, 244))
TYPES_DE_CRITERE = ("etape", "outil", "texte_present", "texte_absent")
MODES_DES_ARGUMENTS = ("egalite", "inclusion")


class ErreurTestRejouable(Exception):
    """Une erreur que l'outil explique en une phrase (fichier illisible, refus, run introuvable)."""


# --- Le fichier ----------------------------------------------------------------------------------


def valider_critere(critere: Any) -> dict[str, Any]:
    """Le critère, validé ; lève ``ErreurTestRejouable`` avec la raison."""
    if not isinstance(critere, dict):
        raise ErreurTestRejouable("le critère doit être un objet")
    genre = critere.get("type")
    if genre not in TYPES_DE_CRITERE:
        raise ErreurTestRejouable(
            f"type de critère inconnu : {genre!r} (attendu : {', '.join(TYPES_DE_CRITERE)})"
        )
    if genre == "etape" and not str(critere.get("attendue") or "").strip():
        raise ErreurTestRejouable("critère « etape » : « attendue » est vide")
    if genre == "outil":
        if not str(critere.get("nom") or "").strip():
            raise ErreurTestRejouable("critère « outil » : « nom » est vide")
        if critere.get("arguments") is not None and not isinstance(critere["arguments"], dict):
            raise ErreurTestRejouable("critère « outil » : « arguments » doit être un objet")
        if critere.get("mode", "inclusion") not in MODES_DES_ARGUMENTS:
            raise ErreurTestRejouable(
                f"critère « outil » : mode inconnu {critere.get('mode')!r} (egalite ou inclusion)"
            )
    if genre in ("texte_present", "texte_absent") and not str(critere.get("texte") or "").strip():
        raise ErreurTestRejouable(f"critère « {genre} » : « texte » est vide")
    return critere


@dataclass
class TestRejouable:
    # Pas collectée par pytest : ce n'est pas un test, c'est la donnée d'un test.
    __test__ = False

    nom: str
    replique: str
    critere: dict[str, Any]
    historique: list[dict[str, str]] = field(default_factory=list)
    etape: dict[str, Any] | None = None
    fiche: dict[str, Any] = field(default_factory=dict)
    organisation_id: int | None = None
    source: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def en_json(self) -> dict[str, Any]:
        return {
            "version": VERSION,
            "nom": self.nom,
            "description": self.description,
            "organisation_id": self.organisation_id,
            "source": self.source,
            "etape": self.etape,
            "historique": self.historique,
            "fiche": self.fiche,
            "replique": self.replique,
            "critere": self.critere,
        }


def lire_test(chemin: Path | str) -> TestRejouable:
    """Lit un fichier de test. Un fichier illisible ou incohérent → ``ErreurTestRejouable`` claire."""
    chemin = Path(chemin)
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErreurTestRejouable(f"{chemin.name} : fichier introuvable") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErreurTestRejouable(f"{chemin.name} : fichier illisible ({e})") from None
    return depuis_json(brut, defaut_nom=chemin.stem, origine=chemin.name)


def depuis_json(brut: Any, *, defaut_nom: str = "", origine: str = "test") -> TestRejouable:
    if not isinstance(brut, dict):
        raise ErreurTestRejouable(f"{origine} : un test est un objet JSON")
    if brut.get("version") != VERSION:
        raise ErreurTestRejouable(
            f"{origine} : version {brut.get('version')!r} non prise en charge (attendu {VERSION})"
        )
    replique = str(brut.get("replique") or "").strip()
    if not replique:
        raise ErreurTestRejouable(f"{origine} : « replique » est vide")
    historique = brut.get("historique") or []
    if not isinstance(historique, list):
        raise ErreurTestRejouable(f"{origine} : « historique » doit être une liste")
    propre: list[dict[str, str]] = []
    for i, m in enumerate(historique, 1):
        if (
            not isinstance(m, dict)
            or m.get("role") not in ("user", "assistant")
            or not isinstance(m.get("texte"), str)
        ):
            raise ErreurTestRejouable(
                f"{origine} : message {i} de l'historique invalide (role user/assistant et texte attendus)"
            )
        propre.append({"role": m["role"], "texte": m["texte"]})
    fiche = brut.get("fiche") or {}
    etape = brut.get("etape")
    if not isinstance(fiche, dict) or not (etape is None or isinstance(etape, dict)):
        raise ErreurTestRejouable(f"{origine} : « fiche » et « etape » doivent être des objets")
    organisation = brut.get("organisation_id")
    if organisation is not None and (
        not isinstance(organisation, int) or isinstance(organisation, bool)
    ):
        raise ErreurTestRejouable(f"{origine} : « organisation_id » doit être un entier ou null")
    try:
        critere = valider_critere(brut.get("critere"))
    except ErreurTestRejouable as e:
        raise ErreurTestRejouable(f"{origine} : {e}") from None
    return TestRejouable(
        nom=str(brut.get("nom") or defaut_nom or "sans-nom"),
        description=str(brut.get("description") or ""),
        organisation_id=organisation,
        source=dict(brut.get("source") or {}),
        etape=etape,
        historique=propre,
        fiche=fiche,
        replique=replique,
        critere=critere,
    )


def ecrire_test(test: TestRejouable, chemin: Path | str) -> Path:
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(test.en_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return chemin


def nom_de_fichier(nom: str) -> str:
    """Un nom de test devient un nom de fichier sûr (ASCII, tirets)."""
    ascii_ = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return (re.sub(r"[^a-zA-Z0-9]+", "-", ascii_).strip("-").lower() or "test") + ".json"


def refuser_si_protege(agent_id: int) -> None:
    if agent_id in AGENTS_PROTEGES:
        raise ErreurTestRejouable(
            f"agent {agent_id} refusé : agent de référence ou de production, "
            "un test se rejoue sur une COPIE d'agent"
        )


# --- Les critères --------------------------------------------------------------------------------


def normaliser(texte: Any) -> str:
    """Casse, accents, apostrophes et espaces ne comptent pas."""
    s = unicodedata.normalize("NFKD", str(texte or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Observation:
    """Ce que le tour rejoué a produit."""

    texte: str = ""
    outils: list[dict[str, Any]] = field(default_factory=list)  # [{"nom", "arguments"}]
    etape_id: str | None = None
    etape_nom: str | None = None
    etapes_traversees: list[str] = field(default_factory=list)  # noms, dans l'ordre
    # Les outils sortants qui n'ont PAS été exécutés (simulés au rejeu) : [{"nom", "categorie", "ecriture", "arguments"}]
    simules: list[dict[str, Any]] = field(default_factory=list)

    def en_json(self) -> dict[str, Any]:
        return {
            "texte": self.texte,
            "outils": self.outils,
            "etape": {"id": self.etape_id, "nom": self.etape_nom},
            "etapes_traversees": self.etapes_traversees,
            "simules": self.simules,
        }


def _inclus(attendu: Any, reel: Any) -> bool:
    if isinstance(attendu, dict):
        return isinstance(reel, dict) and all(
            k in reel and _inclus(v, reel[k]) for k, v in attendu.items()
        )
    return attendu == reel


def evaluer(critere: dict[str, Any], obs: Observation) -> tuple[bool, str]:
    """(réussi, ce qui a été observé de pertinent, en une phrase)."""
    genre = critere["type"]
    if genre == "etape":
        voulue = normaliser(critere["attendue"])
        ok = voulue in (normaliser(obs.etape_id), normaliser(obs.etape_nom))
        return ok, f"étape d'arrivée : {obs.etape_nom or obs.etape_id or 'aucune'}"
    if genre == "outil":
        nom = critere["nom"]
        appels = [o for o in obs.outils if o.get("nom") == nom]
        vus = ", ".join(o.get("nom") or "?" for o in obs.outils) or "aucun"
        if critere.get("appele", True) is False:
            return not appels, f"outils appelés : {vus}"
        if critere.get("arguments") is None:
            return bool(appels), f"outils appelés : {vus}"
        attendus = critere["arguments"]
        egal = critere.get("mode", "inclusion") == "egalite"
        for appel in appels:
            reels = appel.get("arguments") or {}
            if (attendus == reels) if egal else _inclus(attendus, reels):
                return True, f"{nom}({json.dumps(reels, ensure_ascii=False)})"
        if not appels:
            return False, f"{nom} non appelé (outils appelés : {vus})"
        derniers = json.dumps(appels[-1].get("arguments") or {}, ensure_ascii=False)
        return False, f"{nom} appelé avec d'autres arguments : {derniers}"
    present = normaliser(critere["texte"]) in normaliser(obs.texte)
    if genre == "texte_present":
        return present, f"réplique : {obs.texte[:160]!r}"
    return (not present), f"réplique : {obs.texte[:160]!r}"
