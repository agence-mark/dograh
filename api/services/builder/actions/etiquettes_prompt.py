"""[.mark] Builder, lots 8 et 22 : le builder LIT et ÉCRIT les étiquettes d'objets des prompts, et pose ou retire un bloc.

* ``etiquettes_prompt_lire`` : les objets citables de l'organisation (clé à écrire entre {{ }}, nom vu par le modèle, état) et les
  étiquettes en erreur du brouillon, comme l'écran les reçoit ;
* ``bloc_poser``     : ajoute ``{{bloc:slug}}`` (suit la dernière Recette) ou ``{{bloc:slug@vN}}`` (reste sur la N) à la fin du prompt
  d'une étape, dans le BROUILLON ;
* ``bloc_retirer``   : retire un bloc d'une étape (ou de tout l'agent).

``garde`` (appelée par ``registre.executer`` avant toute écriture de l'agent) refuse une étiquette HORS CATALOGUE dans ce que le
builder écrit : il ne peut pas inventer un outil, un document ou un bloc. Les étiquettes d'étapes ne sont pas contrôlées ici (une
étape peut naître dans la même écriture) : le contrôle de publication les attrape.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.db import db_client
from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.etiquettes_prompt import catalogue as cat
from api.services.etiquettes_prompt import corrections
from api.services.etiquettes_prompt import familles as f

GROUPE = "etiquettes_prompt"
# Les actions dont on contrôle les étiquettes écrites (celles qui changent l'agent, plus la création).
ACTIONS_GARDEES = frozenset({"save_workflow", "create_workflow", "brouillon_operation", "bloc_poser"})


def _chaines(valeur: Any):
    if isinstance(valeur, str):
        yield valeur
    elif isinstance(valeur, dict):
        for v in valeur.values():
            yield from _chaines(v)
    elif isinstance(valeur, (list, tuple)):
        for v in valeur:
            yield from _chaines(v)


def hors_catalogue(etiquettes: list[f.Etiquette], catalogue: dict[str, cat.ObjetCitable], illisibles: set[str]) -> list[str]:
    """Pure. Les étiquettes citées qui ne sont pas au catalogue (une famille illisible n'est pas jugée)."""
    sortie: list[str] = []
    for e in etiquettes:
        if e.famille == f.ETAPE or e.famille in illisibles:
            continue
        if e.famille == f.BLOC:
            slug, version = f.bloc_et_version(e.cle)
            objet = catalogue.get(f"{f.BLOC}:{slug}")
            connu = objet is not None and (version is None or any(v["numero"] == version for v in objet.versions))
        else:
            connu = e.complete in catalogue
        if not connu and e.complete not in sortie:
            sortie.append(e.complete)
    return sortie


async def garde(nom: str, arguments: dict[str, Any] | None, contexte: Contexte) -> None:
    if nom not in ACTIONS_GARDEES:
        return
    etiquettes = [e for t in _chaines(arguments or {}) for e in f.etiquettes_de(t)]
    if not etiquettes:
        return
    catalogue, illisibles = await cat.catalogue_de(contexte.organisation_id, None)
    refusees = hors_catalogue(etiquettes, catalogue, illisibles)
    if refusees:
        raise ErreurAction(
            "NOTHING WAS CHANGED. These labels are not in the catalogue of this organization: "
            + ", ".join("{{" + r + "}}" for r in refusees[:10])
            + ". Read etiquettes_prompt_lire and use its keys.",
            "etiquette_hors_catalogue",
        )


class _Lire(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent (default: the conversation's agent).")
    famille: str | None = Field(default=None, description=f"Only one family: {', '.join(f.FAMILLES)}.")


async def _lire(contexte: Contexte, p: _Lire) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    brouillon = await db_client.get_draft_version(agent.id) or getattr(agent, "released_definition", None)
    graphe = getattr(brouillon, "workflow_json", None)
    graphe = graphe if isinstance(graphe, dict) else None
    catalogue, illisibles = await cat.catalogue_de(contexte.organisation_id, graphe)
    configs = getattr(brouillon, "workflow_configurations", None)
    problemes = cat.diagnostiquer(graphe, configs if isinstance(configs, dict) else None, catalogue, illisibles)
    objets = [o for o in catalogue.values() if p.famille is None or o.famille == p.famille]
    return {
        "ok": True,
        "ecriture": "Write {{<cle>}} in a prompt, e.g. {{outil:<uuid>}}; a block: {{bloc:<slug>}} follows the latest Recette, {{bloc:<slug>@v2}} stays on v2.",
        "objets": [
            {"cle": o.cle, "famille": o.famille, "libelle": o.libelle, "rendu": o.rendu[:120], "statut": o.statut, "version": o.version}
            for o in objets[:300]
        ],
        "problemes": [pb.en_dict() for pb in problemes],
        "sources_illisibles": sorted(illisibles),
    }


class _Poser(BaseModel):
    workflow_id: int | None = None
    noeud_id: str = Field(min_length=1, max_length=200, description="The step (node id) whose prompt receives the block.")
    bloc: str = Field(min_length=1, max_length=64, description="The block slug (etiquettes_prompt_lire, famille bloc).")
    version: int | None = Field(default=None, ge=1, le=9999, description="Stay on this version; empty = follow the latest Recette.")


async def _poser(contexte: Contexte, p: _Poser) -> dict[str, Any]:
    from api.services.workflow.dto import ReactFlowDTO

    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    etiquette = "{{bloc:" + p.bloc + (f"@v{p.version}" if p.version else "") + "}}"
    await garde("bloc_poser", {"t": etiquette}, contexte)
    brouillon = await db_client.get_draft_version(agent.id) or await db_client.save_workflow_draft(agent.id)
    graphe = dict(getattr(brouillon, "workflow_json", None) or {})
    noeuds = []
    trouve = False
    for n in graphe.get("nodes") or []:
        if str(n.get("id")) == p.noeud_id:
            donnees = dict(n.get("data") or {})
            if not isinstance(donnees.get("prompt"), str):
                raise ErreurAction("This step has no prompt.", "sans_prompt")
            if etiquette not in donnees["prompt"]:
                donnees["prompt"] = donnees["prompt"].rstrip() + "\n\n" + etiquette
            n = {**n, "data": donnees}
            trouve = True
        noeuds.append(n)
    if not trouve:
        raise ErreurAction("This step does not exist in the draft.", "introuvable")
    graphe["nodes"] = noeuds
    try:
        ReactFlowDTO.model_validate(graphe)
    except Exception:  # noqa: BLE001
        raise ErreurAction("The graph would become invalid: nothing was changed.", "graphe") from None
    await db_client.update_workflow(
        workflow_id=agent.id, name=None, workflow_definition=graphe, template_context_variables=None,
        workflow_configurations=None, organization_id=contexte.organisation_id,
    )
    return {"ok": True, "etiquette": etiquette, "noeud_id": p.noeud_id, "suite": "Written into the DRAFT. Test it; a person publishes."}


class _Retirer(BaseModel):
    workflow_id: int | None = None
    bloc: str = Field(min_length=1, max_length=64, description="The block slug to remove (every version written).")
    noeud_id: str | None = Field(default=None, max_length=200, description="Only this step; empty = the whole agent.")


async def _retirer(contexte: Contexte, p: _Retirer) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, p.workflow_id)
    champ = f"nodes[{p.noeud_id}].prompt" if p.noeud_id else None
    try:
        vue = await corrections.corriger(agent, contexte.organisation_id, {"type": "retirer", "cle": f"bloc:{p.bloc}", "champ": champ})
    except corrections.CorrectionRefusee as erreur:
        raise ErreurAction(str(erreur), "introuvable") from None
    return {"ok": True, "retire": f"bloc:{p.bloc}", "problemes": vue["problemes"]}


for _nom, _desc, _param, _fn, _ecrit in (
    (
        "etiquettes_prompt_lire",
        "List the objects a prompt can cite as a label ({{outil:…}}, {{etape:…}}, {{agent:…}}, {{equipe:…}}, {{document:…}}, "
        "{{phrase:…}}, {{bloc:…}}) and the broken labels of the draft. Never write a label that is not in this list.",
        _Lire,
        _lire,
        False,
    ),
    ("bloc_poser", "Add a library block to the end of a step's prompt, in the DRAFT (follow the latest Recette, or stay on a version).", _Poser, _poser, True),
    ("bloc_retirer", "Remove a library block from a step's prompt (or from the whole agent), in the DRAFT.", _Retirer, _retirer, True),
):
    enregistrer(Action(nom=_nom, description=_desc, parametres=_param, fonction=_fn, ecriture=_ecrit, groupe=GROUPE, extras={"lot": "8-22"}))
