"use client";

/**
 * [.mark] Theme « Données de l'appel »: what the agent writes down, and what is
 * kept or passed on (convention § 2).
 *
 * Our call record, and -- rebuilt from Dograh's « General » (D6 option B) --
 * the call disposition (Dograh's own editor, reused as it is), the
 * timestamped transcript, context compaction and the external PBX. The two PBX
 * lists move into dialogs edited directly and closed with « Done »
 * (convention E4); what they send is what « General » sent: the mappings as
 * typed, the lead fields trimmed.
 */
import { ClipboardList, Plus, Trash2Icon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
    CallDispositionEditor,
    type CallDispositionRow,
    createCallDispositionRows,
    normalizeCallDispositions,
    validateCallDispositionRows,
} from "@/app/workflow/[workflowId]/settings/components/CallDispositionEditor";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useOrgConfig } from "@/context/OrgConfigContext";
import type { CallDispositionOption, ChampFiche, ExternalPBXFieldMapping } from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { AIDES_FICHE, EditeurChampsFiche, pourComparerLaFiche, texteErreursDesChamps } from "../SectionFiche";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, nommerErreurs, type ProprietesThemeAgent, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_DONNEES = "donnees";
export const TITRE_DONNEES = { en: "Call data", fr: "Données de l'appel" };

const NOM_DE_CHAMP_PBX = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

export const ThemeDonnees = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    issuesParDefaut,
}: ProprietesThemeAgent & { issuesParDefaut: CallDispositionOption[] }) => {
    const { t } = useLangue();
    const { externalPbxIntegrationsEnabled } = useOrgConfig();
    const { afficher } = useRevelation(ouvrir);

    // ---- The call record ---------------------------------------------------
    const ficheActiveEnregistree = resolue.fiche_au_fil_de_leau ?? false;
    const champsEnregistres = useMemo(() => (resolue.fiche_champs ?? []) as ChampFiche[], [resolue.fiche_champs]);
    const [ficheActive, setFicheActive] = useState(ficheActiveEnregistree);
    const [champs, setChamps] = useState<ChampFiche[]>(champsEnregistres);
    const ficheModifiee =
        ficheActive !== ficheActiveEnregistree
        || JSON.stringify(pourComparerLaFiche(champs)) !== JSON.stringify(pourComparerLaFiche(champsEnregistres));
    const erreursFiche = texteErreursDesChamps(champs);
    // As the call record card did (24/09): follow the record the server stored,
    // keyed on its CONTENT so another theme's save does not wipe an edit here.
    const ficheEnregistree = JSON.stringify([ficheActiveEnregistree, champsEnregistres]);
    useEffect(() => {
        const [actifRelu, champsRelus] = JSON.parse(ficheEnregistree) as [boolean, ChampFiche[]];
        setFicheActive(actifRelu);
        setChamps(champsRelus);
    }, [ficheEnregistree]);

    // ---- Dograh's « General » parts ------------------------------------------
    const [lignesIssues, setLignesIssues] = useState<CallDispositionRow[]>(() => createCallDispositionRows(resolue.call_dispositions));
    const issuesNormalisees = useMemo(() => normalizeCallDispositions(lignesIssues), [lignesIssues]);
    const issuesValides = useMemo(() => validateCallDispositionRows(lignesIssues).isValid, [lignesIssues]);
    const issuesModifiees = differe(issuesNormalisees, resolue.call_dispositions);

    const horodateeEnregistree = resolue.transcript_configuration?.include_end_timestamps ?? false;
    const [horodatee, setHorodatee] = useState(horodateeEnregistree);
    const [compaction, setCompaction] = useState(resolue.context_compaction_enabled);

    const [correspondances, setCorrespondances] = useState<ExternalPBXFieldMapping[]>(resolue.external_pbx_field_mappings);
    const [champsProspect, setChampsProspect] = useState<string[]>(resolue.external_pbx_lead_headers);
    const [fenetre, setFenetre] = useState<"correspondance" | "prospect" | null>(null);
    const correspondancesValides = correspondances.every(
        (m) => Boolean(m.context_path.trim()) && NOM_DE_CHAMP_PBX.test(m.destination_field.trim()),
    );
    const champsProspectValides = champsProspect.every((champ) => NOM_DE_CHAMP_PBX.test(champ.trim()));
    const pbxModifie =
        differe(correspondances, resolue.external_pbx_field_mappings) || differe(champsProspect, resolue.external_pbx_lead_headers);

    const generalModifie =
        issuesModifiees || horodatee !== horodateeEnregistree || compaction !== resolue.context_compaction_enabled || pbxModifie;

    const erreurs: Array<{ cle: string; libelle: Texte; message: Texte }> = [];
    if (Object.keys(erreursFiche).length > 0) {
        erreurs.push({
            cle: "fiche_champs",
            libelle: { en: "Call record fields", fr: "Champs de la fiche" },
            message: {
                en: "a field has a problem: open the fields to fix it.",
                fr: "un champ a un problème : ouvrez les champs pour le corriger.",
            },
        });
    }
    if (!issuesValides) {
        erreurs.push({
            cle: "call_dispositions",
            libelle: { en: "Call disposition", fr: "Issue de l'appel" },
            message: { en: "an option is not valid.", fr: "une option n'est pas valide." },
        });
    }
    if (externalPbxIntegrationsEnabled && !correspondancesValides) {
        erreurs.push({
            cle: "external_pbx_field_mappings",
            libelle: { en: "Field Mappings", fr: "Correspondance des champs" },
            message: {
                en: "each mapping needs a context field and a destination field containing only letters, numbers, and underscores.",
                fr: "chaque correspondance demande un champ recueilli et un champ de destination fait de lettres, chiffres et _.",
            },
        });
    }
    if (externalPbxIntegrationsEnabled && !champsProspectValides) {
        erreurs.push({
            cle: "external_pbx_lead_headers",
            libelle: { en: "Lead Fields To Capture", fr: "Champs du prospect à lire" },
            message: {
                en: "each lead field must start with a letter and contain only letters, numbers, and underscores.",
                fr: "chaque champ doit commencer par une lettre et ne contenir que lettres, chiffres et _.",
            },
        });
    }

    const modifie = ficheModifiee || generalModifie;
    useEtatTheme(ID_THEME_DONNEES, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_DONNEES,
        resolue,
        workflowName,
        onSave,
        parties: [
            {
                nom: { en: "Call record", fr: "Fiche d'appel" },
                modifie: ficheModifiee,
                config: () => ({ fiche_au_fil_de_leau: ficheActive, fiche_champs: champs }),
            },
            {
                nom: { en: "Call data settings", fr: "Réglages des données de l'appel" },
                modifie: generalModifie,
                config: () => ({
                    call_dispositions: issuesNormalisees,
                    transcript_configuration: {
                        ...(resolue.transcript_configuration ?? {}),
                        include_end_timestamps: horodatee,
                    },
                    context_compaction_enabled: compaction,
                    external_pbx_field_mappings: correspondances,
                    external_pbx_lead_headers: champsProspect.map((champ) => champ.trim()),
                }),
                apres: () => {
                    // What « General » did: keep the rows (and their ids), take the
                    // normalized values that were sent.
                    const envoyees = issuesNormalisees;
                    setLignesIssues((courantes) => courantes.map((ligne, i) => ({ ...ligne, ...envoyees[i] })));
                    setChampsProspect((courants) => courants.map((champ) => champ.trim()));
                },
            },
        ],
    });

    return (
        <Theme
            id={ID_THEME_DONNEES}
            icone={ClipboardList}
            titre={TITRE_DONNEES}
            description={{ en: "What the agent writes down, and what is kept or passed on.", fr: "Ce que l'agent note, et ce qui est conservé ou transmis." }}
            resume={[
                ficheActive
                    ? `${t({ en: "Record", fr: "Fiche" })} · ${champs.length} ${t({ en: "fields", fr: "champs" })}`
                    : t({ en: "Record off", fr: "Fiche éteinte" }),
                lignesIssues.length > 0
                    ? `${lignesIssues.length} ${t({ en: "dispositions", fr: "issues" })}`
                    : t({ en: "Dispositions off", fr: "Issues non extraites" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre id="donnees-fiche" titre={{ en: "Call record", fr: "Fiche d'appel" }}>
                <ChampReglage
                    cle="fiche_au_fil_de_leau"
                    idControle="fiche_au_fil_de_leau"
                    libelle={{ en: "Fill the call record with a tool", fr: "Remplir la fiche avec un outil" }}
                    aides={[
                        {
                            en: "Let the agent write and correct the call record at any moment of the call, whatever the step, with one tool: noter_information.",
                            fr: "L'agent écrit et corrige la fiche à tout moment de l'appel, quelle que soit l'étape, avec un seul outil : noter_information.",
                        },
                        ...AIDES_FICHE,
                    ]}
                    disposition="ligne"
                >
                    <Switch id="fiche_au_fil_de_leau" checked={ficheActive} onCheckedChange={setFicheActive} />
                </ChampReglage>
                <div id="reglage-fiche_champs" data-reglage="fiche_champs" className="space-y-2">
                    <EditeurChampsFiche actif={ficheActive} champs={champs} onChange={setChamps} />
                </div>
            </Intertitre>

            <Intertitre id="donnees-issue" titre={{ en: "Call disposition", fr: "Issue de l'appel" }}>
                <div id="reglage-call_dispositions" data-reglage="call_dispositions">
                    <CallDispositionEditor rows={lignesIssues} onChange={setLignesIssues} defaultDispositions={issuesParDefaut} />
                </div>
            </Intertitre>

            <Intertitre
                id="donnees-transcription"
                titre={{ en: "Transcript", fr: "Transcription horodatée" }}
                description={{
                    en: "Include start and stop timestamps for each speaker in the uploaded transcript.",
                    fr: "Ajoute l'heure de début et de fin de chaque réplique dans la transcription envoyée.",
                }}
            >
                <ChampReglage
                    cle="transcript_configuration.include_end_timestamps"
                    idControle="transcript-end-timestamps-enabled"
                    libelle={{ en: "Enhanced Timestamped Transcript", fr: "Transcription horodatée enrichie" }}
                    disposition="ligne"
                >
                    <Switch id="transcript-end-timestamps-enabled" checked={horodatee} onCheckedChange={setHorodatee} />
                </ChampReglage>
                <div className="rounded-md border bg-muted/20 p-3">
                    <pre className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                        {`[2026-07-06T10:00:00.000Z -> 2026-07-06T10:00:04.800Z] assistant: Can you confirm your date of birth?
[2026-07-06T10:00:06.200Z -> 2026-07-06T10:00:08.700Z] user: January fifth, nineteen ninety.`}
                    </pre>
                </div>
            </Intertitre>

            <Intertitre id="donnees-compaction" titre={{ en: "Context Compaction", fr: "Compaction du contexte" }}>
                <ChampReglage
                    cle="context_compaction_enabled"
                    idControle="context-compaction-enabled"
                    libelle={{ en: "Enable Context Compaction", fr: "Activer la compaction du contexte" }}
                    aides={[
                        {
                            en: "Automatically summarize conversation context when transitioning between nodes. Not applicable in Realtime mode - the speech-to-speech service manages its own conversation state and this setting is ignored.",
                            fr: "Résume automatiquement le contexte de la conversation au passage d'une étape à l'autre. Sans objet en mode temps réel : le service parole à parole gère son propre état et ce réglage y est ignoré.",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch id="context-compaction-enabled" checked={compaction} onCheckedChange={setCompaction} />
                </ChampReglage>
            </Intertitre>

            {externalPbxIntegrationsEnabled ? (
                <Intertitre
                    id="donnees-pbx"
                    titre={{ en: "External PBX Field Updates", fr: "Standard externe" }}
                    description={{
                        en: "Optionally copy final gathered-context values into provider-native fields before transfer or hangup.",
                        fr: "Recopie, si besoin, les valeurs recueillies dans les champs du standard avant un transfert ou un raccrochage.",
                    }}
                >
                    <ChampReglage cle="external_pbx_field_mappings" libelle={{ en: "Field Mappings", fr: "Correspondance des champs" }}>
                        <div className="flex items-center justify-between gap-3 rounded border p-3 text-sm">
                            <span>
                                {correspondances.length} {t({ en: "mappings", fr: "correspondances" })}
                            </span>
                            <Button variant="outline" size="sm" onClick={() => setFenetre("correspondance")}>
                                {t({ en: "Edit field mappings", fr: "Modifier la correspondance" })}
                            </Button>
                        </div>
                    </ChampReglage>
                    <ChampReglage cle="external_pbx_lead_headers" libelle={{ en: "Lead Fields To Capture", fr: "Champs du prospect à lire" }}>
                        <div className="flex items-center justify-between gap-3 rounded border p-3 text-sm">
                            <span>
                                {champsProspect.length} {t({ en: "fields", fr: "champs" })}
                            </span>
                            <Button variant="outline" size="sm" onClick={() => setFenetre("prospect")}>
                                {t({ en: "Edit lead fields", fr: "Modifier les champs du prospect" })}
                            </Button>
                        </div>
                    </ChampReglage>
                </Intertitre>
            ) : (
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "External PBX only appears when « External PBX integrations » is on in the platform settings.",
                        fr: "Le standard externe n'apparaît que si « Intégrations de standard externe » est allumé dans les paramètres de l'organisation.",
                    })}
                </p>
            )}

            <Dialog open={fenetre === "correspondance"} onOpenChange={(o) => setFenetre(o ? "correspondance" : null)}>
                <DialogContent className="sm:max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>{t({ en: "Field Mappings", fr: "Correspondance des champs" })}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: "Optionally copy final gathered-context values into provider-native fields before transfer or hangup.",
                                fr: "Recopie, si besoin, les valeurs recueillies dans les champs du standard avant un transfert ou un raccrochage.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2">
                        <div className="flex justify-end">
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setCorrespondances((courantes) => [...courantes, { context_path: "", destination_field: "" }])}
                            >
                                <Plus className="mr-1 h-4 w-4" /> {t({ en: "Add mapping", fr: "Ajouter une correspondance" })}
                            </Button>
                        </div>
                        {correspondances.map((mapping, index) => (
                            <div key={index} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                                <Input
                                    aria-label={`Gathered context field ${index + 1}`}
                                    value={mapping.context_path}
                                    onChange={(event) =>
                                        setCorrespondances((courantes) =>
                                            courantes.map((item, i) => (i === index ? { ...item, context_path: event.target.value } : item)),
                                        )
                                    }
                                    placeholder="qualified"
                                />
                                <Input
                                    aria-label={`External PBX destination field ${index + 1}`}
                                    value={mapping.destination_field}
                                    onChange={(event) =>
                                        setCorrespondances((courantes) =>
                                            courantes.map((item, i) => (i === index ? { ...item, destination_field: event.target.value } : item)),
                                        )
                                    }
                                    placeholder="address3"
                                />
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    aria-label={`Remove external PBX field mapping ${index + 1}`}
                                    onClick={() => setCorrespondances((courantes) => courantes.filter((_, i) => i !== index))}
                                >
                                    <Trash2Icon className="h-4 w-4" />
                                </Button>
                            </div>
                        ))}
                        {correspondances.length === 0 && (
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "No external fields will be updated. Context names may be direct extracted-variable names or paths such as extracted_variables.qualified.",
                                    fr: "Aucun champ externe ne sera mis à jour. Un nom recueilli peut être un nom de variable extraite ou un chemin comme extracted_variables.qualified.",
                                })}
                            </p>
                        )}
                        {!correspondancesValides && (
                            <p className="text-xs text-destructive">
                                {t({
                                    en: "Each mapping needs a context field and a destination field containing only letters, numbers, and underscores.",
                                    fr: "Chaque correspondance demande un champ recueilli et un champ de destination fait de lettres, chiffres et _.",
                                })}
                            </p>
                        )}
                    </div>
                    <DialogFooter>
                        <Button onClick={() => setFenetre(null)}>{t({ en: "Done", fr: "Terminé" })}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={fenetre === "prospect"} onOpenChange={(o) => setFenetre(o ? "prospect" : null)}>
                <DialogContent className="sm:max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>{t({ en: "Lead Fields To Capture", fr: "Champs du prospect à lire" })}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: "Extra lead fields to read from the inbound call, named without the header prefix (first_name reads X-VICIDIAL-first_name). Captured values are addressable in prompts as {{initial_context.external_pbx_call.lead.<field>}}. Each field adds one request during call setup, so list only what the agent uses.",
                                fr: "Champs du prospect à lire sur l'appel entrant, nommés sans le préfixe de l'en-tête (first_name lit X-VICIDIAL-first_name). Les valeurs lues s'utilisent dans les prompts comme {{initial_context.external_pbx_call.lead.<champ>}}. Chaque champ ajoute une requête à l'établissement de l'appel : ne lister que ce que l'agent utilise.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2">
                        <div className="flex justify-end">
                            <Button type="button" variant="outline" size="sm" onClick={() => setChampsProspect((courants) => [...courants, ""])}>
                                <Plus className="mr-1 h-4 w-4" /> {t({ en: "Add field", fr: "Ajouter un champ" })}
                            </Button>
                        </div>
                        {champsProspect.map((champ, index) => (
                            <div key={index} className="grid grid-cols-[1fr_auto] gap-2">
                                <Input
                                    aria-label={`External PBX lead field ${index + 1}`}
                                    value={champ}
                                    onChange={(event) =>
                                        setChampsProspect((courants) => courants.map((item, i) => (i === index ? event.target.value : item)))
                                    }
                                    placeholder="first_name"
                                />
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    aria-label={`Remove external PBX lead field ${index + 1}`}
                                    onClick={() => setChampsProspect((courants) => courants.filter((_, i) => i !== index))}
                                >
                                    <Trash2Icon className="h-4 w-4" />
                                </Button>
                            </div>
                        ))}
                        {champsProspect.length === 0 && (
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "Only the identity fields needed to transfer or hang up the call are captured.",
                                    fr: "Seuls les champs d'identité nécessaires au transfert ou au raccrochage sont lus.",
                                })}
                            </p>
                        )}
                        {!champsProspectValides && (
                            <p className="text-xs text-destructive">
                                {t({
                                    en: "Each lead field must start with a letter and contain only letters, numbers, and underscores.",
                                    fr: "Chaque champ doit commencer par une lettre et ne contenir que lettres, chiffres et _.",
                                })}
                            </p>
                        )}
                    </div>
                    <DialogFooter>
                        <Button onClick={() => setFenetre(null)}>{t({ en: "Done", fr: "Terminé" })}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Theme>
    );
};
