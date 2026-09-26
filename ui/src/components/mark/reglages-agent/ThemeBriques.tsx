"use client";

/**
 * [.mark] Theme « Briques »: the brain, transcription and voice of this agent
 * (convention § 2).
 *
 * Dograh's « Model Overrides » card rebuilt (option B of D6): the switch that
 * gives the agent its own complete configuration -- the BYOK editor then shows
 * IN the theme, exactly as on the organization's Models screen, never in a
 * dialog (D4) -- or, switch off, our per-service override. This theme keeps
 * the buttons of what it contains (convention E6): each already saves at once.
 */
import { Cpu, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import type {
    ModelConfigurationPricingResponse,
    OrganizationAiModelConfigurationResponse,
    OrganizationAiModelConfigurationV2,
} from "@/client/types.gen";
import { AIModelConfigurationV2Editor, type ModelConfigurationDefaultsV2 } from "@/components/AIModelConfigurationV2Editor";
import { PerServiceModelOverride } from "@/components/mark/PerServiceModelOverride";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SETTINGS_DOCUMENTATION_URLS } from "@/constants/documentation";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { RAPPEL_PUBLICATION_TEXTE } from "./enregistrement";
import { type ProprietesThemeAgent, useEtatTheme } from "./theme-commun";

export const ID_THEME_BRIQUES = "briques";
export const TITRE_BRIQUES = { en: "Services", fr: "Briques" };

function withoutModelConfigurationOverrides(configurations: WorkflowConfigurations): WorkflowConfigurations {
    const next = { ...configurations };
    delete next.model_overrides;
    delete next.model_configuration_v2_override;
    return next;
}

export interface ConfigurationDesModeles {
    defaults: ModelConfigurationDefaultsV2 | null;
    organisation: OrganizationAiModelConfigurationResponse | null;
    tarifs: ModelConfigurationPricingResponse | null;
    chargement: boolean;
    erreur: string | null;
}

export const ThemeBriques = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    modeles,
}: ProprietesThemeAgent & { modeles: ConfigurationDesModeles }) => {
    const { t } = useLangue();
    const rappel = t(RAPPEL_PUBLICATION_TEXTE);
    const savedV2Override = resolue.model_configuration_v2_override;
    const hasSavedModelOverride = Boolean(savedV2Override || resolue.model_overrides);
    const [overrideEnabled, setOverrideEnabled] = useState(Boolean(savedV2Override));
    const [isRemovingOverride, setIsRemovingOverride] = useState(false);

    useEffect(() => {
        setOverrideEnabled(Boolean(resolue.model_configuration_v2_override));
    }, [resolue.model_configuration_v2_override]);

    // No theme button: its parts save at once. It has nothing unsaved to show.
    useEtatTheme(ID_THEME_BRIQUES, false, false);

    const hasOrgConfiguration = modeles.organisation?.source === "organization_v2";

    const saveV2Override = async (configuration: OrganizationAiModelConfigurationV2) => {
        const nextConfigurations = withoutModelConfigurationOverrides(resolue);
        nextConfigurations.model_configuration_v2_override = configuration;
        await onSave(nextConfigurations, workflowName);
        toast.success(`${t({ en: "Model override saved.", fr: "Configuration propre à l'agent enregistrée." })} ${rappel}`);
    };

    const removeV2Override = async () => {
        setIsRemovingOverride(true);
        try {
            await onSave(withoutModelConfigurationOverrides(resolue), workflowName);
            setOverrideEnabled(false);
            toast.success(`${t({ en: "Organization model configuration saved.", fr: "Configuration de l'organisation enregistrée." })} ${rappel}`);
        } finally {
            setIsRemovingOverride(false);
        }
    };

    return (
        <Theme
            id={ID_THEME_BRIQUES}
            icone={Cpu}
            titre={TITRE_BRIQUES}
            description={{ en: "The brain, transcription and voice of this agent.", fr: "Le cerveau, la transcription et la voix de cet agent." }}
            resume={[
                savedV2Override
                    ? t({ en: "Own complete configuration", fr: "Configuration complète propre à l'agent" })
                    : t({ en: "Organization configuration", fr: "Configuration de l'organisation" }),
                !savedV2Override && Boolean(resolue.model_overrides) && t({ en: "services overridden", fr: "services remplacés" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={false}
            erreurs={[]}
        >
            <p className="text-xs text-muted-foreground">
                {t({
                    en: "Override the full organization model configuration for this workflow.",
                    fr: "Remplacer toute la configuration des modèles de l'organisation pour cet agent.",
                })}{" "}
                <a href={SETTINGS_DOCUMENTATION_URLS.modelOverrides} target="_blank" rel="noopener noreferrer" className="underline">
                    {t({ en: "Learn more", fr: "En savoir plus" })}
                </a>
            </p>

            {modeles.chargement && (
                <div className="flex items-center gap-2 rounded-md border p-4 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t({ en: "Loading model configuration", fr: "Chargement de la configuration des modèles" })}
                </div>
            )}

            {modeles.erreur && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {modeles.erreur}
                </div>
            )}

            {!modeles.chargement && !modeles.erreur && !hasOrgConfiguration && (
                <div className="flex flex-col gap-3 rounded-md border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm text-muted-foreground">
                        {t({
                            en: "Set up your organization model configuration before overriding it per workflow.",
                            fr: "Configurez d'abord les modèles de l'organisation avant de les remplacer pour un agent.",
                        })}
                    </p>
                    <Button type="button" variant="outline" size="sm" asChild>
                        <Link href="/model-configurations">{t({ en: "Configure Models", fr: "Configurer les modèles" })}</Link>
                    </Button>
                </div>
            )}

            {!modeles.chargement && !modeles.erreur && hasOrgConfiguration && modeles.defaults && modeles.organisation && (
                <>
                    <Intertitre id="briques-complete" titre={{ en: "Complete configuration", fr: "Configuration complète" }}>
                        <div className="flex items-center justify-between rounded-md border p-4" data-reglage="model_configuration_v2_override">
                            <div className="space-y-0.5">
                                <Label htmlFor="workflow-model-v2-override" className="text-sm font-medium">
                                    {t({ en: "Override for this workflow", fr: "Remplacer toute la configuration pour cet agent" })}{" "}
                                    <code className="text-[11px] font-normal text-muted-foreground/80">model_configuration_v2_override</code>
                                </Label>
                                <p className="text-xs text-muted-foreground">
                                    {overrideEnabled
                                        ? t({
                                              en: "This workflow uses its own complete model configuration.",
                                              fr: "Cet agent utilise sa propre configuration complète des modèles.",
                                          })
                                        : t({
                                              en: "This workflow uses the organization model configuration.",
                                              fr: "Cet agent utilise la configuration des modèles de l'organisation.",
                                          })}
                                </p>
                            </div>
                            <Switch id="workflow-model-v2-override" checked={overrideEnabled} onCheckedChange={setOverrideEnabled} />
                        </div>

                        {overrideEnabled && (
                            <AIModelConfigurationV2Editor
                                defaults={modeles.defaults}
                                configuration={
                                    (savedV2Override as OrganizationAiModelConfigurationV2 | undefined)
                                    || (modeles.organisation.configuration as OrganizationAiModelConfigurationV2 | null)
                                }
                                effectiveConfiguration={savedV2Override ? null : modeles.organisation.effective_configuration}
                                pricing={modeles.tarifs}
                                submitLabel={t({ en: "Save Model Override", fr: "Enregistrer la configuration de l'agent" })}
                                onSave={saveV2Override}
                            />
                        )}
                    </Intertitre>

                    {!overrideEnabled && (
                        <Intertitre id="briques-services" titre={{ en: "Override individual services", fr: "Remplacer certains services seulement" }}>
                            <p className="text-sm text-muted-foreground">
                                {t({ en: "Using organization model configuration.", fr: "Utilise la configuration des modèles de l'organisation." })}
                            </p>
                            <PerServiceModelOverride
                                workflowConfigurations={resolue}
                                workflowName={workflowName}
                                onSave={onSave}
                                publishReminder={rappel}
                            />
                            {hasSavedModelOverride && (
                                <Button type="button" onClick={removeV2Override} disabled={isRemovingOverride}>
                                    {isRemovingOverride
                                        ? t({ en: "Saving...", fr: "Enregistrement..." })
                                        : t({ en: "Save Organization Configuration", fr: "Revenir à la configuration de l'organisation" })}
                                </Button>
                            )}
                        </Intertitre>
                    )}
                </>
            )}
        </Theme>
    );
};
