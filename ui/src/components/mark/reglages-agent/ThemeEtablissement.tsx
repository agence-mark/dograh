"use client";

/**
 * [.mark] Theme « Établissement »: hours, address and voicemail of this agent
 * (convention § 2).
 *
 * Our opening hours and business address, and Dograh's « Voicemail &
 * Screening » rebuilt (D6 option B: Dograh's answer fields, LLM picker and the
 * same save rules -- the classifier instructions are stored only when they
 * differ from the built-in text, the provider only when the workflow LLM is
 * not used).
 *
 * « Use the organization's address » keeps its own button: it saves at once,
 * as it did on its card.
 */
import { Building2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
    AnswerSupervisorFields,
    isVoicemailMessageMissing,
    readAnswerSupervisorSettings,
} from "@/app/workflow/[workflowId]/components/AnswerSupervisorFields";
import type { AdresseEtablissement } from "@/client/types.gen";
import { LLMConfigSelector } from "@/components/LLMConfigSelector";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useOrgConfig } from "@/context/OrgConfigContext";
import { detailFromError } from "@/lib/apiError";
import {
    DEFAULT_VOICEMAIL_DETECTION_CONFIGURATION,
    type VoicemailDetectionConfiguration,
} from "@/types/workflow-configurations";

import { ChampAdresseEtablissement } from "../ChampAdresseEtablissement";
import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { memeAdresse, texteAdresse } from "../SectionAdresseEtablissement";
import { EXEMPLE_HORAIRES } from "../SectionHorairesOuverture";
import { RAPPEL_PUBLICATION_TEXTE, useEnregistrementTheme } from "./enregistrement";
import { nommerErreurs, type ProprietesThemeAgent, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_ETABLISSEMENT = "etablissement";
export const TITRE_ETABLISSEMENT = { en: "Business", fr: "Établissement" };

const lireMessagerie = (configurations: ProprietesThemeAgent["resolue"]): VoicemailDetectionConfiguration => ({
    ...DEFAULT_VOICEMAIL_DETECTION_CONFIGURATION,
    ...configurations.voicemail_detection,
});

export const ThemeEtablissement = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    consignesParDefaut,
}: ProprietesThemeAgent & { consignesParDefaut: string }) => {
    const { t } = useLangue();
    const { organizationPreferences } = useOrgConfig();
    const { afficher } = useRevelation(ouvrir);

    // ---- Opening hours -------------------------------------------------------
    const horairesEnregistres = resolue.horaires_ouverture ?? null;
    const [horaires, setHoraires] = useState<string>(horairesEnregistres ?? "");
    const [erreurHoraires, setErreurHoraires] = useState<string | null>(null);
    const horairesAEnregistrer = horaires.trim() || null;
    const horairesModifies = horairesAEnregistrer !== horairesEnregistres;

    // ---- Business address ----------------------------------------------------
    const adresseEnregistree = (resolue.adresse_etablissement ?? null) as AdresseEtablissement | null;
    const [adresse, setAdresse] = useState<AdresseEtablissement | null>(adresseEnregistree);
    const [adresseIncomplete, setAdresseIncomplete] = useState(false);
    const [erreurAdresse, setErreurAdresse] = useState<string | null>(null);
    const [retourOrganisation, setRetourOrganisation] = useState(false);
    const cleAdresse = JSON.stringify(adresseEnregistree);
    useEffect(() => {
        setAdresse(adresseEnregistree);
        setAdresseIncomplete(false);
        // After a save the draft follows the saved address, as the card did.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cleAdresse]);
    const adresseModifiee = !memeAdresse(adresse, adresseEnregistree);
    const adresseOrganisation = organizationPreferences?.adresse_etablissement ?? null;

    // ---- Voicemail & Screening (Dograh, rebuilt) ------------------------------
    const initiale = lireMessagerie(resolue);
    const [enabled, setEnabled] = useState(initiale.enabled);
    const [useWorkflowLlm, setUseWorkflowLlm] = useState(initiale.use_workflow_llm);
    const [provider, setProvider] = useState(initiale.provider || "openai");
    const [model, setModel] = useState(initiale.model || "gpt-4.1");
    const [apiKey, setApiKey] = useState(initiale.api_key || "");
    const savedPrompt = initiale.system_prompt;
    const [systemPrompt, setSystemPrompt] = useState(savedPrompt || "");
    const [promptEdited, setPromptEdited] = useState(false);
    // The defaults endpoint resolves after first paint. A workflow that saved its
    // own instructions keeps showing those; one that never did starts from the
    // built-in text so it can be edited rather than written from scratch.
    useEffect(() => {
        if (promptEdited) return;
        setSystemPrompt(savedPrompt || consignesParDefaut);
    }, [consignesParDefaut, promptEdited, savedPrompt]);
    const [answerSettings, setAnswerSettings] = useState(readAnswerSupervisorSettings(initiale));

    const messagerieModifiee = useMemo(() => {
        const init = lireMessagerie(resolue);
        return (
            enabled !== init.enabled
            || useWorkflowLlm !== init.use_workflow_llm
            || provider !== (init.provider || "openai")
            || model !== (init.model || "gpt-4.1")
            || apiKey !== (init.api_key || "")
            // Showing the built-in text is not a change; editing it is.
            || systemPrompt !== (init.system_prompt || consignesParDefaut)
            || JSON.stringify(answerSettings) !== JSON.stringify(readAnswerSupervisorSettings(init))
        );
    }, [enabled, useWorkflowLlm, provider, model, apiKey, systemPrompt, consignesParDefaut, answerSettings, resolue]);

    const configurationMessagerie = (): VoicemailDetectionConfiguration => ({
        ...answerSettings,
        enabled,
        use_workflow_llm: useWorkflowLlm,
        provider: useWorkflowLlm ? undefined : provider,
        model: useWorkflowLlm ? undefined : model,
        api_key: useWorkflowLlm ? undefined : apiKey,
        // Persist only instructions that differ from the built-in text, so a
        // workflow that never customized them keeps following platform updates.
        system_prompt:
            systemPrompt.trim() && systemPrompt.trim() !== consignesParDefaut.trim() ? systemPrompt.trim() : undefined,
    });

    // ---- The theme -------------------------------------------------------------
    const erreurs: Array<{ cle: string; libelle: Texte; message: Texte }> = [];
    if (adresseIncomplete) {
        erreurs.push({
            cle: "adresse_etablissement",
            libelle: { en: "Business address", fr: "Adresse de l'établissement" },
            message: { en: "Choose the town for this postal code before saving.", fr: "Choisissez la commune de ce code postal avant d'enregistrer." },
        });
    }
    if (enabled && isVoicemailMessageMissing(answerSettings)) {
        erreurs.push({
            cle: "voicemail_detection",
            libelle: { en: "Voicemail message", fr: "Message laissé sur la messagerie" },
            message: { en: "Enter a voicemail message or select a recording.", fr: "Saisissez un message ou choisissez un enregistrement." },
        });
    }

    const modifie = horairesModifies || adresseModifiee || adresseIncomplete || messagerieModifiee;
    useEtatTheme(ID_THEME_ETABLISSEMENT, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_ETABLISSEMENT,
        resolue,
        workflowName,
        onSave,
        parties: [
            {
                nom: { en: "Opening hours", fr: "Horaires d'ouverture" },
                modifie: horairesModifies,
                config: () => ({ horaires_ouverture: horairesAEnregistrer }),
                surEchec: setErreurHoraires,
            },
            {
                nom: { en: "Business address", fr: "Adresse de l'établissement" },
                modifie: adresseModifiee,
                config: () => ({ adresse_etablissement: adresse }),
                surEchec: setErreurAdresse,
            },
            {
                nom: { en: "Voicemail & Screening", fr: "Messagerie vocale et filtrage" },
                modifie: messagerieModifiee,
                config: () => ({ voicemail_detection: configurationMessagerie() }),
                apres: () => {
                    const envoyee = configurationMessagerie();
                    setSystemPrompt(envoyee.system_prompt || consignesParDefaut);
                    setPromptEdited(false);
                },
            },
        ],
    });

    const utiliserAdresseOrganisation = async () => {
        setRetourOrganisation(true);
        setErreurAdresse(null);
        try {
            await onSave({ ...resolue, adresse_etablissement: null }, workflowName);
            toast.success(`${t({ en: "Business address saved.", fr: "Adresse enregistrée." })} ${t(RAPPEL_PUBLICATION_TEXTE)}`);
        } catch (e) {
            const message = e instanceof Error && e.message ? e.message : detailFromError(e, "Business address not saved.");
            setErreurAdresse(message);
            toast.error(`${t({ en: "Business address not saved:", fr: "Adresse non enregistrée :" })} ${message}`);
        } finally {
            setRetourOrganisation(false);
        }
    };

    return (
        <Theme
            id={ID_THEME_ETABLISSEMENT}
            icone={Building2}
            titre={TITRE_ETABLISSEMENT}
            description={{ en: "Hours, address and voicemail of this agent.", fr: "Horaires, adresse et messagerie vocale de cet agent." }}
            resume={[
                horairesAEnregistrer ? t({ en: "Hours set", fr: "Horaires renseignés" }) : t({ en: "No hours", fr: "Aucun horaire" }),
                adresse ? t({ en: "Own address", fr: "Adresse propre" }) : t({ en: "Organization's address", fr: "Adresse de l'organisation" }),
                enabled && t({ en: "Voicemail handled", fr: "Messagerie gérée" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre id="etablissement-horaires" titre={{ en: "Opening Hours", fr: "Horaires d'ouverture" }}>
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "At the start of each call, the agent receives whether the business is open, on a break, closed or by appointment only, and when it reopens: etat_ouverture, reouverture, horaires_ouverture and annonce_ouverture. The last one is the ready-made sentence to say when picking up (« Nous sommes fermés en ce moment, nous rouvrons … »), empty when the business is reachable: paste {{initial_context.annonce_ouverture}} in the start node's greeting so the announcement no longer depends on the model. Leave the hours empty and nothing is computed.",
                        fr: "Au début de chaque appel, l'agent reçoit l'état (ouvert, en pause, fermé, sur rendez-vous) et la réouverture : etat_ouverture, reouverture, horaires_ouverture et annonce_ouverture. La dernière est la phrase toute prête à dire au décroché (« Nous sommes fermés en ce moment, nous rouvrons … »), vide quand l'entreprise est joignable : collez {{initial_context.annonce_ouverture}} dans l'accueil du nœud de départ pour que l'annonce ne dépende plus du modèle. Sans horaires, rien n'est calculé.",
                    })}
                </p>
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "The WORDS of that sentence, and a state forced by hand for the whole business, are set once for the organization:",
                        fr: "Les MOTS de cette phrase, et un état forcé à la main pour toute l'entreprise, se règlent une fois pour l'organisation :",
                    })}{" "}
                    <Link href="/settings" className="underline">
                        {t({ en: "Platform Settings → Closed-business announcement", fr: "Paramètres de la plateforme → Annonce de fermeture" })}
                    </Link>
                    .{" "}
                    {t({
                        en: "The hours below stay on this agent, because they describe one place.",
                        fr: "Les horaires ci-dessous restent sur cet agent, parce qu'ils décrivent un lieu.",
                    })}
                </p>
                <ChampReglage
                    cle="horaires_ouverture"
                    idControle="horaires_ouverture"
                    libelle={{ en: "Opening hours, written in French", fr: "Horaires d'ouverture, écrits en français" }}
                    aides={[
                        {
                            en: "One line per day, all seven required. A day is fermé or one or more ranges (10:00-12:30 et 14:00-18:30, 10h-12h30). Add sur rendez-vous at the end of a day for appointment-only hours. Public holidays are closed unless a jours fériés line says otherwise. Under exceptions :, one date (24/12/2026, or 25/12 every year) or period (du … au …) per line; an exception wins over holidays and weekdays. Paris time.",
                            fr: "Une ligne par jour, les sept obligatoires. Un jour est « fermé » ou une ou plusieurs plages (10:00-12:30 et 14:00-18:30, 10h-12h30). Ajoutez « sur rendez-vous » en fin de jour pour des horaires sur rendez-vous. Les jours fériés sont fermés sauf ligne « jours fériés ». Sous « exceptions : », une date (24/12/2026, ou 25/12 chaque année) ou une période (du … au …) par ligne ; une exception l'emporte sur les fériés et les jours de la semaine. Heure de Paris.",
                        },
                    ]}
                    erreur={erreurHoraires ? { en: erreurHoraires, fr: erreurHoraires } : null}
                >
                    <Textarea
                        id="horaires_ouverture"
                        className="font-mono text-xs"
                        rows={14}
                        maxLength={4000}
                        placeholder={EXEMPLE_HORAIRES}
                        aria-invalid={erreurHoraires ? true : undefined}
                        value={horaires}
                        onChange={(e) => {
                            setHoraires(e.target.value);
                            setErreurHoraires(null);
                        }}
                    />
                </ChampReglage>
                <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">{EXEMPLE_HORAIRES}</pre>
            </Intertitre>

            <Intertitre id="etablissement-adresse" titre={{ en: "Business address for this agent", fr: "Adresse de cet agent" }}>
                <ChampReglage
                    cle="adresse_etablissement"
                    libelle={{ en: "Business address", fr: "Adresse de l'établissement" }}
                    aides={[
                        {
                            en: "Leave empty to use the organization's address. Given to the agent as {{adresse_etablissement}}, and used to recognise the towns callers name; the street is not.",
                            fr: "Vide : l'agent utilise l'adresse de l'organisation. Donnée à l'agent comme {{adresse_etablissement}}, et utilisée pour reconnaître les communes citées ; la rue ne l'est pas.",
                        },
                    ]}
                >
                    <p className="text-xs text-muted-foreground">
                        {t({ en: "Organization's address:", fr: "Adresse de l'organisation :" })}{" "}
                        <span className="text-foreground">
                            {adresseOrganisation ? texteAdresse(adresseOrganisation) : t({ en: "none set", fr: "aucune" })}
                        </span>
                    </p>
                    <ChampAdresseEtablissement
                        id="agent-business-address"
                        enregistree={adresseEnregistree}
                        erreur={erreurAdresse}
                        desactive={enCours || retourOrganisation}
                        onChange={(valeur, estIncomplete) => {
                            setAdresse(valeur);
                            setAdresseIncomplete(estIncomplete);
                            setErreurAdresse(null);
                        }}
                    />
                    {adresseIncomplete && (
                        <p className="text-xs text-muted-foreground">
                            {t({ en: "Choose the town for this postal code before saving.", fr: "Choisissez la commune de ce code postal avant d'enregistrer." })}
                        </p>
                    )}
                    {adresseEnregistree && (
                        <div>
                            <Button variant="outline" size="sm" onClick={utiliserAdresseOrganisation} disabled={enCours || retourOrganisation}>
                                {t({ en: "Use the organization's address", fr: "Utiliser l'adresse de l'organisation" })}
                            </Button>
                        </div>
                    )}
                </ChampReglage>
            </Intertitre>

            <Intertitre
                id="etablissement-messagerie"
                titre={{ en: "Voicemail & Screening", fr: "Messagerie vocale et filtrage" }}
                description={{
                    en: "Choose how the agent handles voicemail and call screening. Applies to outbound calls with separate speech and language models. These settings do not apply to realtime speech-to-speech models. Support for realtime models is coming soon.",
                    fr: "Comment l'agent traite la messagerie vocale et le filtrage d'appel. Pour les appels sortants avec des modèles de parole et de langage séparés. Sans effet sur les modèles temps réel (prise en charge annoncée).",
                }}
            >
                <div id="reglage-voicemail_detection" data-reglage="voicemail_detection" className="space-y-4">
                    <div className="flex items-center space-x-2 rounded-md border bg-muted/20 p-2">
                        <Switch id="voicemail-enabled" checked={enabled} onCheckedChange={setEnabled} />
                        <Label htmlFor="voicemail-enabled">
                            {t({ en: "Enable voicemail and screening handling", fr: "Gérer la messagerie vocale et le filtrage d'appel" })}
                        </Label>
                        <code className="text-[11px] text-muted-foreground/80">voicemail_detection</code>
                    </div>
                    {enabled && (
                        <>
                            <AnswerSupervisorFields value={answerSettings} onChange={setAnswerSettings} />
                            <details className="rounded-md border p-3">
                                <summary className="cursor-pointer text-sm font-medium">
                                    {t({ en: "Classification model", fr: "Modèle de classification" })}
                                </summary>
                                <div className="mt-3 space-y-3">
                                    <div className="flex items-center space-x-2 rounded-md border bg-muted/20 p-2">
                                        <Switch id="voicemail-use-workflow-llm" checked={useWorkflowLlm} onCheckedChange={setUseWorkflowLlm} />
                                        <Label htmlFor="voicemail-use-workflow-llm">{t({ en: "Use Workflow LLM", fr: "Utiliser le cerveau de l'agent" })}</Label>
                                        <Label className="ml-2 text-xs text-muted-foreground">
                                            {t({ en: "Use the LLM configured in your account settings.", fr: "Utilise le modèle configuré dans les réglages du compte." })}
                                        </Label>
                                    </div>
                                    {!useWorkflowLlm && (
                                        <LLMConfigSelector
                                            provider={provider}
                                            onProviderChange={setProvider}
                                            model={model}
                                            onModelChange={setModel}
                                            apiKey={apiKey}
                                            onApiKeyChange={setApiKey}
                                        />
                                    )}
                                    <div className="space-y-2">
                                        <Label htmlFor="voicemail-system-prompt">{t({ en: "Classifier instructions", fr: "Consignes du classificateur" })}</Label>
                                        <Textarea
                                            id="voicemail-system-prompt"
                                            disabled={enCours}
                                            rows={6}
                                            maxLength={8000}
                                            value={systemPrompt}
                                            placeholder={t({ en: "Leave blank to use the built-in instructions.", fr: "Vide : consignes intégrées." })}
                                            onChange={(e) => {
                                                setPromptEdited(true);
                                                setSystemPrompt(e.target.value);
                                            }}
                                        />
                                        <p className="text-xs text-muted-foreground">
                                            {t({
                                                en: "These instructions decide whether the answering party is a person, a voicemail, a screening service or an IVR menu. Edit them when your calls are not in English: describe the greetings and carrier announcements your callers actually hear. Leave them unchanged to keep following the built-in instructions as they improve; clear the box to go back to them. The reply must be a single label — CONVERSATION, VOICEMAIL, NO_MESSAGE, SCREENER, SCREENING_WAIT, IVR or UNKNOWN. Anything else is read as UNKNOWN, which lets the call through to the agent, so instructions that only answer CONVERSATION or VOICEMAIL will silently disable screening and IVR handling.",
                                                fr: "Ces consignes décident si l'on parle à une personne, une messagerie, un service de filtrage ou un serveur vocal. À adapter quand les appels ne sont pas en anglais : décrivez les accueils et annonces d'opérateur que vos appelants entendent vraiment. Inchangées, elles suivent les consignes intégrées à mesure qu'elles s'améliorent ; vider la zone y revient. La réponse doit être une seule étiquette : CONVERSATION, VOICEMAIL, NO_MESSAGE, SCREENER, SCREENING_WAIT, IVR ou UNKNOWN. Toute autre réponse est lue comme UNKNOWN, qui laisse passer l'appel vers l'agent : des consignes qui ne répondent que CONVERSATION ou VOICEMAIL désactivent sans bruit le filtrage et les serveurs vocaux.",
                                            })}
                                        </p>
                                    </div>
                                </div>
                            </details>
                        </>
                    )}
                </div>
            </Intertitre>
        </Theme>
    );
};
