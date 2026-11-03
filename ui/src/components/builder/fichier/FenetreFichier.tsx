"use client";

/**
 * [.mark] builder partie 2, U5 (E98) : la visionneuse de fichiers. Un clic sur un fichier l'ouvre dans une fenêtre pour le lire vite,
 * sans le télécharger, avec une recherche qui surligne et compte les résultats. Aucune écriture.
 *
 * - un fichier tout juste joint (``fichier``) se lit dans le navigateur : texte, Markdown, CSV (tableau), image, PDF (lecteur du navigateur) ;
 * - un fichier déjà envoyé (``documentUuid``), et tout Word ou Excel, se lit par la route du serveur qui rend le texte extrait
 *   (le même que celui des connaissances), page par page pour un PDF, en lignes pour un tableur.
 */
import { FileImage, FileSpreadsheet, FileText, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { lireLeTexteDUnFichierApiV1BuilderFichiersDocumentUuidTexteGet } from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { FenetreOnglets } from "@/components/mark/studio/fenetre-onglets";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

const T = {
    chercher: { en: "Search in the file", fr: "Rechercher dans le fichier" },
    resultat: { en: "result", fr: "résultat" },
    resultats: { en: "results", fr: "résultats" },
    page: { en: "Page", fr: "Page" },
    sur: { en: "of", fr: "sur" },
    indisponible: { en: "No preview in the browser for this format.", fr: "Aperçu indisponible dans le navigateur pour ce format." },
    charge: { en: "Reading...", fr: "Lecture..." },
} satisfies Record<string, Texte>;

export type ContenuFichier =
    | { sorte: "texte"; texte: string }
    | { sorte: "pages"; pages: string[] }
    | { sorte: "tableau"; colonnes: string[]; lignes: string[][] };

const ext = (nom: string) => nom.split(".").pop()?.toLowerCase() ?? "";
const IMAGES = ["png", "jpg", "jpeg", "webp", "gif"];
const echapper = (q: string) => q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export const lireCsv = (t: string): { colonnes: string[]; lignes: string[][] } => {
    const l = t.trim().split(/\r?\n/).map((x) => x.split(/[;,\t]/));
    return { colonnes: l[0] ?? [], lignes: l.slice(1) };
};

/** Le nombre d'occurrences de la recherche dans le contenu lu (sans casse). */
export function compterDans(contenu: ContenuFichier | null, q: string): number {
    if (!contenu || !q.trim()) return 0;
    const plat = contenu.sorte === "pages" ? contenu.pages.join("\n") : contenu.sorte === "texte" ? contenu.texte : contenu.lignes.flat().join("\n");
    return (plat.match(new RegExp(echapper(q), "gi")) ?? []).length;
}

export function Surligne({ texte, q }: { texte: string; q: string }) {
    if (!q.trim()) return <>{texte}</>;
    const morceaux = texte.split(new RegExp(`(${echapper(q)})`, "gi"));
    return (
        <>
            {morceaux.map((m, i) =>
                m.toLowerCase() === q.toLowerCase() ? (
                    <mark key={i} className="rounded bg-yellow-200 px-0.5 text-foreground">
                        {m}
                    </mark>
                ) : (
                    m
                ),
            )}
        </>
    );
}

export function CorpsFichier({ contenu, q }: { contenu: ContenuFichier; q: string }) {
    const { t } = useLangue();
    if (contenu.sorte === "pages") {
        return (
            <div className="space-y-6">
                {contenu.pages.map((p, i) => (
                    <section key={i} className="space-y-2">
                        <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                            {t(T.page)} {i + 1} {t(T.sur)} {contenu.pages.length}
                        </p>
                        <p className="border-l-2 pl-4 text-sm leading-relaxed whitespace-pre-wrap">
                            <Surligne texte={p} q={q} />
                        </p>
                    </section>
                ))}
            </div>
        );
    }
    if (contenu.sorte === "texte") {
        return (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
                <Surligne texte={contenu.texte} q={q} />
            </p>
        );
    }
    return (
        <table className="w-full text-left text-sm">
            <thead>
                <tr>
                    {contenu.colonnes.map((c, i) => (
                        <th key={i} className="py-2 pr-4 font-semibold">
                            {c}
                        </th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {contenu.lignes.map((l, i) => (
                    <tr key={i}>
                        {l.map((c, j) => (
                            <td key={j} className="py-2 pr-4">
                                <Surligne texte={c} q={q} />
                            </td>
                        ))}
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

type Page = { genre: string; page: number; pages: number; texte: string };

/** Lit toutes les pages d'un fichier du serveur (bornées : un fichier énorme ne bloque pas la fenêtre). */
async function lireSurLeServeur(uuid: string): Promise<ContenuFichier> {
    const premiere = await lireLeTexteDUnFichierApiV1BuilderFichiersDocumentUuidTexteGet({ path: { document_uuid: uuid }, query: { page: 1 } });
    if (premiere.error || !premiere.data) throw new Error(detailFromError(premiere.error, "The file could not be read"));
    const base = premiere.data as unknown as Page;
    const morceaux = [base.texte];
    for (let p = 2; p <= Math.min(base.pages, 60); p++) {
        const r = await lireLeTexteDUnFichierApiV1BuilderFichiersDocumentUuidTexteGet({ path: { document_uuid: uuid }, query: { page: p } });
        if (r.error || !r.data) break;
        morceaux.push((r.data as unknown as Page).texte);
    }
    if (base.genre === "lignes") return { sorte: "tableau", ...lireCsv(morceaux.join("\n")) };
    if (base.genre === "pages") return { sorte: "pages", pages: morceaux };
    return { sorte: "texte", texte: morceaux.join("") };
}

export function FenetreFichier({
    nom,
    fichier,
    documentUuid,
    fermer,
}: {
    nom: string;
    fichier?: File;
    documentUuid?: string;
    fermer: () => void;
}) {
    const { t } = useLangue();
    const [q, setQ] = useState("");
    const [lu, setLu] = useState<ContenuFichier | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const url = useMemo(() => (fichier && typeof URL.createObjectURL === "function" ? URL.createObjectURL(fichier) : null), [fichier]);
    useEffect(() => () => {
        if (url) URL.revokeObjectURL(url);
    }, [url]);
    const e = ext(nom);
    const image = IMAGES.includes(e) || Boolean(fichier?.type.startsWith("image/"));
    const pdfLocal = Boolean(fichier) && (e === "pdf" || fichier?.type === "application/pdf");
    const texteLocal = Boolean(fichier) && !image && !pdfLocal && (["txt", "md", "csv", "json", "html"].includes(e) || Boolean(fichier?.type.startsWith("text/")));

    useEffect(() => {
        if (texteLocal && fichier) {
            void fichier.text().then((x) => setLu(e === "csv" ? { sorte: "tableau", ...lireCsv(x) } : { sorte: "texte", texte: x }));
        } else if (!fichier && documentUuid) {
            lireSurLeServeur(documentUuid).then(setLu, (x: Error) => setErreur(x.message));
        }
    }, [fichier, documentUuid, texteLocal, e]);

    const trouves = compterDans(lu, q);
    const Icone = image ? FileImage : e === "csv" || e === "xlsx" ? FileSpreadsheet : FileText;
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={<span className="truncate">{nom}</span>}
            sous={fichier ? `${Math.max(1, Math.round(fichier.size / 1024))} Ko` : undefined}
            visuel={
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted/40">
                    <Icone className="size-5 text-muted-foreground" />
                </span>
            }
            droite={
                lu ? (
                    <div className="flex items-center gap-2 pt-0.5">
                        <div className="relative w-56">
                            <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                            <Input value={q} onChange={(ev) => setQ(ev.target.value)} placeholder={t(T.chercher)} className="h-8 pl-8 text-sm" />
                        </div>
                        {q.trim() && (
                            <span className="w-24 text-xs text-muted-foreground tabular-nums" data-resultats={trouves}>
                                {trouves} {trouves > 1 ? t(T.resultats) : t(T.resultat)}
                            </span>
                        )}
                    </div>
                ) : undefined
            }
            valider={null}
        >
            {image && url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={url} alt={nom} className="mx-auto max-h-full rounded-lg object-contain" />
            ) : pdfLocal && url ? (
                <iframe src={url} title={nom} className="h-full min-h-[60vh] w-full rounded-lg" />
            ) : lu ? (
                <CorpsFichier contenu={lu} q={q} />
            ) : erreur ? (
                <p className="text-sm text-destructive">{erreur}</p>
            ) : fichier && !texteLocal ? (
                <p className="text-sm text-muted-foreground">{t(T.indisponible)}</p>
            ) : (
                <p className="text-sm text-muted-foreground">{t(T.charge)}</p>
            )}
        </FenetreOnglets>
    );
}
