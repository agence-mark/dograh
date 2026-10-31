"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): the « Deposit » card. Files (PDF, Word, Markdown, text) and the address of the
 * client's site; for each deposit, what was read and what could not be (unreadable = said, with the reason).
 */
import { FileText, Globe, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import {
    deposerUnFichierApiV1BuilderDepotWorkflowIdPost,
    deposerUnSiteApiV1BuilderDepotWorkflowIdSitePost,
    retirerUnDepotApiV1BuilderDepotWorkflowIdDepotIdDelete,
} from "@/client";
import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { useBuilderEcran } from "../store";
import { Carte } from "./Carte";

const T = {
    titre: { en: "Deposits", fr: "Dépôt" },
    aide: {
        en: "PDF, Word, Markdown or text files, and the address of the site. Public pages only.",
        fr: "Fichiers PDF, Word, Markdown ou texte, et l'adresse du site. Pages publiques seulement.",
    },
    ajouter: { en: "Add a file", fr: "Ajouter un fichier" },
    site: { en: "Site address", fr: "Adresse du site" },
    lireLeSite: { en: "Read the site", fr: "Lire le site" },
    retirer: { en: "Remove", fr: "Retirer" },
    aucun: { en: "Nothing deposited yet.", fr: "Rien n'est déposé pour l'instant." },
    lu: { en: "read", fr: "lu" },
    illisible: { en: "unreadable", fr: "illisible" },
    pages: { en: "page(s) or section(s)", fr: "page(s) ou section(s)" },
    tronque: { en: "Only the start was kept (size limit).", fr: "Seul le début est gardé (limite de taille)." },
    refusees: { en: "Pages not read:", fr: "Pages non lues :" },
    echec: { en: "The deposit failed.", fr: "Le dépôt a échoué." },
} satisfies Record<string, Texte>;

export function CarteDepot({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const depots = useBuilderEcran((s) => s.contexte?.depots) ?? [];
    const rafraichir = useBuilderEcran((s) => s.rafraichirLeContexte);
    const entree = useRef<HTMLInputElement>(null);
    const [adresse, setAdresse] = useState("");
    const [erreur, setErreur] = useState<string | null>(null);
    const [occupe, setOccupe] = useState(false);

    const deposer = async (fichier: File) => {
        setOccupe(true);
        setErreur(null);
        const reponse = await deposerUnFichierApiV1BuilderDepotWorkflowIdPost({
            path: { workflow_id: workflowId },
            body: { fichier },
        });
        if (reponse.error) setErreur(detailFromError(reponse.error, t(T.echec)));
        await rafraichir(workflowId);
        setOccupe(false);
    };

    const lireLeSite = async () => {
        if (!adresse.trim()) return;
        setOccupe(true);
        setErreur(null);
        const reponse = await deposerUnSiteApiV1BuilderDepotWorkflowIdSitePost({
            path: { workflow_id: workflowId },
            body: { adresse: adresse.trim() },
        });
        if (reponse.error) setErreur(detailFromError(reponse.error, t(T.echec)));
        else setAdresse("");
        await rafraichir(workflowId);
        setOccupe(false);
    };

    const retirer = async (id: string) => {
        await retirerUnDepotApiV1BuilderDepotWorkflowIdDepotIdDelete({ path: { workflow_id: workflowId, depot_id: id } });
        await rafraichir(workflowId);
    };

    return (
        <Carte type="depot" titre={t(T.titre)} aide={t(T.aide)}>
            {depots.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t(T.aucun)}</p>
            ) : (
                <ul className="space-y-1.5">
                    {depots.map((d) => (
                        <li key={d.id} className="rounded-md border p-2 text-xs" data-depot={d.nom}>
                            <div className="flex items-center gap-2">
                                {d.genre === "site" ? <Globe className="h-3.5 w-3.5 shrink-0" aria-hidden /> : <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />}
                                <span className="min-w-0 flex-1 truncate font-medium" title={d.nom}>{d.nom}</span>
                                <span
                                    className={
                                        d.statut === "lu"
                                            ? "rounded bg-(--signal-ok)/15 px-1.5 py-0.5 text-(--signal-ok)"
                                            : "rounded bg-(--signal-danger)/15 px-1.5 py-0.5 text-(--signal-danger)"
                                    }
                                >
                                    {d.statut === "lu" ? t(T.lu) : t(T.illisible)}
                                </span>
                                <button type="button" aria-label={`${t(T.retirer)} ${d.nom}`} onClick={() => void retirer(d.id)} className="text-muted-foreground hover:text-foreground">
                                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                                </button>
                            </div>
                            {d.statut === "lu" ? (
                                <p className="mt-1 text-muted-foreground">
                                    {d.pages} {t(T.pages)}
                                    {d.tronque ? ` · ${t(T.tronque)}` : ""}
                                </p>
                            ) : (
                                <p className="mt-1 text-(--signal-danger)">{d.raison}</p>
                            )}
                            {d.refusees && d.refusees.length > 0 && (
                                <p className="mt-1 text-muted-foreground">
                                    {t(T.refusees)} {d.refusees.map((r) => r.adresse).join(", ")}
                                </p>
                            )}
                        </li>
                    ))}
                </ul>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                    ref={entree}
                    type="file"
                    accept=".pdf,.docx,.md,.markdown,.txt"
                    className="hidden"
                    data-testid="depot-fichier"
                    onChange={(e) => {
                        const fichier = e.target.files?.[0];
                        e.target.value = "";
                        if (fichier) void deposer(fichier);
                    }}
                />
                <Button type="button" size="sm" variant="outline" disabled={occupe} onClick={() => entree.current?.click()}>
                    {t(T.ajouter)}
                </Button>
            </div>
            <div className="mt-2 flex items-center gap-2">
                <Input
                    value={adresse}
                    onChange={(e) => setAdresse(e.target.value)}
                    placeholder={t(T.site)}
                    aria-label={t(T.site)}
                    className="h-8 text-xs"
                    onKeyDown={(e) => {
                        if (e.key === "Enter") void lireLeSite();
                    }}
                />
                <Button type="button" size="sm" variant="outline" disabled={occupe || !adresse.trim()} onClick={() => void lireLeSite()}>
                    {t(T.lireLeSite)}
                </Button>
            </div>
            {erreur && <p role="alert" className="mt-2 text-xs text-destructive">{erreur}</p>}
        </Carte>
    );
}
