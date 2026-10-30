"use client";

/**
 * [.mark] builder-agent-vocal (lot 2): the « Library » page. Every family of what can be standardised in an agent
 * (B44), with the status of each element (Candidate · Recipe · Rejected), its version, its bench, and « used by N
 * agents ». Everyone reads; only members of the .mark organization write (the server says no to the others).
 */
import { useCallback, useEffect, useState } from "react";

import {
    lireLUtilisationApiV1BuilderBibliothequeFamilleSlugUtilisationGet,
    lireUnElementApiV1BuilderBibliothequeFamilleSlugGet,
    listerLesElementsApiV1BuilderBibliothequeGet,
    listerLesFamillesApiV1BuilderBibliothequeFamillesGet,
} from "@/client";
import type { Element as ElementBibliotheque, Resume, VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { detailFromError } from "@/lib/apiError";

import { ElementDeLaBibliotheque } from "./ElementDeLaBibliotheque";
import { FormulaireImport } from "./FormulaireImport";
import { GROUPES, type StatutDeLaBibliotheque,STATUTS } from "./libelles";
import { PropositionsDeLaBibliotheque } from "./PropositionsDeLaBibliotheque";

type Onglet = "elements" | "propositions" | "ajouter";
const CHAMP = "h-9 rounded-md border bg-background px-2 text-sm";

export function PageBibliotheque() {
    const { t } = useLangue();
    const [onglet, setOnglet] = useState<Onglet>("elements");
    const [familles, setFamilles] = useState<VueFamille[]>([]);
    const [famille, setFamille] = useState("");
    const [statut, setStatut] = useState<StatutDeLaBibliotheque | "">("");
    const [elements, setElements] = useState<Resume[] | null>(null);
    const [choisi, setChoisi] = useState<{ famille: string; slug: string } | null>(null);
    const [detail, setDetail] = useState<ElementBibliotheque | null>(null);
    const [utilisePar, setUtilisePar] = useState(0);
    const [erreur, setErreur] = useState<string | null>(null);

    useEffect(() => {
        void (async () => {
            const reponse = await listerLesFamillesApiV1BuilderBibliothequeFamillesGet();
            if (reponse.error || !reponse.data) {
                setErreur(detailFromError(reponse.error, "The families could not be read"));
                return;
            }
            setFamilles(reponse.data);
        })();
    }, []);

    const chargerLaListe = useCallback(async () => {
        const reponse = await listerLesElementsApiV1BuilderBibliothequeGet({
            query: { famille: famille || undefined, statut: statut || undefined },
        });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The library could not be read"));
            return;
        }
        setErreur(null);
        setElements(reponse.data);
    }, [famille, statut]);

    useEffect(() => {
        void chargerLaListe();
    }, [chargerLaListe]);

    const ouvrir = useCallback(async (f: string, slug: string) => {
        setChoisi({ famille: f, slug });
        const [element, usage] = await Promise.all([
            lireUnElementApiV1BuilderBibliothequeFamilleSlugGet({ path: { famille: f, slug } }),
            lireLUtilisationApiV1BuilderBibliothequeFamilleSlugUtilisationGet({ path: { famille: f, slug } }),
        ]);
        if (element.error || !element.data) {
            setErreur(detailFromError(element.error, "The element could not be read"));
            return;
        }
        setDetail(element.data);
        setUtilisePar((usage.data as { nombre?: number } | undefined)?.nombre ?? 0);
    }, []);

    const groupes = [...new Set(familles.map((f) => f.groupe))];
    const nomDeFamille = (slug: string) => familles.find((f) => f.slug === slug)?.libelle ?? slug;

    return (
        <div className="space-y-4" data-testid="page-bibliotheque">
            <div role="tablist" className="flex gap-2 border-b">
                {(
                    [
                        ["elements", { en: "Elements", fr: "Éléments" }],
                        ["propositions", { en: "Proposals", fr: "Propositions" }],
                        ["ajouter", { en: "Add", fr: "Ajouter" }],
                    ] as const
                ).map(([id, texte]) => (
                    <button
                        key={id}
                        role="tab"
                        aria-selected={onglet === id}
                        className={`px-3 py-2 text-sm ${onglet === id ? "border-b-2 border-primary font-medium" : "text-muted-foreground"}`}
                        onClick={() => setOnglet(id)}
                    >
                        {t(texte)}
                    </button>
                ))}
            </div>

            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}

            {onglet === "propositions" && <PropositionsDeLaBibliotheque onDecision={() => void chargerLaListe()} />}

            {onglet === "ajouter" && (
                <FormulaireImport
                    familles={familles}
                    familleChoisie={famille}
                    onCree={(f, slug, garderLEcran) => {
                        void chargerLaListe();
                        void ouvrir(f, slug);
                        if (!garderLEcran) setOnglet("elements");
                    }}
                />
            )}

            {onglet === "elements" && (
                <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-3">
                        <label className="flex items-center gap-2 text-sm">
                            <span>{t({ en: "Family", fr: "Famille" })}</span>
                            <select
                                aria-label={t({ en: "Filter by family", fr: "Filtrer par famille" })}
                                className={CHAMP}
                                value={famille}
                                onChange={(e) => setFamille(e.target.value)}
                            >
                                <option value="">{t({ en: "All families", fr: "Toutes les familles" })}</option>
                                {groupes.map((g) => (
                                    <optgroup key={g} label={GROUPES[g] ? t(GROUPES[g]) : g}>
                                        {familles
                                            .filter((f) => f.groupe === g)
                                            .map((f) => (
                                                <option key={f.slug} value={f.slug}>
                                                    {f.libelle}
                                                </option>
                                            ))}
                                    </optgroup>
                                ))}
                            </select>
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                            <span>{t({ en: "Status", fr: "Statut" })}</span>
                            <select
                                aria-label={t({ en: "Filter by status", fr: "Filtrer par statut" })}
                                className={CHAMP}
                                value={statut}
                                onChange={(e) => setStatut(e.target.value as StatutDeLaBibliotheque | "")}
                            >
                                <option value="">{t({ en: "All statuses", fr: "Tous les statuts" })}</option>
                                {(Object.keys(STATUTS) as StatutDeLaBibliotheque[]).map((s) => (
                                    <option key={s} value={s}>
                                        {t(STATUTS[s].texte)}
                                    </option>
                                ))}
                            </select>
                        </label>
                    </div>

                    {elements !== null && elements.length === 0 && (
                        <p className="rounded border p-4 text-sm text-muted-foreground" data-testid="bibliotheque-vide">
                            {t({ en: "Nothing in the library for this filter.", fr: "Rien dans la bibliothèque pour ce filtre." })}
                        </p>
                    )}
                    <ul className="space-y-2">
                        {(elements ?? []).map((e) => (
                            <li key={`${e.famille}/${e.slug}`}>
                                <button
                                    className={`w-full rounded border p-3 text-left text-sm hover:bg-muted ${
                                        choisi?.famille === e.famille && choisi.slug === e.slug ? "border-primary" : ""
                                    }`}
                                    data-testid={`element-${e.famille}-${e.slug}`}
                                    onClick={() => void ouvrir(e.famille, e.slug)}
                                >
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className="font-medium">{e.titre}</span>
                                        <span className={`rounded px-2 py-0.5 text-xs ${STATUTS[e.statut as StatutDeLaBibliotheque].classe}`}>
                                            {t(STATUTS[e.statut as StatutDeLaBibliotheque].texte)}
                                        </span>
                                        <span className="text-xs text-muted-foreground">
                                            {nomDeFamille(e.famille)} · v{e.version_courante} · {e.auteur}
                                        </span>
                                        <span className="ml-auto text-xs text-muted-foreground">
                                            {t({ en: `Used by ${e.utilisee_par ?? 0} agent(s)`, fr: `Utilisée par ${e.utilisee_par ?? 0} agent(s)` })}
                                        </span>
                                    </div>
                                    {e.banc && <p className="mt-1 text-xs text-muted-foreground">{e.banc.description}</p>}
                                </button>
                            </li>
                        ))}
                    </ul>

                    {detail && choisi && (
                        <ElementDeLaBibliotheque
                            key={`${detail.famille}/${detail.slug}`}
                            element={detail}
                            utilisePar={utilisePar}
                            onChange={(nouveau) => {
                                setDetail(nouveau);
                                void chargerLaListe();
                            }}
                        />
                    )}
                </div>
            )}
        </div>
    );
}
