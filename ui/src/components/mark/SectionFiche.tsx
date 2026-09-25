"use client";

import { ClipboardList, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import { detailFromError } from "@/lib/apiError";
import type { ChampFiche, WorkflowConfigurations } from "@/types/workflow-configurations";

import { RAPPEL_PUBLICATION } from "./SectionReglagesPipecat";

/**
 * [.mark] The "Call Record" card of an agent's settings page (plan fiche au fil
 * de l'eau, lot 5).
 *
 * Switched on, the model gets one tool, `noter_information`, that it can call
 * at any step to write or correct a field of the call record declared here.
 * Switched off (the default), the tool is not offered at all and the agent
 * behaves exactly as before.
 *
 * ⛔ A long list is never shown in one block: the fields are edited in a
 * dialog, the card only says how many there are.
 */

export const ID_SECTION_FICHE = "call-record";

const NOM_CHAMP = /^[a-z][a-z0-9_]{0,63}$/;

/** `max_length` of `fiche_champs` on the server; a test compares the two. */
export const NOMBRE_MAX_CHAMPS = 60;

// Mirrors `NOMS_RESERVES` (`api/schemas/fiche_agent.py`): the server refuses
// them too (422), the screen says so before.
export const NOMS_RESERVES = [
    "call_disposition",
    "mapped_call_disposition",
    "call_status",
    "call_tags",
    "answer_supervisor",
    "extracted_variables",
    "nodes_visited",
    "agent_visits",
    "communes_verifiees",
    "voies_verifiees",
    "epellations_lues",
    "nombres_lus",
    "lexique_reconnu",
    "lexique_metier",
    "fiche_etat",
    "fiche_journal",
];

/** Mirrors `lecteur_par_defaut` on the server. */
export const lecteurParDefaut = (nom: string): "commune" | "rue" | "date" | "aucun" =>
    nom.startsWith("commune")
        ? "commune"
        : nom.startsWith("adresse") || nom.startsWith("rue")
          ? "rue"
          : nom.includes("date") || nom.startsWith("dernier_") || nom.startsWith("annee")
            ? "date"
            : "aucun";

/** `MAX_VALEURS` and `MAX_LONGUEUR_VALEUR` on the server; a test compares them. */
export const NOMBRE_MAX_VALEURS = 20;
export const LONGUEUR_MAX_VALEUR = 40;

/** "danger, panne , normal" -> ["danger", "panne", "normal"]; nothing -> null. */
export const lireLesValeurs = (texte: string): string[] | null => {
    const valeurs = texte
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
    return valeurs.length ? valeurs : null;
};

/** The same record, with "no list" written one way only, to compare two records. */
const pourComparer = (champs: ChampFiche[]) =>
    champs.map((c) => ({ ...c, valeurs: c.valeurs?.length ? c.valeurs : null }));

/** The first problem of each field, by index: what the server would refuse. */
export const erreursDesChamps = (champs: ChampFiche[]): Record<number, string> => {
    const erreurs: Record<number, string> = {};
    const vus = new Set<string>();
    const insee = new Set(
        champs
            .filter((c) => (c.lecteur ?? lecteurParDefaut(c.nom)) === "commune")
            .map((c) => `${c.nom}_insee`),
    );
    // Mirrors `cle_dit` (D46): where the caller's words for a date are kept.
    const dits = new Set(
        champs
            .filter((c) => (c.lecteur ?? lecteurParDefaut(c.nom)) === "date")
            .map((c) => `${c.nom}_dit`),
    );
    champs.forEach((champ, i) => {
        if (!NOM_CHAMP.test(champ.nom)) {
            erreurs[i] = "Lowercase letters, digits and _, starting with a letter.";
        } else if (NOMS_RESERVES.includes(champ.nom)) {
            erreurs[i] = "This name is used by the agent itself.";
        } else if (vus.has(champ.nom)) {
            erreurs[i] = "This name is used twice.";
        } else if (insee.has(champ.nom)) {
            erreurs[i] = "This is where a town's INSEE code is written.";
        } else if (dits.has(champ.nom)) {
            erreurs[i] = "This is where the caller's words for a date are kept.";
        } else if ((champ.valeurs?.length ?? 0) > NOMBRE_MAX_VALEURS) {
            erreurs[i] = `At most ${NOMBRE_MAX_VALEURS} allowed values.`;
        } else if (champ.valeurs?.some((v) => v.length > LONGUEUR_MAX_VALEUR)) {
            erreurs[i] = `An allowed value is longer than ${LONGUEUR_MAX_VALEUR} characters.`;
        }
        vus.add(champ.nom);
    });
    return erreurs;
};

const nouveauChamp = (): ChampFiche => ({
    nom: "",
    type: "string",
    origine: "dicte",
    description: "",
    lecteur: null,
});

/**
 * PB3: the closed list of a field, typed as comma-separated values.
 *
 * ⚠️ The text typed is kept as typed: rebuilt from the parsed list, "danger,"
 * would lose its comma and the next value could never be typed. It is taken
 * from the record again only when the record says something else (a field
 * removed above shifts the rows).
 */
const ValeursPermises = ({
    index,
    valeurs,
    onChange,
}: {
    index: number;
    valeurs: string[] | null;
    onChange: (valeurs: string[] | null) => void;
}) => {
    const [texte, setTexte] = useState((valeurs ?? []).join(", "));
    const cle = JSON.stringify(valeurs ?? null);
    useEffect(() => {
        setTexte((avant) =>
            JSON.stringify(lireLesValeurs(avant)) === cle
                ? avant
                : ((JSON.parse(cle) as string[] | null) ?? []).join(", "),
        );
    }, [cle]);
    return (
        <div className="space-y-1">
            <Label htmlFor={`fiche_valeurs_${index}`} className="text-xs">
                Allowed values
            </Label>
            <Input
                id={`fiche_valeurs_${index}`}
                value={texte}
                placeholder="Any value"
                onChange={(e) => {
                    setTexte(e.target.value);
                    onChange(lireLesValeurs(e.target.value));
                }}
            />
            <p className="text-xs text-muted-foreground">
                Separated by commas, up to {NOMBRE_MAX_VALEURS}. The field then only accepts one of
                them, written as typed here, and a deduced field no longer has to use the
                caller&apos;s words.
            </p>
        </div>
    );
};

interface SectionFicheProps {
    /** The RESOLVED configuration, as the page hands it to every other section. */
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    onSave: (
        configurations: WorkflowConfigurations,
        workflowName: string,
    ) => Promise<void>;
}

export const SectionFiche = ({
    workflowConfigurations,
    workflowName,
    onSave,
}: SectionFicheProps) => {
    const actifEnregistre = workflowConfigurations.fiche_au_fil_de_leau ?? false;
    const champsEnregistres = useMemo(
        () => workflowConfigurations.fiche_champs ?? [],
        [workflowConfigurations.fiche_champs],
    );
    const [actif, setActif] = useState(actifEnregistre);
    const [champs, setChamps] = useState<ChampFiche[]>(champsEnregistres);
    const [ouvert, setOuvert] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    // After a save the page hands back the configuration as the server stored
    // it: the card follows it, so it never stays "Unsaved changes" on what the
    // server just confirmed (defect of 24/09, which blocked leaving the page).
    // Keyed on the CONTENT: another card's save hands a new object with the same
    // record, and must not wipe an edit in progress here.
    const cleEnregistree = JSON.stringify([actifEnregistre, champsEnregistres]);
    useEffect(() => {
        const [actifRelu, champsRelus] = JSON.parse(cleEnregistree) as [boolean, ChampFiche[]];
        setActif(actifRelu);
        setChamps(champsRelus);
    }, [cleEnregistree]);

    const erreurs = useMemo(() => erreursDesChamps(champs), [champs]);
    const nombreDErreurs = Object.keys(erreurs).length;
    const isDirty =
        actif !== actifEnregistre ||
        JSON.stringify(pourComparer(champs)) !== JSON.stringify(pourComparer(champsEnregistres));
    const maximum = NOMBRE_MAX_CHAMPS;

    useUnsavedChanges(ID_SECTION_FICHE, isDirty);

    const modifier = (i: number, changement: Partial<ChampFiche>) =>
        setChamps((avant) => avant.map((c, j) => (j === i ? { ...c, ...changement } : c)));

    const handleSave = async () => {
        setIsSaving(true);
        setErreur(null);
        try {
            await onSave(
                {
                    ...workflowConfigurations,
                    fiche_au_fil_de_leau: actif,
                    fiche_champs: champs,
                },
                workflowName,
            );
            toast.success(`Call record saved. ${RAPPEL_PUBLICATION}`);
        } catch (e) {
            const message = detailFromError(e, "Call record not saved. Check the fields and try again.");
            setErreur(message);
            toast.error(`Call record not saved: ${message}`);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id={ID_SECTION_FICHE}>
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <ClipboardList className="h-4 w-4" />
                    Call Record
                </CardTitle>
                <CardDescription>
                    Let the agent write and correct the call record at any moment of the call,
                    whatever the step, with one tool:{" "}
                    <code className="rounded bg-muted px-1 text-xs">noter_information</code>.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-2">
                    <div className="flex items-center justify-between gap-4">
                        <Label htmlFor="fiche_au_fil_de_leau" className="text-sm">
                            Fill the call record with a tool
                        </Label>
                        <Switch
                            id="fiche_au_fil_de_leau"
                            checked={actif}
                            onCheckedChange={setActif}
                        />
                    </div>
                    <p className="text-xs text-muted-foreground">
                        Off: the tool is not offered and the agent behaves exactly as before.
                    </p>
                    <p className="text-xs text-muted-foreground">
                        On: the step-by-step extraction stops, the record is written by the tool,
                        and a final pass at the end of the call fills only the fields left empty.
                        The town, street and spelling readers stop adding notes to what the model
                        reads and answer the tool instead. A value the caller never said is
                        refused. No effect in realtime mode.
                    </p>
                    <p className="text-xs text-muted-foreground">
                        ⚠️ The agent&apos;s prompts must say how the record is filled. Prompts
                        written for step-by-step extraction still ask for a step per piece of
                        information.
                    </p>
                </div>

                <div className="flex items-center justify-between gap-4 rounded border p-3">
                    <div className="text-sm">
                        <span id="fiche_nombre_de_champs">{champs.length}</span>{" "}
                        {champs.length === 1 ? "field" : "fields"} in the record
                        {actif && champs.length === 0 && (
                            <p className="text-xs text-destructive">
                                No field: the tool will not be offered.
                            </p>
                        )}
                    </div>
                    <Button variant="outline" onClick={() => setOuvert(true)}>
                        Edit fields
                    </Button>
                </div>
                {nombreDErreurs > 0 && (
                    <p role="alert" className="text-xs text-destructive">
                        {nombreDErreurs} field{nombreDErreurs > 1 ? "s have" : " has"} a problem:
                        open the fields to fix it.
                    </p>
                )}
                {erreur && (
                    <p role="alert" className="text-xs text-destructive">
                        {erreur}
                    </p>
                )}
            </CardContent>
            <CardFooter className="justify-end gap-3 border-t pt-6">
                {isDirty && nombreDErreurs === 0 && (
                    <span className="text-xs text-muted-foreground">Unsaved changes</span>
                )}
                <Button onClick={handleSave} disabled={isSaving || !isDirty || nombreDErreurs > 0}>
                    {isSaving ? "Saving..." : "Save Call Record"}
                </Button>
            </CardFooter>

            <Dialog open={ouvert} onOpenChange={setOuvert}>
                {/* ⛔ `sm:` : la largeur de base du composant (sm:max-w-lg) l'emporte
                    sur un `max-w-*` sans préfixe, et les champs se chevauchaient (24/09). */}
                <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-5xl">
                    <DialogHeader>
                        <DialogTitle>Call record fields</DialogTitle>
                        <DialogDescription>
                            Each field becomes a parameter of the tool. <strong>Dictated</strong>:
                            the value must have been said by the caller (name, phone, town,
                            street, brand). <strong>Deduced</strong>: the model sums it up
                            (reason for the call, urgency). The <strong>reader</strong> checks a
                            town against the list of communes, or a street against the streets of
                            the town, or computes a <strong>date</strong> said as &quot;last
                            year&quot; on the day of the call (the caller&apos;s words are kept
                            next to it); &quot;From the name&quot; picks it as the server does
                            (<code>commune…</code> → town, <code>adresse…</code> or{" "}
                            <code>rue…</code> → street, <code>…date…</code>,{" "}
                            <code>dernier_…</code> or <code>annee…</code> → date).
                        </DialogDescription>
                    </DialogHeader>
                    <div className="flex-1 space-y-3 overflow-y-auto pr-1">
                        {champs.map((champ, i) => (
                            <div key={i} className="space-y-2 rounded border p-3" data-champ={i}>
                                <div className="grid grid-cols-1 gap-2 md:grid-cols-12">
                                    <div className="space-y-1 md:col-span-3">
                                        <Label htmlFor={`fiche_nom_${i}`} className="text-xs">
                                            Name
                                        </Label>
                                        <Input
                                            id={`fiche_nom_${i}`}
                                            value={champ.nom}
                                            maxLength={64}
                                            aria-invalid={erreurs[i] ? true : undefined}
                                            onChange={(e) => modifier(i, { nom: e.target.value })}
                                        />
                                    </div>
                                    <div className="space-y-1 md:col-span-2">
                                        <Label className="text-xs">Type</Label>
                                        <Select
                                            value={champ.type}
                                            onValueChange={(v: ChampFiche["type"]) => modifier(i, { type: v })}
                                        >
                                            <SelectTrigger id={`fiche_type_${i}`}>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="string">Text</SelectItem>
                                                <SelectItem value="number">Number</SelectItem>
                                                <SelectItem value="boolean">Yes / no</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1 md:col-span-2">
                                        <Label className="text-xs">Origin</Label>
                                        <Select
                                            value={champ.origine}
                                            onValueChange={(v: ChampFiche["origine"]) => modifier(i, { origine: v })}
                                        >
                                            <SelectTrigger id={`fiche_origine_${i}`}>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="dicte">Dictated</SelectItem>
                                                <SelectItem value="deduit">Deduced</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1 md:col-span-4">
                                        <Label className="text-xs">Reader</Label>
                                        <Select
                                            value={champ.lecteur ?? "auto"}
                                            onValueChange={(v) =>
                                                modifier(i, {
                                                    lecteur: v === "auto" ? null : (v as ChampFiche["lecteur"]),
                                                })
                                            }
                                        >
                                            <SelectTrigger id={`fiche_lecteur_${i}`}>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="auto">
                                                    From the name ({lecteurParDefaut(champ.nom)})
                                                </SelectItem>
                                                <SelectItem value="commune">Town</SelectItem>
                                                <SelectItem value="rue">Street</SelectItem>
                                                <SelectItem value="date">Date</SelectItem>
                                                <SelectItem value="aucun">None</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="flex items-end justify-end md:col-span-1">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            aria-label={`Remove field ${champ.nom || i + 1}`}
                                            onClick={() => setChamps((avant) => avant.filter((_, j) => j !== i))}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <Label htmlFor={`fiche_description_${i}`} className="text-xs">
                                        Hint for the model
                                    </Label>
                                    <Input
                                        id={`fiche_description_${i}`}
                                        value={champ.description}
                                        maxLength={500}
                                        onChange={(e) => modifier(i, { description: e.target.value })}
                                    />
                                </div>
                                <ValeursPermises
                                    index={i}
                                    valeurs={champ.valeurs ?? null}
                                    onChange={(valeurs) => modifier(i, { valeurs })}
                                />
                                {erreurs[i] && (
                                    <p className="text-xs text-destructive">{erreurs[i]}</p>
                                )}
                            </div>
                        ))}
                    </div>
                    <DialogFooter className="justify-between sm:justify-between">
                        <Button
                            variant="outline"
                            disabled={champs.length >= maximum}
                            onClick={() => setChamps((avant) => [...avant, nouveauChamp()])}
                        >
                            <Plus className="mr-1 h-4 w-4" />
                            Add field
                        </Button>
                        <Button onClick={() => setOuvert(false)}>Done</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    );
};
