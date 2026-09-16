"use client";

import { MapPin } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import type { AdresseEtablissement } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { useOrgConfig } from "@/context/OrgConfigContext";
import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import { detailFromError } from "@/lib/apiError";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { ChampAdresseEtablissement } from "./ChampAdresseEtablissement";
import { RAPPEL_PUBLICATION } from "./SectionReglagesPipecat";

/**
 * [.mark] The "Business address for this agent" card of an agent's settings page.
 *
 * Decision D2 of 2026-09-16: the address lives on the organization, and an
 * agent may override it. Left empty, the agent uses the organization's address,
 * which is shown here read-only so nobody has to guess what applies.
 *
 * ⛔ A refusal from the server (a town that does not carry the postal code) is
 * shown under the fields, not only in a toast, like the opening hours.
 */

export const ID_SECTION_ADRESSE_ETABLISSEMENT = "business-address";

interface SectionAdresseEtablissementProps {
    /** The RESOLVED configuration, as the page hands it to every other section. */
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    onSave: (
        configurations: WorkflowConfigurations,
        workflowName: string,
    ) => Promise<void>;
}

const texteAdresse = (adresse: AdresseEtablissement): string => {
    const ville = `${adresse.code_postal} ${adresse.commune}`;
    return adresse.voie ? `${adresse.voie}, ${ville}` : ville;
};

const memeAdresse = (a: AdresseEtablissement | null, b: AdresseEtablissement | null): boolean =>
    JSON.stringify(a ? { ...a, voie: a.voie ?? null } : null)
    === JSON.stringify(b ? { ...b, voie: b.voie ?? null } : null);

export const SectionAdresseEtablissement = ({
    workflowConfigurations,
    workflowName,
    onSave,
}: SectionAdresseEtablissementProps) => {
    const { organizationPreferences } = useOrgConfig();
    const enregistree = workflowConfigurations.adresse_etablissement ?? null;
    const [adresse, setAdresse] = useState<AdresseEtablissement | null>(enregistree);
    const [incomplete, setIncomplete] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    // After a save the page hands over the new saved address: the draft follows.
    const cleEnregistree = JSON.stringify(enregistree);
    useEffect(() => {
        setAdresse(enregistree);
        setIncomplete(false);
    }, [cleEnregistree]); // eslint-disable-line react-hooks/exhaustive-deps

    const isDirty = !memeAdresse(adresse, enregistree);
    useUnsavedChanges(ID_SECTION_ADRESSE_ETABLISSEMENT, isDirty || incomplete);

    const adresseOrganisation = organizationPreferences?.adresse_etablissement ?? null;

    const enregistrer = async (valeur: AdresseEtablissement | null) => {
        setIsSaving(true);
        setErreur(null);
        try {
            // The whole resolved configuration first, then our one key.
            await onSave({ ...workflowConfigurations, adresse_etablissement: valeur }, workflowName);
            toast.success(`Business address saved. ${RAPPEL_PUBLICATION}`);
        } catch (e) {
            const message = e instanceof Error && e.message
                ? e.message
                : detailFromError(e, "Business address not saved. Check the entry and try again.");
            setErreur(message);
            toast.error(`Business address not saved: ${message}`);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id={ID_SECTION_ADRESSE_ETABLISSEMENT}>
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <MapPin className="h-4 w-4" />
                    Business address for this agent
                </CardTitle>
                <CardDescription>
                    Leave empty to use the organization&apos;s address. Given to the agent as
                    {" "}<code className="rounded bg-muted px-1 text-xs">{"{{adresse_etablissement}}"}</code>,
                    and used to recognise the towns callers name; the street is not.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">
                    Organization&apos;s address:{" "}
                    <span className="text-foreground">
                        {adresseOrganisation ? texteAdresse(adresseOrganisation) : "none set"}
                    </span>
                </p>
                <ChampAdresseEtablissement
                    id="agent-business-address"
                    enregistree={enregistree}
                    erreur={erreur}
                    onChange={(valeur, estIncomplete) => {
                        setAdresse(valeur);
                        setIncomplete(estIncomplete);
                        setErreur(null);
                    }}
                />
                {incomplete && (
                    <p className="text-xs text-muted-foreground">
                        Choose the town for this postal code before saving.
                    </p>
                )}
            </CardContent>
            <CardFooter className="justify-end gap-3 border-t pt-6">
                {isDirty && !erreur && !incomplete && (
                    <span className="text-xs text-muted-foreground">Unsaved changes</span>
                )}
                {enregistree && (
                    <Button variant="outline" onClick={() => enregistrer(null)} disabled={isSaving}>
                        Use the organization&apos;s address
                    </Button>
                )}
                <Button onClick={() => enregistrer(adresse)} disabled={isSaving || !isDirty || incomplete}>
                    {isSaving ? "Saving..." : "Save Business Address"}
                </Button>
            </CardFooter>
        </Card>
    );
};
