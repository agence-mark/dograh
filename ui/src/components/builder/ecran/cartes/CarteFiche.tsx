"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): the « Client sheet » card (the pivot). Every line with its SOURCE (document,
 * page) and the place of the fact (object, knowledge base, prompt rule: B47); gaps in orange with a suggested
 * answer; correcting a line or answering a gap is a person's gesture; « Validate the sheet » is refused by the
 * server while a gap is open.
 */
import { Check, Pencil } from "lucide-react";
import { useState } from "react";

import {
    ecrireUneLigneDeLaFicheApiV1BuilderFicheWorkflowIdLignePut,
    validerLaFicheApiV1BuilderFicheWorkflowIdValiderPost,
} from "@/client";
import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { useBuilderEcran } from "../store";
import { Carte } from "./Carte";

const T = {
    titre: { en: "Client sheet", fr: "Fiche client" },
    aide: {
        en: "Each line cites where it comes from. Nothing is built from a line until a person validates the sheet.",
        fr: "Chaque ligne cite sa source. Rien n'est construit depuis une ligne tant qu'une personne n'a pas validé la fiche.",
    },
    vide: { en: "The sheet is empty.", fr: "La fiche est vide." },
    source: { en: "Source", fr: "Source" },
    trous: { en: "Questions to answer", fr: "Questions à trancher" },
    suggestion: { en: "Suggested answer", fr: "Réponse suggérée" },
    utiliser: { en: "Use it", fr: "La reprendre" },
    repondre: { en: "Answer", fr: "Répondre" },
    corriger: { en: "Correct", fr: "Corriger" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    valider: { en: "Validate the sheet", fr: "Valider la fiche" },
    validee: { en: "Validated by", fr: "Validée par" },
    reste: { en: "Answer the open questions to validate.", fr: "Répondez aux questions ouvertes pour valider." },
    place: { en: "Goes to", fr: "Va dans" },
    objet: { en: "an object", fr: "un objet" },
    base: { en: "the knowledge base", fr: "la base de connaissances" },
    regle: { en: "a prompt rule", fr: "une règle du prompt" },
    echec: { en: "The request failed.", fr: "La demande a échoué." },
} satisfies Record<string, Texte>;

interface LigneDeLaFiche {
    valeur: unknown;
    source: string;
    classement?: "objet" | "base" | "regle" | null;
}
interface FicheLue {
    champs: Record<string, LigneDeLaFiche>;
    trous: { champ: string; question: string; reponse_suggeree?: string | null }[];
    valide_par?: string | null;
}

const montrer = (valeur: unknown) => (typeof valeur === "string" ? valeur : JSON.stringify(valeur));

export function CarteFiche({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const contexte = useBuilderEcran((s) => s.contexte);
    const rafraichir = useBuilderEcran((s) => s.rafraichirLeContexte);
    const [saisies, setSaisies] = useState<Record<string, string>>({});
    const [enEdition, setEnEdition] = useState<string | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    const fiche = (contexte?.fiche ?? { champs: {}, trous: [] }) as unknown as FicheLue;
    const classements = (contexte?.classements ?? {}) as Record<string, "objet" | "base" | "regle">;
    const lignes = Object.entries(fiche.champs);

    const ecrire = async (champ: string, valeur: string, classement?: "objet" | "base" | "regle") => {
        setErreur(null);
        const reponse = await ecrireUneLigneDeLaFicheApiV1BuilderFicheWorkflowIdLignePut({
            path: { workflow_id: workflowId },
            body: { champ, valeur, classement: classement ?? null },
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, t(T.echec)));
            return;
        }
        setEnEdition(null);
        setSaisies((s) => ({ ...s, [champ]: "" }));
        await rafraichir(workflowId);
    };

    const valider = async () => {
        setErreur(null);
        const reponse = await validerLaFicheApiV1BuilderFicheWorkflowIdValiderPost({ path: { workflow_id: workflowId } });
        if (reponse.error) setErreur(detailFromError(reponse.error, t(T.echec)));
        await rafraichir(workflowId);
    };

    const placeDe = (classement: string) => (classement === "objet" ? T.objet : classement === "base" ? T.base : T.regle);

    return (
        <Carte type="fiche" titre={t(T.titre)} aide={t(T.aide)}>
            {lignes.length === 0 && fiche.trous.length === 0 && <p className="text-xs text-muted-foreground">{t(T.vide)}</p>}
            <ul className="space-y-1.5">
                {lignes.map(([champ, ligne]) => (
                    <li key={champ} className="rounded-md border p-2 text-xs" data-ligne={champ}>
                        <div className="flex items-start gap-2">
                            <span className="font-medium">{champ}</span>
                            <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-muted-foreground" data-classement={classements[champ]}>
                                {t(T.place)} {t(placeDe(classements[champ] ?? "regle"))}
                            </span>
                            <button
                                type="button"
                                aria-label={`${t(T.corriger)} ${champ}`}
                                className="text-muted-foreground hover:text-foreground"
                                onClick={() => {
                                    setEnEdition(champ);
                                    setSaisies((s) => ({ ...s, [champ]: montrer(ligne.valeur) }));
                                }}
                            >
                                <Pencil className="h-3.5 w-3.5" aria-hidden />
                            </button>
                        </div>
                        {enEdition === champ ? (
                            <div className="mt-1 flex gap-2">
                                <Input value={saisies[champ] ?? ""} onChange={(e) => setSaisies((s) => ({ ...s, [champ]: e.target.value }))} className="h-8 text-xs" aria-label={champ} />
                                <Button type="button" size="sm" disabled={!(saisies[champ] ?? "").trim()} onClick={() => void ecrire(champ, saisies[champ], classements[champ])}>
                                    {t(T.enregistrer)}
                                </Button>
                            </div>
                        ) : (
                            <p className="mt-1 whitespace-pre-wrap break-words">{montrer(ligne.valeur)}</p>
                        )}
                        <p className="mt-1 text-[11px] text-muted-foreground">
                            {t(T.source)} : {ligne.source}
                        </p>
                    </li>
                ))}
            </ul>
            {fiche.trous.length > 0 && (
                <div className="mt-2 space-y-1.5" data-trous>
                    <h5 className="text-xs font-semibold text-(--signal-warn)">{t(T.trous)}</h5>
                    {fiche.trous.map((trou) => (
                        <div key={trou.champ} className="rounded-md border border-(--signal-warn) bg-(--signal-warn)/10 p-2 text-xs" data-trou={trou.champ}>
                            <p className="font-medium">{trou.question}</p>
                            {trou.reponse_suggeree && (
                                <p className="mt-1 text-muted-foreground">
                                    {t(T.suggestion)} : {trou.reponse_suggeree}{" "}
                                    <button type="button" className="underline" onClick={() => void ecrire(trou.champ, trou.reponse_suggeree ?? "")}>
                                        {t(T.utiliser)}
                                    </button>
                                </p>
                            )}
                            <div className="mt-1 flex gap-2">
                                <Input value={saisies[trou.champ] ?? ""} onChange={(e) => setSaisies((s) => ({ ...s, [trou.champ]: e.target.value }))} className="h-8 text-xs" aria-label={trou.question} />
                                <Button type="button" size="sm" disabled={!(saisies[trou.champ] ?? "").trim()} onClick={() => void ecrire(trou.champ, saisies[trou.champ])}>
                                    {t(T.repondre)}
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
            <div className="mt-3 flex items-center gap-2">
                {fiche.valide_par ? (
                    <span className="flex items-center gap-1 text-xs text-(--signal-ok)" data-validee>
                        <Check className="h-3.5 w-3.5" aria-hidden /> {t(T.validee)} {fiche.valide_par}
                    </span>
                ) : (
                    <>
                        <Button type="button" size="sm" disabled={lignes.length === 0 || fiche.trous.length > 0} onClick={() => void valider()}>
                            {t(T.valider)}
                        </Button>
                        {fiche.trous.length > 0 && <span className="text-xs text-muted-foreground">{t(T.reste)}</span>}
                    </>
                )}
            </div>
            {erreur && <p role="alert" className="mt-2 text-xs text-destructive">{erreur}</p>}
        </Carte>
    );
}
