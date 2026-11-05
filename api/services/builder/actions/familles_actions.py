"""[.mark] Builder partie 3, N1 (sous-lot 1) : la famille de chaque action du registre (05, « Les permissions du builder »).

Le builder peut tout faire ; ce n'est plus un interdit codé qui décide, c'est la PERMISSION, lue d'après la famille de l'action, le mode
du chat et le rôle de la personne (``modes.py``). Une liste fermée de neuf familles :

=================  =====================================================================================================
``lecture``        lire, et les cartes du dialogue (plan, question, rapport, annonce d'une dépense, propositions)
``brouillon``      le brouillon de l'agent ouvert et ses notes de construction (fiche, conception, contexte, sauvegarde)
``reglages``       les réglages de l'agent : réglages, phrases, lexique, outils, tests, étiquettes
``publication``    publier un agent, une branche ou un groupe, fusionner, répartir le trafic
``entreprise``     ce qui sert toute l'organisation : objets, bibliothèque, jeu public d'attaques
``autre_agent``    un autre agent ou un groupe : créer, régler, compléter
``depense``        ce qui fait tourner des modèles payants : rejouer les tests, les attaques, l'appelant simulé
``appels_reels``   ce qui appelle de vrais gens (démarrer ou reprendre une campagne, appel de test vers un vrai numéro)
``irreversible``   supprimer, archiver
=================  =====================================================================================================

Chaque action du registre a sa ligne ici (``test_builder_familles_et_modes.py`` échoue sinon, et une ligne sans action aussi). Une action
sans famille est traitée comme ``irreversible`` (la plus fermée) par la porte des modes.
"""

from __future__ import annotations

FAMILLES: tuple[str, ...] = (
    "lecture",
    "brouillon",
    "reglages",
    "publication",
    "entreprise",
    "autre_agent",
    "depense",
    "appels_reels",
    "irreversible",
)

# La permission de rôle que chaque famille exige (``equipe_mark/permissions.py``) : le builder ne donne jamais plus de droits que la personne
# qui l'utilise. Les mêmes clés que les routes de l'écran pour le même geste (``registre_routes.py``).
PERMISSION_DE_LA_FAMILLE: dict[str, str | None] = {
    "lecture": None,
    "brouillon": "agents.modifier",
    "reglages": "agents.modifier",
    "publication": "agents.publier",
    "entreprise": "agents.modifier",
    "autre_agent": "agents.modifier",
    "depense": "tests.jouer",
    "appels_reels": "agents.publier",  # comme le départ d'une campagne (``/campaign/{id}/start``)
    "irreversible": "agents.supprimer",
}

_PAR_FAMILLE: dict[str, tuple[str, ...]] = {
    "lecture": (
        # lire un agent, le catalogue, la méthode
        "list_workflows", "get_workflow", "get_workflow_code", "list_node_types", "get_node_type", "list_tools", "list_documents",
        "list_credentials", "list_recordings", "get_voice_prompting_guide", "builder_methode", "builder_conventions",
        "brouillon_voir", "fiche_lire", "conception_lire", "contexte_lire", "phrases_catalogue", "reglages_lire",
        "modeles_reglages_lister", "fiche_tirer_des_documents", "prompt_controler", "objets_agent_lister", "base_lister",
        "bibliotheque_chercher", "bibliotheque_lister", "bibliotheque_lire", "recette_lire", "agent_montrer_le_graphe",
        "etiquettes_prompt_lire", "branches_lire", "branche_travailler", "outils_versions_lire", "groupes_lister", "groupe_lire",
        "juge_a_faire", "juge_lire", "publication_controler", "attaques_rapport", "attaques_jeu_public",
        "tests_lister", "tests_lire", "correction_bilan", "modifications_lister",
        "fork_resume", "executions_lister", "a_ameliorer_lire", "appels_lister", "appel_lire", "versions_lister", "chat_etat",
        "qualite_lire",
        # N1 (sous-lot 5) : lire l'entreprise (établissements, phrases, annonce, vocabulaire, listes, équipe, campagnes, téléphonie par leur nom)
        "etablissements_lire", "phrases_organisation_lire", "annonce_lire", "lexique_lire", "listes_valeurs_lire", "equipe_lister",
        "campagnes_lister", "campagne_lire", "telephonie_lister",
        # N2 : lectures de l'écran qui passent par un POST
        "etablissements_reprise_essayer", "horaires_controler", "etablissements_de_l_agent_lire", "lexique_budget_lire",
        # les cartes du dialogue : elles ne font rien d'autre que demander ou montrer (une personne clique ensuite)
        "plan_mettre_a_jour", "question_poser", "rapport_de_fin", "depense_annoncer", "correction_proposer",
        "agent_proposer_archivage", "tests_supprimer", "deleguer",
    ),
    "brouillon": (
        "create_workflow", "save_workflow", "brouillon_operation", "brouillon_enregistrer", "brouillon_jeter",
        "fiche_ecrire", "conception_ecrire", "contexte_ecrire", "depot_ajouter_site", "base_proposer", "base_rattacher",
        "bibliotheque_appliquer", "publication_corriger_la_liste_vocale", "sauvegarde_prendre", "sauvegarde_refuser",
        "bloc_poser", "bloc_retirer", "branche_creer",
    ),
    "reglages": (
        "reglages_regler", "phrases_regler", "lexique_remplir_depuis_fiche", "modeles_reglages_appliquer", "etiquettes_agent",
        "create_tool", "outil_essayer", "outil_passer_a_la_version", "tests_creer", "tests_modifier", "tests_depuis_la_bibliotheque",
        "attaques_creer_des_tests", "attaques_envoyer_a_ameliorer", "juge_ecrire",
    ),
    "publication": (
        "agent_publier", "groupe_publier", "branche_publier", "branche_fusionner", "repartition_regler",
    ),
    "entreprise": (
        "objets_agent_ecrire", "fiche_creer_les_objets", "bibliotheque_ranger", "bibliotheque_ecrire_candidat", "bibliotheque_proposer",
        "attaques_importer_le_jeu_public", "bibliotheque_marquer", "bibliotheque_accepter_proposition",
        "bibliotheque_refuser_proposition", "bibliotheque_retour_arriere",
        # N1 (sous-lot 5) : écrire l'entreprise
        "etablissements_remplacer", "etablissement_modifier", "etablissement_fermer_ou_rouvrir", "phrases_organisation_ecrire",
        "annonce_regler", "lexique_ecrire", "listes_valeurs_cocher", "equipe_inviter", "campagne_creer", "campagne_modifier", "campagne_pause",
        # N2 : les restes de l'écran
        "etablissement_copier", "etablissements_reprise_ecrire", "etablissement_appliquer_a_tous", "lexique_importer", "equipe_annuler_invitation",
    ),
    "autre_agent": (
        "groupe_creer", "groupe_specialise_creer", "groupe_regler", "groupe_completer",
    ),
    "depense": (
        "tests_rejouer", "attaques_lancer", "attaques_rejouer", "test_demarrer", "test_tour", "test_finir",
    ),
    "appels_reels": ("campagne_demarrer", "campagne_reprendre", "campagne_rappeler", "appel_de_test_lancer"),
    "irreversible": (
        "agent_archiver", "outil_supprimer",
    ),
}

FAMILLE_DES_ACTIONS: dict[str, str] = {nom: famille for famille, noms in _PAR_FAMILLE.items() for nom in noms}

# Une permission de rôle plus juste que celle de la famille, quand l'écran exige autre chose pour le même geste.
PERMISSION_DE_L_ACTION: dict[str, str] = {
    # La bibliothèque se règle depuis le Labo (``/builder/bibliotheque/...`` : « atelier.regler »).
    "bibliotheque_marquer": "atelier.regler",
    "bibliotheque_accepter_proposition": "atelier.regler",
    "bibliotheque_refuser_proposition": "atelier.regler",
    "bibliotheque_retour_arriere": "atelier.regler",
    # Supprimer un outil est une écriture des outils à l'écran (``/tools/...`` : « agents.modifier »).
    "outil_supprimer": "agents.modifier",
    # L'équipe .mark se gère avec « equipe.gerer » (jamais une clé d'API), comme ``/equipe-mark/*`` ; un appel de test est un test (« tests.jouer »).
    "equipe_lister": "equipe.gerer",
    "equipe_inviter": "equipe.gerer",
    "equipe_annuler_invitation": "equipe.gerer",
    "appel_de_test_lancer": "tests.jouer",
}


def famille_de(nom: str) -> str | None:
    return FAMILLE_DES_ACTIONS.get(nom)


def permission_de(nom: str, famille: str) -> str | None:
    return PERMISSION_DE_L_ACTION.get(nom, PERMISSION_DE_LA_FAMILLE.get(famille, "agents.supprimer"))
