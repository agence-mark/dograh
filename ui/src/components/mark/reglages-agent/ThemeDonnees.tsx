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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useOrgConfig } from "@/context/OrgConfigContext";
import type {
    CallDispositionOption,
    ChampFiche,
    ExternalPBXFieldMapping,
    FicheModeDeNote,
    GreffierLlm,
} from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { AIDES_FICHE, EditeurChampsFiche, pourComparerLaFiche, texteErreursDesChamps } from "../SectionFiche";
import {
    CONSIGNE_GENERIQUE_GREFFIER,
    fournisseurDuGreffier,
    FOURNISSEURS_AVEC_TEMPERATURE,
    NOMS_AVEC_TEMPERATURE,
} from "./consigne-greffier";
import { useEnregistrementTheme } from "./enregistrement";
import { champsInvalides, lireApresAppel, pourEnvoyer, SectionApresAppelAgent } from "./SectionApresAppelAgent";
import { differe, nommerErreurs, type ProprietesThemeAgent, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_DONNEES = "donnees";
export const TITRE_DONNEES = { en: "Call data", fr: "Données de l'appel" };

const NOM_DE_CHAMP_PBX = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

// Plan mode-prise-de-notes (D2): one line per mode, the tool named as the default.
export const AIDES_MODE_DE_NOTE: Texte[] = [
    {
        en: "Tool (default): the agent calls noter_information, then speaks in a second pass. The behaviour of before.",
        fr: "Outil (par défaut) : l'agent appelle noter_information, puis parle dans une seconde passe. Le comportement d'avant.",
    },
    {
        en: "Postscript: the agent speaks, then writes its note after a separator in the same answer. One pass, the note is never spoken; checks that ask the caller something reach the agent at its next turn.",
        fr: "Post-scriptum : l'agent parle, puis écrit sa note après un séparateur dans la même réponse. Une seule passe, la note n'est jamais dite ; ce que les contrôles demandent arrive à l'agent au tour suivant.",
    },
    {
        en: "Clerk: a second model keeps the record alongside the agent, which only speaks. It rereads the whole conversation after each answer of the agent; one pass at a time, a pass refused for rate limit is skipped. Its model, key and instructions are set in « Configure the clerk ».",
        fr: "Greffier : un second modèle tient la fiche à côté de l'agent, qui parle seulement. Il relit toute la conversation après chaque réponse de l'agent ; une passe à la fois, une passe refusée pour quota est sautée. Son modèle, sa clé et sa consigne se règlent dans « Régler le greffier ».",
    },
    {
        en: "Switching mode changes no prompt: write « you note it », never the tool's name. The end-of-call pass stays in every mode.",
        fr: "Changer de mode ne demande de retoucher aucun prompt : écrire « tu le notes », jamais le nom de l'outil. La passe de fin d'appel reste dans tous les modes.",
    },
];

// Plan porte-parlee (D14, D16): the box under the note-taking mode, Postscript only.
export const AIDES_PORTES_DANS_LA_REPONSE: Texte[] = [
    {
        en: "The agent takes a transition inside its reply and already speaks the next step's first reply: no silence between steps. Requires Postscript and a First reply on each step.",
        fr: "L'agent prend une porte dans sa réponse et dit déjà la première réplique de l'étape suivante : aucun silence entre deux étapes. Demande le post-scriptum et une première réplique sur chaque étape.",
    },
    {
        en: "A transition's written speech is spoken before the first reply; a recorded one plays after it.",
        fr: "La phrase de transition écrite d'une porte est dite avant la première réplique ; une phrase enregistrée en audio, après.",
    },
];

// The clerk's block, compared key by key whatever the order of its keys.
const pourComparerLeGreffier = (bloc: GreffierLlm | null | undefined) =>
    bloc && Object.keys(bloc).length > 0
        ? JSON.stringify(Object.fromEntries(Object.entries(bloc).sort(([a], [b]) => a.localeCompare(b))))
        : null;

export const ThemeDonnees = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    issuesParDefaut,
    etapesSansPremiereReplique = [],
}: ProprietesThemeAgent & {
    issuesParDefaut: CallDispositionOption[];
    /** Plan porte-parlee (D3): steps a transition leads to, with no first reply. */
    etapesSansPremiereReplique?: string[];
}) => {
    const { t } = useLangue();
    const { externalPbxIntegrationsEnabled, userConfig } = useOrgConfig();
    const { afficher } = useRevelation(ouvrir);

    // ---- The call record ---------------------------------------------------
    const ficheActiveEnregistree = resolue.fiche_au_fil_de_leau ?? false;
    // Plan mode-prise-de-notes (D1): absent = the tool, the behaviour of before.
    const modeEnregistre: FicheModeDeNote = resolue.fiche_mode_de_note ?? "outil";
    const champsEnregistres = useMemo(() => (resolue.fiche_champs ?? []) as ChampFiche[], [resolue.fiche_champs]);
    const [ficheActive, setFicheActive] = useState(ficheActiveEnregistree);
    const [modeDeNote, setModeDeNote] = useState<FicheModeDeNote>(modeEnregistre);
    const [champs, setChamps] = useState<ChampFiche[]>(champsEnregistres);
    const ficheModifiee =
        ficheActive !== ficheActiveEnregistree
        || JSON.stringify(pourComparerLaFiche(champs)) !== JSON.stringify(pourComparerLaFiche(champsEnregistres));
    const modeModifie = modeDeNote !== modeEnregistre;
    const erreursFiche = texteErreursDesChamps(champs);
    // Plan porte-parlee (D1): read only in Postscript, the same rule as the code
    // (E8); outside it the box is sent off, or the server would refuse the save.
    const portesEnregistrees = resolue.portes_dans_la_reponse ?? false;
    const [portes, setPortes] = useState(portesEnregistrees);
    useEffect(() => setPortes(portesEnregistrees), [portesEnregistrees]);
    const portesEnvoyees = modeDeNote === "post_scriptum" && portes;
    const portesModifiees = portesEnvoyees !== portesEnregistrees;
    // As the call record card did (24/09): follow the record the server stored,
    // keyed on its CONTENT so another theme's save does not wipe an edit here.
    const ficheEnregistree = JSON.stringify([ficheActiveEnregistree, modeEnregistre, champsEnregistres]);
    useEffect(() => {
        const [actifRelu, modeRelu, champsRelus] = JSON.parse(ficheEnregistree) as [boolean, FicheModeDeNote, ChampFiche[]];
        setFicheActive(actifRelu);
        setModeDeNote(modeRelu);
        setChamps(champsRelus);
    }, [ficheEnregistree]);

    // ---- The clerk (plan mode-prise-de-notes, part 2) ---------------------------
    // Its key comes back MASKED from the server: left untouched, the mask is
    // sent back and the server restores the real key (Evan, 04/10: « comme
    // Dograh »). A key typed replaces it; « conversation's key » removes it.
    const greffierEnregistre = useMemo(() => (resolue.greffier_llm ?? null) as GreffierLlm | null, [resolue.greffier_llm]);
    const consigneEnregistree = resolue.greffier_consigne ?? null;
    const [fournisseurGreffier, setFournisseurGreffier] = useState("");
    const [modeleGreffier, setModeleGreffier] = useState("");
    const [temperatureGreffier, setTemperatureGreffier] = useState("");
    const [cleGreffier, setCleGreffier] = useState("");
    const [cleRetiree, setCleRetiree] = useState(false);
    const [consigne, setConsigne] = useState(consigneEnregistree ?? CONSIGNE_GENERIQUE_GREFFIER);
    const greffierRelu = JSON.stringify([greffierEnregistre, consigneEnregistree]);
    useEffect(() => {
        const [bloc, texte] = JSON.parse(greffierRelu) as [GreffierLlm | null, string | null];
        setFournisseurGreffier(bloc?.provider ?? "");
        setModeleGreffier(bloc?.model ?? "");
        setTemperatureGreffier(bloc?.temperature === undefined || bloc?.temperature === null ? "" : String(bloc.temperature));
        setCleGreffier("");
        setCleRetiree(false);
        setConsigne(texte ?? CONSIGNE_GENERIQUE_GREFFIER);
    }, [greffierRelu]);
    // The temperature only plays where the provider declares one (registry.py):
    // elsewhere the server ignores it, so the field is greyed out. Unknown
    // provider (no configuration loaded): left open.
    const fournisseurEffectif = fournisseurDuGreffier(fournisseurGreffier, resolue, userConfig);
    const temperatureJoue = fournisseurEffectif === undefined || FOURNISSEURS_AVEC_TEMPERATURE.includes(fournisseurEffectif);
    const temperatureValide = temperatureGreffier.trim() === "" || Number.isFinite(Number(temperatureGreffier.replace(",", ".")));
    const blocGreffier = (): GreffierLlm | null => {
        const bloc: GreffierLlm = { ...(greffierEnregistre ?? {}) };
        const poser = (cle: string, valeur: unknown) => {
            if (valeur === undefined) delete bloc[cle];
            else bloc[cle] = valeur;
        };
        poser("provider", fournisseurGreffier.trim().toLowerCase() || undefined);
        poser("model", modeleGreffier.trim() || undefined);
        poser(
            "temperature",
            temperatureGreffier.trim() && temperatureValide ? Number(temperatureGreffier.replace(",", ".")) : undefined,
        );
        if (cleGreffier.trim()) poser("api_key", cleGreffier.trim());
        else if (cleRetiree) poser("api_key", undefined);
        return Object.keys(bloc).length > 0 ? bloc : null;
    };
    const greffierModifie = pourComparerLeGreffier(blocGreffier()) !== pourComparerLeGreffier(greffierEnregistre);
    // Saved equal to the template (or emptied), the instructions are sent empty:
    // the agent then follows the template when the template improves.
    const consigneEnvoyee = consigne.trim() === "" || consigne === CONSIGNE_GENERIQUE_GREFFIER ? null : consigne;
    const consigneModifiee = consigneEnvoyee !== consigneEnregistree;
    const cleEnregistree = typeof greffierEnregistre?.api_key === "string" && greffierEnregistre.api_key !== "" && !cleRetiree;

    // ---- After the call (chantier l-agent-travaille, L4, A6) ------------------
    const apresAppelEnregistre = JSON.stringify(pourEnvoyer(lireApresAppel(resolue.apres_appel)));
    const [apresAppel, setApresAppel] = useState(() => lireApresAppel(resolue.apres_appel));
    useEffect(() => setApresAppel(JSON.parse(apresAppelEnregistre)), [apresAppelEnregistre]);
    // Absent and « off with the defaults » are the same agent: not a modification.
    const apresAppelModifie =
        JSON.stringify(pourEnvoyer(apresAppel)) !== apresAppelEnregistre;

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
    const [fenetre, setFenetre] = useState<"correspondance" | "prospect" | "greffier" | null>(null);
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
    // A saved key only goes back to ITS provider (the server refuses it elsewhere):
    // a changed provider needs its key typed, or the conversation's key.
    const fournisseurChange = (fournisseurGreffier.trim() || undefined) !== (greffierEnregistre?.provider || undefined);
    if (fournisseurChange && cleEnregistree && !cleGreffier.trim()) {
        erreurs.push({
            cle: "greffier_llm",
            libelle: { en: "Clerk", fr: "Greffier" },
            message: {
                en: "the provider changed: type its API key, or use the conversation's key.",
                fr: "le fournisseur a changé : tapez sa clé API, ou prenez la clé de la conversation.",
            },
        });
    }
    if (!temperatureValide) {
        erreurs.push({
            cle: "greffier_llm",
            libelle: { en: "Clerk", fr: "Greffier" },
            message: { en: "the temperature must be a number.", fr: "la température doit être un nombre." },
        });
    }
    if (apresAppel.actif && champsInvalides(apresAppel).length > 0) {
        erreurs.push({
            cle: "apres_appel.champs",
            libelle: { en: "Record fields read after the call", fr: "Champs de la fiche lus après l'appel" },
            message: {
                en: "a field name starts with a letter and holds only letters, digits and _.",
                fr: "un nom de champ commence par une lettre et ne contient que lettres, chiffres et _.",
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

    const modifie =
        ficheModifiee || modeModifie || portesModifiees || greffierModifie || consigneModifiee || generalModifie || apresAppelModifie;
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
                // Its own part (like the flow map): sent only when changed, so the
                // record's save sends exactly what it sent before (E6).
                nom: { en: "Note-taking mode", fr: "Mode de prise de notes" },
                modifie: modeModifie,
                config: () => ({ fiche_mode_de_note: modeDeNote }),
            },
            {
                // Plan porte-parlee: its own part, sent only when changed (E6).
                nom: { en: "Transitions in the reply", fr: "Portes dans la réponse" },
                modifie: portesModifiees,
                config: () => ({ portes_dans_la_reponse: portesEnvoyees }),
            },
            {
                // L4: its own part, sent only when changed (E6).
                nom: { en: "After the call", fr: "Après l'appel" },
                modifie: apresAppelModifie,
                config: () => ({ apres_appel: pourEnvoyer(apresAppel) }),
            },
            {
                // The clerk's two parts, each sent only when changed (E6).
                nom: { en: "Clerk model", fr: "Modèle du greffier" },
                modifie: greffierModifie,
                config: () => ({ greffier_llm: blocGreffier() }),
            },
            {
                nom: { en: "Clerk instructions", fr: "Consigne du greffier" },
                modifie: consigneModifiee,
                config: () => ({ greffier_consigne: consigneEnvoyee }),
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
                    ? `${t({ en: "Record", fr: "Fiche" })} · ${champs.length} ${t({ en: "fields", fr: "champs" })}${
                          modeDeNote === "post_scriptum"
                              ? ` · ${t({ en: "Postscript", fr: "Post-scriptum" })}${
                                    portes ? ` · ${t({ en: "transitions in the reply", fr: "portes dans la réponse" })}` : ""
                                }`
                              : modeDeNote === "greffier"
                                ? ` · ${t({ en: "Clerk", fr: "Greffier" })}`
                                : ""
                      }`
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
                    libelle={{ en: "Fill the call record during the call", fr: "Remplir la fiche pendant l'appel" }}
                    aides={[
                        {
                            en: "Let the agent write and correct the call record at any moment of the call, whatever the step. How it writes is the note-taking mode below.",
                            fr: "L'agent écrit et corrige la fiche à tout moment de l'appel, quelle que soit l'étape. La façon dont il l'écrit est le mode de prise de notes, juste dessous.",
                        },
                        ...AIDES_FICHE,
                    ]}
                    disposition="ligne"
                >
                    <Switch id="fiche_au_fil_de_leau" checked={ficheActive} onCheckedChange={setFicheActive} />
                </ChampReglage>
                {/* Plan mode-prise-de-notes (D1, D2): shown only with the record on, the same
                    condition as in the code (no record, no note-taking mode). */}
                {ficheActive && (
                    <ChampReglage
                        cle="fiche_mode_de_note"
                        idControle="fiche_mode_de_note"
                        libelle={{ en: "Note-taking mode", fr: "Mode de prise de notes" }}
                        aides={AIDES_MODE_DE_NOTE}
                        bornes={{ en: "Default: Tool", fr: "Par défaut : outil" }}
                    >
                        <Select value={modeDeNote} onValueChange={(v: FicheModeDeNote) => setModeDeNote(v)}>
                            <SelectTrigger id="fiche_mode_de_note">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="outil">{t({ en: "Tool", fr: "Outil" })}</SelectItem>
                                <SelectItem value="post_scriptum">{t({ en: "Postscript", fr: "Post-scriptum" })}</SelectItem>
                                <SelectItem value="greffier">{t({ en: "Clerk", fr: "Greffier" })}</SelectItem>
                            </SelectContent>
                        </Select>
                    </ChampReglage>
                )}
                {/* Plan porte-parlee (D1, D3): only in Postscript, the same condition as the code. */}
                {ficheActive && modeDeNote === "post_scriptum" && (
                    <ChampReglage
                        cle="portes_dans_la_reponse"
                        idControle="portes_dans_la_reponse"
                        libelle={{ en: "Transitions in the reply", fr: "Portes dans la réponse" }}
                        aides={AIDES_PORTES_DANS_LA_REPONSE}
                        bornes={{ en: "Default: off", fr: "Par défaut : éteint" }}
                        disposition="ligne"
                    >
                        <Switch id="portes_dans_la_reponse" checked={portes} onCheckedChange={setPortes} />
                    </ChampReglage>
                )}
                {ficheActive && modeDeNote === "post_scriptum" && portes && etapesSansPremiereReplique.length > 0 && (
                    <p role="note" className="rounded border bg-muted/30 p-3 text-sm">
                        {t({
                            en: "Steps without a first reply (the agent gets a generic line instead): ",
                            fr: "Étapes sans première réplique (l'agent reçoit une ligne générique à la place) : ",
                        })}
                        {etapesSansPremiereReplique.join(", ")}
                    </p>
                )}
                {/* Part 2: the clerk's settings, only in its mode, in a dialog (convention E4). */}
                {ficheActive && modeDeNote === "greffier" && (
                    <ChampReglage
                        cle="greffier_llm"
                        libelle={{ en: "Clerk", fr: "Greffier" }}
                        aides={[
                            {
                                en: "The clerk's model, its own API key and its instructions. Empty fields come from the conversation model; by default, Mistral Large.",
                                fr: "Le modèle du greffier, sa propre clé API et sa consigne. Un champ vide reprend le modèle de la conversation ; par défaut, Mistral Large.",
                            },
                        ]}
                    >
                        <div className="flex items-center justify-between gap-3 rounded border p-3 text-sm">
                            <span>
                                {modeleGreffier.trim() || t({ en: "Model by default", fr: "Modèle par défaut" })} ·{" "}
                                {cleGreffier.trim() || cleEnregistree
                                    ? t({ en: "own key", fr: "clé propre" })
                                    : t({ en: "conversation's key", fr: "clé de la conversation" })}
                            </span>
                            <Button variant="outline" size="sm" onClick={() => setFenetre("greffier")}>
                                {t({ en: "Configure the clerk", fr: "Régler le greffier" })}
                            </Button>
                        </div>
                    </ChampReglage>
                )}
                {ficheActive && modeDeNote === "greffier" && (
                    <ChampReglage
                        cle="greffier_consigne"
                        libelle={{ en: "Clerk instructions", fr: "Consigne du greffier" }}
                        aides={[
                            {
                                en: "What the clerk is told before each pass. By default the generic template, with no trade vocabulary; what is specific to a trade goes here, agent by agent.",
                                fr: "Ce qui est dit au greffier avant chaque passe. Par défaut le modèle générique, sans vocabulaire de métier ; ce qui est propre à un métier s'écrit ici, agent par agent.",
                            },
                        ]}
                    >
                        <div className="flex items-center justify-between gap-3 rounded border p-3 text-sm">
                            <span>
                                {consigneEnvoyee === null
                                    ? t({ en: "Generic template", fr: "Modèle générique" })
                                    : t({ en: "Own instructions", fr: "Consigne propre" })}
                            </span>
                            <Button variant="outline" size="sm" onClick={() => setFenetre("greffier")}>
                                {t({ en: "Edit the instructions", fr: "Modifier la consigne" })}
                            </Button>
                        </div>
                    </ChampReglage>
                )}
                <div id="reglage-fiche_champs" data-reglage="fiche_champs" className="space-y-2">
                    <EditeurChampsFiche actif={ficheActive} champs={champs} onChange={setChamps} />
                </div>
            </Intertitre>

            <Intertitre id="donnees-issue" titre={{ en: "Call disposition", fr: "Issue de l'appel" }}>
                <div id="reglage-call_dispositions" data-reglage="call_dispositions">
                    <CallDispositionEditor rows={lignesIssues} onChange={setLignesIssues} defaultDispositions={issuesParDefaut} />
                </div>
            </Intertitre>

            {/* [.mark] Chantier l-agent-travaille, L4 (A6). */}
            <Intertitre id="donnees-apres-appel" titre={{ en: "After the call", fr: "Après l'appel" }}>
                <SectionApresAppelAgent valeur={apresAppel} onChange={setApresAppel} />
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

            <Dialog open={fenetre === "greffier"} onOpenChange={(o) => setFenetre(o ? "greffier" : null)}>
                <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>{t({ en: "Clerk", fr: "Greffier" })}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: "A second model keeps the record alongside the agent. Empty fields come from the conversation model.",
                                fr: "Un second modèle tient la fiche à côté de l'agent. Un champ vide reprend le modèle de la conversation.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                            <div className="space-y-1">
                                <label htmlFor="greffier_fournisseur" className="text-sm font-medium">
                                    {t({ en: "Provider", fr: "Fournisseur" })}
                                </label>
                                <Input
                                    id="greffier_fournisseur"
                                    value={fournisseurGreffier}
                                    onChange={(e) => setFournisseurGreffier(e.target.value)}
                                    placeholder={t({ en: "as the conversation", fr: "comme la conversation" })}
                                />
                            </div>
                            <div className="space-y-1">
                                <label htmlFor="greffier_modele" className="text-sm font-medium">
                                    {t({ en: "Model", fr: "Modèle" })}
                                </label>
                                <Input
                                    id="greffier_modele"
                                    value={modeleGreffier}
                                    onChange={(e) => setModeleGreffier(e.target.value)}
                                    placeholder={t({ en: "mistral-large-2512", fr: "mistral-large-2512" })}
                                />
                            </div>
                            <div className="space-y-1">
                                <label htmlFor="greffier_temperature" className="text-sm font-medium">
                                    {t({ en: "Temperature", fr: "Température" })}
                                </label>
                                <Input
                                    id="greffier_temperature"
                                    inputMode="decimal"
                                    disabled={!temperatureJoue}
                                    value={temperatureGreffier}
                                    onChange={(e) => setTemperatureGreffier(e.target.value)}
                                    placeholder={t({ en: "as the conversation", fr: "comme la conversation" })}
                                />
                                {!temperatureJoue && (
                                    <p className="text-xs text-muted-foreground">
                                        {t({
                                            en: `No effect with ${fournisseurEffectif}: only ${NOMS_AVEC_TEMPERATURE("and")} take a temperature.`,
                                            fr: `Sans effet chez ${fournisseurEffectif} : seuls ${NOMS_AVEC_TEMPERATURE("et")} prennent une température.`,
                                        })}
                                    </p>
                                )}
                                {/* A value kept from another provider would play again on a return to it: it can be cleared. */}
                                {!temperatureJoue && temperatureGreffier.trim() !== "" && (
                                    <Button type="button" variant="outline" size="sm" onClick={() => setTemperatureGreffier("")}>
                                        {t({ en: "Clear the temperature", fr: "Effacer la température" })}
                                    </Button>
                                )}
                            </div>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {t({
                                en: "Provider as named in the model settings (for example mistral). Without a model, Mistral uses mistral-large-2512.",
                                fr: "Le fournisseur tel qu'il est nommé dans les réglages des modèles (par exemple mistral). Sans modèle, Mistral prend mistral-large-2512.",
                            })}
                        </p>
                        {!temperatureValide && (
                            <p className="text-xs text-destructive">
                                {t({ en: "The temperature must be a number.", fr: "La température doit être un nombre." })}
                            </p>
                        )}
                        <div className="space-y-1">
                            <label htmlFor="greffier_cle" className="text-sm font-medium">
                                {t({ en: "API key", fr: "Clé API" })}
                            </label>
                            <div className="flex gap-2">
                                <Input
                                    id="greffier_cle"
                                    type="password"
                                    autoComplete="off"
                                    value={cleGreffier}
                                    onChange={(e) => setCleGreffier(e.target.value)}
                                    placeholder={
                                        cleEnregistree
                                            ? `${t({ en: "Saved key", fr: "Clé enregistrée" })} ${String(greffierEnregistre?.api_key)}`
                                            : t({ en: "Empty: the conversation's key", fr: "Vide : la clé de la conversation" })
                                    }
                                />
                                {(cleEnregistree || cleGreffier) && (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                            setCleGreffier("");
                                            setCleRetiree(true);
                                        }}
                                    >
                                        {t({ en: "Use the conversation's key", fr: "Prendre la clé de la conversation" })}
                                    </Button>
                                )}
                            </div>
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "A saved key is never shown again. Empty, the clerk uses the conversation's key, and its rate limit: Mistral limits each organization, so for the clerk not to share the agent's limit, the key must come from another Mistral organization.",
                                    fr: "Une clé enregistrée n'est jamais réaffichée. Vide, le greffier prend la clé de la conversation, et son quota : Mistral limite chaque organisation, donc pour que le greffier ne partage pas la limite de l'agent, la clé doit venir d'une autre organisation Mistral.",
                                })}
                            </p>
                            {fournisseurChange && cleEnregistree && !cleGreffier.trim() && (
                                <p className="text-xs text-destructive">
                                    {t({
                                        en: "The provider changed: type its API key, or use the conversation's key.",
                                        fr: "Le fournisseur a changé : tapez sa clé API, ou prenez la clé de la conversation.",
                                    })}
                                </p>
                            )}
                        </div>
                        <div className="space-y-1">
                            <div className="flex items-center justify-between gap-2">
                                <label htmlFor="greffier_consigne" className="text-sm font-medium">
                                    {t({ en: "Instructions", fr: "Consigne" })}
                                </label>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={consigne === CONSIGNE_GENERIQUE_GREFFIER}
                                    onClick={() => setConsigne(CONSIGNE_GENERIQUE_GREFFIER)}
                                >
                                    {t({ en: "Back to the template", fr: "Revenir au modèle" })}
                                </Button>
                            </div>
                            <Textarea
                                id="greffier_consigne"
                                rows={12}
                                value={consigne}
                                onChange={(e) => setConsigne(e.target.value)}
                                className="font-mono text-xs"
                            />
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "Prefilled with the generic template, which has no trade vocabulary. The record's fields and the expected answer format are always added by the code.",
                                    fr: "Préremplie du modèle générique, sans vocabulaire de métier. Les champs de la fiche et le format de la réponse sont toujours ajoutés par le code.",
                                })}
                            </p>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button onClick={() => setFenetre(null)}>{t({ en: "Done", fr: "Terminé" })}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

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
