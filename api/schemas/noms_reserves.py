"""[.mark] RA-A (R3, audit du 04/11, 02 B6) : LA liste des noms réservés, une seule.

Il y en avait trois : les clés que le moteur écrit dans la fiche de l'appel (``fiche_agent``), les noms que Dograh
donne au contexte de l'appel (``phrases``) et les variables que le code pose (``objets_agent``). Un objet refusait le
nom d'une phrase mais pas l'inverse ; un champ de fiche pouvait prendre le nom d'une variable posée par le code.

Maintenant : fiche, phrases du catalogue, objets de l'agent et catalogue des variables importent cette liste.
Pur : aucun import du fork, pour que les schémas puissent l'utiliser sans cycle. Une clé posée par une injection
nouvelle de ``run_pipeline.py`` qui n'est pas ici fait échouer ``tests/mark/test_ra_a_r3_noms_reserves.py``.
"""

from __future__ import annotations

# Clés que le moteur et les modules écrivent eux-mêmes dans la fiche de l'appel, et variables posées par le code.
# Un champ de fiche, une phrase du catalogue ou un objet de ce nom les écraserait (ou serait écrasé) : refusé.
NOMS_RESERVES: frozenset[str] = frozenset(
    {
        # moteur (`_ENGINE_OWNED_CONTEXT_KEYS` et clés d'état)
        "call_disposition",
        "mapped_call_disposition",
        "call_status",
        "call_tags",
        "answer_supervisor",
        # [.mark] lot 3 de cloture-code (amont b10e829f) : les résultats des outils
        "tool_results",
        "extracted_variables",
        "nodes_visited",
        "agent_visits",
        # [.mark] agents-specialises (lots 2, 5, 7) : les traces du groupe
        "parcours",
        "parcours_etapes",
        "porte_reecrite",
        "passations",
        "transferts_humains",
        # [.mark] agents-specialises (lot 17) : les demandes closes d'un appel à plusieurs demandes
        "demandes",
        "demande_au_retour",
        # traces des modules
        "communes_verifiees",
        # chantier postscriptum-et-communes, lot 1 : les communes lues sur le nom de la personne
        "communes_ecartees",
        # plan mode-prise-de-notes : la trace de chaque post-scriptum et de chaque passe du greffier
        "post_scriptums",
        "greffier_passes",
        # chantier greffier-conversation, lot A : les portes écrites dans la réponse (greffier)
        "portes_lues",
        # chantier greffier-conversation, lot E : le transfert lancé par le code
        "transferts_garantis",
        "voies_verifiees",
        "epellations_lues",
        "nombres_lus",
        "lexique_reconnu",
        "lexique_metier",
        # la fiche elle-même
        "fiche_etat",
        "fiche_journal",
        "tour_appelant",
        # [.mark] l-agent-travaille, L5 : les traces des connecteurs
        "connecteurs",
        "connecteurs_differes",
        # [.mark] l-agent-collegue : les traces de l'équipe, du hub, du planificateur et de la
        # vérification de l'appelant (L2 à L6, R-3)
        "equipe_gestes",
        "equipe_assignation",
        "hub_rendez_vous",
        "planificateur",
        "planificateur_rappel",
        "verification_appelant",
        "dossier_lu",
        # [.mark] orchestrateur-trois-cerveaux, lot 4 : la trace du cerveau de fond (oubliée alors,
        # ajoutée par fiabilite-orchestration) ; fiabilite-orchestration : les phrases du code.
        "travaux",
        "phrases_du_code",
        # fiabilite-orchestration, lot 9 : connexions au modèle et liaison audio relevées par appel.
        "mark_connexions_modele",
        "mark_reseau",
        # actions-sures-et-parite-clavier, lot F : le journal des actions de l'appel, gardé avec la fiche.
        "mark_journal_des_actions",
        # passages-fiables : les retenues de la vérité des actions (file de tri) ; le rejeu d'un test et ses outils simulés.
        "retenues_verite",
        "rejeu_sortants_simules",
        "outils_simules",
        # passages-fiables : les traces du décideur et de l'arbitre, l'attente accordée, les signalements et les alertes.
        "passages_par_le_code",
        "arbitre",
        "desaccords_arbitre",
        "attentes_accordees",
        "signalements",
        "alertes",
        "alertes_mail",
    
        # Ce que Dograh et le fork posent dans le contexte de l'appel (ex-liste des phrases du catalogue).
        "annonce_fermeture",
        "annonce_pause",
        "annonce_ouverture",
        "etat_ouverture",
        "reouverture",
        "horaires_ouverture",
        "date_appel",
        "heure_appel",
        "adresse_etablissement",
        "etablissement",
        "etablissement_id",
        "numero_transfert",
        "lexique_propose",
        "lexique_a_ecouter",
        "caller_number",
        "called_number",
        "direction",
        "provider",
        "call_id",
        "workflow_run_id",
        "telephony_configuration_id",
        "runtime_configuration",
        "initial_context",
        "gathered_context",
        # l-agent-collegue (C4, C7): the team known to the agent and its closed list.
        "equipe",
        "equipe_cles",
        # Posées par les injections de ``run_pipeline.py`` (lues dans les constantes de leur module, contrôlées par un test).
        "etablissement_de_lappel",
        "mps_correlation_id",
    }
)
