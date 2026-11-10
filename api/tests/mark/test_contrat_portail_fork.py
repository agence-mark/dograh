"""[.mark] Builder partie 3, sous-lot 17b : le contrat entre le portail et le fork, figé et comparé à chaque exécution (CI comprise).

Le portail génère son client d'API depuis la spec OpenAPI du fork. Les routes qu'il lit ou écrit avec la clé d'un client sont listées ici
(``ROUTES_DU_PORTAIL``) ; leur FORME (paramètres, corps demandé, réponse, permission et ouverture à une clé) est rangée dans
``contrat_portail_fork.json``. Un test échoue si une de ces formes change : un champ qui disparaît, un type qui bouge, une route qui
passe sous une autre permission ou se ferme à la clé.

| Test | Ce qu'il prouve |
|---|---|
| route présente | chaque route du portail existe dans la spec |
| forme figée | la forme de chaque route est celle du fichier ; sinon la différence est dite champ par champ |
| ouverte à la clé | chaque route du portail est permise à une clé d'API (liste fermée) : une fermeture par erreur casse le portail |
| la comparaison mord | une forme modifiée (champ retiré, type changé) est vue ; l'ajout d'un champ optionnel aussi (le portail régénère son client) |

Changement voulu : prévenir le portail, puis ``FIGER_CONTRAT_PORTAIL=1 pytest tests/mark/test_contrat_portail_fork.py`` réécrit le fichier
(à relire dans le diff avant de le commiter).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from api.app import app
from api.services.equipe_mark import registre_routes as registre
from api.services.equipe_mark.acces import ROUTES_ECRITURE_FERMEES_AUX_CLES, ROUTES_FERMEES_AUX_CLES
from api.services.equipe_mark.permissions import PERMISSIONS_DE_CLE

FICHIER = Path(__file__).with_name("contrat_portail_fork.json")
P = "/api/v1"

# (méthode, chemin) des routes que le portail utilise avec la clé du client (lot 8 du portail, § 3).
ROUTES_DU_PORTAIL: list[tuple[str, str]] = [
    # messages, signalements, entrée de .mark
    ("GET", f"{P}/organizations/relation/fils"),
    ("GET", f"{P}/organizations/relation/fils/{{fil_id}}"),
    ("POST", f"{P}/organizations/relation/fils"),
    ("POST", f"{P}/organizations/relation/fils/{{fil_id}}/messages"),
    ("POST", f"{P}/organizations/relation/entree/verifier"),
    ("POST", f"{P}/organizations/relation/entree/{{entree_id}}/fin"),
    # agents, widgets, sites
    ("GET", f"{P}/organizations/agents-servis"),
    ("GET", f"{P}/organizations/sites"),
    ("GET", f"{P}/organizations/agents-site/{{workflow_id}}/apparence"),
    ("PUT", f"{P}/organizations/agents-site/{{workflow_id}}/apparence"),
    ("PUT", f"{P}/organizations/agents-site/{{workflow_id}}/emplacement"),
    # établissements, équipe, lexique
    ("GET", f"{P}/organizations/etablissements"),
    ("PATCH", f"{P}/organizations/etablissements/{{identifiant}}"),
    ("POST", f"{P}/organizations/etablissements/{{identifiant}}/etat"),
    ("POST", f"{P}/organizations/etablissements/{{identifiant}}/appliquer-a-tous"),
    ("GET", f"{P}/organizations/equipe"),
    ("PUT", f"{P}/organizations/equipe"),
    ("PATCH", f"{P}/organizations/equipe/personnes/{{cle}}"),
    ("GET", f"{P}/organizations/lexique"),
    ("PUT", f"{P}/organizations/lexique"),
    # connaissances
    ("GET", f"{P}/knowledge-base/documents"),
    ("POST", f"{P}/knowledge-base/upload-url"),
    ("POST", f"{P}/knowledge-base/process-document"),  # clôture, lot A (D9) : « Ajouter un document » rouvert
    ("GET", f"{P}/knowledge-base/documents/{{document_uuid}}/content"),  # tranché par Evan le 09/11 : lire et modifier le texte d'un document
    ("PUT", f"{P}/knowledge-base/documents/{{document_uuid}}/content"),
    ("POST", f"{P}/knowledge-base/documents/{{document_uuid}}/remplacer"),
    ("DELETE", f"{P}/knowledge-base/documents/{{document_uuid}}"),
    ("GET", f"{P}/knowledge-base/documents/{{document_uuid}}/utilisation"),
    # logiciels
    ("GET", f"{P}/connecteurs/connexions"),
    ("GET", f"{P}/connecteurs/propositions"),
    ("POST", f"{P}/connecteurs/lien"),
    ("POST", f"{P}/connecteurs/propositions/{{identifiant}}/lien"),
    ("DELETE", f"{P}/connecteurs/connexions/{{integration}}"),
    ("GET", f"{P}/connecteurs/historique"),
    # base du client, actions d'après-appel
    ("POST", f"{P}/organizations/base-client/connexion-portail"),
    ("POST", f"{P}/organizations/apres-appel/actions/{{action_id}}/relancer"),
    # contacts (SA-17c) : fusionner, « ce n'est pas la même personne », « ne pas mémoriser »
    ("POST", f"{P}/organizations/contacts/{{contact_id}}/fusionner"),
    ("POST", f"{P}/organizations/contacts/{{contact_id}}/separer"),
    ("PUT", f"{P}/organizations/contacts/{{contact_id}}/memoriser"),
]


def _resoudre(spec: dict, schema, vus: tuple = ()):
    """Un schéma OpenAPI réduit à ce qui compte pour un client généré : type, format, énumération, obligatoire, enfants. Sans nom de classe."""
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        nom = schema["$ref"].rsplit("/", 1)[-1]
        if nom in vus:
            return {"recursif": True}
        return _resoudre(spec, spec["components"]["schemas"][nom], vus + (nom,))
    sortie: dict = {}
    for cle in ("type", "format", "enum", "const", "nullable"):
        if cle in schema:
            sortie[cle] = schema[cle]
    for cle in ("anyOf", "oneOf", "allOf"):
        if cle in schema:
            sortie[cle] = [_resoudre(spec, s, vus) for s in schema[cle]]
    if "items" in schema:
        sortie["items"] = _resoudre(spec, schema["items"], vus)
    if "properties" in schema:
        sortie["required"] = sorted(schema.get("required", []))
        sortie["properties"] = {n: _resoudre(spec, s, vus) for n, s in sorted(schema["properties"].items())}
    if isinstance(schema.get("additionalProperties"), dict):
        sortie["additionalProperties"] = _resoudre(spec, schema["additionalProperties"], vus)
    return sortie


def _contenu(spec: dict, bloc: dict | None):
    if not bloc:
        return None
    contenus = bloc.get("content") or {}
    if not contenus:
        return None
    return {type_: _resoudre(spec, c.get("schema", {})) for type_, c in sorted(contenus.items())}


def _decision_pour_une_cle(methode: str, chemin: str) -> dict:
    """Ce que le registre décide pour ce chemin, et si une clé d'API y entre (liste fermée comprise)."""
    modele = chemin.removeprefix(P)
    trouvee = registre.decision_de(methode, modele)
    assert trouvee is not None, f"{methode} {chemin} n'a pas de décision de permission"
    decision = trouvee[0]
    de_cle = None
    if isinstance(decision, registre.Permission):
        de_cle = decision.pour_cle or decision.cle  # RV (point 3) : la permission que la CLÉ doit porter
        nom, permise = decision.cle, de_cle in PERMISSIONS_DE_CLE
    elif isinstance(decision, registre.Exemption):
        nom, permise = "exemption", True
    else:
        nom, permise = "membre", True
    if any(modele == r or modele.startswith(r + "/") for r in ROUTES_FERMEES_AUX_CLES):
        permise = False
    if methode in registre.ECRITURE and any(modele == r or modele.startswith(r + "/") for r in ROUTES_ECRITURE_FERMEES_AUX_CLES):
        permise = False
    return {"permission": nom, "permission_de_cle": de_cle, "ouverte_a_la_cle": permise}


def forme_de(spec: dict, methode: str, chemin: str) -> dict:
    operation = spec["paths"][chemin][methode.lower()]
    parametres = [
        {"nom": p["name"], "dans": p["in"], "obligatoire": bool(p.get("required")), "schema": _resoudre(spec, p.get("schema", {}))}
        for p in operation.get("parameters", [])
    ]
    reponses = {
        code: _contenu(spec, r)
        for code, r in sorted(operation.get("responses", {}).items())
        if code.startswith("2")
    }
    return {
        "parametres": sorted(parametres, key=lambda p: (p["dans"], p["nom"])),
        "corps": _contenu(spec, operation.get("requestBody")),
        "reponses": reponses,
        **_decision_pour_une_cle(methode, chemin),
    }


def contrat_actuel(spec: dict | None = None) -> dict:
    spec = spec or app.openapi()
    return {f"{m} {c}": forme_de(spec, m, c) for m, c in ROUTES_DU_PORTAIL}


def differences(attendu, actuel, chemin: str = "") -> list[str]:
    """Les écarts entre deux formes, un par ligne, avec le chemin du champ touché."""
    if isinstance(attendu, dict) and isinstance(actuel, dict):
        sorties = []
        for cle in sorted(set(attendu) | set(actuel)):
            if cle not in actuel:
                sorties.append(f"{chemin}/{cle} : retiré")
            elif cle not in attendu:
                sorties.append(f"{chemin}/{cle} : ajouté")
            else:
                sorties += differences(attendu[cle], actuel[cle], f"{chemin}/{cle}")
        return sorties
    if attendu != actuel:
        return [f"{chemin} : {attendu!r} devient {actuel!r}"]
    return []


def test_chaque_route_du_portail_existe_dans_la_spec():
    spec = app.openapi()
    manquantes = [f"{m} {c}" for m, c in ROUTES_DU_PORTAIL if m.lower() not in spec["paths"].get(c, {})]
    assert not manquantes, f"Routes du portail absentes de la spec : {manquantes}"


def test_chaque_route_du_portail_est_permise_a_une_cle_d_api():
    fermees = [f"{m} {c}" for m, c in ROUTES_DU_PORTAIL if not _decision_pour_une_cle(m, c)["ouverte_a_la_cle"]]
    assert not fermees, f"Routes du portail fermées à une clé (le portail ne marcherait plus) : {fermees}"


def test_la_forme_des_routes_du_portail_est_celle_du_contrat_fige():
    actuel = contrat_actuel()
    if os.environ.get("FIGER_CONTRAT_PORTAIL") == "1":
        FICHIER.write_text(json.dumps(actuel, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    attendu = json.loads(FICHIER.read_text(encoding="utf-8"))
    ecarts = differences(attendu, actuel)
    assert not ecarts, (
        "Le contrat avec le portail a changé (prévenir le portail, puis relancer avec FIGER_CONTRAT_PORTAIL=1) :\n" + "\n".join(ecarts[:40])
    )


def test_la_comparaison_voit_un_champ_retire_un_type_change_et_un_champ_ajoute():
    spec = app.openapi()
    base = contrat_actuel(spec)
    cle = f"POST {P}/organizations/relation/fils"
    corps = base[cle]["corps"]["application/json"]["properties"]

    retire = json.loads(json.dumps(base))
    del retire[cle]["corps"]["application/json"]["properties"]["sujet"]
    assert any("sujet" in e and "ajouté" in e for e in differences(retire, base))

    change = json.loads(json.dumps(base))
    change[cle]["corps"]["application/json"]["properties"]["sujet"]["type"] = "integer"
    assert any("sujet" in e and "integer" in e for e in differences(change, base))

    ajoute = json.loads(json.dumps(base))
    ajoute[cle]["corps"]["application/json"]["properties"]["nouveau_champ"] = {"type": "string"}
    assert any("nouveau_champ" in e and "retiré" in e for e in differences(ajoute, base))
    assert "sujet" in corps and "run_id" in corps  # le signalement lié à un appel est dans le contrat


def test_le_fichier_du_widget_est_servi_pour_l_apercu_du_portail():
    """Le script du widget se charge depuis la page d'un autre site (l'aperçu du portail) : le fichier existe, est public (hors connexion) et
    lisible de partout (CORS ouvert). L'adresse à charger est donnée par ``script`` de ``GET /organizations/sites``."""
    ui = Path(__file__).resolve().parents[3] / "ui"
    fichier = ui / "public" / "embed" / "dograh-widget.js"
    assert fichier.is_file() and fichier.stat().st_size > 1000
    config = (ui / "next.config.ts").read_text(encoding="utf-8")
    assert '"/embed/:path*"' in config and "Access-Control-Allow-Origin" in config
    assert "'/embed'" in (ui / "src" / "middleware.ts").read_text(encoding="utf-8")
    from api.routes import agents_site

    site = type("S", (), {"cle": "cle-de-test"})()
    assert "/embed/dograh-widget.js?site=cle-de-test" in agents_site._script(site)


@pytest.mark.parametrize("methode, chemin", ROUTES_DU_PORTAIL, ids=[f"{m} {c.removeprefix(P)}" for m, c in ROUTES_DU_PORTAIL])
def test_chaque_route_du_portail_a_une_reponse_decrite(methode, chemin):
    forme = contrat_actuel()[f"{methode} {chemin}"]
    assert forme["reponses"], "une route lue par le portail décrit sa réponse (sinon le client généré ne la type pas)"
