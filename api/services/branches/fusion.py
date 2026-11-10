"""[.mark] Partie 3, SA-L3c (05 § 12) : fusionner une branche dans la principale, et la mettre à jour depuis la principale.

* **Fusion** (``agents.publier``) : la version en ligne de la branche entre dans la principale. Aperçu champ par champ ; chaque
  conflit est choisi à l'écran. La fusion crée UNE version publiée sur la principale, lui donne la part de trafic de la branche et
  archive la branche. Sur une principale protégée, elle exige ``relue`` (« fusion relue »). Elle se défait tant qu'aucune autre
  publication n'a suivi.
* **Mise à jour** (``agents.modifier``, « rebase ») : les nouveautés de la principale entrent dans le brouillon DE LA PERSONNE sur
  la branche, qui garde les siennes. Un instantané est rangé avant : « Revenir avant » la défait.

Tout est lu, calculé et VALIDÉ avant la première écriture (choix complets, graphe cohérent et valide, chemins de déclencheurs libres,
aperçu encore à jour) ; l'écriture est un seul bloc (``BranchesClient``). Un refus n'écrit rien.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client
from api.db.branches_client import ErreurDeBranche
from api.db.outils_epingles import seulement_blocs
from api.services.branches import champs
from api.services.builder import stock
from api.services.builder.constantes import cle_builder

PARTIE_FUSION = "FUSION"


def _etat(contenu: dict[str, Any] | None) -> champs.Etat:
    contenu = contenu or {}
    return champs.Etat(contenu.get("graphe"), contenu.get("reglages"), contenu.get("variables"), contenu.get("outils"))


def _numero(contenu: dict[str, Any] | None) -> int | None:
    return contenu["numero"] if contenu else None


def _cle_defaire(workflow_id: int, branch_id: int) -> str:
    return cle_builder(workflow_id, f"{PARTIE_FUSION}:{branch_id}")


async def _valider(organization_id: int, workflow_id: int, fusionne: champs.Etat, *, controler_les_declencheurs: bool) -> list[dict[str, Any]]:
    """Les problèmes qui empêcheraient d'écrire, avant toute écriture."""
    from api.services.builder import brouillon

    trouves = champs.problemes(fusionne.graphe)
    if trouves:
        return trouves
    for message in await brouillon.valider(fusionne.graphe, organization_id):
        trouves.append({"code": "graphe_invalide", "message": message})
    if controler_les_declencheurs and not trouves:
        from api.db.agent_trigger_client import TriggerPathConflictError
        from api.services.workflow.trigger_paths import extract_trigger_paths

        chemins = extract_trigger_paths(fusionne.graphe)
        if chemins:
            try:
                await db_client.assert_trigger_paths_available(trigger_paths=chemins, exclude_workflow_id=workflow_id)
            except TriggerPathConflictError:
                trouves.append({"code": "declencheur_pris"})
    return trouves


async def _noms_des_outils(organization_id: int, lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Le libellé d'une ligne « outil » est le NOM de l'outil (lu avec l'organisation, en une requête), pas son identifiant."""
    uuids = [ligne["cle"].split(":", 1)[1] for ligne in lignes if ligne["famille"] == "outils"]
    if not uuids:
        return lignes
    noms = {o.tool_uuid: o.name for o in await db_client.get_tools_by_uuids(uuids, organization_id)}
    return [{**l, "libelle": noms.get(l["cle"].split(":", 1)[1], l["libelle"])} if l["famille"] == "outils" else l for l in lignes]


def _resume(lignes: list[dict[str, Any]]) -> dict[str, int]:
    return {statut: sum(1 for ligne in lignes if ligne["statut"] == statut) for statut in ("reprise", "gardee", "conflit")}


# --- fusion -----------------------------------------------------------------------------------------------------------------------


async def apercu_de_la_fusion(organization_id: int, agent: Any, branch_id: int) -> dict[str, Any]:
    lu = await db_client.lire_pour_la_fusion(organization_id, agent.id, branch_id, None)
    if lu["tete_branche"] is None:
        raise ErreurDeBranche("This branch has no published version to merge: publish it first", "sans_version")
    if lu["tete_principale"] is None:
        raise ErreurDeBranche("The main branch has no live version", "sans_version")
    base = _etat(lu["base"] if lu["base"] is not None else lu["tete_principale"])
    lignes = await _noms_des_outils(organization_id, champs.comparer(base, _etat(lu["tete_branche"]), _etat(lu["tete_principale"])))
    protegee, par_defaut = await db_client.protection_de_la_principale(organization_id, agent.id)
    problemes: list[dict[str, Any]] = []
    if lu["brouillon_de_la_principale"]:
        problemes.append({"code": "brouillon_en_attente"})
    if not any(ligne["statut"] == "conflit" for ligne in lignes):
        # aucun conflit : on sait déjà ce que la fusion écrirait, on montre ses problèmes avant le clic
        fusionne = champs.resoudre(base, _etat(lu["tete_branche"]), _etat(lu["tete_principale"]), {})
        problemes += await _valider(organization_id, agent.id, fusionne, controler_les_declencheurs=True)
    return {
        "branche": {"id": lu["branche"]["id"], "nom": lu["branche"]["nom"], "version": _numero(lu["tete_branche"]), "id_version": lu["tete_branche"]["id"]},
        "cible": {"nom": "Principale", "version": _numero(lu["tete_principale"]), "id_version": lu["tete_principale"]["id"]},
        "depart": {"version": _numero(lu["base"])},
        "champs": lignes,
        "resume": _resume(lignes),
        "problemes": problemes,
        "protegee": protegee,
        "relue_obligatoire": protegee,
        "trafic": {"part_branche": lu["branche"]["part"], "part_principale": lu["principale"]["part"], "part_principale_apres": lu["principale"]["part"] + lu["branche"]["part"]},
    }


async def fusionner(
    organization_id: int, agent: Any, branch_id: int, *, choix: dict[str, str], relue: bool, version_branche: int, version_cible: int, user: Any = None
) -> dict[str, Any]:
    lu = await db_client.lire_pour_la_fusion(organization_id, agent.id, branch_id, None)
    if lu["tete_branche"] is None or lu["tete_principale"] is None:
        raise ErreurDeBranche("This branch has no published version to merge: publish it first", "sans_version")
    if lu["tete_branche"]["id"] != version_branche or lu["tete_principale"]["id"] != version_cible:
        raise ErreurDeBranche("The branch or the main branch changed since the preview: read it again", "perime")
    protegee, _ = await db_client.protection_de_la_principale(organization_id, agent.id)
    if protegee and not relue:
        raise ErreurDeBranche("The main branch is protected: the merge must be reviewed (tick the review box)", "relecture")
    if lu["brouillon_de_la_principale"]:
        raise ErreurDeBranche("The main branch has an unpublished draft: publish or discard it first", "brouillon_en_attente")
    base = _etat(lu["base"] if lu["base"] is not None else lu["tete_principale"])
    source, cible = _etat(lu["tete_branche"]), _etat(lu["tete_principale"])
    try:
        fusionne = champs.resoudre(base, source, cible, choix)
    except champs.ChoixIncomplet as erreur:
        raise ErreurDeBranche(str(erreur), "choix") from None
    problemes = await _valider(organization_id, agent.id, fusionne, controler_les_declencheurs=True)
    if problemes:
        raise ErreurDeBranche(f"The merged agent would be invalid ({problemes[0]['code']}): change a choice", "invalide")

    ecrit = await db_client.appliquer_la_fusion(
        organization_id,
        agent.id,
        branch_id,
        graphe=fusionne.graphe,
        reglages=fusionne.reglages,
        variables=fusionne.variables,
        outils_epingles={**fusionne.outils, **{f"bloc:{s}": n for s, n in seulement_blocs((lu["tete_branche"] or {}).get("outils")).items()}},
        attendu_source=version_branche,
        attendu_cible=version_cible,
    )
    await stock.ecrire(organization_id, _cle_defaire(agent.id, branch_id), {**ecrit["defaire"], "version": ecrit["version_number"], "defaite": False})
    await _apres_la_fusion(organization_id, agent, ecrit, fusionne, user)
    return {"version": ecrit["version_number"], "part_reprise": ecrit["part_reprise"], "branche_archivee": branch_id}


async def _apres_la_fusion(organization_id: int, agent: Any, ecrit: dict[str, Any], fusionne: champs.Etat, user: Any) -> None:
    """Ce que fait aussi une publication : l'instantané pour « Revenir avant » et les déclencheurs. Ne lève jamais (la fusion est faite)."""
    try:
        from types import SimpleNamespace

        from api.services.builder import revue

        publiee = SimpleNamespace(workflow_json=fusionne.graphe, workflow_configurations=fusionne.reglages, version_number=ecrit["version_number"])
        await revue.apres_une_publication(organization_id, agent, publiee, user)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fusion] instantané non pris : {type(erreur).__name__}")
    try:
        from api.services.workflow.trigger_paths import extract_trigger_paths

        await db_client.sync_triggers_for_workflow(
            workflow_id=agent.id, organization_id=organization_id, trigger_paths=extract_trigger_paths(fusionne.graphe)
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fusion] déclencheurs non synchronisés : {type(erreur).__name__}")


async def defaire_la_fusion(organization_id: int, agent: Any, branch_id: int) -> dict[str, Any]:
    trace = await stock.lire(organization_id, _cle_defaire(agent.id, branch_id))
    if trace is None or trace.get("defaite"):
        raise ErreurDeBranche("No merge to undo for this branch", "introuvable")
    numero = await db_client.defaire_la_fusion(organization_id, agent.id, branch_id, trace)
    await stock.ecrire(organization_id, _cle_defaire(agent.id, branch_id), {**trace, "defaite": True})
    return {"version_retiree": numero}


async def derniere_fusion_defaisable(organization_id: int, agent: Any, branch_id: int) -> bool:
    trace = await stock.lire(organization_id, _cle_defaire(agent.id, branch_id))
    return bool(trace and not trace.get("defaite") and trace.get("version_creee") == getattr(agent, "released_definition_id", None))


# --- mise à jour depuis la principale ---------------------------------------------------------------------------------------------


def _cote_de_la_branche(lu: dict[str, Any]) -> dict[str, Any] | None:
    """Ce que la personne a sur la branche : son brouillon, sinon la version en ligne de la branche."""
    return lu["mon_brouillon"] or lu["tete_branche"]


async def apercu_de_la_mise_a_jour(organization_id: int, agent: Any, branch_id: int, user_id: int | None) -> dict[str, Any]:
    lu = await db_client.lire_pour_la_fusion(organization_id, agent.id, branch_id, user_id)
    ma_branche = _cote_de_la_branche(lu)
    if ma_branche is None or lu["tete_principale"] is None:
        raise ErreurDeBranche("Nothing to update: the branch or the main branch has no version", "sans_version")
    a_jour = lu["branche"]["base"] == lu["tete_principale"]["id"]
    base = _etat(lu["base"] if lu["base"] is not None else lu["tete_principale"])
    lignes = [] if a_jour else await _noms_des_outils(organization_id, champs.comparer(base, _etat(lu["tete_principale"]), _etat(ma_branche)))
    problemes: list[dict[str, Any]] = []
    if lignes and not any(ligne["statut"] == "conflit" for ligne in lignes):
        fusionne = champs.resoudre(base, _etat(lu["tete_principale"]), _etat(ma_branche), {})
        problemes = await _valider(organization_id, agent.id, fusionne, controler_les_declencheurs=False)
    return {
        "branche": {"id": lu["branche"]["id"], "nom": lu["branche"]["nom"], "version": _numero(ma_branche), "brouillon": lu["mon_brouillon"] is not None, "id_base": lu["branche"]["base"]},
        "principale": {"version": _numero(lu["tete_principale"]), "id_version": lu["tete_principale"]["id"]},
        "depart": {"version": _numero(lu["base"])},
        "a_jour": a_jour,
        "champs": lignes,
        "resume": _resume(lignes),
        "problemes": problemes,
    }


async def mettre_a_jour(
    organization_id: int, agent: Any, branch_id: int, user: Any, *, choix: dict[str, str], base_attendue: int | None, version_principale: int
) -> dict[str, Any]:
    from api.services.builder import instantane, revue

    lu = await db_client.lire_pour_la_fusion(organization_id, agent.id, branch_id, user.id)
    ma_branche = _cote_de_la_branche(lu)
    if ma_branche is None or lu["tete_principale"] is None:
        raise ErreurDeBranche("Nothing to update: the branch or the main branch has no version", "sans_version")
    if lu["tete_principale"]["id"] != version_principale or lu["branche"]["base"] != base_attendue:
        raise ErreurDeBranche("The branch or the main branch changed since the preview: read it again", "perime")
    if lu["branche"]["base"] == lu["tete_principale"]["id"]:
        raise ErreurDeBranche("The branch is already up to date", "a_jour")
    base = _etat(lu["base"] if lu["base"] is not None else lu["tete_principale"])
    try:
        fusionne = champs.resoudre(base, _etat(lu["tete_principale"]), _etat(ma_branche), choix)
    except champs.ChoixIncomplet as erreur:
        raise ErreurDeBranche(str(erreur), "choix") from None
    problemes = await _valider(organization_id, agent.id, fusionne, controler_les_declencheurs=False)
    if problemes:
        raise ErreurDeBranche(f"The updated branch would be invalid ({problemes[0]['code']}): change a choice", "invalide")

    # L'état d'avant est rangé AVANT d'écrire : « Revenir avant » (sur cette branche) défait la mise à jour.
    complement = await instantane.capturer(organization_id, agent, user=user, configurations=ma_branche["reglages"])
    await revue._ranger(  # noqa: SLF001 -- le même rangement que les instantanés de la revue
        organization_id,
        agent.id,
        cause="mise à jour depuis la principale",
        avant=ma_branche["graphe"],
        apres=fusionne.graphe,
        version_avant=_numero(ma_branche),
        version_apres=_numero(ma_branche),
        fil_id=None,
        operations=[],
        complement=complement,
        branche=branch_id,
    )
    brouillon = await db_client.ecrire_le_brouillon_de_branche(
        organization_id,
        agent.id,
        branch_id,
        user.id,
        graphe=fusionne.graphe,
        reglages=fusionne.reglages,
        variables=fusionne.variables,
        outils_epingles=fusionne.outils,
        attendu_base=base_attendue,
        nouvelle_base=lu["tete_principale"]["id"],
    )
    return {"brouillon": brouillon.id, "version": brouillon.version_number}
