"""[.mark] Rejoue les tours réels d'appels par la vraie route des modules et de la fiche.

Chantier correctifs-modules, lot 0 (28/09/2026). Le corpus (``donnees/rejeu_runs_861_881.json``)
garde, pour chaque run, l'entendu exact de chaque tour de l'appelant, l'étape, la dernière réplique
de l'agent, et les notes que le modèle a passées à ``noter_information`` avec leur résultat en
production.

Le rejeu, tour par tour, fait ce que fait un appel :

1. le message de l'appelant passe par les VRAIS processeurs, dans l'ordre du pipeline
   (``ReconnaissanceLexiqueProcessor`` puis ``LectureAppelantProcessor``), qui écrivent leurs
   traces dans la fiche de l'appel par le vrai ``Consignation`` ;
2. les notes du modèle, telles qu'il les a passées en production, sont données au VRAI
   gestionnaire de ``noter_information`` (``creer_gestionnaire``), sur les messages que le modèle
   a lus ;
3. en fin d'appel, la passe de fin d'appel (``balayer_la_fiche``) reçoit ce que l'extraction a
   proposé en production.

⚠️ La limite, à dire avec chaque mesure : le modèle est figé. Ses notes sont celles de la
production ; un correctif qui lui aurait fait noter autre chose, ou poser d'autres questions,
n'est pas mesuré ici. Le banc vocal le mesure.

Lancé seul, il écrit la mesure (``python -m api.tests.mark.rejeu_corpus [sortie.json]``).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from api.schemas.lexique_metier import LexiqueMetier, normaliser_terme
from api.schemas.organization_preferences import AdresseEtablissement
from api.services.communes.base import charger_base
from api.services.pipecat.lecture_appelant import creer_lecture_appelant
from api.services.pipecat.reconnaissance_lexique import creer_reconnaissance_lexique
from api.services.pipecat.verification_communes import consigner_dans
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    ReglagesFiche,
    balayer_la_fiche,
    creer_gestionnaire,
)

CORPUS = Path(__file__).parent / "donnees" / "rejeu_runs_861_881.json"

# Ce qu'un appelant dit pour confirmer, en tête de sa réponse (mesure « après un oui »).
_OUI = ("oui", "ouais", "c'est ça", "c est ça", "exactement", "voilà", "tout à fait", "absolument")

# Le rang d'un champ par rapport à sa cible, du meilleur au pire (zéro perte = jamais pire).
JUSTE_SUR, JUSTE_A_CONFIRMER, VIDE, FAUX = 3, 2, 1, 0
NOMS_DES_RANGS = {JUSTE_SUR: "juste_sur", JUSTE_A_CONFIRMER: "juste_a_confirmer", VIDE: "vide", FAUX: "faux"}


def charger() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _pareil(a, b) -> bool:
    return normaliser_terme(str(a or "")) == normaliser_terme(str(b or ""))


def est_un_oui(texte: str) -> bool:
    debut = normaliser_terme(texte or "")
    return any(debut.startswith(normaliser_terme(o)) for o in _OUI)


class _Frame(SimpleNamespace):
    """Ce que les deux processeurs lisent d'un ``LLMContextFrame``."""


async def rejouer_run(run: dict, corpus: dict) -> dict:
    """Rejoue un run ; rend les résultats de l'outil tour par tour et la fiche finale."""
    charger_base()
    configs = corpus["agents"][str(run["agent"])]
    lexique = LexiqueMetier.model_validate(corpus["lexique"])
    adresse = AdresseEtablissement(**corpus["adresse_etablissement"])
    reglages = ReglagesFiche.depuis(configs, lexique=lexique)
    fiche: dict = {}
    messages: list[dict] = []
    etape = SimpleNamespace(name=None, extraction_variables=[])

    lexique_proc = creer_reconnaissance_lexique(
        configs, lexique, lambda: etape, consigner_dans(lambda: fiche), avec_sons=True
    )
    if lexique_proc is not None:
        await lexique_proc._preparer()
    lecture_proc = creer_lecture_appelant(
        configs, SimpleNamespace(language="fr"), adresse, lambda: etape, consigner_dans(lambda: fiche)
    )
    gestionnaire = creer_gestionnaire(reglages, lambda: fiche, lambda: messages)

    tours = []
    for tour in run["tours"]:
        etape.name = tour["etape"]
        if tour.get("agent_avant"):
            messages.append({"role": "assistant", "content": tour["agent_avant"]})
        message = {"role": "user", "content": tour["entendu"]}
        messages.append(message)
        frame = _Frame(context=SimpleNamespace(messages=messages), speculation=False)
        for proc in (lexique_proc, lecture_proc):
            if proc is not None:
                await proc._lire_contexte(frame)
        # Les champs que la fiche tenait « à confirmer » avant ce tour (mesure D6).
        en_suspens = sorted(
            c
            for c, e in (fiche.get(CLE_ETAT) or {}).items()
            if not e.get("sure") and fiche.get(c) not in (None, "")
        )
        resultats = []
        for note in tour["notes"]:
            recu: dict = {}

            async def rappel(resultat, properties=None, recu=recu):
                recu["resultat"] = resultat

            await gestionnaire(
                SimpleNamespace(
                    arguments=note["arguments"],
                    tool_call_id=note["id"],
                    result_callback=rappel,
                )
            )
            resultats.append(
                {
                    "arguments": note["arguments"],
                    "resultat": recu.get("resultat"),
                    "production": _lire_resultat(note.get("production")),
                }
            )
        tours.append(
            {
                "tour": tour["tour"],
                "entendu": tour["entendu"],
                "lu": message["content"],
                "en_suspens": en_suspens,
                "resultats": resultats,
            }
        )

    async def extraire(variables, _consigne):
        noms = {v.name for v in variables}
        return {k: v for k, v in (run.get("balayage") or {}).items() if k in noms}

    if reglages is not None:
        await balayer_la_fiche(reglages, extraire, fiche, messages)
    return {"id": run["id"], "tours": tours, "fiche": fiche}


def _lire_resultat(texte):
    if not texte:
        return None
    try:
        return ast.literal_eval(texte)
    except (ValueError, SyntaxError):
        return {"brut": texte}


def rang(fiche: dict, champ: str, cible) -> int:
    valeur = fiche.get(champ)
    if cible is None:
        return JUSTE_SUR if valeur in (None, "") else FAUX
    if valeur in (None, ""):
        return VIDE
    if not _pareil(valeur, cible):
        return FAUX
    sure = ((fiche.get(CLE_ETAT) or {}).get(champ) or {}).get("sure")
    return JUSTE_SUR if sure else JUSTE_A_CONFIRMER


def _champs_a_faire_confirmer(resultat: dict | None) -> set[str]:
    if not isinstance(resultat, dict):
        return set()
    return {c["champ"] for c in (resultat.get("a_confirmer") or []) + (resultat.get("a_proposer") or [])}


def mesurer(rejeu: dict, run: dict) -> dict:
    """Ce que le chantier promet de faire bouger, run par run."""
    fiche = rejeu["fiche"]
    cibles = {c: rang(fiche, c, v) for c, v in run["cibles"].items()}
    apres_oui, confirmations = [], 0
    for tour in rejeu["tours"]:
        for r in tour["resultats"]:
            champs = _champs_a_faire_confirmer(r["resultat"])
            confirmations += len(champs)
            # D6 : la personne dit oui, le champ était à confirmer, l'outil le redemande.
            if est_un_oui(tour["entendu"]):
                apres_oui += [
                    f"{tour['tour']}:{c}" for c in sorted(champs & set(tour["en_suspens"]))
                ]
    cible_marque = run["cibles"].get("marque_appareil")
    marques_parasites = sorted(
        {
            f"{t.get('entendu')}->{t.get('terme')}"
            for t in fiche.get("lexique_reconnu") or []
            if not (cible_marque and _pareil(t.get("terme"), cible_marque))
        }
    )
    cible_commune = run["cibles"].get("commune")
    communes_parasites = sorted(
        {
            f"{t.get('entendu')}->{t.get('statut')}"
            for t in fiche.get("communes_verifiees") or []
            if t.get("statut") in ("sure", "a_confirmer", "ambigu")
            and not (
                cible_commune
                and any(
                    _pareil(p.get("nom"), cible_commune)
                    for p in [t.get("commune_retenue") or {}, *(t.get("propositions") or [])]
                )
            )
        }
    )
    notes_lexique = sum(1 for t in rejeu["tours"] if "[Lexique" in (t["lu"] or ""))
    return {
        "cibles": {c: NOMS_DES_RANGS[v] for c, v in cibles.items()},
        "confirmations_demandees": confirmations,
        "confirmations_apres_un_oui": apres_oui,
        "marques_hors_cible": marques_parasites,
        "communes_hors_cible": communes_parasites,
        "tours_avec_note_du_lexique": notes_lexique,
    }


def fidelite(rejeu: dict, run: dict | None = None) -> list[str]:
    """Les notes dont le statut rejoué diffère de la production, et les champs de la fiche
    finale qui diffèrent (sur le code de production, cette liste dit ce que le rejeu ne
    reproduit pas)."""
    ecarts = []
    if run is not None:
        for champ, valeur in (run["production"]["fiche"] or {}).items():
            if not _pareil(rejeu["fiche"].get(champ), valeur):
                ecarts.append(f"{rejeu['id']}:fiche {champ} {valeur!r} -> {rejeu['fiche'].get(champ)!r}")
    for tour in rejeu["tours"]:
        for r in tour["resultats"]:
            prod, rejoue = r["production"] or {}, r["resultat"] or {}
            if prod.get("statut") != rejoue.get("statut"):
                ecarts.append(f"{rejeu['id']}:{tour['tour']} {prod.get('statut')} -> {rejoue.get('statut')}")
    return ecarts


async def rejouer_tout(corpus: dict | None = None) -> dict:
    corpus = corpus or charger()
    mesures, ecarts = {}, []
    for run in corpus["runs"]:
        rejeu = await rejouer_run(run, corpus)
        mesures[str(run["id"])] = mesurer(rejeu, run)
        ecarts += fidelite(rejeu, run)
    return {"mesures": mesures, "ecarts_a_la_production": ecarts}


def resume(resultat: dict) -> dict:
    compte: dict[str, int] = {}
    for m in resultat["mesures"].values():
        for v in m["cibles"].values():
            compte[v] = compte.get(v, 0) + 1
    return {
        "cibles": compte,
        "confirmations_demandees": sum(m["confirmations_demandees"] for m in resultat["mesures"].values()),
        "confirmations_apres_un_oui": sum(len(m["confirmations_apres_un_oui"]) for m in resultat["mesures"].values()),
        "marques_hors_cible": sum(len(m["marques_hors_cible"]) for m in resultat["mesures"].values()),
        "communes_hors_cible": sum(len(m["communes_hors_cible"]) for m in resultat["mesures"].values()),
        "tours_avec_note_du_lexique": sum(m["tours_avec_note_du_lexique"] for m in resultat["mesures"].values()),
        "ecarts_a_la_production": len(resultat["ecarts_a_la_production"]),
    }


if __name__ == "__main__":
    from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante

    sortie = executer_sans_toucher_la_boucle_courante(rejouer_tout())
    sortie["resume"] = resume(sortie)
    texte = json.dumps(sortie, ensure_ascii=False, indent=1)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(texte, encoding="utf-8")
    print(json.dumps(sortie["resume"], ensure_ascii=False, indent=1))
