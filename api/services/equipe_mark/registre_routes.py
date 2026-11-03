"""[.mark] Le registre des routes : pour CHAQUE route de l'API, la permission qu'elle exige, ou son exemption écrite.

Trois sortes de décision, jamais une quatrième :

* ``Permission("agents.publier")`` : le compte doit porter cette permission (rôle de l'équipe), vérifiée côté serveur ;
* ``MEMBRE`` : tout compte membre de l'organisation de l'adresse (lecture, pas de permission particulière) ;
* ``Exemption("raison")`` : la route ne passe pas par la session d'un compte (santé, connexion, widget public,
  rappel d'un fournisseur, authentification propre) ; la raison est obligatoire.

Les règles sont lues dans l'ordre, la première qui correspond gagne. Une route que AUCUNE règle ne couvre fait
échouer ``test_inventaire_permissions_routes.py`` : on ne livre pas une route sans décision.
Les chemins sont ceux de l'application sans le préfixe ``/api/v1``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LECTURE = frozenset({"GET", "HEAD"})
ECRITURE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
TOUTES = LECTURE | ECRITURE | {"OPTIONS", "WS"}


@dataclass(frozen=True)
class Permission:
    cle: str


@dataclass(frozen=True)
class Exemption:
    raison: str

    def __post_init__(self):
        if len(self.raison.strip()) < 15:
            raise ValueError("Une exemption s'écrit avec sa raison.")


class _Membre:
    def __repr__(self):  # pragma: no cover
        return "MEMBRE"


MEMBRE = _Membre()

Decision = Permission | Exemption | _Membre


@dataclass(frozen=True)
class Regle:
    methodes: frozenset
    motif: re.Pattern
    decision: Decision
    par_defaut: bool = False  # règle de repli d'un domaine (couvre aussi les routes futures du domaine)


def _r(methodes, motif, decision, par_defaut=False) -> Regle:
    return Regle(frozenset(methodes), re.compile(motif), decision, par_defaut)


P = Permission

REGLES: tuple[Regle, ...] = (
    # ------------------------------------------------------------------ sans session de compte
    _r(TOUTES, r"^/health(/.*)?$", Exemption("Santé : sonde de déploiement ; les deux sous-routes exigent le secret d'exploitation.")),
    _r(TOUTES, r"^/metrics$", Exemption("Métriques : protégées par le secret d'exploitation, sans session de compte.")),
    _r(TOUTES, r"^/(openapi\.json|docs(/.*)?|redoc)$", Exemption("Documentation de l'API : description des routes, aucune donnée.")),
    _r(TOUTES, r"^/mcp$", Exemption("Serveur MCP monté à part : authentifie par clé d'API dans son propre module.")),
    _r(TOUTES, r"^/auth/(login|signup)$", Exemption("Connexion et premier compte : par définition sans session.")),
    _r(TOUTES, r"^/auth/invitation(/.*)?$", Exemption("Invitation : le jeton à usage unique fait foi, pas de session.")),
    # Lot S3 : trois routes publiques du widget, chacune avec sa limite écrite (une exemption n'est pas un trou).
    _r({"POST"}, r"^/public/embed/avis/[^/]+$", Exemption("Avis du visiteur du site : jeton de session du widget + domaine d'origine ; une fois par conversation, après sa fin ; écrit dans la base de l'organisation de la session.")),
    _r({"POST"}, r"^/public/embed/rappel/[^/]+$", Exemption("Demande de rappel du visiteur du site : clé publique du site + domaine d'origine ; refusée tant que le plafond du mois n'est pas atteint ; limitée par adresse (non gardée).")),
    _r({"POST"}, r"^/public/embed/evenement$", Exemption("Compteur anonyme du widget (affiché, ouvert) : clé du site ou jeton + domaine d'origine ; un total par jour et par agent, ni cookie ni adresse lue.")),
    _r(TOUTES, r"^/public/.*$", Exemption("Widget public et agents publics : jeton d'intégration ou clé de l'agent.")),
    _r(TOUTES, r"^/ws/public/signaling/.*$", Exemption("Signalisation du widget public : jeton de session du widget.")),
    _r(TOUTES, r"^/agent-stream/.*$", Exemption("Flux d'un fournisseur de téléphonie : authentifié par le fournisseur.")),
    _r(TOUTES, r"^/appel-simule/ws/.*$", Exemption("Entrée audio de l'appelant simulé : jeton à usage unique du run.")),
    _r(TOUTES, r"^/ws/signaling/.*$", Exemption("Signalisation du test navigateur : jeton de session, run créé avant par une route soumise à tests.jouer.")),
    _r(TOUTES, r"^/telephony/ws/.*$", Exemption("Flux audio d'un appel : authentifié par le fournisseur de téléphonie et le jeton du run.")),
    _r(TOUTES, r"^/telephony/(cloudonix|exotel|plivo|telnyx|twilio|vobiz|vonage)/.*$", Exemption("Rappel d'un fournisseur de téléphonie : signature vérifiée par la route.")),
    _r(TOUTES, r"^/telephony/(inbound.*|ncco|plivo-xml|transfer-result/.*|transfer-twiml/.*|twiml|vobiz-xml)$", Exemption("Appel entrant ou rappel d'un fournisseur de téléphonie : signature vérifiée par la route.")),
    _r(TOUTES, r"^/superuser(/.*)?$", Exemption("Réservé aux super-utilisateurs : contrôle propre (get_superuser), pas de rôle d'équipe.")),
    _r({"GET"}, r"^/workflow/templates$", Exemption("Catalogue de modèles d'agents de l'installation : aucune donnée d'organisation.")),
    _r({"GET"}, r"^/user/configurations/defaults$", Exemption("Valeurs par défaut des services : constantes du serveur, aucune donnée d'organisation.")),
    # ------------------------------------------------------------------ téléphonie
    _r({"POST"}, r"^/telephony/initiate-call$", P("tests.jouer")),
    # ------------------------------------------------------------------ builder
    _r(ECRITURE, r"^/builder/bibliotheque/propositions$", P("builder.lancer")),
    _r(ECRITURE, r"^/builder/bibliotheque(/.*)?$", P("atelier.regler")),
    _r(ECRITURE, r"^/builder/(cerveau|prix|options|sources(/[^/]+)?)$", P("atelier.regler")),
    # U11 : le déploiement progressif et les positions de la publication sont des gestes de publication ; la liste vocale écrit le brouillon ; les attaques se jouent comme des tests.
    _r(ECRITURE, r"^/builder/publication/[^/]+/(deploiement/.*|reglages)$", P("agents.publier")),
    _r(ECRITURE, r"^/builder/publication/.*$", P("agents.modifier")),
    _r(ECRITURE, r"^/builder/attaques/.*$", P("tests.jouer")),
    _r(ECRITURE, r"^/builder/tests/.*$", P("tests.jouer")),
    _r(ECRITURE, r"^/builder/.*$", P("builder.lancer"), par_defaut=True),
    _r(LECTURE, r"^/builder/.*$", MEMBRE, par_defaut=True),
    # ------------------------------------------------------------------ appelant simulé
    _r({"PUT"}, r"^/appel-simule/reglages$", P("atelier.regler")),
    _r(ECRITURE, r"^/appel-simule/.*$", P("tests.jouer"), par_defaut=True),
    _r(LECTURE, r"^/appel-simule/runs/.*$", P("conversations.voir")),
    _r(LECTURE, r"^/appel-simule/.*$", MEMBRE, par_defaut=True),
    # ------------------------------------------------------------------ agents (workflow)
    _r({"POST"}, r"^/workflow/\{workflow_id\}/(publish|groupe/publier)$", P("agents.publier")),
    _r({"PUT"}, r"^/workflow/\{workflow_id\}/status$", P("agents.supprimer")),
    _r({"POST"}, r"^/workflow/\{workflow_id\}/(runs|text-chat/sessions.*)$", P("tests.jouer")),
    _r({"POST"}, r"^/workflow/\{workflow_id\}/runs/\{run_id\}/renvoi-en-test$", P("tests.jouer")),
    _r(LECTURE, r"^/workflow/\{workflow_id\}/(runs.*|report)$", P("conversations.voir")),
    _r(LECTURE, r"^/workflow/\{workflow_id\}/text-chat/.*$", P("tests.jouer")),
    # U4 : la préparation d'un agent et l'origine de ses réglages, calculées à la lecture (rien d'écrit).
    _r(LECTURE, r"^/workflow/\{workflow_id\}/(preparation|heritage-reglages)$", MEMBRE),
    _r(ECRITURE, r"^/workflow/.*$", P("agents.modifier"), par_defaut=True),
    _r(LECTURE, r"^/workflow/.*$", MEMBRE, par_defaut=True),
    # U3, E30 : les étiquettes des agents (lire = membre, poser = modifier un agent).
    _r(ECRITURE, r"^/etiquettes(/.*)?$", P("agents.modifier"), par_defaut=True),
    _r(LECTURE, r"^/etiquettes(/.*)?$", MEMBRE, par_defaut=True),
    _r(LECTURE, r"^/agents/.*$", MEMBRE, par_defaut=True),
    _r(ECRITURE, r"^/agents/.*$", P("agents.modifier"), par_defaut=True),
    _r(ECRITURE, r"^/workflow-recordings/.*$", P("agents.modifier"), par_defaut=True),
    _r(LECTURE, r"^/workflow-recordings/.*$", MEMBRE, par_defaut=True),
    _r(ECRITURE, r"^/(tools|knowledge-base|folder|tts-cache)(/.*)?$", P("agents.modifier"), par_defaut=True),
    _r(LECTURE, r"^/(tools|knowledge-base|folder|tts-cache|node-types)(/.*)?$", MEMBRE, par_defaut=True),
    # ------------------------------------------------------------------ campagnes
    _r({"POST"}, r"^/campaign/\{campaign_id\}/(start|resume|redial)$", P("agents.publier")),
    _r(LECTURE, r"^/campaign/\{campaign_id\}/(runs|report|source-download-url)$", P("conversations.voir")),
    _r(ECRITURE, r"^/campaign(/.*)?$", P("agents.modifier"), par_defaut=True),
    _r(LECTURE, r"^/campaign(/.*)?$", MEMBRE, par_defaut=True),
    # ------------------------------------------------------------------ conversations, tri, alertes, stockage
    _r({"PUT"}, r"^/tri/\{run_id\}$", P("agents.modifier")),
    _r(LECTURE, r"^/(tri(/.*)?|alertes)$", P("conversations.voir")),
    # U8 : la boucle (« À améliorer ») et la page Qualité. Lire = voir les conversations ; changer un problème = modifier un agent.
    _r(LECTURE, r"^/(ameliorations(/.*)?|qualite(/.*)?)$", P("conversations.voir")),
    _r(ECRITURE, r"^/ameliorations(/.*)?$", P("agents.modifier")),
    _r({"GET"}, r"^/s3/(signed-url|file-metadata)$", P("conversations.voir")),
    _r({"POST"}, r"^/s3/presigned-upload-url$", P("agents.modifier")),
    # ------------------------------------------------------------------ clés et comptes techniques
    _r(ECRITURE, r"^/(cles|credentials|connecteurs)(/.*)?$", P("cles.gerer")),
    _r(LECTURE, r"^/(cles|credentials|connecteurs)(/.*)?$", MEMBRE, par_defaut=True),
    _r({"PUT"}, r"^/user/onboarding-state$", MEMBRE),
    _r(ECRITURE, r"^/user/(api-keys|service-keys|configurations)(/.*)?$", P("cles.gerer")),
    _r(LECTURE, r"^/user/.*$", MEMBRE, par_defaut=True),
    _r(LECTURE, r"^/turn/credentials$", MEMBRE),
    _r({"GET"}, r"^/auth/me$", MEMBRE),
    # ------------------------------------------------------------------ équipe .mark
    _r(TOUTES, r"^/equipe-mark/moi(/.*)?$", MEMBRE),
    _r({"GET"}, r"^/equipe-mark/permissions$", MEMBRE),
    _r(ECRITURE, r"^/equipe-mark/roles(/.*)?$", P("roles.gerer")),
    _r(ECRITURE, r"^/equipe-mark/.*$", P("equipe.gerer"), par_defaut=True),
    _r(LECTURE, r"^/equipe-mark/.*$", P("equipe.gerer"), par_defaut=True),
    # ------------------------------------------------------------------ espaces
    _r({"GET"}, r"^/espaces$", MEMBRE),
    _r({"GET"}, r"^/espaces/conversations$", P("conversations.voir")),
    _r({"PUT"}, r"^/espaces/\{organization_id\}$", P("atelier.regler")),
    # ------------------------------------------------------------------ Hub « Relation clients » (U3 septies, E78)
    # Le Hub exige une SESSION d'équipe (la route refuse une clé d'API) ; le lien d'entrée dans un portail exige en plus la permission.
    _r({"POST"}, r"^/relation/clients/\{organization_id\}/entree$", P("clients.ouvrir_portail")),
    _r(TOUTES, r"^/relation(/.*)?$", MEMBRE, par_defaut=True),
    # Côté portail : clé d'API du client seulement (la route refuse une session) ; une clé ne lit que son organisation.
    _r(TOUTES, r"^/organizations/relation(/.*)?$", MEMBRE, par_defaut=True),
    # U2 quinquies (E58, E33) : copier un agent d'une organisation à une autre ; la route refuse en plus toute clé d'API.
    _r(TOUTES, r"^/export-agent(/.*)?$", P("clients.exporter_ramener"), par_defaut=True),
    # ------------------------------------------------------------------ organisation
    _r({"POST"}, r"^/organizations$", P("clients.creer")),
    _r({"GET"}, r"^/organizations$", MEMBRE),
    _r({"PUT"}, r"^/organizations/selected$", MEMBRE),
    _r(ECRITURE, r"^/organizations/(telephony-configs|telephony-providers)(/.*)?$", P("telephonie.gerer")),
    _r(ECRITURE, r"^/organizations/(model-configurations|langfuse-credentials|usage)(/.*)?$", P("cles.gerer")),
    # Le portail ouvre sa connexion à la base du client avec la clé d'API de l'organisation (lot F6) :
    # une permission qu'une clé peut porter, celle des accès techniques, jamais ``atelier.regler``.
    _r({"POST"}, r"^/organizations/base-client/connexion-portail$", P("cles.gerer")),
    _r(ECRITURE, r"^/organizations/(base-client|conservation-appels|fenetre-du-run)(/.*)?$", P("atelier.regler")),
    _r(ECRITURE, r"^/organizations/agents-servis/rattachement$", P("clients.exporter_ramener")),
    _r(ECRITURE, r"^/organizations/.*$", P("agents.modifier"), par_defaut=True),
    _r(LECTURE, r"^/organizations/.*$", MEMBRE, par_defaut=True),
    # U3 bis : le catalogue des variables d'un agent (lecture seule, tout membre de l'organisation).
    _r(LECTURE, r"^/mark/variables(/.*)?$", MEMBRE),
)


def decision_de(methode: str, chemin: str) -> tuple[Decision, bool] | None:
    """(décision, venait d'une règle de repli) pour une méthode et un chemin sans ``/api/v1``, ou ``None``."""
    for regle in REGLES:
        if methode in regle.methodes and regle.motif.match(chemin):
            return regle.decision, regle.par_defaut
    return None
