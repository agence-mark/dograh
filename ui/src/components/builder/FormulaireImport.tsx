"use client";

/**
 * [.mark] builder-agent-vocal (lot 2): create an element, or import one from the market with its origin
 * (source, licence, date). A re-import shows what changed since the last one. Always a Candidate.
 */
import { useState } from "react";

import { creerUnElementApiV1BuilderBibliothequeFamillePost, importerApiV1BuilderBibliothequeImportPost } from "@/client";
import type { VueFamille } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

const CHAMP = "w-full rounded-md border bg-background px-2 py-1.5 text-sm";
const aujourdhui = () => new Date().toISOString().slice(0, 10);

interface Props {
    familles: VueFamille[];
    familleChoisie: string;
    /** ``garderLEcran``: a comparison is shown, the page stays on this form so it can be read. */
    onCree: (famille: string, slug: string, garderLEcran: boolean) => void;
}

export function FormulaireImport({ familles, familleChoisie, onCree }: Props) {
    const { t } = useLangue();
    const [choix, setFamille] = useState("");
    // The families arrive after the form may be shown: the default is read when needed, never frozen at first render.
    const famille = choix || familleChoisie || familles[0]?.slug || "";
    const [slug, setSlug] = useState("");
    const [titre, setTitre] = useState("");
    const [contenu, setContenu] = useState('{\n  "texte": ""\n}');
    const [importer, setImporter] = useState(false);
    const [source, setSource] = useState("");
    const [licence, setLicence] = useState("");
    const [date, setDate] = useState(aujourdhui());
    const [erreur, setErreur] = useState<string | null>(null);
    const [comparatif, setComparatif] = useState<{ ajoutees: number; retirees: number; identique: boolean; diff: string } | null>(null);

    const envoyer = async () => {
        let objet: Record<string, unknown>;
        try {
            const lu = JSON.parse(contenu);
            if (typeof lu !== "object" || lu === null || Array.isArray(lu)) throw new Error("not an object");
            objet = lu;
        } catch {
            setErreur(t({ en: "The content is not a valid JSON object.", fr: "Le contenu n'est pas un objet JSON valide." }));
            return;
        }
        setComparatif(null);
        if (importer) {
            const reponse = await importerApiV1BuilderBibliothequeImportPost({
                body: { famille, slug, titre, contenu: objet, origine: { source: source.trim(), licence: licence.trim(), date } },
            });
            if (reponse.error || !reponse.data) {
                setErreur(detailFromError(reponse.error, "The import failed"));
                return;
            }
            setErreur(null);
            if (reponse.data.comparatif) setComparatif(reponse.data.comparatif as never);
            onCree(famille, slug, Boolean(reponse.data.comparatif));
            return;
        }
        const reponse = await creerUnElementApiV1BuilderBibliothequeFamillePost({ path: { famille }, body: { slug, titre, contenu: objet } });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The element was not created"));
            return;
        }
        setErreur(null);
        onCree(famille, slug, false);
    };

    const pret = Boolean(famille && slug.trim() && titre.trim() && (!importer || (source.trim() && licence.trim())));

    return (
        <section className="space-y-3 rounded border p-4" data-testid="formulaire-import">
            <h2 className="text-lg font-semibold">{t({ en: "Add to the library", fr: "Ajouter à la bibliothèque" })}</h2>
            <div className="grid gap-3 md:grid-cols-3">
                <label className="block space-y-1 text-sm">
                    <span>{t({ en: "Family", fr: "Famille" })}</span>
                    <select className={CHAMP} value={famille} onChange={(e) => setFamille(e.target.value)}>
                        {familles.map((f) => (
                            <option key={f.slug} value={f.slug}>
                                {f.libelle}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="block space-y-1 text-sm">
                    <span>{t({ en: "Identifier (a-z, 0-9, -)", fr: "Identifiant (a-z, 0-9, -)" })}</span>
                    <input className={CHAMP} value={slug} onChange={(e) => setSlug(e.target.value)} />
                </label>
                <label className="block space-y-1 text-sm">
                    <span>{t({ en: "Title", fr: "Titre" })}</span>
                    <input className={CHAMP} value={titre} onChange={(e) => setTitre(e.target.value)} />
                </label>
            </div>
            <label className="block space-y-1 text-sm">
                <span>{t({ en: "Content (JSON)", fr: "Contenu (JSON)" })}</span>
                <textarea className={`${CHAMP} h-32 font-mono text-xs`} value={contenu} onChange={(e) => setContenu(e.target.value)} />
            </label>
            <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={importer} onChange={(e) => setImporter(e.target.checked)} />
                <span>{t({ en: "It comes from a source outside .mark (import)", fr: "Cela vient d'une source extérieure à .mark (import)" })}</span>
            </label>
            {importer && (
                <div className="grid gap-3 md:grid-cols-3">
                    <label className="block space-y-1 text-sm">
                        <span>{t({ en: "Source (address or file)", fr: "Source (adresse ou fichier)" })}</span>
                        <input className={CHAMP} value={source} onChange={(e) => setSource(e.target.value)} />
                    </label>
                    <label className="block space-y-1 text-sm">
                        <span>{t({ en: "Licence (or « unknown »)", fr: "Licence (ou « inconnue »)" })}</span>
                        <input className={CHAMP} value={licence} onChange={(e) => setLicence(e.target.value)} />
                    </label>
                    <label className="block space-y-1 text-sm">
                        <span>{t({ en: "Date", fr: "Date" })}</span>
                        <input className={CHAMP} value={date} onChange={(e) => setDate(e.target.value)} />
                    </label>
                </div>
            )}
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            {comparatif && (
                <div className="space-y-1 text-sm" data-testid="comparatif">
                    <p>
                        {comparatif.identique
                            ? t({ en: "Nothing changed since the last import.", fr: "Rien n'a changé depuis le dernier import." })
                            : t({
                                  en: `Changed since the last import: ${comparatif.ajoutees} line(s) added, ${comparatif.retirees} removed.`,
                                  fr: `Changé depuis le dernier import : ${comparatif.ajoutees} ligne(s) ajoutée(s), ${comparatif.retirees} retirée(s).`,
                              })}
                    </p>
                    {!comparatif.identique && <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-xs">{comparatif.diff}</pre>}
                </div>
            )}
            <Button size="sm" disabled={!pret} onClick={() => void envoyer()}>
                {importer ? t({ en: "Import as a Candidate", fr: "Importer comme Candidat" }) : t({ en: "Create as a Candidate", fr: "Créer comme Candidat" })}
            </Button>
        </section>
    );
}
