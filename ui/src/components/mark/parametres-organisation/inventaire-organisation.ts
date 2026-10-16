/**
 * [.mark] Inventory of the organization settings: where each key is on screen.
 *
 * Same rule as `reglages-agent/inventaire-agent.ts` (convention § 6), for the
 * two rows the Platform Settings page edits: the preferences
 * (`OrganizationPreferences`) and the closed-business announcement
 * (`ReglagesAnnonceOuverture`). The trade vocabulary, MCP and Telemetry are
 * separate resources edited by components reused as they are.
 */
import type { ThemeOrganisation } from "./references/cas-organisation";

export type EntreeInventaireOrganisation =
    | { theme: ThemeOrganisation; cas: string[] }
    | { horsEcran: string };

export const INVENTAIRE_PREFERENCES: Record<string, EntreeInventaireOrganisation> = {
    test_phone_number: { theme: "organisation", cas: ["telephone"] },
    timezone: { theme: "organisation", cas: ["fuseau"] },
    adresses_notification: { theme: "organisation", cas: ["adresses-notification"] },
    adresse_etablissement: { theme: "etablissement", cas: ["adresse-voie"] },
    external_pbx_integrations_enabled: { theme: "integrations", cas: ["standard-externe"] },
    disposition_mapping_enabled: { theme: "integrations", cas: ["correspondance"] },
    disposition_mapping: { theme: "integrations", cas: ["correspondance-liste"] },
    // Chantier agents-specialises, lot 5 (3 bis) added the key on the server; no screen yet. Said here, never
    // lost in silence (convention § 6): to be decided with Evan (A-VALIDER), it is not part of the lot 11 table.
    numero_des_transferts: {
        horsEcran:
            "Caller ID shown to the person a transfer rings (lot 5, 3 bis): set through the API for now, its field in the theme Organization is not built yet (outside the lot 11 table, to decide)",
    },
    call_events: {
        horsEcran:
            "BigQuery call-event export, neutralised by decision of Evan (25/09/2026, E3) and refused by the server; its card was removed at the rise to 4e6cb22b",
    },
};

export const INVENTAIRE_ANNONCE: Record<string, EntreeInventaireOrganisation> = {
    annonce_fermeture: { theme: "etablissement", cas: ["annonce-fermeture"] },
    annonce_pause: { theme: "etablissement", cas: ["annonce-pause"] },
    etat_force: { theme: "etablissement", cas: ["etat-force", "etat-calcule"] },
    etat_force_jusqu_a: { theme: "etablissement", cas: ["etat-force-jusqua"] },
    format: { horsEcran: "Technical marker of the stored document, never edited by a person" },
    version: { horsEcran: "Technical version of the stored document, never edited by a person" },
};
