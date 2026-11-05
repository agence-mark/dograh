"use client";

/**
 * [.mark] Partie 3, N1 (sous-lot 4) : le journal de ce que le builder écrit, et « Annuler » sur l'action faite.
 *
 * - `BoutonAnnuler` : à la fin d'une ligne d'action du fil. « Annuler » quand le serveur dit que l'action se défait, « Annulée » une fois
 *   fait, sinon la raison pour laquelle elle ne se défait pas (publiée, supprimée, dépensée, appel réel...). Le serveur décide : l'écran
 *   ne devine rien, il lit `journal` dans le résultat de l'action.
 * - `JournalDuBuilder` : la liste, par organisation, paginée (qui, quoi, quand, quel mode, quelle autorisation, état). Jamais une valeur
 *   de clé : le serveur ne les garde pas.
 */
import { ChevronLeft, ChevronRight, ScrollText } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { annulerUneActionDuBuilderApiV1BuilderJournalLigneIdAnnulerPost, lireLeJournalDuBuilderApiV1BuilderJournalGet, type LigneDuJournal } from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

import { quand } from "./ListeDesFils";

export type JournalDeLaLigne = { id: number; annulable: boolean; raison?: string | null; annulee?: boolean };

const T = {
    annuler: { en: "Undo", fr: "Annuler" },
    annulerLibelle: { en: "Undo this action of the builder", fr: "Annuler cette action du builder" },
    annulee: { en: "Undone", fr: "Annulée" },
    fait: { en: "Action undone.", fr: "Action annulée." },
    echec: { en: "The action was not undone.", fr: "L'action n'a pas été annulée." },
    titre: { en: "Journal of the builder", fr: "Journal du builder" },
    vide: { en: "The builder has written nothing yet", fr: "Le builder n'a encore rien écrit" },
    precedent: { en: "Newer", fr: "Plus récentes" },
    suivant: { en: "Older", fr: "Plus anciennes" },
    page: { en: "Page", fr: "Page" },
    sur: { en: "of", fr: "sur" },
} satisfies Record<string, Texte>;

/** Pourquoi une action ne se défait pas d'un clic (codes du serveur, `journal.py`). */
export const RAISONS: Record<string, Texte> = {
    publication: { en: "Published: go back to an earlier version and publish again.", fr: "Publiée : revenez à une version antérieure puis publiez de nouveau." },
    irreversible: { en: "Cannot be undone: deleted or archived, a person restores it.", fr: "Ne se défait pas : supprimée ou archivée, une personne la restaure." },
    depense: { en: "Cannot be undone: the money is spent.", fr: "Ne se défait pas : la dépense est faite." },
    appels_reels: { en: "Cannot be undone: real people were called.", fr: "Ne se défait pas : de vraies personnes ont été appelées." },
    revue: { en: "Not applied yet: refuse it in the review.", fr: "Pas encore appliquée : refusez-la dans la revue." },
    creation: { en: "Created: delete it from its own screen.", fr: "Créée : supprimez-la depuis son écran." },
    echec: { en: "Failed: nothing to undo.", fr: "Échec : rien à annuler." },
    sans_version: { en: "No earlier version was kept.", fr: "Aucune version antérieure n'a été gardée." },
    illisible: { en: "The earlier state could not be kept.", fr: "L'état d'avant n'a pas pu être gardé." },
    annulation: { en: "This is an undo.", fr: "C'est une annulation." },
    autre: { en: "Cannot be undone from here.", fr: "Ne se défait pas d'ici." },
    ordre: { en: "A more recent change is in place: undo it first.", fr: "Un changement plus récent est en place : annulez-le d'abord." },
    deja_annulee: { en: "Already undone.", fr: "Déjà annulée." },
    droits: { en: "Your role does not allow this.", fr: "Votre rôle ne le permet pas." },
    protegee: { en: "The main version is protected: the change goes on a branch.", fr: "La version principale est protégée : le changement passe par une branche." },
};

const raisonDe = (code: string | null | undefined): Texte => RAISONS[code ?? "autre"] ?? RAISONS.autre;

/** Défait une ligne du journal ; dit le résultat par une notification (jamais le texte brut du serveur). */
export async function annulerLaLigne(id: number): Promise<{ ok: boolean; code?: string }> {
    const r = await annulerUneActionDuBuilderApiV1BuilderJournalLigneIdAnnulerPost({ path: { ligne_id: id } });
    if (!r.error) {
        notifier.succes(T.fait);
        return { ok: true };
    }
    const detail = (r.error as { detail?: { code?: string } } | undefined)?.detail;
    const code = typeof detail === "object" && detail !== null ? detail.code : undefined;
    notifier.echec(code && RAISONS[code] ? RAISONS[code] : T.echec);
    return { ok: false, code };
}

export function BoutonAnnuler({ journal }: { journal: JournalDeLaLigne }) {
    const { t } = useLangue();
    const [fait, setFait] = useState(false);
    const [occupe, setOccupe] = useState(false);
    if (journal.annulee || fait) {
        return (
            <span className="ml-5 text-xs text-muted-foreground" data-journal-annulee>
                {t(T.annulee)}
            </span>
        );
    }
    if (!journal.annulable) {
        return (
            <span className="ml-5 text-xs text-muted-foreground" data-journal-definitif={journal.raison ?? "autre"}>
                {t(raisonDe(journal.raison))}
            </span>
        );
    }
    return (
        <Button
            type="button"
            size="sm"
            variant="ghost"
            className="ml-3 h-6 cursor-pointer px-2 text-xs hover:font-semibold"
            disabled={occupe}
            aria-label={t(T.annulerLibelle)}
            data-annuler-action={journal.id}
            onClick={async () => {
                setOccupe(true);
                const r = await annulerLaLigne(journal.id);
                setOccupe(false);
                if (r.ok || r.code === "deja_annulee") setFait(true);
            }}
        >
            {t(T.annuler)}
        </Button>
    );
}

const FAMILLES: Record<string, Texte> = {
    lecture: { en: "Read", fr: "Lecture" },
    brouillon: { en: "Draft", fr: "Brouillon" },
    reglages: { en: "Settings", fr: "Réglages" },
    publication: { en: "Publication", fr: "Publication" },
    entreprise: { en: "Organisation", fr: "Entreprise" },
    autre_agent: { en: "Other agent", fr: "Autre agent" },
    depense: { en: "Spending", fr: "Dépense" },
    appels_reels: { en: "Real calls", fr: "Appels réels" },
    irreversible: { en: "Irreversible", fr: "Irréversible" },
};
const MODES: Record<string, Texte> = {
    demander: { en: "Ask", fr: "Demander" },
    agent: { en: "Allow on this agent", fr: "Tout permettre sur cet agent" },
    tout: { en: "Allow everything", fr: "Tout permettre" },
    plan: { en: "Plan", fr: "Plan" },
};
const AUTORISATIONS: Record<string, Texte> = {
    mode: { en: "by the mode", fr: "par le mode" },
    une_fois: { en: "once", fr: "une fois" },
    pour_ce_chat: { en: "for this chat", fr: "pour ce chat" },
    depense: { en: "spending agreed", fr: "dépense accordée" },
    personne: { en: "by the person", fr: "par la personne" },
    claude_code: { en: "Claude Code", fr: "Claude Code" },
};
const ETATS: Record<string, Texte> = {
    fait: { en: "done", fr: "fait" },
    echec: { en: "failed", fr: "échec" },
    en_cours: { en: "running", fr: "en cours" },
};

const PAR_PAGE = 25;

export function JournalDuBuilder() {
    const { t, langue } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [page, setPage] = useState(0);
    const [lignes, setLignes] = useState<LigneDuJournal[] | null>(null);
    const [total, setTotal] = useState(0);
    const [erreur, setErreur] = useState(false);

    const lire = useCallback(async () => {
        const r = await lireLeJournalDuBuilderApiV1BuilderJournalGet({ query: { limit: PAR_PAGE, offset: page * PAR_PAGE } });
        if (r.error || !r.data) return setErreur(true);
        setErreur(false);
        setLignes(r.data.lignes);
        setTotal(r.data.total);
    }, [page]);

    useEffect(() => {
        if (authLoading || !user) return;
        void lire();
    }, [authLoading, user, lire]);

    if (erreur) return <EtatVide cas="erreur" reessayer={() => void lire()} />;
    if (lignes === null) return <EtatVide cas="chargement" lignes={4} />;
    if (lignes.length === 0 && page === 0) return <EtatVide cas="premier" icone={ScrollText} titre={t(T.vide)} />;
    const pages = Math.max(1, Math.ceil(total / PAR_PAGE));

    return (
        <section aria-label={t(T.titre)} data-journal-du-builder>
            <ul className="divide-y border-y">
                {lignes.map((l) => (
                    <li key={l.id} className="flex items-center gap-3 px-1 py-2.5 text-sm" data-ligne-du-journal={l.id}>
                        <span className="min-w-0 flex-1">
                            <span className="block truncate font-medium">{l.action}</span>
                            <span className="block truncate text-xs text-muted-foreground">
                                {t(FAMILLES[l.famille] ?? { en: l.famille, fr: l.famille })}
                                {l.mode ? ` · ${t(MODES[l.mode] ?? { en: l.mode, fr: l.mode })}` : ""}
                                {` · ${t(AUTORISATIONS[l.autorisation] ?? { en: l.autorisation, fr: l.autorisation })}`}
                                {l.workflow_id ? ` · #${l.workflow_id}` : ""}
                            </span>
                        </span>
                        <span className="text-xs text-muted-foreground">{t(ETATS[l.statut] ?? { en: l.statut, fr: l.statut })}</span>
                        <span className="w-24 text-right text-xs text-muted-foreground">{quand(l.quand, langue)}</span>
                        <span className="w-44 text-right">
                            {l.annule_le ? (
                                <span className="text-xs text-muted-foreground">{t(T.annulee)}</span>
                            ) : l.statut === "fait" && l.action !== "annuler" ? (
                                <BoutonAnnuler journal={{ id: l.id, annulable: l.annulable, raison: l.non_annulable }} />
                            ) : null}
                        </span>
                    </li>
                ))}
            </ul>
            {pages > 1 && (
                <nav className="mt-3 flex items-center justify-end gap-2 text-xs text-muted-foreground" aria-label={t(T.titre)}>
                    <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))} aria-label={t(T.precedent)}>
                        <ChevronLeft className="size-4" aria-hidden />
                    </Button>
                    <span>
                        {t(T.page)} {page + 1} {t(T.sur)} {pages}
                    </span>
                    <Button size="sm" variant="ghost" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)} aria-label={t(T.suivant)}>
                        <ChevronRight className="size-4" aria-hidden />
                    </Button>
                </nav>
            )}
        </section>
    );
}
