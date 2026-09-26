"use client";

/**
 * [.mark] The organization's preferences row: read once, saved by three
 * themes (chantier reorganisation-ecran-reglages, step 5, option B of D6).
 *
 * Rebuilt from Dograh's `OrganizationPreferencesSection` (left in its file,
 * unused), which edited the whole row with one button. The row is now shown in
 * three themes -- Organization (test number, timezone), Business (address),
 * Integrations (external PBX, disposition mapping) -- and each theme saves the
 * row as it is stored with ITS OWN fields as typed: a theme never sends what
 * is being typed in another one.
 *
 * The body is built exactly as theirs was: same keys, same fallbacks, the
 * address only when there is one (the PUT replaces the row, an absent key
 * clears it like null), the mapping sent even when switched off. Same toasts,
 * same refresh of the user configuration, same address refusal under its
 * fields. Frozen by `references/charges-utiles-organisation.test.tsx`.
 */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
    getPreferencesApiV1OrganizationsPreferencesGet,
    savePreferencesApiV1OrganizationsPreferencesPut,
} from "@/client/sdk.gen";
import type { OrganizationPreferences } from "@/client/types.gen";
import { useUserConfig } from "@/context/UserConfigContext";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

export const PREFERENCES_VIDES: OrganizationPreferences = {
    test_phone_number: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    external_pbx_integrations_enabled: false,
    disposition_mapping_enabled: false,
    disposition_mapping: {},
    adresse_etablissement: null,
};

/** A server answer, in the shape the themes edit (Dograh's `toFormPreferences`). */
export const versFormulaire = (preferences: OrganizationPreferences): OrganizationPreferences => ({
    test_phone_number: preferences.test_phone_number || "",
    timezone: preferences.timezone || PREFERENCES_VIDES.timezone,
    external_pbx_integrations_enabled: preferences.external_pbx_integrations_enabled ?? false,
    disposition_mapping_enabled: preferences.disposition_mapping_enabled ?? false,
    disposition_mapping: preferences.disposition_mapping ?? {},
    adresse_etablissement: preferences.adresse_etablissement ?? null,
});

/** The result of a save, for the theme that asked. */
export interface ResultatPreferences {
    ok: boolean;
    /** The server refused the ADDRESS: shown under its fields. */
    refusAdresse: string | null;
}

export const usePreferencesOrganisation = () => {
    const { user, loading: authLoading } = useAuth();
    const { refreshConfig } = useUserConfig();
    const dejaLu = useRef(false);
    const [enregistrees, setEnregistrees] = useState<OrganizationPreferences>(PREFERENCES_VIDES);
    const [chargement, setChargement] = useState(true);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void charger();
    }, [authLoading, user]);

    async function charger() {
        setChargement(true);
        try {
            const result = await getPreferencesApiV1OrganizationsPreferencesGet();
            if (result.error) {
                toast.error(detailFromError(result.error, "Failed to load organization preferences"));
                return;
            }
            setEnregistrees(versFormulaire(result.data || PREFERENCES_VIDES));
        } catch {
            toast.error("Failed to load organization preferences");
        } finally {
            setChargement(false);
        }
    }

    /** Saves the stored row with `modifications` over it. */
    async function enregistrer(
        modifications: Partial<OrganizationPreferences>,
        messageSucces: string,
    ): Promise<ResultatPreferences> {
        const suivantes = { ...enregistrees, ...modifications };
        setEnCours(true);
        try {
            const result = await savePreferencesApiV1OrganizationsPreferencesPut({
                body: {
                    test_phone_number: suivantes.test_phone_number || null,
                    timezone: suivantes.timezone,
                    external_pbx_integrations_enabled: suivantes.external_pbx_integrations_enabled ?? false,
                    disposition_mapping_enabled: suivantes.disposition_mapping_enabled ?? false,
                    // Sent even when the toggle is off: turning the mapping off
                    // should stop it being applied, not discard the entries.
                    disposition_mapping: suivantes.disposition_mapping ?? {},
                    // The PUT replaces the whole row, so an absent key clears the
                    // address exactly like null. Sent only when there is one.
                    ...(suivantes.adresse_etablissement
                        ? { adresse_etablissement: suivantes.adresse_etablissement }
                        : {}),
                },
            });

            if (result.error) {
                const message = detailFromError(result.error, "Failed to save preferences");
                // Only an ADDRESS refusal goes under the address: the route raises
                // it as a plain string, while a validation error of another field
                // comes as a list naming that field (review of 2026-09-16).
                const detail = (result.error as { detail?: unknown } | undefined)?.detail;
                const refusAdresse =
                    typeof detail === "string" || JSON.stringify(detail ?? "").includes("adresse_etablissement");
                toast.error(message);
                return { ok: false, refusAdresse: result.response?.status === 422 && refusAdresse ? message : null };
            }
            if (!result.data) {
                toast.error("Failed to save preferences");
                return { ok: false, refusAdresse: null };
            }

            setEnregistrees(versFormulaire(result.data));
            await refreshConfig();
            toast.success(messageSucces);
            return { ok: true, refusAdresse: null };
        } catch {
            toast.error("Failed to save preferences");
            return { ok: false, refusAdresse: null };
        } finally {
            setEnCours(false);
        }
    }

    return { enregistrees, chargement, enCours, enregistrer };
};

export type EtatPreferences = ReturnType<typeof usePreferencesOrganisation>;
