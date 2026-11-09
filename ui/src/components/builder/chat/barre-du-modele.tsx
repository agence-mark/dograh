"use client";

/**
 * Clôture D1 (É50, maquette `chat-builder.tsx`) : la barre de saisie du chat dit le modèle, la dépense du chat sur son plafond (« 0,42 $
 * sur 2 $ », jauge fine) et offre la pièce jointe. Tout vient du serveur : le modèle et le plafond du cerveau du builder, la dépense
 * du fil, le dépôt de l'agent du chat (le même que « Déposer un dossier » du panneau du builder).
 */
import { Paperclip } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { deposerUnFichierApiV1BuilderDepotWorkflowIdPost, lireLeCerveauApiV1BuilderCerveauGet } from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";

/** « 0,42 $ sur 2 $ » (français) ou « $0.42 of $2 » (anglais) ; sans plafond : la dépense seule. */
export const texteDepense = (cout: number, plafond: number, langue: "fr" | "en"): string => {
    const nombre = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2)).replace(".", langue === "fr" ? "," : ".");
    const chiffre = (n: number) => (langue === "fr" ? `${n.toFixed(2).replace(".", ",")} $` : `$${n.toFixed(2)}`);
    if (!plafond) return chiffre(cout);
    return langue === "fr" ? `${chiffre(cout)} sur ${nombre(plafond)} $` : `${chiffre(cout)} of $${nombre(plafond)}`;
};

export function BarreDuModele({ cout, workflowId, rafraichir, desactive }: { cout: number; workflowId: number | null; rafraichir: () => void; desactive: boolean }) {
    const { t, langue } = useLangue();
    const [cerveau, setCerveau] = useState<{ modele: string; plafond: number } | null>(null);
    const entree = useRef<HTMLInputElement>(null);
    useEffect(() => {
        let annule = false;
        void (async () => {
            const r = await lireLeCerveauApiV1BuilderCerveauGet();
            if (annule || !r.data) return;
            setCerveau({ modele: r.data.modele ?? "", plafond: r.data.plafond_depense ?? 0 });
        })();
        return () => {
            annule = true;
        };
    }, []);

    const joindre = async (fichiers: File[]) => {
        if (!workflowId) return;
        const echecs = await Promise.all(
            fichiers.map(async (fichier) => {
                const reponse = await deposerUnFichierApiV1BuilderDepotWorkflowIdPost({ path: { workflow_id: workflowId }, body: { fichier } });
                if (reponse.error) notifier.echec(ECHECS.builderDeposerFichier, { erreur: reponse.error });
                return Boolean(reponse.error);
            }),
        );
        if (echecs.some((e) => !e)) notifier.succes({ en: "File added.", fr: "Fichier ajouté." });
        rafraichir();
    };

    const part = cerveau?.plafond ? Math.min(1, cout / cerveau.plafond) : 0;
    const titrePiece = workflowId
        ? t({ en: "Attach a file (PDF, Word, notes)", fr: "Joindre un fichier (PDF, Word, notes)" })
        : t({ en: "Open an agent to attach files", fr: "Ouvrez un agent pour joindre des fichiers" });
    return (
        <>
            <input
                ref={entree}
                type="file"
                multiple
                hidden
                accept=".pdf,.docx,.md,.markdown,.txt"
                data-joindre-chat
                onChange={(e) => {
                    const choisis = Array.from(e.target.files ?? []);
                    e.target.value = "";
                    void joindre(choisis);
                }}
            />
            <button
                type="button"
                className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                aria-label={titrePiece}
                title={titrePiece}
                disabled={!workflowId || desactive}
                onClick={() => entree.current?.click()}
            >
                <Paperclip className="size-4" aria-hidden />
            </button>
            <span className="mr-auto flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground" data-barre-modele>
                {cerveau?.modele && <span className="truncate">{cerveau.modele} ·</span>}
                {cerveau && cerveau.plafond > 0 && (
                    <span className="h-1 w-12 shrink-0 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(part * 100)}>
                        <span className="block h-full rounded-full bg-(--acc)" style={{ width: `${part * 100}%` }} />
                    </span>
                )}
                {cerveau && <span className="shrink-0 tabular-nums">{texteDepense(cout, cerveau.plafond, langue as "fr" | "en")}</span>}
            </span>
        </>
    );
}
