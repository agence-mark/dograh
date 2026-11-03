"""[.mark] Builder, lot 6 : créer un test (Q3, B12).

Trois origines, un seul format (``tests_rejouables`` v1 étendu) :

* **depuis une réplique d'un appel** (bouton sur la page de l'appel) : ``tests_rejouables.creation.creer_depuis_un_run`` coupe le run
  au tour fautif ; l'organisation du run est vérifiée ;
* **à la main** : une réplique et son historique, ou un scénario de conversation libre ;
* **par le builder, depuis la fiche** : le même geste (``origine = "fiche"``), le builder écrit le scénario.

⛔ Q3 : les données personnelles sont remplacées par des fausses AVANT d'écrire (``donnees_fictives.rendre_fictif``) ; un test qui en
garderait une quand même est refusé. Un test a une ORIGINE (client, recette, code, manuel, fiche) : elle sert au tri de la boucle.
"""

from __future__ import annotations

from typing import Any

from api.services.builder.donnees_fictives import est_fictive, rendre_fictif
from api.services.builder.tests_agent import corrige as etat_final
from api.services.builder.tests_agent import stockage, verdict
from api.services.tests_rejouables.modele import ErreurTestRejouable

LONGUEUR_NOM_MAX = 200


async def creer(
    organisation_id: int,
    workflow_id: int,
    *,
    nom: str,
    criteres: list[dict[str, Any]],
    origine: str = "manuel",
    obligatoire: bool = False,
    dossier: str = "",
    description: str = "",
    auteur: str | None = None,
    run_id: int | None = None,
    rang: int | None = None,
    replique: str | None = None,
    historique: list[dict[str, str]] | None = None,
    scenario: str | None = None,
    personnage: str | None = None,
    ouverture: str | None = None,
    tours_max: int | None = None,
    questions_juge: list[str] | None = None,
    corrige: dict[str, Any] | None = None,
    comportements: list[str] | None = None,
) -> dict[str, Any]:
    """Crée et range un test. ``stockage.ErreurTest`` ou ``ErreurTestRejouable`` avec la raison."""
    nom = " ".join(nom.split())[:LONGUEUR_NOM_MAX]
    if not nom:
        raise stockage.ErreurTest("A test needs a name.")
    # U8 (F) : le corrigé (état final attendu) se compile en critères jugés par le code ; un ou deux comportements au plus.
    corrige_propre = etat_final.valider(corrige) if corrige else None
    criteres = verdict.valider_criteres(etat_final.fusionner(criteres, corrige_propre) if criteres or corrige_propre else criteres)
    test: dict[str, Any] = {
        "corrige": corrige_propre,
        "comportements": etat_final.comportements_valides(comportements),
        "version": stockage.VERSION,
        "nom": nom,
        "description": description,
        "organisation_id": organisation_id,
        "criteres": criteres,
        "critere": criteres[0] if criteres[0]["type"] in verdict.TYPES_DE_BASE else verdict.CRITERE_NEUTRE,
        "obligatoire": bool(obligatoire),
        "dossier": dossier.strip()[:80],
        "origine": origine,
        "questions_juge": [q[:300] for q in (questions_juge or [])][:5],
        "cree_le": stockage.maintenant(),
        "cree_par": auteur,
    }
    if run_id is not None:
        if rang is None:
            raise stockage.ErreurTest("Say which reply of the call (rang, from 1).")
        from api.services.tests_rejouables.creation import creer_depuis_un_run

        base_critere = next((c for c in criteres if c["type"] in verdict.TYPES_DE_BASE), verdict.CRITERE_NEUTRE)
        rejouable = await creer_depuis_un_run(run_id, organisation_id, rang, base_critere, nom, description)
        test.update(rejouable.en_json())
        test.update({"criteres": criteres, "obligatoire": bool(obligatoire), "origine": origine, "dossier": dossier.strip()[:80], "questions_juge": test["questions_juge"]})
        test["critere"] = base_critere
    elif replique:
        test.update({"replique": replique.strip(), "historique": list(historique or []), "etape": None, "fiche": {}, "source": {"main": True}})
    elif scenario:
        test["scenario"] = {
            "but": scenario.strip()[:4000],
            "personnage": personnage,
            "ouverture": (ouverture or "").strip()[:500],
            "tours_max": tours_max,
        }
    else:
        raise stockage.ErreurTest("Give a reply (replique or run_id + rang) or a scenario.")
    test = rendre_fictif(test)
    if not est_fictive(test):
        raise stockage.ErreurTest("The test still holds data that looks real: nothing was kept.")
    test["slug"] = await _slug_libre(organisation_id, workflow_id, nom)
    await stockage.ecrire(organisation_id, workflow_id, test)
    return test


async def modifier(
    organisation_id: int,
    workflow_id: int,
    slug: str,
    *,
    nom: str | None = None,
    description: str | None = None,
    criteres: list[dict[str, Any]] | None = None,
    obligatoire: bool | None = None,
    dossier: str | None = None,
    questions_juge: list[str] | None = None,
    replique: str | None = None,
    historique: list[dict[str, str]] | None = None,
    scenario: str | None = None,
    personnage: str | None = None,
    ouverture: str | None = None,
    tours_max: int | None = None,
    corrige: dict[str, Any] | None = None,
    comportements: list[str] | None = None,
) -> dict[str, Any]:
    """U3 (E47) : modification COMPLÈTE d'un test existant, même validation qu'à la création.

    Le ``slug`` ne change jamais ; les résultats d'avant sont remis à zéro (ils jugeaient l'ancien test) ; les données personnelles sont
    remplacées par des fausses comme à la création. La sorte (réplique ou conversation) ne change pas : c'est un autre test.
    """
    ancien = await stockage.lire(organisation_id, workflow_id, slug)
    test = dict(ancien)
    if nom is not None:
        nom = " ".join(nom.split())[:LONGUEUR_NOM_MAX]
        if not nom:
            raise stockage.ErreurTest("A test needs a name.")
        test["nom"] = nom
    if description is not None:
        test["description"] = description
    if comportements is not None:
        test["comportements"] = etat_final.comportements_valides(comportements)
    if corrige is not None:
        # un corrigé vide le retire ; sinon il remplace l'ancien et ses critères compilés sont recalculés
        nouveau = etat_final.valider(corrige) if corrige else None
        base = list(test.get("criteres") or [])
        if test.get("corrige"):
            compile_ancien = {repr(sorted(c.items())) for c in etat_final.en_criteres(test["corrige"])}
            base = [c for c in (test.get("criteres") or []) if repr(sorted(c.items())) not in compile_ancien]
        if nouveau is not None:
            base = etat_final.fusionner(base, nouveau)
        test["corrige"] = nouveau
        criteres = base if criteres is None else etat_final.fusionner(criteres, nouveau)
    if criteres is not None:
        criteres = verdict.valider_criteres(criteres)
        test["criteres"] = criteres
        test["critere"] = criteres[0] if criteres[0]["type"] in verdict.TYPES_DE_BASE else verdict.CRITERE_NEUTRE
    if obligatoire is not None:
        test["obligatoire"] = bool(obligatoire)
    if dossier is not None:
        test["dossier"] = dossier.strip()[:80]
    if questions_juge is not None:
        test["questions_juge"] = [q[:300] for q in questions_juge][:5]
    if test.get("scenario"):
        if replique or historique:
            raise stockage.ErreurTest("This test is a simulated conversation: it has no single reply to change.")
        base = dict(test["scenario"])
        if scenario is not None:
            if not scenario.strip():
                raise stockage.ErreurTest("A conversation test needs its scenario.")
            base["but"] = scenario.strip()[:4000]
        if personnage is not None:
            base["personnage"] = personnage or None
        if ouverture is not None:
            base["ouverture"] = ouverture.strip()[:500]
        if tours_max is not None:
            base["tours_max"] = tours_max
        test["scenario"] = base
    else:
        if scenario or personnage or ouverture or tours_max:
            raise stockage.ErreurTest("This test is one reply: it has no scenario to change.")
        if replique is not None:
            if not replique.strip():
                raise stockage.ErreurTest("A reply test needs its reply.")
            test["replique"] = replique.strip()
        if historique is not None:
            test["historique"] = list(historique)
    test = rendre_fictif(test)
    if not est_fictive(test):
        raise stockage.ErreurTest("The test still holds data that looks real: nothing was kept.")
    test["modifie_le"] = stockage.maintenant()
    await stockage.ecrire(organisation_id, workflow_id, test)
    await stockage.effacer_les_resultats(organisation_id, workflow_id, slug)
    return test


async def _slug_libre(organisation_id: int, workflow_id: int, nom: str) -> str:
    pris = {t["slug"] for t in await stockage.lister(organisation_id, workflow_id)}
    base, n, slug = stockage.slug_de(nom), 2, stockage.slug_de(nom)
    while slug in pris:
        slug = f"{base[:60]}-{n}"
        n += 1
    return slug


def en_resume(test: dict[str, Any]) -> dict[str, Any]:
    """Ce que les listes et la carte lisent : jamais la conversation entière."""
    return {
        "slug": test["slug"],
        "nom": test["nom"],
        "obligatoire": bool(test.get("obligatoire")),
        "dossier": test.get("dossier", ""),
        "origine": test.get("origine"),
        "genre": "conversation" if test.get("scenario") else "replique",
        "description": test.get("description", ""),
        "criteres": len(test.get("criteres") or []),
        "corrige": test.get("corrige"),
        "comportements": list(test.get("comportements") or []),
        "construction": etat_final.construction(test),
        "source": test.get("source") or {},
        "cree_le": test.get("cree_le"),
        "modifie_le": test.get("modifie_le") or test.get("cree_le"),
    }
