/**
 * [.mark] Partie 3, lot 14 (J-1, SE-19) : les logos officiels des logiciels du catalogue.
 *
 * Les fichiers sont ceux de la maquette validée par Evan (publiés par Nango ou icône de l'éditeur, jamais redessinés). Tant qu'un fichier n'est pas versé, la ligne ou la carte
 * montre les initiales du logiciel. Pour en ajouter un : déposer le fichier dans `ui/public/logos/` et ajouter UNE ligne
 * ici, clé = la clé du logiciel (`integration` du catalogue), valeur = son adresse publique.
 * Exemple : `google_agenda: "/logos/google-agenda.svg"`.
 */
export const LOGOS: Record<string, string> = {
    "acuity-scheduling": "/logos/acuity-scheduling.svg",
    "aircall": "/logos/aircall.svg",
    "airtable": "/logos/airtable.svg",
    "apimo": "/logos/apimo.jpg",
    "axonaut": "/logos/axonaut.png",
    "calendly": "/logos/calendly.svg",
    "cosium": "/logos/cosium.png",
    "crisp": "/logos/crisp.svg",
    "doctolib": "/logos/doctolib.png",
    "folk": "/logos/folk.svg",
    "freshdesk": "/logos/freshdesk.svg",
    "google-calendar": "/logos/google-calendar.svg",
    "google-mail": "/logos/google-mail.svg",
    "google-sheet": "/logos/google-sheet.svg",
    "hubspot": "/logos/hubspot.svg",
    "nocrm": "/logos/nocrm.svg",
    "notion": "/logos/notion.svg",
    "organilog": "/logos/organilog.png",
    "outlook": "/logos/outlook.svg",
    "pennylane": "/logos/pennylane.svg",
    "pipedrive": "/logos/pipedrive.svg",
    "praxedo": "/logos/praxedo.svg",
    "ringover": "/logos/ringover.svg",
    "salesforce": "/logos/salesforce.svg",
    "sellsy": "/logos/sellsy.svg",
    "setmore": "/logos/setmore.svg",
    "slack": "/logos/slack.svg",
    "teamleader-focus": "/logos/teamleader.svg",
    "twilio": "/logos/twilio.svg",
    "whatsapp-business": "/logos/whatsapp-business.svg",
    "zendesk": "/logos/zendesk.svg",
    // Fournisseurs de modèles (tableau des clés, Modèles et clés). Même règle : un fournisseur sans fichier garde ses initiales.
    // Les variantes d'un même fournisseur (OpenAI Realtime, Google Vertex, Azure Speech) montrent le logo de la marque.
    "mistral": "/logos/mistral.svg",
    "elevenlabs": "/logos/elevenlabs.svg",
    "cartesia": "/logos/cartesia.svg",
    "soniox": "/logos/soniox.svg",
    "openai": "/logos/openai.svg",
    "openai_realtime": "/logos/openai.svg",
    "deepgram": "/logos/deepgram.svg",
    "google": "/logos/google.svg",
    "google_vertex": "/logos/google.svg",
    "openrouter": "/logos/openrouter.svg",
    "azure": "/logos/azure.svg",
    "azure_speech": "/logos/azure.svg",
    "minimax": "/logos/minimax.svg",
};

export const logoDe = (integration: string | null | undefined): string | null => (integration ? (LOGOS[integration] ?? null) : null);
