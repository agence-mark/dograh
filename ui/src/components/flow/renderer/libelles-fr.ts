/**
 * [.mark] K2 : les champs de la fenêtre d'un nœud, dits en français. Le serveur déclare les champs de chaque type de nœud
 * (nom, explication, choix) en anglais, dans les spécifications qu'il sert à `/node-types` : l'écran les traduit ici, par
 * nom de champ. Un champ sans traduction garde le texte du serveur. L'anglais reste le texte du serveur, tel quel.
 */
import type { NodeSpec } from "@/client/types.gen";

type Propriete = NodeSpec["properties"][number];
type Fr = { libelle?: string; explication?: string; choix?: Record<string, string> };

const FR: Record<string, Fr> = {
    name: { libelle: "Nom", explication: "Un nom court, repris dans le canevas et les journaux d'appel." },
    prompt: { libelle: "Prompt de l'étape", explication: "Les consignes de l'agent pour cette étape. Accepte les variables {{…}} issues de l'extraction ou de la récupération avant l'appel." },
    premiere_replique: {
        libelle: "Première réplique",
        explication: "Ce que l'agent dit en premier en arrivant à cette étape. Utilisée seulement quand « Transitions dans la réponse » est allumé. Accepte les variables {{…}}.",
    },
    champs_etape: {
        libelle: "Champs de l'étape",
        explication:
            "Les champs de la fiche que cette étape recueille, par ordre de priorité, séparés par des virgules. Utilisé seulement quand « Montrer au modèle ce qui est connu et attendu » est allumé dans les réglages de l'agent : le code nomme alors ceux qui manquent, et les outils de l'étape attendent qu'ils soient connus.",
    },
    qui_decide_du_passage: {
        libelle: "Qui décide du passage",
        explication:
            "Agent (par défaut) : le modèle seul prend les sorties. Collecte : le code prend la première sortie dès que chaque champ de l'étape est recueilli. Choix : le code prend la sortie dont la condition sur la fiche est vraie, sinon l'arbitre choisit. Libre : l'agent mène, l'arbitre est le filet de sécurité.",
        choix: {
            agent: "Agent (comme avant)",
            collecte: "Collecte (la fiche décide)",
            choix: "Choix (une règle, sinon l'arbitre)",
            libre: "Libre (l'agent, l'arbitre en filet)",
        },
    },
    moment_du_passage: {
        libelle: "Moment du passage",
        explication:
            "Après la réponse (par défaut) : le code passe dès que l'agent a répondu. Attendre le dernier champ : quand un seul champ manque, la requête attend (brièvement) que le greffier lise les derniers mots de l'appelant, et l'étape suivante parle aussitôt. Attendre à chaque tour (étapes de collecte) : la requête attend toujours (brièvement) le greffier, pour que la fiche montrée à l'agent contienne ce que l'appelant vient de dire.",
        choix: {
            apres_la_reponse: "Après la réponse",
            attendre_le_dernier_champ: "Attendre le dernier champ",
            attendre_a_chaque_tour: "Attendre à chaque tour",
        },
    },
    delai_du_passage: {
        libelle: "Attente la plus longue avant la réponse (secondes)",
        explication: "Combien de temps la réponse de l'agent peut attendre le greffier (Attendre le dernier champ) ou l'arbitre, avant de partir sans eux. 1,5 par défaut.",
    },
    arbitre: {
        libelle: "Arbitre",
        explication:
            "Un petit modèle à part, interrogé quand l'appelant finit de parler, qui dit quelle sortie (s'il y en a une) ses mots appellent. La réponse de l'agent l'attend (de façon bornée) ; quand il est sûr, l'étape suivante répond aussitôt. Vide : éteint, sauf sur une étape Choix ou Libre.",
    },
    seuil_de_l_arbitre: { libelle: "Seuil de confiance de l'arbitre", explication: "La confiance minimale à laquelle le choix de l'arbitre est pris (de 0 à 1). 0,8 par défaut." },
    allow_interrupt: { libelle: "L'appelant peut couper la parole", explication: "Allumé, l'appelant peut interrompre l'agent en pleine phrase. Éteint pour les mentions qui doivent être dites en entier." },
    add_global_prompt: { libelle: "Ajouter le prompt général", explication: "Allumé et s'il existe un nœud Global, son texte est placé avant le prompt de cette étape à l'appel." },
    extraction_enabled: { libelle: "Extraire des variables", explication: "Allumé, un passage du modèle extrait des variables de la conversation pour cette étape." },
    extraction_prompt: { libelle: "Consigne d'extraction", explication: "Les consignes générales qui guident l'extraction des variables." },
    extraction_variables: {
        libelle: "Variables à extraire",
        explication: "Chaque ligne déclare une variable à recueillir : son nom, son type et un indice d'extraction. Les issues d'appel se règlent à part, dans les réglages de l'agent.",
    },
    tool_uuids: { libelle: "Outils", explication: "Les outils que l'agent peut appeler pendant cette étape." },
    document_uuids: { libelle: "Documents de la base de connaissances", explication: "Les documents que l'agent peut consulter pendant cette étape." },
    greeting_type: {
        libelle: "Type d'accueil",
        explication: "L'accueil facultatif est dit par la voix à partir d'un texte, ou joué depuis un enregistrement.",
        choix: { text: "Texte (voix)", audio: "Enregistrement" },
    },
    greeting: { libelle: "Texte de l'accueil", explication: "Dit par la voix au début de l'appel. Accepte les variables {{…}}. Vide : pas d'accueil." },
    greeting_recording_id: { libelle: "Enregistrement de l'accueil", explication: "Le fichier audio joué au début de l'appel." },
    delayed_start: { libelle: "Démarrage différé", explication: "Règle la fenêtre d'écoute initiale pour les appels sortants (messagerie, filtrage). Un court bonjour humain peut la raccourcir." },
    delayed_start_duration: { libelle: "Durée du délai (secondes)", explication: "Secondes d'écoute d'un décrochage silencieux avant de parler, de 0,1 à 10. Remplace la fenêtre de 1,2 s par défaut." },
    pre_call_fetch_mode: {
        libelle: "Données avant l'appel",
        explication: "Dit quand une requête POST enrichit le contexte de l'appel avant l'ouverture de l'étape de début.",
        choix: { disabled: "Désactivé", always: "Toujours", inbound: "Appels entrants seulement", outbound: "Appels sortants seulement" },
    },
    pre_call_fetch_url: { libelle: "Adresse de la requête", explication: "L'adresse à laquelle part la requête POST. Le corps contient les numéros de l'appelant et de l'appelé." },
    pre_call_fetch_credential_uuid: { libelle: "Authentification", explication: "Un identifiant facultatif joint à la requête." },
    enabled: { libelle: "Actif", explication: "Éteint, l'élément est ignoré." },
    trigger_path: { libelle: "Chemin du déclencheur", explication: "Le morceau d'adresse qui identifie ce déclencheur : 36 caractères au plus, lettres, chiffres, tirets ou soulignés." },
    http_method: { libelle: "Méthode HTTP", explication: "Le verbe HTTP de la requête sortante." },
    endpoint_url: { libelle: "Adresse", explication: "L'adresse à laquelle la requête est envoyée." },
    credential_uuid: { libelle: "Authentification", explication: "Un identifiant facultatif placé dans l'en-tête Authorization." },
    custom_headers: { libelle: "En-têtes", explication: "Des en-têtes HTTP en plus, joints à la requête." },
    payload_template: { libelle: "Corps de la requête", explication: "Le corps JSON de la requête. Les valeurs sont complétées avec le contexte de l'appel : {{workflow_run_id}}, {{gathered_context.xxx}}, {{annotations.qa_xxx}}…" },
    qa_enabled: { libelle: "Actif", explication: "Éteint, l'analyse qualité est ignorée." },
    qa_system_prompt: { libelle: "Consigne du relecteur", explication: "Les instructions du modèle qui relit l'appel. Accepte {node_summary}, {previous_conversation_summary}, {transcript}, {metrics}." },
    qa_min_call_duration: { libelle: "Durée minimale de l'appel (secondes)", explication: "Les appels plus courts sont ignorés." },
    qa_voicemail_calls: { libelle: "Inclure les messageries", explication: "Éteint, les appels reconnus comme messagerie sont ignorés." },
    qa_sample_rate: { libelle: "Part des appels relus (%)", explication: "Le pourcentage d'appels éligibles relus. 100 : tous ; moins : tirage au hasard." },
    qa_use_workflow_llm: { libelle: "Utiliser le modèle de l'agent", explication: "Allumé, la relecture utilise le même modèle que l'agent. Éteint pour choisir un autre fournisseur et un autre modèle." },
    qa_provider: { libelle: "Fournisseur du modèle de relecture", explication: "Le fournisseur du modèle qui relit les appels." },
    qa_model: { libelle: "Modèle de relecture", explication: "L'identifiant du modèle, propre au fournisseur." },
    qa_api_key: { libelle: "Clé d'API", explication: "La clé du fournisseur choisi." },
    qa_endpoint: { libelle: "Adresse Azure", explication: "Obligatoire pour le fournisseur Azure." },
};

/** Le champ du serveur, dit en français quand la langue l'est et que la traduction existe. */
export function localiserLaPropriete(p: Propriete, langue: "fr" | "en"): Propriete {
    if (langue !== "fr") return p;
    const fr = FR[p.name];
    if (!fr) return p;
    return {
        ...p,
        display_name: fr.libelle ?? p.display_name,
        description: fr.explication ?? p.description,
        options: p.options?.map((o) => ({ ...o, label: fr.choix?.[String(o.value)] ?? o.label })) ?? p.options,
    };
}
