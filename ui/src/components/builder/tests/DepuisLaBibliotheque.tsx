"use client";

/**
 * [.mark] U3 (E47): « Add a test › From the library ». The typical scenarios come from the library (family `scenarios-test`); before
 * copying, the window says what the agent lacks (a step, a tool, an outcome, a field, a character). Nothing is copied while
 * something lacks, unless the person chooses « copy anyway ». The copy is a test of the agent, adjusted after.
 */
import { useState } from "react";

import {
    copierUnScenarioApiV1BuilderBibliothequeScenariosTypesSlugCopierPost,
    examinerUnScenarioApiV1BuilderBibliothequeScenariosTypesSlugExaminerPost,
} from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import type { BilanDeScenario, RessourcesDeTest } from "./types";

export function DepuisLaBibliotheque({
    workflowId,
    ressources,
    onFermer,
    onCopie,
}: {
    workflowId: number;
    ressources: RessourcesDeTest | null;
    onFermer: () => void;
    onCopie: (slug: string) => void;
}) {
    const { t } = useLangue();
    const [choisi, setChoisi] = useState<string | null>(null);
    const [bilan, setBilan] = useState<BilanDeScenario | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    const examiner = async (slug: string) => {
        setChoisi(slug);
        setBilan(null);
        setErreur(null);
        const r = await examinerUnScenarioApiV1BuilderBibliothequeScenariosTypesSlugExaminerPost({ path: { slug }, body: { workflow_id: workflowId } as never });
        if (r.error) setErreur(echecAffiche(r.error));
        else setBilan(r.data as unknown as BilanDeScenario);
    };

    const copier = async (quandMeme: boolean) => {
        if (!choisi) return;
        const r = await copierUnScenarioApiV1BuilderBibliothequeScenariosTypesSlugCopierPost({
            path: { slug: choisi },
            body: { workflow_id: workflowId, copier_quand_meme: quandMeme } as never,
        });
        if (r.error) {
            setErreur(echecAffiche(r.error));
            return;
        }
        const donnees = r.data as unknown as { copie?: boolean; test?: { slug: string } } & BilanDeScenario;
        if (donnees.copie && donnees.test) onCopie(donnees.test.slug);
        else setBilan(donnees);
    };

    const manque = bilan ? bilan.absents.length > 0 || bilan.personnage_absent : false;
    const scenarios = ressources?.scenarios_types ?? [];

    return (
        <Dialog open onOpenChange={(o) => !o && onFermer()}>
            <DialogContent
                onOpenAutoFocus={(e) => e.preventDefault()}
                className="flex max-h-[86vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl"
                data-testid="depuis-la-bibliotheque"
            >
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        {t({ en: "Add a test from the library", fr: "Ajouter un test depuis la bibliothèque" })}
                        <Info>{t({ en: "A typical scenario becomes a test of this agent. It first says what the agent lacks.", fr: "Un scénario type devient un test de cet agent. On dit d'abord ce qui lui manque." })}</Info>
                    </DialogTitle>
                </div>
                <div className="min-h-0 flex-1 space-y-4 overflow-auto bg-background px-6 py-4">
                    {scenarios.length === 0 && (
                        <p className="text-sm text-muted-foreground">{t({ en: "The library holds no typical scenario yet.", fr: "La bibliothèque ne contient encore aucun scénario type." })}</p>
                    )}
                    <ul className="divide-y">
                        {scenarios.map((s) => (
                            <li key={s.slug}>
                                <button
                                    type="button"
                                    onClick={() => void examiner(s.slug)}
                                    className={`flex w-full cursor-pointer items-center gap-2 py-2 text-left text-sm hover:font-medium ${choisi === s.slug ? "font-medium" : ""}`}
                                >
                                    {s.titre}
                                    <span className="ml-auto text-xs text-muted-foreground">{s.statut}</span>
                                </button>
                            </li>
                        ))}
                    </ul>
                    {bilan && (
                        <section className="space-y-2 text-sm" data-testid="bilan-du-scenario">
                            <h3 className="font-semibold">{bilan.titre}</h3>
                            {bilan.but && <p className="text-muted-foreground">{bilan.but}</p>}
                            {bilan.absents.map((a, i) => (
                                <p key={i} className="text-(--signal-danger)">
                                    {t({ en: "The agent lacks", fr: "L'agent n'a pas" })} : {a.manque} ({a.sorte})
                                </p>
                            ))}
                            {bilan.personnage_absent && <p className="text-(--signal-danger)">{t({ en: "The character is not in the library.", fr: "Le personnage n'est pas dans la bibliothèque." })}</p>}
                            {!manque && <p>{t({ en: "The agent has everything this scenario cites.", fr: "L'agent a tout ce que ce scénario cite." })}</p>}
                        </section>
                    )}
                    {erreur && (
                        <p role="alert" className="text-sm text-destructive">
                            {erreur}
                        </p>
                    )}
                </div>
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    <Button variant="outline" onClick={onFermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button disabled={!bilan} onClick={() => void copier(manque)}>
                        {manque ? t({ en: "Copy anyway", fr: "Copier quand même" }) : t({ en: "Copy as a test", fr: "Copier comme test" })}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
