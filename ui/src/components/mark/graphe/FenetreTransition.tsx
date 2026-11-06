"use client";

import { AlertCircle, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import type { FlowEdgeData, RegleDePorte } from "@/components/flow/types";
import { identifiantGarde } from "@/components/flow/edges/porte";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Info, Marque } from "@/components/mark/studio/marques";
import { SuppressionConfirmee } from "@/components/mark/studio/suppression-confirmee";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import {
    CHAMPS_FIXES,
    COMPARAISONS,
    comparaisonsDe,
    ecrireLaCondition,
    type EtatCondition,
    fauteDeLaRegle,
    type GenreCondition,
    lireLaCondition,
    NOM_DECIDEUR,
    type QuiDecide,
    regleNeuve,
    sansEffet,
    sansValeur,
    SOURCES,
    type SourceRegle,
} from "./conditions-de-porte";

/**
 * [.mark] Partie 3, sous-lot 21 : la fenêtre d'une transition, reprise de `FenetreTransition` de la maquette
 * (`maquette-dograh/components/studio/canevas.tsx`) : qui décide (hérité de l'étape), la condition (le modèle juge, des
 * règles vérifiées par le code, sinon, toujours), « sans effet » avec sa correction, la phrase de transition. Tous les
 * champs d'avant sont gardés (libellé, condition lue par le modèle, condition sur la fiche, phrase, enregistrement,
 * identifiant de la porte). Un onglet du panneau de droite (jamais centrée).
 */
const GENRES: { id: GenreCondition; titre: Texte; sous: Texte }[] = [
    {
        id: "modele",
        titre: { en: "An intention", fr: "Une intention" },
        sous: { en: "What the model (or the arbiter) judges in what the caller says: a wish, a tone.", fr: "Ce que le modèle (ou l'arbitre) juge dans ce que dit l'appelant : un souhait, un ton." },
    },
    {
        id: "regles",
        titre: { en: "Rules on the record", fr: "Des règles de la fiche" },
        sous: { en: "Safe and testable: record, tool result, time, establishment.", fr: "Sûr et testable : fiche, résultat d'un outil, heure, établissement." },
    },
    {
        id: "sinon",
        titre: { en: "Otherwise", fr: "Sinon" },
        sous: { en: "When no other link of the step passes.", fr: "Quand aucune autre liaison de l'étape ne passe." },
    },
    {
        id: "toujours",
        titre: { en: "Always", fr: "Toujours" },
        sous: { en: "Passes as soon as the step is done.", fr: "On passe dès que l'étape est finie." },
    },
];

const PHRASE = { none: { en: "None", fr: "Aucune" }, text: { en: "Text", fr: "Texte" }, audio: { en: "Recording", fr: "Enregistrement" } } as const;
type Phrase = keyof typeof PHRASE;

export type Enregistrement = { recording_id: string; transcript?: string | null };

export function FenetreTransition({
    ouverte,
    fermer,
    data,
    etape,
    autreSinon,
    enregistrements,
    lecture = false,
    onSave,
    onDelete,
}: {
    ouverte: boolean;
    fermer: () => void;
    data?: FlowEdgeData;
    /** L'étape d'où part la liaison : son nom et qui y décide (`qui_decide_du_passage`). */
    etape: { nom: string; qui: QuiDecide };
    /** Une autre liaison de la même étape est déjà « sinon » (une seule par étape). */
    autreSinon: boolean;
    enregistrements: Enregistrement[];
    lecture?: boolean;
    /** `quiPose` : la correction « faire décider la fiche » choisie dans la fenêtre, posée sur l'étape avec la liaison. */
    onSave: (valeur: FlowEdgeData, quiPose?: QuiDecide) => void | Promise<void>;
    onDelete: () => void;
}) {
    return ouverte ? (
        <Ouverte fermer={fermer} data={data} etape={etape} autreSinon={autreSinon} enregistrements={enregistrements} lecture={lecture} onSave={onSave} onDelete={onDelete} />
    ) : null;
}

function Ouverte({ fermer, data, etape, autreSinon, enregistrements, lecture, onSave, onDelete }: Omit<Parameters<typeof FenetreTransition>[0], "ouverte">) {
    const { t } = useLangue();
    const libelleEnr = (r: Enregistrement) => r.transcript || r.recording_id;
    const depart = {
        label: data?.label ?? "",
        condition: data?.condition ?? "",
        cond: lireLaCondition(data?.condition_sur_la_fiche),
        phrase: (data?.transition_speech_type === "audio" && data.transition_speech_recording_id ? "audio" : data?.transition_speech ? "text" : "none") as Phrase,
        texte: data?.transition_speech ?? "",
        enr: data?.transition_speech_recording_id ?? enregistrements[0]?.recording_id ?? "",
    };
    const [label, setLabel] = useState(depart.label);
    const [condition, setCondition] = useState(depart.condition);
    const [cond, setCond] = useState<EtatCondition>(depart.cond);
    const [phrase, setPhrase] = useState<Phrase>(depart.phrase);
    const [texte, setTexte] = useState(depart.texte);
    const [enr, setEnr] = useState(depart.enr);
    const [quiPose, setQuiPose] = useState<QuiDecide | undefined>(undefined);
    const [montrerFautes, setMontrerFautes] = useState(false);
    const [abandon, setAbandon] = useState(false);
    const [enCours, setEnCours] = useState(false);

    const qui = quiPose ?? etape.qui;
    const inutile = sansEffet(cond.genre, qui);
    const modifie =
        JSON.stringify({ label, condition, c: ecrireLaCondition(cond), phrase, texte, enr, quiPose }) !==
        JSON.stringify({ label: depart.label, condition: depart.condition, c: ecrireLaCondition(depart.cond), phrase: depart.phrase, texte: depart.texte, enr: depart.enr, quiPose: undefined });
    const fautes = cond.genre === "regles" ? cond.regles.map(fauteDeLaRegle) : [];
    const fauteLibelle = !label.trim() ? t({ en: "A link needs a label.", fr: "Une liaison a besoin d'un libellé." }) : null;
    const fauteCondition = !condition.trim() ? t({ en: "Describe when the model takes this link.", fr: "Décrivez quand le modèle prend cette liaison." }) : null;
    const fauteSinon = cond.genre === "sinon" && autreSinon ? t({ en: "This step already has an « Otherwise » link.", fr: "Cette étape a déjà une liaison « Sinon »." }) : null;
    const fauteRegles = cond.genre === "regles" && cond.regles.length === 0 ? t({ en: "Add at least one rule.", fr: "Ajoutez au moins une règle." }) : null;

    const demanderFermeture = () => {
        if (enCours) return;
        if (modifie && !lecture) setAbandon(true);
        else fermer();
    };
    const maj = (i: number, p: Partial<RegleDePorte>) => setCond((c) => ({ ...c, regles: c.regles.map((r, j) => (j === i ? { ...r, ...p } : r)) }));
    const choisirGenre = (genre: GenreCondition) =>
        setCond((c) => ({ ...c, genre, regles: genre === "regles" && c.regles.length === 0 ? [regleNeuve()] : c.regles }));

    const enregistrer = async () => {
        if (fauteLibelle || fauteCondition || fauteSinon || fauteRegles || fautes.some(Boolean)) {
            setMontrerFautes(true);
            return;
        }
        const identifiant = identifiantGarde(data, label); // L6+ : la porte garde son nom au renommage
        const valeur: FlowEdgeData = {
            condition,
            label,
            ...(identifiant ? { identifiant } : {}),
            condition_sur_la_fiche: ecrireLaCondition(cond),
            transition_speech: phrase === "text" ? texte || undefined : undefined,
            transition_speech_type: phrase === "audio" ? "audio" : "text",
            transition_speech_recording_id: phrase === "audio" ? enr || undefined : undefined,
        };
        setEnCours(true);
        try {
            await onSave(valeur, quiPose);
            fermer();
        } catch {
            setEnCours(false); // l'échec est dit par la notification de l'enregistrement ; la saisie reste là
        }
    };

    const sousLeChamp = (texte: string | null) =>
        montrerFautes && texte ? (
            <p role="alert" className="text-xs text-(--marque-danger-texte)">
                {texte}
            </p>
        ) : null;

    return (
        <Dialog open onOpenChange={(o) => !o && demanderFermeture()}>
            <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="flex max-h-[86vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
                <DialogTitle className="sr-only">
                    {t({ en: "Transition", fr: "Transition" })} : {label}
                </DialogTitle>
                <div className="shrink-0 px-6 pt-5 pb-2 pr-12">
                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t({ en: "Transition", fr: "Transition" })}</p>
                    <Input
                        value={label}
                        onChange={(e) => setLabel(e.target.value)}
                        disabled={lecture}
                        aria-label={t({ en: "Label of the transition", fr: "Libellé de la transition" })}
                        aria-invalid={montrerFautes && !!fauteLibelle}
                        className="mt-1 h-9 border-transparent px-1 text-lg font-semibold shadow-none hover:border-input"
                    />
                    {sousLeChamp(fauteLibelle)}
                </div>
                <div className="min-h-0 flex-1 space-y-6 overflow-auto bg-background px-6 py-3">
                    {data?.invalid && data.validationMessage && (
                        <div className="flex items-center gap-2 text-sm text-destructive">
                            <AlertCircle className="size-4" />
                            <span>{data.validationMessage}</span>
                        </div>
                    )}
                    <section className="space-y-2" data-section="qui-decide">
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t({ en: "Who decides we move to the next step?", fr: "Qui décide qu'on passe à l'étape suivante ?" })}
                            <Info>
                                {t({
                                    en: "The link inherits the choice of its step (Who decides the transition). A link left to the model behaves exactly as before.",
                                    fr: "La liaison hérite du choix de son étape (« Qui décide du passage »). Une liaison laissée au modèle se comporte exactement comme avant.",
                                })}
                            </Info>
                        </p>
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                            <Marque ton={quiPose ? "plein" : "neutre"}>
                                {quiPose
                                    ? t({ en: "changed on the step when you save", fr: "changé sur l'étape à l'enregistrement" })
                                    : t({ en: `inherited from step « ${etape.nom} »`, fr: `hérité de l'étape « ${etape.nom} »` })}
                            </Marque>
                            <span className="font-medium">{t(NOM_DECIDEUR[qui])}</span>
                        </div>
                    </section>

                    <section className="space-y-2" data-section="condition">
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t({ en: "Condition", fr: "Condition" })}
                            <Info>
                                {t({
                                    en: "When the code decides, a false condition closes the link to the model: even if it calls the function, the step does not pass. The links are read in the order of the canvas, the first true one wins.",
                                    fr: "Quand le code décide, une condition fausse ferme la porte au modèle : même s'il appelle la fonction, l'étape ne passe pas. Les liaisons se lisent dans l'ordre du canevas, la première vraie l'emporte.",
                                })}
                            </Info>
                        </p>
                        <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t({ en: "Condition", fr: "Condition" })}>
                            {GENRES.map((g) => (
                                <button
                                    key={g.id}
                                    type="button"
                                    role="radio"
                                    aria-checked={cond.genre === g.id}
                                    data-genre={g.id}
                                    disabled={lecture}
                                    onClick={() => choisirGenre(g.id)}
                                    className={`flex cursor-pointer gap-2.5 rounded-xl border p-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-ring ${cond.genre === g.id ? "border-primary bg-muted/50" : "border-black/10 hover:border-black/25 dark:border-white/15 dark:hover:border-white/30"}`}
                                >
                                    <span>
                                        <span className="block text-sm font-medium">{t(g.titre)}</span>
                                        <span className="block text-xs text-muted-foreground">{t(g.sous)}</span>
                                    </span>
                                </button>
                            ))}
                        </div>
                        {sousLeChamp(fauteSinon)}
                    </section>

                    {inutile && (
                        <section className="space-y-2 border-t pt-4" data-section="sans-effet">
                            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                                <Marque ton="danger">{t({ en: "no effect", fr: "sans effet" })}</Marque>
                                {t({
                                    en: `${t(GENRES.find((g) => g.id === cond.genre)!.titre)} does not play when « ${t(NOM_DECIDEUR[qui])} » decides`,
                                    fr: `${t(GENRES.find((g) => g.id === cond.genre)!.titre)} ne joue pas quand « ${t(NOM_DECIDEUR[qui])} » décide`,
                                })}
                                <Info>
                                    {t({
                                        en: "This condition is saved but ignored: « Before publishing » flags it.",
                                        fr: "Cette condition est enregistrée mais ignorée : « Avant de publier » la signale.",
                                    })}
                                </Info>
                            </p>
                            {!lecture && (
                                <div className="flex flex-wrap gap-2">
                                    <Button type="button" size="sm" onClick={() => setQuiPose("choix")}>
                                        {t({ en: "Let the record decide on this step", fr: "Faire décider la fiche sur cette étape" })}
                                    </Button>
                                    <Button type="button" size="sm" variant="outline" onClick={() => choisirGenre("modele")}>
                                        {t({ en: "Leave it to the model", fr: "Laisser le modèle juger" })}
                                    </Button>
                                </div>
                            )}
                        </section>
                    )}

                    <section className="space-y-2" data-section="intention">
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {qui === "libre" || qui === "choix"
                                ? t({ en: "The intention the model and the arbiter judge", fr: "L'intention que jugent le modèle et l'arbitre" })
                                : t({ en: "The intention the model judges", fr: "L'intention que le modèle juge" })}
                            <Info>
                                {t({
                                    en: "Describes when this link should open. The model reads it to choose the exit; it stays useful with rules (the model still sees the link when it is open).",
                                    fr: "Décrit quand cette porte doit s'ouvrir. Le modèle la lit pour choisir la sortie ; elle reste utile avec des règles (le modèle voit la porte quand elle est ouverte).",
                                })}
                            </Info>
                        </p>
                        <Textarea
                            value={condition}
                            onChange={(e) => setCondition(e.target.value)}
                            disabled={lecture}
                            rows={3}
                            aria-label={t({ en: "Condition (for the model)", fr: "Condition (pour le modèle)" })}
                            aria-invalid={montrerFautes && !!fauteCondition}
                            placeholder={t({ en: "E.g.: the person wants an appointment.", fr: "Ex. : la personne veut un rendez-vous." })}
                        />
                        {sousLeChamp(fauteCondition)}
                    </section>

                    {cond.genre === "regles" && (
                        <section className="space-y-3" data-section="regles">
                            <div className="flex items-center gap-2">
                                <p className="flex-1 text-sm font-medium">{t({ en: "The rules", fr: "Les règles" })}</p>
                                <span className="inline-flex rounded-lg bg-muted p-0.5 text-sm">
                                    {(["toutes", "au_moins_une"] as const).map((c) => (
                                        <button
                                            key={c}
                                            type="button"
                                            aria-pressed={cond.combien === c}
                                            disabled={lecture}
                                            onClick={() => setCond((x) => ({ ...x, combien: c }))}
                                            className={`cursor-pointer rounded-md px-3 py-1 ${cond.combien === c ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                                        >
                                            {c === "toutes" ? t({ en: "All", fr: "Toutes" }) : t({ en: "At least one", fr: "Au moins une" })}
                                        </button>
                                    ))}
                                </span>
                            </div>
                            <div className="space-y-2">
                                {cond.regles.map((r, i) => (
                                    <LigneRegle key={i} r={r} i={i} lecture={!!lecture} faute={montrerFautes ? fautes[i] : null} maj={maj} retirer={() => setCond((c) => ({ ...c, regles: c.regles.filter((_, j) => j !== i) }))} />
                                ))}
                                {sousLeChamp(fauteRegles)}
                                {!lecture && (
                                    <Button type="button" variant="ghost" size="sm" className="-ml-2" onClick={() => setCond((c) => ({ ...c, regles: [...c.regles, regleNeuve()] }))}>
                                        <Plus className="size-3.5" /> {t({ en: "Add a rule", fr: "Ajouter une règle" })}
                                    </Button>
                                )}
                            </div>
                            {(qui === "collecte" || qui === "choix") && (
                                <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                                    {t({ en: "If a piece of data is missing, the link stays closed", fr: "Si une donnée manque, la porte reste fermée" })}
                                    <Info>
                                        {t({
                                            en: "A rule the code cannot read (missing data, still to confirm) is false: the link stays closed and the arbiter never passes against it.",
                                            fr: "Une règle que le code ne peut pas lire (donnée absente, encore à confirmer) est fausse : la porte reste fermée et l'arbitre ne passe jamais contre elle.",
                                        })}
                                    </Info>
                                </p>
                            )}
                        </section>
                    )}

                    {cond.genre === "sinon" && (
                        <p className="text-sm text-muted-foreground">
                            {t({
                                en: "This link is taken after the caller speaks, when no other link of the step passes (neither a condition nor the arbiter). One « Otherwise » per step.",
                                fr: "Cette liaison est prise après la parole de l'appelant, quand aucune autre liaison de l'étape ne passe (ni condition, ni arbitre). Une seule « Sinon » par étape.",
                            })}
                        </p>
                    )}

                    <section className="space-y-2" data-section="phrase">
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                            {t({ en: "Transition sentence", fr: "Phrase de transition" })}
                            <Info>
                                {t({
                                    en: "Said just before moving to the next step. It does not enter the conversation context: a filler sentence that shortens the wait.",
                                    fr: "Dite juste avant de passer à l'étape suivante. Elle n'entre pas dans le contexte de la conversation : une phrase de remplissage qui réduit l'attente.",
                                })}
                            </Info>
                        </p>
                        <span className="inline-flex rounded-lg bg-muted p-0.5 text-sm">
                            {(Object.keys(PHRASE) as Phrase[])
                                .filter((p) => p !== "audio" || enregistrements.length > 0 || phrase === "audio")
                                .map((p) => (
                                    <button
                                        key={p}
                                        type="button"
                                        aria-pressed={phrase === p}
                                        disabled={lecture}
                                        onClick={() => setPhrase(p)}
                                        className={`cursor-pointer rounded-md px-3 py-1 ${phrase === p ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                                    >
                                        {t(PHRASE[p])}
                                    </button>
                                ))}
                        </span>
                        {phrase === "text" && (
                            <Textarea value={texte} onChange={(e) => setTexte(e.target.value)} disabled={lecture} aria-label={t({ en: "Sentence text", fr: "Texte de la phrase" })} placeholder={t({ en: "E.g.: Let me check the slots.", fr: "Ex. : Je regarde les créneaux." })} className="min-h-16" />
                        )}
                        {phrase === "audio" && enregistrements.length > 0 && (
                            <Liste valeur={enr} changer={setEnr} options={enregistrements.map((r) => ({ valeur: r.recording_id, libelle: libelleEnr(r) }))} taille="default" className="w-full" />
                        )}
                    </section>
                </div>
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    {!lecture && !abandon && (
                        <div className="mr-auto">
                            <SuppressionConfirmee
                                size="default"
                                className="text-destructive hover:text-destructive"
                                onConfirmer={() => {
                                    onDelete();
                                    fermer();
                                }}
                            >
                                <Trash2 className="size-4" /> {t({ en: "Delete the link", fr: "Supprimer la liaison" })}
                            </SuppressionConfirmee>
                        </div>
                    )}
                    {lecture ? (
                        <Button onClick={fermer}>{t({ en: "Close", fr: "Fermer" })}</Button>
                    ) : abandon ? (
                        <>
                            <span className="text-sm" role="alert">
                                {t({ en: "Discard your changes?", fr: "Abandonner vos modifications ?" })}
                            </span>
                            <Button variant="outline" className="cursor-pointer" autoFocus onClick={() => setAbandon(false)}>
                                {t({ en: "Keep editing", fr: "Continuer la saisie" })}
                            </Button>
                            <Button variant="destructive" className="cursor-pointer" data-abandonner onClick={fermer}>
                                {t({ en: "Discard", fr: "Abandonner" })}
                            </Button>
                        </>
                    ) : (
                        <>
                            <Button variant="outline" onClick={demanderFermeture}>
                                {t({ en: "Cancel", fr: "Annuler" })}
                            </Button>
                            <Button disabled={enCours} onClick={() => void enregistrer()}>
                                {t({ en: "Save", fr: "Enregistrer" })}
                            </Button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}

function LigneRegle({ r, i, lecture, faute, maj, retirer }: { r: RegleDePorte; i: number; lecture: boolean; faute: Texte | null; maj: (i: number, p: Partial<RegleDePorte>) => void; retirer: () => void }) {
    const { t } = useLangue();
    const fixes = CHAMPS_FIXES[r.source];
    const champ = r.champ ?? "";
    const comparaisons = comparaisonsDe(r.source, champ);
    return (
        <div data-regle={i} className="space-y-1 rounded-xl bg-muted/50 p-2">
            {/* Deux lignes dans la largeur du panneau (480 px) : source et champ, puis comparaison et valeur. */}
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-2">
                <Liste
                    valeur={r.source}
                    changer={(v) => {
                        const source = v as SourceRegle;
                        const premier = CHAMPS_FIXES[source]?.[0]?.id ?? "";
                        maj(i, { source, champ: premier, comparaison: comparaisonsDe(source, premier)[0], valeur: "" });
                    }}
                    options={SOURCES.map((s) => ({ valeur: s.id, libelle: t(s.nom) }))}
                    className="w-full"
                />
                {fixes ? (
                    <Liste valeur={champ} changer={(v) => maj(i, { champ: v, comparaison: comparaisonsDe(r.source, v)[0] })} options={fixes.map((c) => ({ valeur: c.id, libelle: t(c.nom) }))} className="w-full" />
                ) : r.source !== "etape" ? (
                    <Input
                        value={champ}
                        onChange={(e) => maj(i, { champ: e.target.value })}
                        disabled={lecture}
                        aria-label={r.source === "outil" ? t({ en: "Tool name", fr: "Nom de l'outil" }) : t({ en: "Field", fr: "Champ" })}
                        placeholder={r.source === "outil" ? t({ en: "tool name", fr: "nom de l'outil" }) : t({ en: "field", fr: "champ" })}
                        className="h-8 w-full bg-card"
                    />
                ) : (
                    <span />
                )}
                {!lecture ? (
                    <button type="button" aria-label={t({ en: "Remove the rule", fr: "Retirer la règle" })} onClick={retirer} className="cursor-pointer rounded-md p-1.5 text-muted-foreground hover:bg-card hover:text-foreground">
                        <X className="size-3.5" />
                    </button>
                ) : (
                    <span />
                )}
                <Liste valeur={r.comparaison} changer={(v) => maj(i, { comparaison: v })} options={comparaisons.map((c) => ({ valeur: c, libelle: t(COMPARAISONS[c]) }))} className="w-full" />
                {!sansValeur(r.comparaison) && (
                    <Input
                        value={r.valeur ?? ""}
                        onChange={(e) => maj(i, { valeur: e.target.value })}
                        disabled={lecture}
                        aria-label={t({ en: "Value", fr: "Valeur" })}
                        placeholder={r.source === "heure" && champ === "heure" ? "18:00" : r.source === "heure" ? t({ en: "saturday, sunday", fr: "samedi, dimanche" }) : t({ en: "value", fr: "valeur" })}
                        className="h-8 w-full bg-card"
                    />
                )}
            </div>
            {faute && (
                <p role="alert" className="px-1 text-xs text-(--marque-danger-texte)">
                    {t(faute)}
                </p>
            )}
        </div>
    );
}
