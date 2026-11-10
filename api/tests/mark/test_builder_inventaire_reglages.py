"""[.mark] Partie 3, N2 (sous-lot 1) : l'inventaire scripté « chaque réglage a son écran et son accès du builder » (05 § 4).

| Test | Ce qu'il prouve |
|---|---|
| agent | chaque clé du schéma des réglages d'un agent est écrivable par le builder (``reglages_regler``), ou figure dans ``EXEMPTES_AGENT`` avec sa raison ; l'écran de chacune est prouvé par ``ui/.../inventaire-agent.test.ts`` |
| organisation | chaque route d'ÉCRITURE de ``/organizations/*`` a son action du builder, ou une exemption écrite avec sa raison ; une route neuve sans décision fait échouer |
| outils | chaque réglage d'un outil existant se change par ``outil_modifier`` (la définition complète, un seul chemin) |
| sous-réglages | « après l'appel » et « panne » (organisation) ne changent QUE le sous-réglage envoyé ; une référence masquée ne remplace rien |
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute

from api.app import app
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.builder import reglages_agent
from api.services.builder.actions import registre
from api.services.builder.actions.familles_actions import FAMILLE_DES_ACTIONS, permission_de
from api.services.builder.actions.outil_modifier import fusionner_la_config
from api.services.builder.actions.registre import Contexte
from api.services.builder.actions.reglages_organisation import BLOCS, fusionner
from api.services.builder.reglages_agent import CLE_MASQUEE
from api.tests.mark.builder_commun import utilisateur
from api.tests.mark.test_builder_entreprise import RESTE_A_FAIRE, ROUTE_VERS_ACTION

PREFIXE = "/api/v1"

# --- agent ---------------------------------------------------------------------------------------------------------------------------------

# Une clé du schéma de l'agent que le builder n'écrit pas, avec la raison. Aucune aujourd'hui : un champ qui sent le secret serait ici.
EXEMPTES_AGENT: dict[str, str] = {}


def test_chaque_cle_du_schema_de_l_agent_est_ecrivable_par_le_builder_ou_exemptee():
    cles = set(WorkflowConfigurationDefaults.model_fields)
    sans_acces = sorted(cles - reglages_agent.cles_reglables() - set(EXEMPTES_AGENT))
    assert not sans_acces, f"Réglages de l'agent sans accès du builder ni exemption écrite : {sans_acces}"
    assert not set(EXEMPTES_AGENT) - cles, "Exemption d'une clé qui n'existe plus"
    assert all(EXEMPTES_AGENT.values())


# --- organisation --------------------------------------------------------------------------------------------------------------------------

ORGANISATION_VERS_ACTION = {
    ("PUT", "/organizations/panne"): "panne_organisation_regler",
    ("PUT", "/organizations/apres-appel"): "apres_appel_organisation_regler",
    ("PUT", "/organizations/verification-appelant"): "verification_appelant_regler",
    ("PUT", "/organizations/planificateur-moteur"): "planificateur_moteur_regler",
    ("PUT", "/organizations/planificateur"): "planificateur_regler",
    ("PATCH", "/organizations/planificateur"): "planificateur_regler",
    ("PUT", "/organizations/fenetre-du-run"): "fenetre_du_run_regler",
    ("PUT", "/organizations/conservation-appels"): "conservation_appels_regler",
}

# Écriture de l'organisation SANS action du builder, avec la raison (écrite, jamais « on verra »). « Reste » = construit par un lot suivant.
EXEMPTEES = {
    ("POST", "/organizations"): "créer un client : geste de l'équipe .mark (« Nouveau client », permission clients.creer), jamais le chat d'un client",
    ("PUT", "/organizations/selected"): "choisir l'organisation de la session : geste de la personne, pas un réglage",
    ("PUT", "/organizations/preferences"): "adresses de notification de la personne et de l'organisation : reste à construire (adresses de mail, donnée personnelle : choix d'Evan)",
    ("POST", "/organizations/apres-appel/actions/{action_id}/relancer"): "relance une action de la chaîne après l'appel (envoie un mail, un SMS ou un webhook) : effet réel, geste de la personne",
    ("POST", "/organizations/apres-appel/essai-mail"): "envoie un mail d'essai à une adresse : effet réel, geste de la personne",
    ("POST", "/organizations/apres-appel/nuit"): "lance la tâche de nuit d'une base : effet réel, geste de la personne",
    ("POST", "/organizations/apres-appel/recapitulatif"): "envoie le récapitulatif maintenant : effet réel, geste de la personne",
    ("PUT", "/organizations/apres-appel/installation"): "réglages de l'INSTALLATION .mark (mail et adresses de l'équipe, superutilisateur) : jamais le builder d'un client",
    ("POST", "/organizations/panne/adresse-de-secours"): "vérifie l'adresse de secours en l'appelant (effet réel, Twilio) : geste de la personne",
    ("POST", "/organizations/panne/rattrapage"): "rattrape les appels perdus (appels réels) : geste de la personne",
    ("PUT", "/organizations/base-client"): "rattacher une base client : outil de l'équipe (atelier.regler), identifiants de connexion saisis par une personne",
    ("PUT", "/organizations/base-client/conservation"): "outil de l'équipe (atelier.regler) : reste à construire avec la base client",
    ("POST", "/organizations/base-client/connexion-portail"): "connexion du portail (clé d'API), jamais le builder",
    ("POST", "/organizations/base-client/creer"): "créer une base client : dépense et outil de l'équipe",
    ("POST", "/organizations/base-client/mettre-a-niveau"): "migration d'une base client : outil de l'équipe, irréversible",
    ("POST", "/organizations/base-client/resynchroniser"): "resynchronise une base : outil de l'équipe",
    ("POST", "/organizations/call-events/test"): "envoie un événement d'essai à une adresse : effet réel, geste de la personne",
    ("POST", "/organizations/contacts/{contact_id}/fusionner"): "contacts du portail (données de personnes) : geste de la personne",
    ("POST", "/organizations/contacts/{contact_id}/separer"): "contacts du portail (données de personnes) : geste de la personne",
    ("PUT", "/organizations/contacts/{contact_id}/memoriser"): "contacts du portail (données de personnes) : geste de la personne",
    ("PUT", "/organizations/equipe"): "l'équipe du client (personnes de la fiche) : reste à construire (données de personnes, choix d'Evan)",
    ("PATCH", "/organizations/equipe/personnes/{cle}"): "une personne de l'équipe du client : reste à construire (données de personnes, choix d'Evan)",
    ("PUT", "/organizations/agents-servis/rattachement"): "rattacher un agent servi à des fiches : reste à construire (lot suivant)",
    ("PUT", "/organizations/agents-site/{workflow_id}/affichage"): "réglages du site d'un agent : reste à construire (lot suivant)",
    ("PUT", "/organizations/agents-site/{workflow_id}/apparence"): "réglages du site d'un agent : reste à construire (lot suivant)",
    ("PUT", "/organizations/agents-site/{workflow_id}/canal"): "réglages du site d'un agent : reste à construire (lot suivant)",
    ("PUT", "/organizations/agents-site/{workflow_id}/emplacement"): "réglages du site d'un agent : reste à construire (lot suivant)",
    ("POST", "/organizations/agents-site/{workflow_id}/lire-site"): "lit un site public (appel réseau) : geste de la personne",
    ("PUT", "/organizations/agents-site/{workflow_id}/reglages"): "plafonds de coût et domaines d'un site (atelier.regler) : outil de l'équipe, reste à construire",
    ("POST", "/organizations/langfuse-credentials"): "clés d'un fournisseur : saisies par une personne (garde des secrets)",
    ("DELETE", "/organizations/langfuse-credentials"): "clés d'un fournisseur : saisies par une personne (garde des secrets)",
    ("PUT", "/organizations/model-configurations/v2"): "modèles et clés des fournisseurs : saisis par une personne (garde des secrets, décision d'Evan)",
    ("POST", "/organizations/model-configurations/v2/migrate"): "migration des modèles et clés : geste de la personne",
    ("PUT", "/organizations/model-configurations/v2/mode"): "mode des clés des fournisseurs : geste de la personne",
    ("POST", "/organizations/modeles-de-reglages"): "gestion du stock des modèles de réglages (atelier.regler) : outil de l'équipe ; appliquer un modèle a son action",
    ("POST", "/organizations/modeles-de-reglages/import"): "gestion du stock des modèles de réglages (atelier.regler) : outil de l'équipe",
    ("PATCH", "/organizations/modeles-de-reglages/{modele_id}"): "gestion du stock des modèles de réglages (atelier.regler) : outil de l'équipe",
    ("DELETE", "/organizations/modeles-de-reglages/{modele_id}"): "gestion du stock des modèles de réglages (atelier.regler) : outil de l'équipe",
    ("POST", "/organizations/modeles-de-reglages/{modele_id}/appliquer"): "rejoué par l'action modeles_reglages_appliquer (même service)",
    ("POST", "/organizations/objets"): "objets d'un agent : rejoués par objets_agent_ecrire",
    ("PUT", "/organizations/objets/reglages"): "objets d'un agent : rejoués par objets_agent_ecrire",
    ("PUT", "/organizations/objets/{objet_id}"): "objets d'un agent : rejoués par objets_agent_ecrire",
    ("DELETE", "/organizations/objets/{objet_id}"): "objets d'un agent : rejoués par objets_agent_ecrire",
    ("POST", "/organizations/relation/entree/verifier"): "relation client du portail : geste de la personne (entrée d'un client)",
    ("POST", "/organizations/relation/entree/{entree_id}/fin"): "relation client du portail : geste de la personne",
    ("POST", "/organizations/relation/fils"): "relation client du portail : fils de discussion entre personnes",
    ("POST", "/organizations/relation/fils/{fil_id}/messages"): "relation client du portail : messages entre personnes",
    ("POST", "/organizations/sites"): "sites d'un client (clés de site) : reste à construire ; la clé n'est jamais rendue au builder",
    ("PUT", "/organizations/sites/{site_id}"): "sites d'un client : reste à construire",
    ("POST", "/organizations/sites/{site_id}/regenerer-cle"): "régénère une clé de site (secret) : geste de la personne",
    ("POST", "/organizations/usage/mps-credits/purchase-url"): "achat de crédits : dépense, jamais le builder",
}
# Les routes de l'organisation traitées dans le test d'inventaire de l'entreprise (N1b) : établissements, phrases, annonce, vocabulaire,
# listes, téléphonie : leurs actions ou leurs exemptions y sont écrites.
_TRAITEES_AILLEURS = (
    "/organizations/etablissements", "/organizations/phrases", "/organizations/annonce-ouverture", "/organizations/lexique",
    "/organizations/listes-valeurs", "/organizations/telephony-configs",
)
EXEMPTEES_TELEPHONIE = "identifiants des comptes de téléphonie saisis par une personne (garde des secrets) : lecture par le nom seulement (telephonie_lister)"


def _ecritures_de_l_organisation() -> set[tuple[str, str]]:
    trouvees = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        chemin = route.path[len(PREFIXE):] if route.path.startswith(PREFIXE) else route.path
        if not chemin.startswith("/organizations") or chemin.startswith(_TRAITEES_AILLEURS):
            continue
        trouvees |= {(m, chemin) for m in (route.methods or []) if m in {"POST", "PUT", "PATCH", "DELETE"}}
    return trouvees


def test_chaque_route_d_ecriture_de_l_organisation_a_son_action_ou_une_exemption_ecrite():
    ecritures = _ecritures_de_l_organisation()
    decidees = set(ORGANISATION_VERS_ACTION) | set(EXEMPTEES) | set(ROUTE_VERS_ACTION) | set(RESTE_A_FAIRE)
    sans_decision = sorted(ecritures - decidees)
    assert not sans_decision, f"Écritures de l'organisation sans action du builder ni exemption écrite : {sans_decision}"
    assert not [r for r in list(ORGANISATION_VERS_ACTION) + list(EXEMPTEES) if r not in ecritures], "Route citée qui n'existe plus"
    assert all(EXEMPTEES.values())
    assert not (set(ORGANISATION_VERS_ACTION) & set(EXEMPTEES)), "Une route a une action ET une exemption"
    manquantes = sorted(a for a in ORGANISATION_VERS_ACTION.values() if a not in registre.REGISTRE)
    assert not manquantes, manquantes


def test_chaque_bloc_d_organisation_a_sa_lecture_son_ecriture_sa_famille_et_la_permission_de_la_route():
    for bloc in BLOCS:
        lire, regler = f"{bloc.nom}_lire", f"{bloc.nom}_regler"
        assert FAMILLE_DES_ACTIONS[lire] == "lecture" and FAMILLE_DES_ACTIONS[regler] == "entreprise", bloc.nom
        assert registre.REGISTRE[lire].ecriture is False and registre.REGISTRE[regler].ecriture is True
        assert registre.REGISTRE[regler].mcp is False and registre.REGISTRE[regler].extras.get("avant") and registre.REGISTRE[regler].extras.get("defaire")
        assert permission_de(regler, "entreprise") == (bloc.permission or "agents.modifier")
    assert permission_de("fenetre_du_run_regler", "entreprise") == "atelier.regler"
    assert permission_de("conservation_appels_regler", "entreprise") == "atelier.regler"


# --- outils --------------------------------------------------------------------------------------------------------------------------------


def test_outil_modifier_est_une_action_de_reglages_avec_sa_permission():
    assert FAMILLE_DES_ACTIONS["outil_modifier"] == "reglages"
    assert permission_de("outil_modifier", "reglages") == "agents.modifier"
    assert registre.REGISTRE["outil_modifier"].extras.get("avant") and registre.REGISTRE["outil_modifier"].extras.get("defaire")


def test_la_config_d_un_outil_se_fusionne_sans_effacer_le_reste():
    en_place = {"method": "POST", "url": "https://x.test", "resolver": {"url": "https://r.test", "timeout_ms": 3000}, "customMessage": "Je regarde"}
    suite = fusionner_la_config(en_place, {"url": "https://y.test", "resolver": {"timeout_ms": 5000}, "customMessage": None, "body_template": {"a": "{{b}}"}})
    assert suite == {"method": "POST", "url": "https://y.test", "resolver": {"url": "https://r.test", "timeout_ms": 5000}, "body_template": {"a": "{{b}}"}}
    assert en_place["url"] == "https://x.test"  # l'entrée n'est pas modifiée


class _Outil(SimpleNamespace):
    pass


async def test_outil_modifier_envoie_la_definition_complete_et_range_l_etat_d_avant(monde, monkeypatch):
    from api.db import db_client

    existant = _Outil(
        tool_uuid="u1", name="Reserver", description="Réserve.",
        definition={"schema_version": 1, "type": "http_api", "config": {"method": "POST", "url": "https://a.test/rdv", "timeout_ms": 5000, "customMessage": "Je regarde"}},
    )

    async def lire(uuid, organization_id, include_archived=False):
        return existant

    envoyes = []

    async def update_tool(uuid, corps, user):
        envoyes.append((uuid, corps))
        return SimpleNamespace(model_dump=lambda mode="json": {"tool_uuid": uuid, "name": corps.name})

    monkeypatch.setattr(db_client, "get_tool_by_uuid", lire)
    monkeypatch.setattr("api.routes.tool.update_tool", update_tool)
    contexte = Contexte(user=utilisateur(1), conversation={"mode": "tout", "messages": []})
    resultat = await registre.executer("outil_modifier", {"outil": "u1", "reglages": {"body_format": "form", "preset_parameters": [{"name": "site", "type": "string", "value_template": "{{initial_context.site}}", "required": True}], "customMessage": None}}, contexte)
    assert resultat["ok"] is True, resultat
    (uuid, corps), = envoyes
    config = corps.definition.config.model_dump() if hasattr(corps.definition.config, "model_dump") else corps.definition.config
    assert uuid == "u1" and corps.name == "Reserver"
    assert config["url"] == "https://a.test/rdv" and config["timeout_ms"] == 5000 and config["body_format"] == "form"
    assert config["preset_parameters"][0]["name"] == "site" and not config.get("customMessage")
    assert contexte.journal["annulable"] is True


async def test_outil_modifier_refuse_sans_rien_a_changer_et_un_outil_inconnu(monde, monkeypatch):
    from api.db import db_client

    async def rien(uuid, organization_id, include_archived=False):
        return None

    monkeypatch.setattr(db_client, "get_tool_by_uuid", rien)
    contexte = Contexte(user=utilisateur(1), conversation={"mode": "tout", "messages": []})
    assert (await registre.executer("outil_modifier", {"outil": "u1"}, contexte))["code"] == "rien"
    assert (await registre.executer("outil_modifier", {"outil": "u1", "nom": "x"}, contexte))["code"] == "introuvable"


# --- sous-réglages -------------------------------------------------------------------------------------------------------------------------


def test_la_fusion_ne_change_que_le_sous_reglage_envoye():
    en_place = {"synthese": {"modele": "m1", "consigne": "Résume."}, "smtp": {"hote": "smtp.test", "port": 587, "mot_de_passe": "mark-cle:3"}, "recapitulatif": {"actif": False, "heures": [8]}}
    suite = fusionner(en_place, {"synthese": {"consigne": "Résume en deux phrases."}, "recapitulatif": {"heures": [8, 17]}, "smtp": {"mot_de_passe": CLE_MASQUEE}})
    assert suite["synthese"] == {"modele": "m1", "consigne": "Résume en deux phrases."}
    assert suite["smtp"] == en_place["smtp"]  # la référence masquée ne remplace rien
    assert suite["recapitulatif"] == {"actif": False, "heures": [8, 17]}
    assert en_place["synthese"]["consigne"] == "Résume."


@pytest.mark.parametrize("nom", ["panne_organisation", "apres_appel_organisation"])
async def test_regler_la_panne_ou_l_apres_appel_n_ecrit_que_le_sous_reglage(nom, monde, monkeypatch):
    bloc = next(b for b in BLOCS if b.nom == nom)
    modele = bloc.modele()
    en_place = modele.model_validate({}) if nom == "apres_appel_organisation" else modele.model_validate({"url_secours": "https://handler.twilio.test/bin-1"})
    ecrits = []

    async def lire(contexte):
        return ecrits[-1] if ecrits else en_place

    async def ecrire(contexte, reglages):
        ecrits.append(reglages)
        return reglages

    import api.services.builder.actions.reglages_organisation as ro

    monkeypatch.setitem(ro.ACCES, nom, dataclasses.replace(bloc, lire=lire, ecrire=ecrire))
    contexte = Contexte(user=utilisateur(1), conversation={"mode": "tout", "messages": []})
    envoi = {"valeurs": {"url_secours_promesse": "https://handler.twilio.test/bin-2"}} if nom == "panne_organisation" else {"valeurs": {"synthese": {"consigne": "Résume en une phrase."}}}
    resultat = await registre.executer(f"{nom}_regler", envoi, contexte)
    assert resultat["ok"] is True, resultat
    (ecrit,) = ecrits
    avant, apres = en_place.model_dump(mode="json"), ecrit.model_dump(mode="json")
    changes = {k for k in apres if apres[k] != avant[k]}
    assert changes == ({"url_secours_promesse"} if nom == "panne_organisation" else {"synthese"})
    if nom == "apres_appel_organisation":
        assert apres["synthese"]["modele"] == avant["synthese"]["modele"] and apres["smtp"] == avant["smtp"]
    assert contexte.journal["annulable"] is True


async def test_un_reglage_refuse_par_l_ecran_est_dit_en_une_phrase(monde, monkeypatch):
    bloc = next(b for b in BLOCS if b.nom == "panne_organisation")

    async def lire(contexte):
        return bloc.modele().model_validate({})

    async def ecrire(contexte, reglages):  # pragma: no cover -- ne doit pas être atteint
        raise AssertionError("rien ne s'écrit")

    import api.services.builder.actions.reglages_organisation as ro

    monkeypatch.setitem(ro.ACCES, "panne_organisation", dataclasses.replace(bloc, lire=lire, ecrire=ecrire))
    contexte = Contexte(user=utilisateur(1), conversation={"mode": "tout", "messages": []})
    refus = await registre.executer("panne_organisation_regler", {"valeurs": {"url_secours": "http://pas-https.test/bin"}}, contexte)
    assert refus["ok"] is False and refus["code"] == "refus_ecran" and "Traceback" not in str(refus)


# --- sous-réglage d'un agent, vraie base -----------------------------------------------------------------------------------------------------


async def test_regler_la_panne_ou_l_apres_appel_d_un_agent_ne_change_que_le_sous_reglage(db_session):
    from api.services.builder import brouillon
    from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
    from api.tests.mark.test_builder_c2 import decor
    from api.db import db_client

    org, user, jeton, agent = await decor(db_session, "sub1")
    user.selected_organization_id = org
    contexte = Contexte(user=user, workflow_id=agent.id, conversation={"messages": [], "mode": "tout"})
    ok = await registre.executer("reglages_regler", {"workflow_id": agent.id, "valeurs": {"panne": {"actif": True, "delai_voix_s": 4.0, "sonnerie_s": 20}, "apres_appel": {"actif": True, "synthese": False, "mail": True}}}, contexte)
    assert ok["ok"] is True, ok
    suite = await registre.executer("reglages_regler", {"workflow_id": agent.id, "valeurs": {"panne": {"sonnerie_s": 30}, "apres_appel": {"synthese": True}}}, contexte)
    assert suite["ok"] is True, suite
    workflow = await db_client.get_workflow(agent.id, organization_id=org)
    configurations = await brouillon.configurations_courantes(workflow)
    assert configurations["panne"]["actif"] is True and configurations["panne"]["delai_voix_s"] == 4.0 and configurations["panne"]["sonnerie_s"] == 30
    assert configurations["apres_appel"]["actif"] is True and configurations["apres_appel"]["synthese"] is True and configurations["apres_appel"]["mail"] is True
