"use client";

/**
 * [.mark] The catalogue of deterministic sentences (chantier l-agent-travaille, L2, E5).
 *
 * A list to edit, so a modal (E4) working on a copy: « Cancel » / « Save », its own PUT.
 * Each sentence: its variable (given to the agents as {{variable}}), what it is for, its
 * content said word for word, and its level. At the establishment's level, each
 * establishment may give its own content (in the establishments' modal); otherwise this
 * content is used.
 *
 * The two pick-up announcements are two fiches of the catalogue: shown here, read-only,
 * with where they are edited (the announcement below, and each establishment).
 */
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
    getPhrasesApiV1OrganizationsPhrasesGet,
    savePhrasesApiV1OrganizationsPhrasesPut,
} from "@/client/sdk.gen";
import type { Phrase, ReglagesAnnonceOuverture } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

export const PHRASES_ENREGISTREES: Texte = { en: "Sentences saved", fr: "Phrases enregistrées" };

const VARIABLE = /^[a-z][a-z0-9_]{1,39}$/;

export const charge_utile_phrases = (liste: Phrase[]) => ({
    format: "phrases-mark" as const,
    version: 1 as const,
    phrases: liste.map((p) => ({
        variable: p.variable.trim(),
        description: (p.description ?? "").trim(),
        contenu: (p.contenu ?? "").trim(),
        niveau: p.niveau ?? "organisation",
    })),
});

export function ModalePhrases({
    ouverte,
    onFermer,
    annonceOrganisation,
}: {
    ouverte: boolean;
    onFermer: (enregistre: boolean) => void;
    annonceOrganisation: ReglagesAnnonceOuverture;
}) {
    const { t } = useLangue();
    const [liste, setListe] = useState<Phrase[] | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!ouverte) return;
        setListe(null);
        setErreur(null);
        void (async () => {
            const reponse = await getPhrasesApiV1OrganizationsPhrasesGet();
            if (reponse.error || !reponse.data) {
                setErreur(detailFromError(reponse.error, "Sentences unreadable"));
                return;
            }
            setListe(reponse.data.phrases ?? []);
        })();
    }, [ouverte]);

    const modifier = (rang: number, champ: Partial<Phrase>) =>
        setListe((avant) => (avant ? avant.map((p, i) => (i === rang ? { ...p, ...champ } : p)) : avant));

    const fautes: string[] = [];
    const vues = new Set<string>();
    (liste ?? []).forEach((p) => {
        if (!VARIABLE.test(p.variable))
            fautes.push(
                `${p.variable || "…"} : ${t({ en: "lower case letters, digits and underscores, 2 to 40 characters.", fr: "minuscules, chiffres et tirets bas, 2 à 40 caractères." })}`,
            );
        if (vues.has(p.variable)) fautes.push(`${p.variable} : ${t({ en: "used twice.", fr: "utilisée deux fois." })}`);
        vues.add(p.variable);
    });

    const enregistrer = async () => {
        if (!liste) return;
        setEnCours(true);
        setErreur(null);
        const reponse = await savePhrasesApiV1OrganizationsPhrasesPut({ body: charge_utile_phrases(liste) });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Sentences not saved"));
            return;
        }
        toast.success(t(PHRASES_ENREGISTREES));
        onFermer(true);
    };

    const fixes: Array<{ variable: string; contenu: string; ou: Texte }> = [
        {
            variable: "annonce_fermeture",
            contenu: annonceOrganisation.annonce_fermeture ?? "",
            ou: { en: "Edited in « Closed-business announcement » below, and per establishment.", fr: "Modifiée dans « Annonce de fermeture » ci-dessous, et par établissement." },
        },
        {
            variable: "annonce_pause",
            contenu: annonceOrganisation.annonce_pause ?? "",
            ou: { en: "Edited in « Closed-business announcement » below, and per establishment.", fr: "Modifiée dans « Annonce de fermeture » ci-dessous, et par établissement." },
        },
    ];

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(false))}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl" data-testid="modale-phrases">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Sentences", fr: "Phrases" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "Sentences said word for word, given to the agents as {{variable}}. At the establishment's level, each establishment may have its own content; otherwise this one is used. The client sees them, only .mark changes them.",
                            fr: "Des phrases dites mot pour mot, données aux agents comme {{variable}}. Au niveau de l'établissement, chaque établissement peut avoir son propre contenu ; sinon celui-ci est utilisé. Le client les voit, seul .mark les modifie.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert" data-testid="erreur-phrases">
                        {erreur}
                    </p>
                )}
                <div className="space-y-2" data-testid="phrases-fixes">
                    {fixes.map((f) => (
                        <div key={f.variable} className="rounded border border-dashed border-border p-2 text-sm text-muted-foreground">
                            <code className="text-xs">{`{{${f.variable}}}`}</code>
                            <p className="whitespace-pre-line">{f.contenu}</p>
                            <p className="text-xs">{t(f.ou)}</p>
                        </div>
                    ))}
                </div>
                {liste === null ? (
                    !erreur && <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : (
                    <div className="space-y-3" data-testid="liste-phrases">
                        {liste.map((p, i) => (
                            <div key={i} className="space-y-2 rounded border border-border p-3">
                                <div className="grid gap-2 sm:grid-cols-[1fr_12rem_auto]">
                                    <Input
                                        aria-label={t({ en: "Variable", fr: "Variable" })}
                                        value={p.variable}
                                        placeholder="phrase_horaires_ete"
                                        className="font-mono"
                                        onChange={(e) => modifier(i, { variable: e.target.value })}
                                    />
                                    <select
                                        aria-label={t({ en: "Level", fr: "Niveau" })}
                                        className="rounded border border-border bg-background px-2 py-1 text-sm"
                                        value={p.niveau ?? "organisation"}
                                        onChange={(e) => modifier(i, { niveau: e.target.value as Phrase["niveau"] })}
                                    >
                                        <option value="organisation">{t({ en: "Organization", fr: "Organisation" })}</option>
                                        <option value="etablissement">{t({ en: "Establishment", fr: "Établissement" })}</option>
                                    </select>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        aria-label={t({ en: "Remove this sentence", fr: "Retirer cette phrase" })}
                                        onClick={() => setListe((avant) => (avant ? avant.filter((_p, j) => j !== i) : avant))}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                                <Input
                                    aria-label={t({ en: "Description", fr: "Description" })}
                                    value={p.description ?? ""}
                                    maxLength={200}
                                    placeholder={t({ en: "What it is for", fr: "À quoi elle sert" })}
                                    onChange={(e) => modifier(i, { description: e.target.value })}
                                />
                                <Textarea
                                    aria-label={t({ en: "Content", fr: "Contenu" })}
                                    rows={2}
                                    maxLength={1000}
                                    value={p.contenu ?? ""}
                                    onChange={(e) => modifier(i, { contenu: e.target.value })}
                                />
                            </div>
                        ))}
                        <Button
                            variant="outline"
                            size="sm"
                            data-testid="ajouter-phrase"
                            onClick={() => setListe((avant) => [...(avant ?? []), { variable: "", description: "", contenu: "", niveau: "organisation" }])}
                        >
                            <Plus className="mr-1 h-4 w-4" />
                            {t({ en: "Add a sentence", fr: "Ajouter une phrase" })}
                        </Button>
                        {fautes.length > 0 && (
                            <ul className="text-sm text-destructive" data-testid="fautes-phrases">
                                {fautes.map((f, i) => (
                                    <li key={i}>{f}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}
                <DialogFooter>
                    <Button variant="outline" onClick={() => onFermer(false)}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()} disabled={enCours || liste === null || fautes.length > 0} data-testid="enregistrer-phrases">
                        {t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
