/**
 * [.mark] One modification per setting of the Platform Settings page.
 *
 * Same contract as `reglages-agent/references/cas-agent.ts`, for the
 * organization (chantier reorganisation-ecran-reglages, steps 1 and 5). Each
 * case names the ORIGINAL card and the THEME it goes to (convention § 2).
 *
 * Unlike the agent's cards, the two original buttons here are ENABLED while
 * nothing was touched, and saving untouched sends the whole row (the PUT
 * replaces it). So « save without touching » is a case of its own.
 */
import type { Geste } from "../../reglages-agent/references/cas-agent";

export type CarteOrganisation = "preferences" | "annonce" | "correspondance";

export type ThemeOrganisation = "organisation" | "etablissement" | "ecoute" | "integrations" | "developpeurs";

export interface CasOrganisation {
    id: string;
    carte: CarteOrganisation;
    theme: ThemeOrganisation;
    cles: string[];
    gestes: Geste[];
    enregistreSeul?: boolean;
}

export const BOUTON_DE_LA_CARTE_ORGANISATION: Record<CarteOrganisation, string | null> = {
    preferences: "Save",
    annonce: "Save announcement settings",
    correspondance: null,
};

const c = (
    id: string,
    carte: CarteOrganisation,
    theme: ThemeOrganisation,
    cles: string[],
    gestes: Geste[],
    enregistreSeul = false,
): CasOrganisation => ({ id, carte, theme, cles, gestes, enregistreSeul });

export const CAS_ORGANISATION: CasOrganisation[] = [
    // Preferences: one row, one button on the old page, split over three themes.
    c("preferences-sans-rien", "preferences", "organisation", [], []),
    c("telephone", "preferences", "organisation", ["test_phone_number"], [
        { type: "saisir", id: "settings-test-phone-number", valeur: "+33612345678" },
    ]),
    c("fuseau", "preferences", "organisation", ["timezone"], [
        { type: "choisir", id: "settings-timezone", valeur: "America/New_York" },
    ]),
    c("adresse-voie", "preferences", "etablissement", ["adresse_etablissement"], [
        { type: "saisir", id: "settings-business-address-voie", valeur: "7 rue Neuve" },
    ]),
    c("standard-externe", "preferences", "integrations", ["external_pbx_integrations_enabled"], [
        { type: "interrupteur", id: "settings-external-pbx-integrations" },
    ]),
    c("correspondance", "preferences", "integrations", ["disposition_mapping_enabled"], [
        { type: "interrupteur", id: "settings-disposition-mapping" },
    ]),
    c("correspondance-liste", "correspondance", "integrations", ["disposition_mapping"], [
        { type: "cliquer", nom: "Configure mapping" },
        { type: "cliquer", nom: "Stub: save mapping" },
    ], true),
    // Closed-business announcement: its own button on the old page.
    c("annonce-sans-rien", "annonce", "etablissement", [], []),
    c("annonce-fermeture", "annonce", "etablissement", ["annonce_fermeture"], [
        { type: "saisir", id: "annonce_fermeture", valeur: "Nous sommes fermés[, retour {reouverture}]." },
    ]),
    c("annonce-pause", "annonce", "etablissement", ["annonce_pause"], [
        { type: "saisir", id: "annonce_pause", valeur: "Petite pause[, retour {reouverture}]." },
    ]),
    c("etat-force", "annonce", "etablissement", ["etat_force"], [
        { type: "choisir", id: "etat_force", valeur: "FERME" },
    ]),
    c("etat-force-jusqua", "annonce", "etablissement", ["etat_force", "etat_force_jusqu_a"], [
        { type: "choisir", id: "etat_force", valeur: "PAUSE" },
        { type: "saisir", id: "etat_force_jusqu_a", valeur: "2026-12-24T18:00" },
    ]),
    c("etat-calcule", "annonce", "etablissement", ["etat_force", "etat_force_jusqu_a"], [
        { type: "choisir", id: "etat_force", valeur: "" },
    ]),
];
