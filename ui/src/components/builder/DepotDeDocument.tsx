"use client";

/**
 * [.mark] builder partie 2, E1 (U7): drop a document (PDF, Word, Markdown or text) into a family. The server converts it on the
 * spot (nothing leaves the installation) and the text enters as a Candidate with its origin (file name, licence, date). A
 * second drop of the same file shows what changed. A family with a structured content (characters, scenarios...) takes none.
 */
import { FileUp } from "lucide-react";
import { useRef, useState } from "react";

import { deposerUnDocumentApiV1BuilderBibliothequeDepotPost } from "@/client";
import type { VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
// The families whose content has a shape read by the code: a document cannot be dropped in them (the server says so too).
export const STRUCTUREES = ["personnages-appelant", "scenarios-test", "criteres-types", "phrases-du-code", "lexiques", "modeles-reglages"];

interface Props {
    familles: VueFamille[];
    familleChoisie: string;
    onDepose: (famille: string, slug: string, comparatif: { identique: boolean } | null) => void;
    /** K5 : dans « Nouvel élément » (onglet « Déposer un fichier ») : la famille est celle de la fenêtre, pas de titre de section. */
    integre?: boolean;
}

export function DepotDeDocument({ familles, familleChoisie, onDepose, integre = false }: Props) {
    const { t } = useLangue();
    const permises = familles.filter((f) => !STRUCTUREES.includes(f.slug));
    const [choix, setFamille] = useState("");
    const famille = choix || (permises.some((f) => f.slug === familleChoisie) ? familleChoisie : permises[0]?.slug) || "";
    const [licence, setLicence] = useState("");
    const [titre, setTitre] = useState("");
    const [fichier, setFichier] = useState<File | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const entree = useRef<HTMLInputElement>(null);

    const deposer = async () => {
        if (!fichier) return;
        const reponse = await deposerUnDocumentApiV1BuilderBibliothequeDepotPost({
            body: { famille, fichier, licence: licence.trim() || "inconnue", titre: titre.trim() || undefined },
        });
        if (reponse.error || !reponse.data) {
            setMessage(null);
            setErreur(echecAffiche(reponse.error, ECHECS.bibliothequeDeposerDocument));
            return;
        }
        setErreur(null);
        const comparatif = (reponse.data.comparatif as { identique: boolean } | null) ?? null;
        setMessage(
            reponse.data.cree
                ? t({ en: "Dropped as a Candidate.", fr: "Déposé comme Candidat." })
                : comparatif?.identique
                  ? t({ en: "Nothing changed since the last drop.", fr: "Rien n'a changé depuis le dernier dépôt." })
                  : t({ en: "A new Candidate version was added.", fr: "Une nouvelle version Candidat a été ajoutée." }),
        );
        setFichier(null);
        if (entree.current) entree.current.value = "";
        onDepose(reponse.data.element.famille, reponse.data.element.slug, comparatif);
    };

    return (
        <section className="space-y-3 text-sm" data-testid="depot-document">
            {!integre && <h2 className="text-lg font-semibold">{t({ en: "Drop a document", fr: "Déposer un document" })}</h2>}
            <div className="grid gap-3 md:grid-cols-3">
                {!integre && (
                    <label className="block space-y-1">
                        <span>{t({ en: "Family", fr: "Famille" })}</span>
                        <Liste valeur={famille} changer={setFamille} options={permises.map((f) => ({ valeur: f.slug, libelle: f.libelle }))} className="w-full" />
                    </label>
                )}
                <label className="block space-y-1">
                    <span>{t({ en: "Title (optional)", fr: "Titre (facultatif)" })}</span>
                    <Input value={titre} onChange={(e) => setTitre(e.target.value)} />
                </label>
                <label className="block space-y-1">
                    <span>{t({ en: "Licence (or « unknown »)", fr: "Licence (ou « inconnue »)" })}</span>
                    <Input value={licence} onChange={(e) => setLicence(e.target.value)} />
                </label>
            </div>
            <div className="flex items-center gap-3">
                <input
                    ref={entree}
                    type="file"
                    accept=".pdf,.docx,.md,.markdown,.txt"
                    className="hidden"
                    data-depot-fichier
                    onChange={(e) => setFichier(e.target.files?.[0] ?? null)}
                />
                <Button type="button" variant="outline" size="sm" onClick={() => entree.current?.click()}>
                    <FileUp className="mr-1.5 h-4 w-4" />
                    {t({ en: "Choose a file", fr: "Choisir un fichier" })}
                </Button>
                <span className="text-muted-foreground">{fichier ? fichier.name : t({ en: "PDF, Word, Markdown or text", fr: "PDF, Word, Markdown ou texte" })}</span>
                <Button size="sm" disabled={!fichier || !famille} onClick={() => void deposer()}>
                    {t({ en: "Drop as a Candidate", fr: "Déposer comme Candidat" })}
                </Button>
            </div>
            {erreur && (
                <p role="alert" className="text-destructive">
                    {erreur}
                </p>
            )}
            {message && <p data-testid="depot-resultat">{message}</p>}
        </section>
    );
}
