"""[.mark] Revue 4 du chantier cloture-code-avant-migration : un objet de l'agent ne prend pas le nom d'une
variable que le code pose pour l'appel, ni celui d'une phrase du catalogue de l'organisation.

Pourquoi : l'objet se pose dans le contexte sous son nom (``{{nom}}``) AVANT l'établissement, la date, l'état
d'ouverture, l'adresse... qui gardent alors la valeur de l'objet : la variable du code est masquée sans un mot.

| Test | Ce qu'il prouve |
|---|---|
| liste complète | chaque injection appelée par `run_pipeline.py` est dans la liste unique ; une injection nouvelle fait échouer le test |
| liste exacte | ce que les injections écrivent vraiment (date, heure, état d'ouverture, adresse, lexique) est dans la liste |
| routes | un nom posé par le code, une clé du moteur, une phrase du catalogue : 409 avec un message clair, rien d'écrit ; en création comme en réécriture ; un objet déjà enregistré garde son nom |
"""

from __future__ import annotations

import ast
from pathlib import Path

from api.schemas.fiche_agent import NOMS_RESERVES
from api.schemas.objets_agent import ObjetEnvoye
from api.services.objets_agent.noms_poses_par_le_code import (
    INJECTIONS_DES_DONNEES_DU_CLIENT,
    INJECTIONS_DU_CODE,
    VARIABLES_POSEES_PAR_LE_CODE,
)
from api.tests.mark.test_agents_servis import (  # noqa: F401  (fixtures)
    _client,
    base_v4,
    smtp,
)
from api.tests.mark.test_base_client import _RedisFactice, base_essai  # noqa: F401

RUN_PIPELINE = Path(__file__).resolve().parents[2] / "services" / "pipecat" / "run_pipeline.py"


def _injections_appelees() -> set[str]:
    arbre = ast.parse(RUN_PIPELINE.read_text(encoding="utf-8"))
    appelees: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            f = noeud.func
            nom = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if nom.startswith("injecter_"):
                appelees.add(nom)
    return appelees


def test_toute_injection_de_run_pipeline_est_dans_la_liste_unique():
    appelees = _injections_appelees()
    assert appelees, "le test ne lit plus rien dans run_pipeline.py"
    connues = set(INJECTIONS_DU_CODE) | set(INJECTIONS_DES_DONNEES_DU_CLIENT)
    manquantes = sorted(appelees - connues)
    assert not manquantes, (
        f"injection(s) de run_pipeline.py absente(s) de noms_poses_par_le_code.py : {manquantes}. "
        "Ajouter les clés qu'elles écrivent, sinon un objet pourra les masquer."
    )
    # Et l'inverse : rien de périmé dans la liste.
    assert not sorted(set(INJECTIONS_DU_CODE) - appelees), "une injection de la liste n'est plus appelée"


def test_ce_que_les_injections_ecrivent_vraiment_est_dans_la_liste():
    from api.schemas.organization_preferences import AdresseEtablissement
    from api.services.communes.adresse import injecter_adresse_etablissement
    from api.services.lexique.ecoute import injecter_lexique_propose
    from api.services.pipecat.etat_ouverture import injecter_date_heure_appel, injecter_etat_ouverture

    horaires = "lundi : 09:00-12:00\n" + "".join(f"{j} : fermé\n" for j in ("mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"))
    ecrites = {
        "injecter_date_heure_appel": set(injecter_date_heure_appel({})),
        "injecter_etat_ouverture": set(injecter_etat_ouverture({}, {"horaires_ouverture": horaires})),
        "injecter_lexique_propose": set(injecter_lexique_propose({}, ["Edilkamin"])),
        "injecter_adresse_etablissement": set(
            injecter_adresse_etablissement({}, AdresseEtablissement(voie="1 rue de la Gare", code_postal="60740", commune="Saint-Maximin", code_insee="60600"))
        ),
    }
    for injection, cles in ecrites.items():
        assert cles, f"{injection} n'a rien écrit : le test ne prouve rien"
        assert cles <= INJECTIONS_DU_CODE[injection], (injection, cles - INJECTIONS_DU_CODE[injection])
    assert NOMS_RESERVES <= VARIABLES_POSEES_PAR_LE_CODE
    assert {"etablissement", "numero_transfert", "equipe", "etat_ouverture", "date_appel", "adresse_etablissement"} <= VARIABLES_POSEES_PAR_LE_CODE


def _objet(nom):
    return ObjetEnvoye(nom=nom, libelle=nom.capitalize(), forme="valeur", type="texte", valeur="x").model_dump(mode="json")


async def test_les_routes_refusent_un_nom_pose_par_le_code_ou_pris_par_une_phrase(base_v4, smtp, db_session, async_session):
    from api.tests.mark.test_ecritures_par_element import RACINE, _garnir, _installer, _rediriger

    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes)  # le catalogue porte « mot_du_lieu » et « mot_commun »
            for nom in ("etablissement", "numero_transfert", "date_appel", "etat_ouverture", "call_status", "mot_commun", "mot_du_lieu"):
                r = await client.post(f"{RACINE}/objets", json=_objet(nom), headers=entetes)
                assert r.status_code == 409, (nom, r.status_code, r.text)
                assert nom in r.json()["detail"] and "Choose another name" in r.json()["detail"]
            assert (await client.get(f"{RACINE}/objets", headers=entetes)).json()["objets"] == [], "rien d'écrit"

            # Un nom libre passe.
            r = await client.post(f"{RACINE}/objets", json=_objet("frais"), headers=entetes)
            assert r.status_code == 200, r.text
            cree = r.json()
            # Renommer vers un nom pris : 409, l'objet garde son nom.
            envoi = {k: cree[k] for k in ObjetEnvoye.model_fields}
            r = await client.put(f"{RACINE}/objets/{cree['id']}", json={**envoi, "nom": "adresse_etablissement"}, headers=entetes)
            assert r.status_code == 409
            assert (await client.get(f"{RACINE}/objets", headers=entetes)).json()["objets"][0]["nom"] == "frais"

            # Une phrase ajoutée APRÈS l'objet, du même nom : l'objet reste modifiable (seul un nom nouveau est jugé).
            r = await client.put(
                f"{RACINE}/phrases",
                json={"phrases": [{"variable": "frais", "contenu": "Les frais", "niveau": "organisation"}]},
                headers=entetes,
            )
            assert r.status_code == 200, r.text
            r = await client.put(f"{RACINE}/objets/{cree['id']}", json={**envoi, "valeur": "40"}, headers=entetes)
            assert r.status_code == 200, r.text
