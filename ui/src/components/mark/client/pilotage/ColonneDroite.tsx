"use client";

/**
 * [.mark] Partie 3, L5b (sous-lot 2) : la colonne de droite de la page de pilotage d'un client : la santé des branchements (repliée
 * quand tout va bien), « Relation client » en petit (non lus, dernière phrase reçue, lien vers le Hub) et l'activité récente
 * (qui a fait quoi). Elle passe SOUS la colonne principale quand la place manque (règle du panneau : le conteneur, pas l'écran).
 */
import { Check, ChevronDown, Mail } from "lucide-react";
import Link from "next/link";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

import { T, texte } from "./textes";
import type { PilotageClient } from "./types";

export type Branchement = { id: string; titre: Texte; ok: boolean; etat: string; vers: string };

function Section({ titre, info, action, children }: { titre: string; info?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode }) {
    return (
        <section>
            <div className="flex items-center gap-2 pb-2">
                <h2 className="flex flex-1 items-center gap-1.5 text-base font-semibold">
                    {titre}
                    {info && <Info>{info}</Info>}
                </h2>
                {action}
            </div>
            {children}
        </section>
    );
}

export function Branchements({ branchements, base }: { branchements: Branchement[] | null; base: string }) {
    const { t } = useLangue();
    const problemes = (branchements ?? []).filter((b) => !b.ok);
    return (
        <Section titre={t(T.branchements)} info={t(T.branchementsInfo)}>
            {branchements === null ? (
                <p className="py-2 text-sm text-muted-foreground">{t(T.chargement)}</p>
            ) : problemes.length === 0 ? (
                <Collapsible data-pilotage="branchements-ok">
                    <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-2 py-2 text-sm hover:font-semibold">
                        <Check className="size-4 text-(--etat-fait)" strokeWidth={2.5} />
                        <span className="flex-1 text-left">{t(T.toutVaBien)}</span>
                        <ChevronDown className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                        <ul className="divide-y">
                            {branchements.map((b) => (
                                <li key={b.id} data-branchement={b.id} className="py-2 text-sm">
                                    <Link href={`${base}/${b.vers}`} className="block hover:font-semibold">
                                        {t(b.titre)}
                                    </Link>
                                    <span className="text-xs text-muted-foreground">{b.etat}</span>
                                </li>
                            ))}
                        </ul>
                    </CollapsibleContent>
                </Collapsible>
            ) : (
                <ul className="divide-y" data-pilotage="branchements-a-regler">
                    {branchements.map((b) => (
                        <li key={b.id} data-branchement={b.id} className="flex items-start gap-2 py-2 text-sm">
                            <span className={`mt-1.5 size-2 shrink-0 rounded-full ${b.ok ? "bg-(--point-publie)" : "bg-destructive"}`} />
                            <span className="min-w-0 flex-1">
                                <span className="block">{t(b.titre)}</span>
                                <span className="text-xs text-muted-foreground">{b.etat}</span>
                            </span>
                            {!b.ok && (
                                <Link href={`${base}/${b.vers}`} className="shrink-0 text-xs text-(--acc) hover:font-semibold">
                                    {t(T.regler)}
                                </Link>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </Section>
    );
}

export function RelationCompacte({ pilotage, org }: { pilotage: PilotageClient | null; org: string }) {
    const { t, langue } = useLangue();
    const relation = pilotage?.relation ?? null;
    const rien = relation !== null && relation.non_lus === 0 && relation.demandes_nouvelles === 0;
    return (
        <Section
            titre={t(T.relation)}
            action={
                <Link href="/relation/clients" className="text-sm text-(--acc) hover:font-semibold">
                    {t(T.ouvrirLeHub)}
                </Link>
            }
        >
            {pilotage === null ? (
                <p className="py-2 text-sm text-muted-foreground">{t(T.chargement)}</p>
            ) : relation === null ? (
                <p data-pilotage="relation-illisible" className="py-2 text-sm text-muted-foreground">
                    {t(T.lectureImpossible)} {t(T.sujets.relation)}
                </p>
            ) : rien ? (
                <p data-pilotage="relation-vide" className="py-2 text-sm text-muted-foreground">
                    {t(T.rienEnAttente)}
                </p>
            ) : (
                <Link href={`/relation/clients/${org}`} data-pilotage="relation" className="block space-y-1 py-1 text-sm hover:font-semibold">
                    <span className="flex items-center gap-2">
                        <Mail className="size-4 text-muted-foreground" />
                        {t(texte(T.nonLus, relation.non_lus))}
                        {relation.demandes_nouvelles > 0 && <span className="font-normal text-muted-foreground">· {t(texte(T.demandes, relation.demandes_nouvelles))}</span>}
                    </span>
                    {relation.dernier && (
                        <>
                            <span className="block font-normal text-muted-foreground">« {relation.dernier.texte} »</span>
                            <span className="block text-xs font-normal text-muted-foreground">
                                {relation.dernier.auteur} · {quand(relation.dernier.cree_le, langue)}
                            </span>
                        </>
                    )}
                </Link>
            )}
        </Section>
    );
}

/** « 05/11 08:40 », dans la langue de l'écran. */
export function quand(iso: string, langue?: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString(langue === "en" ? "en-GB" : "fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function ActiviteRecente({ pilotage }: { pilotage: PilotageClient | null }) {
    const { t, langue } = useLangue();
    const activite = pilotage?.activite ?? null;
    return (
        <Section titre={t(T.activite)}>
            {pilotage === null ? (
                <p className="py-2 text-sm text-muted-foreground">{t(T.chargement)}</p>
            ) : activite === null ? (
                <p data-pilotage="activite-illisible" className="py-2 text-sm text-muted-foreground">
                    {t(T.lectureImpossible)} {t(T.sujets.activite)}
                </p>
            ) : activite.length === 0 ? (
                <p className="py-2 text-sm text-muted-foreground">{t(T.rienPourLeMoment)}</p>
            ) : (
                <ul className="divide-y" data-pilotage="activite">
                    {activite.map((g) => (
                        <li key={g.id} className="py-2 text-sm">
                            <span className="font-medium">{g.par_builder ? t(T.builder) : (g.qui ?? t(T.equipe))}</span> {t(T.gestes[g.action] ?? T.geste)}
                            <span className="block text-xs text-muted-foreground">
                                {quand(g.quand, langue)}
                                {g.par_builder && g.qui ? ` · ${g.qui}` : ""}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </Section>
    );
}
