"use client";

/**
 * [.mark] U3 ter (E67) : « Configurer le tableau », l'éditeur de tableau PARTAGÉ avec le portail.
 *
 * Une fenêtre à part, de la même taille que celle qui l'ouvre, par-dessus : le tableau sur toute la largeur, en-tête fixe
 * en descendant, numéros fixes en allant à droite, colonnes jamais écrasées (le défilement est dans la zone du tableau).
 * Saisie de tableur : Tab, Entrée (ligne suivante, créée au bout), collage depuis Excel ou Google Sheets réparti dans les
 * cases, import CSV (la première ligne donne les colonnes). Jauge des caractères envoyés à l'agent dans le pied ;
 * « Valider » grisé au-delà du plafond ; « Annuler » ne garde rien.
 *
 * `verrouillerColonnesMark` : dans le portail, une colonne posée par .mark porte un cadenas (ni renommée, ni supprimée, ni
 * changée de type, mais déplaçable) et l'import CSV est grisé quand le tableau en a une. Dans Dograh rien n'est verrouillé.
 */
import { ArrowLeft, ArrowRight, Lock, Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { type Texte, useLangue } from "../langue/langue";
import { CadreModale } from "../reglages-agent/phrases/cadre";
import {
    ajouterColonne,
    ajouterLigne,
    changerType,
    coller,
    deplacerColonne,
    estVerrouillee,
    importerCsv,
    poserCase,
    renommerColonne,
    resume,
    retirerColonne,
    retirerLigne,
    type Tableau,
    texteRecu,
    type TypeColonne,
} from "./tableau-logique";

const TYPES: TypeColonne[] = ["texte", "nombre", "montant", "oui_non", "date"];
const LIBELLE_TYPE: Record<TypeColonne, Texte> = {
    texte: { en: "Text", fr: "Texte" },
    nombre: { en: "Number", fr: "Nombre" },
    montant: { en: "Amount (EUR)", fr: "Montant (€)" },
    oui_non: { en: "Yes / no", fr: "Oui / non" },
    date: { en: "Date", fr: "Date" },
};

export const JaugeCaracteres = ({ taille, plafond }: { taille: number; plafond: number }) => {
    const { t } = useLangue();
    const part = Math.min(100, Math.round((taille / Math.max(1, plafond)) * 100));
    return (
        <div className="min-w-48 space-y-1" data-jauge={taille > plafond ? "depasse" : "ok"}>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div className={`h-full ${taille > plafond ? "bg-destructive" : "bg-primary"}`} style={{ width: `${part}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">{t({ en: `${taille} / ${plafond} characters sent to the agent`, fr: `${taille} / ${plafond} caractères envoyés à l'agent` })}</p>
        </div>
    );
};

/** Le résumé de « Sa valeur » : 3 premières lignes, « … et N autres lignes », compteur, bouton « Configurer le tableau ». */
export const ResumeTableau = ({ tableau, plafond, onConfigurer }: { tableau: Tableau; plafond: number; onConfigurer: () => void }) => {
    const { t } = useLangue();
    const { apercu, autres } = resume(tableau);
    return (
        <div className="space-y-2" data-resume-tableau>
            {tableau.colonnes.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t({ en: "No column yet.", fr: "Aucune colonne pour l'instant." })}</p>
            ) : (
                <table className="w-full text-sm">
                    <thead data-reglage="colonnes">
                        <tr>
                            {tableau.colonnes.map((c) => (
                                <th key={c.libelle} className="px-2 py-1 text-left font-medium">
                                    {c.libelle}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody data-reglage="lignes">
                        {apercu.map((ligne, i) => (
                            <tr key={i}>
                                {ligne.map((v, j) => (
                                    <td key={j} className="px-2 py-1">
                                        {v}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {autres > 0 && <p className="text-xs text-muted-foreground">{t({ en: `… and ${autres} more lines`, fr: `… et ${autres} autres lignes` })}</p>}
            <JaugeCaracteres taille={texteRecu(tableau).length} plafond={plafond} />
            <Button variant="outline" size="sm" onClick={onConfigurer} data-testid="configurer-tableau">
                {t({ en: "Configure the table", fr: "Configurer le tableau" })}
            </Button>
        </div>
    );
};

export const EditeurDeTableau = ({
    tableau,
    plafond,
    verrouillerColonnesMark = false,
    onValider,
    onAnnuler,
}: {
    tableau: Tableau;
    plafond: number;
    verrouillerColonnesMark?: boolean;
    onValider: (t: Tableau) => void;
    onAnnuler: () => void;
}) => {
    const { t } = useLangue();
    const [brouillon, setBrouillon] = useState<Tableau>(() => ({
        colonnes: tableau.colonnes.map((c) => ({ ...c })),
        lignes: tableau.lignes.map((l) => ({ ...l, valeurs: { ...(l.valeurs ?? {}) } })),
    }));
    const fichier = useRef<HTMLInputElement>(null);
    const zone = useRef<HTMLDivElement>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const posePar = verrouillerColonnesMark ? "client" : "mark";

    const taille = texteRecu(brouillon).length;
    const doublon = new Set(brouillon.colonnes.map((c) => c.libelle.trim())).size !== brouillon.colonnes.length;
    const sansNom = brouillon.colonnes.some((c) => !c.libelle.trim());
    const importGrise = verrouillerColonnesMark && brouillon.colonnes.some((c) => c.pose_par === "mark");
    const invalide = taille > plafond || doublon || sansNom;

    const aller = (ligne: number, colonne: number) => {
        // Après le rendu : la case existe (ligne créée au bout).
        setTimeout(() => zone.current?.querySelector<HTMLInputElement>(`[data-case="${ligne}-${colonne}"]`)?.focus(), 0);
    };

    const surEntree = (e: React.KeyboardEvent, ligne: number, colonne: number) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        if (ligne + 1 >= brouillon.lignes.length) setBrouillon((b) => ajouterLigne(b));
        aller(ligne + 1, colonne);
    };

    const surCollage = (e: React.ClipboardEvent, ligne: number, colonne: number) => {
        const brut = e.clipboardData.getData("text");
        if (!brut.includes("\t") && !brut.includes("\n")) return;
        e.preventDefault();
        setBrouillon((b) => coller(b, ligne, colonne, brut, posePar));
    };

    const lireCsv = async (f: File | undefined) => {
        if (!f) return;
        const importe = importerCsv(await f.text(), posePar);
        if (importe.colonnes.length === 0) {
            setErreur(t({ en: "The file has no column.", fr: "Le fichier n'a aucune colonne." }));
            return;
        }
        setErreur(null);
        setBrouillon(importe);
    };

    return (
        <CadreModale
            identifiant="tableau"
            titre={t({ en: "Configure the table", fr: "Configurer le tableau" })}
            description={t({ en: "Tab and Enter move between cells; paste from Excel or Google Sheets fills the cells.", fr: "Tab et Entrée passent d'une case à l'autre ; un collage depuis Excel ou Google Sheets remplit les cases." })}
            onFermer={onAnnuler}
            pied={
                <>
                    <JaugeCaracteres taille={taille} plafond={plafond} />
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={onAnnuler} data-testid="annuler-tableau">
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button disabled={invalide} onClick={() => onValider(brouillon)} data-testid="valider-tableau">
                            {t({ en: "Validate", fr: "Valider" })}
                        </Button>
                    </div>
                </>
            }
        >
            <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setBrouillon((b) => ajouterColonne(b, posePar))} data-testid="ajouter-colonne-tableau">
                        <Plus className="h-3.5 w-3.5" /> {t({ en: "Add a column", fr: "Ajouter une colonne" })}
                    </Button>
                    <Button variant="ghost" size="sm" disabled={brouillon.colonnes.length === 0} onClick={() => setBrouillon((b) => ajouterLigne(b))} data-testid="ajouter-ligne-tableau">
                        <Plus className="h-3.5 w-3.5" /> {t({ en: "Add a line", fr: "Ajouter une ligne" })}
                    </Button>
                    <Button variant="ghost" size="sm" disabled={importGrise} onClick={() => fichier.current?.click()} data-testid="importer-csv" title={importGrise ? t({ en: "This table has columns set by .mark.", fr: "Ce tableau a des colonnes posées par .mark." }) : undefined}>
                        <Upload className="h-3.5 w-3.5" /> {t({ en: "Import a CSV", fr: "Importer un CSV" })}
                    </Button>
                    <input ref={fichier} type="file" accept=".csv,text/csv" hidden data-testid="fichier-csv" onChange={(e) => void lireCsv(e.target.files?.[0])} />
                </div>
                <div ref={zone} className="max-h-[50vh] overflow-auto rounded-md border" data-zone-tableau>
                    <table className="min-w-max border-collapse text-sm">
                        <thead className="sticky top-0 z-10 bg-background">
                            <tr>
                                <th className="w-10 border-b px-2 py-1 text-right text-xs text-muted-foreground">#</th>
                                {brouillon.colonnes.map((c, i) => {
                                    const verrou = estVerrouillee(c, verrouillerColonnesMark);
                                    return (
                                        <th key={i} className="min-w-44 border-b px-2 py-1 text-left align-top" data-colonne={c.libelle}>
                                            <div className="flex items-center gap-1">
                                                {verrou && <Lock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label={t({ en: "Set by .mark", fr: "Posée par .mark" })} />}
                                                <Input aria-label={`${t({ en: "Column", fr: "Colonne" })} ${i + 1}`} value={c.libelle} disabled={verrou} onChange={(e) => setBrouillon((b) => renommerColonne(b, i, e.target.value))} className="h-8" />
                                            </div>
                                            <div className="mt-1 flex items-center gap-1">
                                                <Select value={c.type ?? "texte"} disabled={verrou} onValueChange={(v: string) => setBrouillon((b) => changerType(b, i, v as TypeColonne))}>
                                                    <SelectTrigger className="h-7 w-32 text-xs" aria-label={`${t({ en: "Type", fr: "Type" })} ${i + 1}`}>
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {TYPES.map((ty) => (
                                                            <SelectItem key={ty} value={ty}>
                                                                {t(LIBELLE_TYPE[ty])}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                                <Button variant="ghost" size="icon" className="h-7 w-7" disabled={i === 0} aria-label={`${t({ en: "Move left", fr: "Déplacer à gauche" })} ${i + 1}`} onClick={() => setBrouillon((b) => deplacerColonne(b, i, i - 1))}>
                                                    <ArrowLeft className="h-3.5 w-3.5" />
                                                </Button>
                                                <Button variant="ghost" size="icon" className="h-7 w-7" disabled={i === brouillon.colonnes.length - 1} aria-label={`${t({ en: "Move right", fr: "Déplacer à droite" })} ${i + 1}`} onClick={() => setBrouillon((b) => deplacerColonne(b, i, i + 1))}>
                                                    <ArrowRight className="h-3.5 w-3.5" />
                                                </Button>
                                                <Button variant="ghost" size="icon" className="h-7 w-7" disabled={verrou} aria-label={`${t({ en: "Remove the column", fr: "Retirer la colonne" })} ${i + 1}`} onClick={() => setBrouillon((b) => retirerColonne(b, i))}>
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                            </div>
                                        </th>
                                    );
                                })}
                            </tr>
                        </thead>
                        <tbody>
                            {brouillon.lignes.map((l, i) => (
                                <tr key={i} data-ligne-tableau={i}>
                                    <td className="sticky right-0 w-10 bg-background px-2 text-right text-xs text-muted-foreground">
                                        <button type="button" className="cursor-pointer hover:font-medium" aria-label={`${t({ en: "Remove line", fr: "Retirer la ligne" })} ${i + 1}`} onClick={() => setBrouillon((b) => retirerLigne(b, i))}>
                                            {i + 1}
                                        </button>
                                    </td>
                                    {brouillon.colonnes.map((c, j) => (
                                        <td key={j} className="px-1 py-0.5">
                                            <CaseDuTableau type={c.type ?? "texte"} valeur={l.valeurs?.[c.libelle] ?? ""} ligne={i} colonne={j} libelle={`${c.libelle} ${i + 1}`} onChange={(v) => setBrouillon((b) => poserCase(b, i, c.libelle, v))} onKeyDown={(e) => surEntree(e, i, j)} onPaste={(e) => surCollage(e, i, j)} />
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {(doublon || sansNom || taille > plafond || erreur) && (
                    <div className="space-y-1 text-sm text-destructive" role="alert" data-testid="erreur-tableau">
                        {doublon && <p>{t({ en: "Two columns have the same label.", fr: "Deux colonnes ont le même libellé." })}</p>}
                        {sansNom && <p>{t({ en: "A column has no label.", fr: "Une colonne n'a pas de libellé." })}</p>}
                        {taille > plafond && <p>{t({ en: `The agent would receive ${taille} characters, over the ceiling of ${plafond}.`, fr: `L'agent recevrait ${taille} caractères, au-delà du plafond de ${plafond}.` })}</p>}
                        {erreur && <p>{erreur}</p>}
                    </div>
                )}
            </div>
        </CadreModale>
    );
};

const CaseDuTableau = ({
    type,
    valeur,
    ligne,
    colonne,
    libelle,
    onChange,
    onKeyDown,
    onPaste,
}: {
    type: TypeColonne;
    valeur: string;
    ligne: number;
    colonne: number;
    libelle: string;
    onChange: (v: string) => void;
    onKeyDown: (e: React.KeyboardEvent) => void;
    onPaste: (e: React.ClipboardEvent) => void;
}) => {
    if (type === "oui_non") {
        return (
            <select data-case={`${ligne}-${colonne}`} aria-label={libelle} value={valeur} onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} className="h-8 w-full rounded-md border bg-background px-2 text-sm">
                <option value="" />
                <option value="oui">oui</option>
                <option value="non">non</option>
            </select>
        );
    }
    return (
        <div className="relative">
            <Input
                data-case={`${ligne}-${colonne}`}
                aria-label={libelle}
                type={type === "date" ? "date" : "text"}
                inputMode={type === "nombre" || type === "montant" ? "decimal" : undefined}
                value={valeur}
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={onKeyDown}
                onPaste={onPaste}
                className={type === "montant" ? "h-8 pr-6 text-right" : "h-8"}
            />
            {type === "montant" && <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">€</span>}
        </div>
    );
};
