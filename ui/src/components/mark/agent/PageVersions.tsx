"use client";

/**
 * [.mark] L'onglet Versions d'un agent (U3, E46) : l'historique paginé (25 par page, côté serveur), ouvrir une version
 * (le Parcours, en lecture seule si elle n'est pas la version en cours) et la comparer à la précédente. Reprend ce que
 * faisait le panneau latéral de l'éditeur (supprimé) : rien n'est perdu.
 *
 * La version « en cours » est le brouillon s'il existe, sinon la publiée : son lien ouvre le Parcours modifiable
 * (`/agents/<id>`) ; toutes les autres ouvrent `?version=<n>`.
 */
import { FileDiff, FileText } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { WorkflowVersionDiffDialog } from "@/app/workflow/[workflowId]/components/WorkflowVersionDiffDialog";
import { getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet } from "@/client/sdk.gen";
import type { WorkflowVersionResponse } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { useOrganizationTimezone } from "@/hooks/useOrganizationTimezone";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dateTime";

import { EtatVide } from "../studio/etat-vide";
import { type EtatPoint, PointEtat } from "../studio/marques";
import { BarrePagination, fenetrePage, PAR_PAGE } from "../studio/pagination";
import { Cellule, Ligne, Tableau } from "../studio/tableau";
import { adresseOnglet } from "./onglets-agent";

const T = {
    version: { en: "Version", fr: "Version" },
    etat: { en: "State", fr: "État" },
    date: { en: "Date", fr: "Date" },
    brouillon: { en: "Draft", fr: "Brouillon" },
    publiee: { en: "Published", fr: "Publiée" },
    archivee: { en: "Archived", fr: "Archivée" },
    enCours: { en: "current", fr: "en cours" },
    ouvrir: { en: "Open", fr: "Ouvrir" },
    comparer: { en: "Compare with the previous one", fr: "Comparer avec la précédente" },
    aucune: { en: "No version yet", fr: "Aucune version pour l'instant" },
    sansPrecedente: { en: "has no previous version", fr: "n'a pas de version précédente" },
    echecComparaison: { en: "The versions could not be compared.", fr: "Les versions n'ont pas pu être comparées." },
    historiqueChange: {
        en: "The history changed. Try the comparison again.",
        fr: "L'historique a changé. Recommencez la comparaison.",
    },
} satisfies Record<string, Texte>;

const POINT: Record<string, EtatPoint> = { draft: "brouillon", published: "publie", archived: "fini" };

/** L'adresse qui ouvre une version : le Parcours modifiable pour la version en cours, `?version=<n>` pour les autres. */
export function adresseDeLaVersion(agentId: number, version: Pick<WorkflowVersionResponse, "version_number">, enCours: boolean) {
    return enCours ? adresseOnglet(agentId, "parcours") : `${adresseOnglet(agentId, "parcours")}?version=${version.version_number}`;
}

export function PageVersions({ agentId }: { agentId: number }) {
    const { t } = useLangue();
    const fuseau = useOrganizationTimezone();
    const { user, loading: authLoading } = useAuth();
    const [page, setPage] = useState(0);
    const [lignes, setLignes] = useState<WorkflowVersionResponse[] | null>(null);
    const [aSuite, setASuite] = useState(false);
    const [brouillonId, setBrouillonId] = useState<number | null>(null);
    const [erreur, setErreur] = useState(false);
    const [enComparaison, setEnComparaison] = useState<number | null>(null);
    const [paire, setPaire] = useState<{ previousVersion: WorkflowVersionResponse; selectedVersion: WorkflowVersionResponse } | null>(null);

    const charger = useCallback(async () => {
        setErreur(false);
        try {
            const { limit, offset } = fenetrePage(page);
            const [liste, brouillon] = await Promise.all([
                getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet({
                    path: { workflow_id: agentId },
                    // Une ligne de plus que la page : « il y a une suite » est exact sans compter tout l'historique.
                    query: { limit: limit + 1, offset },
                }),
                getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet({
                    path: { workflow_id: agentId },
                    query: { status: "draft", limit: 1 },
                }),
            ]);
            if (liste.error || !liste.data) {
                setErreur(true);
                return;
            }
            setLignes(liste.data.slice(0, PAR_PAGE));
            setASuite(liste.data.length > PAR_PAGE);
            setBrouillonId(brouillon.data?.[0]?.id ?? null);
        } catch {
            setErreur(true);
        }
    }, [agentId, page]);

    useEffect(() => {
        if (authLoading || !user) return;
        void charger();
    }, [charger, authLoading, user]);

    const comparer = async (version: WorkflowVersionResponse, rang: number) => {
        if (enComparaison !== null) return;
        setEnComparaison(version.id);
        try {
            const reponse = await getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet({
                path: { workflow_id: agentId },
                query: { limit: 2, offset: page * PAR_PAGE + rang },
            });
            if (reponse.error) {
                notifier.echec({ fr: "Comparaison impossible. Réessayez.", en: "Could not compare. Try again." }, { erreur: reponse.error });
                return;
            }
            const [choisie, precedente] = reponse.data ?? [];
            // Un brouillon créé entre-temps décale tous les rangs : on recharge plutôt que de comparer deux autres versions.
            if (!choisie || choisie.id !== version.id) {
                await charger();
                return;
            }
            if (!precedente || precedente.version_number >= choisie.version_number) {
                notifier.information({ fr: `La version ${choisie.version_number} n'a pas de version précédente.`, en: `Version ${choisie.version_number} has no previous version.` });
                return;
            }
            setPaire({ previousVersion: precedente, selectedVersion: choisie });
        } catch {
            notifier.echec({ fr: "Comparaison impossible. Réessayez.", en: "Could not compare. Try again." });
        } finally {
            setEnComparaison(null);
        }
    };

    if (erreur) return <EtatVide cas="erreur" reessayer={() => void charger()} />;
    if (lignes === null) return <EtatVide cas="chargement" lignes={5} />;
    if (lignes.length === 0) return <EtatVide cas="premier" icone={FileText} titre={t(T.aucune)} />;

    const total = page * PAR_PAGE + lignes.length + (aSuite ? 1 : 0);
    // La version en cours : le brouillon s'il existe, sinon la publiée la plus récente de la liste.
    const publieeCourante = lignes.find((l) => l.status === "published")?.id ?? null;
    const enCours = (v: WorkflowVersionResponse) => (brouillonId !== null ? v.id === brouillonId : v.id === publieeCourante && page === 0);
    const nom = (statut: string) => (statut === "draft" ? T.brouillon : statut === "published" ? T.publiee : T.archivee);

    return (
        <div className="mx-auto w-full max-w-4xl px-6 py-6" data-page-versions>
            <Tableau colonnes={[{ titre: t(T.version) }, { titre: t(T.etat) }, { titre: t(T.date) }, { titre: "", droite: true }]}>
                {lignes.map((v, i) => {
                    const courante = enCours(v);
                    return (
                        <Ligne key={v.id} href={adresseDeLaVersion(agentId, v, courante)}>
                            <Cellule principale sous={courante ? t(T.enCours) : undefined}>
                                v{v.version_number}
                            </Cellule>
                            <Cellule>
                                <PointEtat etat={POINT[v.status] ?? "fini"}>{t(nom(v.status))}</PointEtat>
                            </Cellule>
                            <Cellule>{formatDateTime(v.published_at || v.created_at, fuseau)}</Cellule>
                            <Cellule droite>
                                <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                                    <Button asChild variant="ghost" size="sm" className="cursor-pointer hover:font-medium">
                                        <Link href={adresseDeLaVersion(agentId, v, courante)}>{t(T.ouvrir)}</Link>
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="cursor-pointer"
                                        aria-label={`${t(T.comparer)} (v${v.version_number})`}
                                        title={t(T.comparer)}
                                        disabled={enComparaison !== null}
                                        onClick={() => void comparer(v, i)}
                                    >
                                        <FileDiff className="size-4" />
                                    </Button>
                                </span>
                            </Cellule>
                        </Ligne>
                    );
                })}
            </Tableau>
            <BarrePagination total={total} page={page} changerPage={setPage} />
            {paire && <WorkflowVersionDiffDialog open onOpenChange={(ouvert) => !ouvert && setPaire(null)} {...paire} />}
        </div>
    );
}
