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

/** [.mark] L7 (PN7): the three sentences of the outage fallback, with the defaults the server
 * says when they are absent or empty (``api/schemas/panne.py``, kept word for word). */
export const PHRASES_DE_PANNE: Phrase[] = [
    {
        variable: "phrase_renvoi_panne",
        description: "Said by Twilio when the agent fails, before ringing the second number.",
        contenu: "Je rencontre un souci technique, je vous passe un collaborateur, ne quittez pas.",
        niveau: "etablissement",
    },
    {
        variable: "phrase_rappel_panne",
        description: "Said when closed or when nobody answers; {reouverture} and the [ ] like the closing announcement.",
        contenu: "Je rencontre un souci technique. Nous vous rappelons [dès la réouverture, {reouverture}]. Merci et au revoir.",
        niveau: "etablissement",
    },
    {
        variable: "phrase_excuse_panne",
        description: "Said on an outbound call when the agent fails, before hanging up.",
        contenu: "Je rencontre un souci technique, je vous prie de m'excuser. Nous vous rappellerons. Au revoir.",
        niveau: "organisation",
    },
];

/** [.mark] l-agent-collegue (R-4, decision of Evan 07/10): the sentences the CODE says for the team
 * and the actions, each a fiche of the catalogue with the default the server says when it is
 * absent or empty (kept word for word: ``services/equipe/diriger.py``, ``services/planificateur/
 * action.py``, ``services/verification/action.py``; a test compares them). The content is said to
 * the caller in French; its description is written in the language of the screen. */
export const PHRASES_DES_ACTIONS: Array<{ variable: string; description: Texte; contenu: string; niveau: Phrase["niveau"] }> = [
    {
        variable: "phrase_transfert_personne",
        description: {
            en: "Said before the call is put through to a person of the team ({{prenom}}: her first name).",
            fr: "Dite avant que l'appel soit passé à une personne de l'équipe ({{prenom}} : son prénom).",
        },
        contenu: "Je vous mets en relation avec {{prenom}}, ne quittez pas.",
        niveau: "organisation",
    },
    {
        variable: "phrase_transmission_personne",
        description: {
            en: "Said when the request is passed on to a person, or when she does not take the transfer and will call back ({{prenom}}: her first name).",
            fr: "Dite quand la demande est transmise à une personne, ou quand elle ne prend pas le transfert et rappellera ({{prenom}} : son prénom).",
        },
        contenu: "Je transmets votre demande à {{prenom}}, qui reviendra vers vous.",
        niveau: "organisation",
    },
    {
        variable: "phrase_planificateur_rappel",
        description: {
            en: "Said when the planner finds no slot: the request is noted for a call-back ({{souhait}}: the caller's wish).",
            fr: "Dite quand le planificateur ne trouve aucun créneau : la demande est notée pour un rappel ({{souhait}} : le souhait de l'appelant).",
        },
        contenu: "Je n'ai pas de créneau qui convienne pour le moment : je note votre demande, on vous rappelle pour fixer le rendez-vous.",
        niveau: "organisation",
    },
    {
        variable: "phrase_verification_rappel",
        description: {
            en: "Said when the caller could not be verified after two attempts: nothing of his record is read, a colleague calls back.",
            fr: "Dite quand l'appelant n'a pas pu être vérifié après deux tentatives : rien de son dossier n'est lu, un collègue rappelle.",
        },
        contenu: "Je ne peux pas vous donner ces informations sans vérifier votre identité : je note votre demande, un collègue vous rappelle.",
        niveau: "organisation",
    },
];

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
                        {PHRASES_DE_PANNE.some((d) => !liste.some((p) => p.variable === d.variable)) && (
                            <Button
                                variant="outline"
                                size="sm"
                                data-testid="ajouter-phrases-panne"
                                onClick={() =>
                                    setListe((avant) => [
                                        ...(avant ?? []),
                                        ...PHRASES_DE_PANNE.filter((d) => !(avant ?? []).some((p) => p.variable === d.variable)),
                                    ])
                                }
                            >
                                <Plus className="mr-1 h-4 w-4" />
                                {t({ en: "Add the outage sentences", fr: "Ajouter les phrases de panne" })}
                            </Button>
                        )}
                        {PHRASES_DES_ACTIONS.some((d) => !liste.some((p) => p.variable === d.variable)) && (
                            <Button
                                variant="outline"
                                size="sm"
                                data-testid="ajouter-phrases-actions"
                                onClick={() =>
                                    setListe((avant) => [
                                        ...(avant ?? []),
                                        ...PHRASES_DES_ACTIONS.filter((d) => !(avant ?? []).some((p) => p.variable === d.variable)).map((d) => ({
                                            variable: d.variable,
                                            description: t(d.description),
                                            contenu: d.contenu,
                                            niveau: d.niveau,
                                        })),
                                    ])
                                }
                            >
                                <Plus className="mr-1 h-4 w-4" />
                                {t({ en: "Add the sentences of the team and the actions", fr: "Ajouter les phrases de l'équipe et des actions" })}
                            </Button>
                        )}
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
