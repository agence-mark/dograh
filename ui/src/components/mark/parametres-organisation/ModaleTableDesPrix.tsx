"use client";

/**
 * [.mark] The organization's price table (chantier langwatch-et-fenetre-du-run, lot 2, L5 and L18).
 *
 * The run window turns a call's consumption into an estimated cost with these prices: one line per
 * provider model, dated (prices change; the window says at which rate). Edited here, never in a
 * file. A list to edit, so a modal (E4) working on a copy: « Cancel » / « Save ». No price is
 * offered by default: an empty table means « cost not captured », never a guessed cost.
 */
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
    getTableDesPrixApiV1OrganizationsTableDesPrixGet,
    saveTableDesPrixApiV1OrganizationsTableDesPrixPut,
} from "@/client";
import type { LignePrix, TableDesPrix } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

type Brique = LignePrix["brique"];
type ChampPrix =
    | "entree_par_million"
    | "cache_par_million"
    | "sortie_par_million"
    | "par_minute"
    | "par_million_caracteres";

const BRIQUES: { valeur: Brique; libelle: Texte }[] = [
    { valeur: "llm", libelle: { en: "Model", fr: "Modèle" } },
    { valeur: "stt", libelle: { en: "Transcription", fr: "Transcription" } },
    { valeur: "tts", libelle: { en: "Voice", fr: "Voix" } },
    { valeur: "telephony", libelle: { en: "Telephony", fr: "Téléphonie" } },
];

// The prices each component takes: the same rule as the server (`PRIX_PERMIS`).
export const PRIX_DE_LA_BRIQUE: Record<Brique, { champ: ChampPrix; libelle: Texte; requis: boolean }[]> = {
    llm: [
        { champ: "entree_par_million", libelle: { en: "Input / 1M tokens", fr: "Entrée / 1 M jetons" }, requis: true },
        {
            champ: "cache_par_million",
            libelle: { en: "Cached / 1M tokens (empty = input)", fr: "Cache / 1 M jetons (vide = entrée)" },
            requis: false,
        },
        { champ: "sortie_par_million", libelle: { en: "Output / 1M tokens", fr: "Sortie / 1 M jetons" }, requis: true },
    ],
    stt: [{ champ: "par_minute", libelle: { en: "Per minute", fr: "Par minute" }, requis: true }],
    tts: [
        {
            champ: "par_million_caracteres",
            libelle: { en: "Per 1M characters", fr: "Par 1 M caractères" },
            requis: true,
        },
    ],
    telephony: [{ champ: "par_minute", libelle: { en: "Per minute", fr: "Par minute" }, requis: true }],
};

const aujourdhui = () => new Date().toISOString().slice(0, 10);

const ligneVide = (): LignePrix => ({ brique: "llm", modele: "", date_du_tarif: aujourdhui() });

/** The faults of a draft, named, before anything is sent (the server checks the same). */
export const fautesDeLaTable = (lignes: LignePrix[], t: (texte: Texte) => string): string[] => {
    const fautes: string[] = [];
    const vues = new Set<string>();
    lignes.forEach((ligne, i) => {
        const n = i + 1;
        if (!ligne.modele.trim()) fautes.push(t({ en: `Line ${n}: model missing`, fr: `Ligne ${n} : modèle manquant` }));
        for (const prix of PRIX_DE_LA_BRIQUE[ligne.brique]) {
            const valeur = ligne[prix.champ];
            if (prix.requis && (valeur === null || valeur === undefined))
                fautes.push(t({ en: `Line ${n}: ${t(prix.libelle)} missing`, fr: `Ligne ${n} : ${t(prix.libelle)} manquant` }));
            if (typeof valeur === "number" && valeur < 0)
                fautes.push(t({ en: `Line ${n}: negative price`, fr: `Ligne ${n} : prix négatif` }));
        }
        const cle = `${ligne.brique}|${ligne.modele.trim()}`;
        if (ligne.modele.trim() && vues.has(cle))
            fautes.push(t({ en: `Line ${n}: model declared twice`, fr: `Ligne ${n} : modèle déclaré deux fois` }));
        vues.add(cle);
    });
    return fautes;
};

/** Only the prices of the line's component leave: a price typed then the component changed is dropped. */
const nettoyer = (ligne: LignePrix): LignePrix => {
    const propre: LignePrix = { brique: ligne.brique, modele: ligne.modele.trim(), date_du_tarif: ligne.date_du_tarif };
    for (const { champ } of PRIX_DE_LA_BRIQUE[ligne.brique]) {
        const valeur = ligne[champ];
        if (typeof valeur === "number") propre[champ] = valeur;
    }
    return propre;
};

export function ModaleTableDesPrix({ ouverte, onFermer }: { ouverte: boolean; onFermer: () => void }) {
    const { t } = useLangue();
    const [table, setTable] = useState<TableDesPrix | null>(null);
    const [brouillon, setBrouillon] = useState<LignePrix[]>([]);
    const [devise, setDevise] = useState<"USD" | "EUR">("USD");
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!ouverte) return;
        let annule = false;
        setErreur(null);
        setTable(null);
        (async () => {
            const reponse = await getTableDesPrixApiV1OrganizationsTableDesPrixGet();
            if (annule) return;
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Price table unreadable"));
                return;
            }
            const lue = reponse.data as TableDesPrix;
            setTable(lue);
            setBrouillon(lue.lignes ?? []);
            setDevise(lue.devise ?? "USD");
        })();
        return () => {
            annule = true;
        };
    }, [ouverte]);

    const fautes = fautesDeLaTable(brouillon, t);
    const changer = (i: number, morceau: Partial<LignePrix>) =>
        setBrouillon((avant) => avant.map((l, k) => (k === i ? { ...l, ...morceau } : l)));

    const enregistrer = async () => {
        setEnCours(true);
        setErreur(null);
        const reponse = await saveTableDesPrixApiV1OrganizationsTableDesPrixPut({
            body: { format: "table-des-prix-mark", version: 1, devise, lignes: brouillon.map(nettoyer) },
        });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Price table not saved"));
            return;
        }
        onFermer();
    };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer())}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl" data-testid="modale-table-des-prix">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Price table", fr: "Table des prix" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "One line per provider model, with the date of the rate. The run window multiplies each call's consumption by these prices. A model without a price is shown as unpriced, never guessed.",
                            fr: "Une ligne par modèle de fournisseur, avec la date du tarif. La fenêtre du run multiplie la consommation de chaque appel par ces prix. Un modèle sans prix est affiché « sans prix », jamais deviné.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert">
                        {erreur}
                    </p>
                )}
                {table === null && !erreur ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : (
                    <div className="space-y-3">
                        <label className="flex items-center gap-2 text-sm">
                            {t({ en: "Currency", fr: "Devise" })}
                            <select
                                className="rounded border border-border bg-background px-2 py-1"
                                value={devise}
                                onChange={(e) => setDevise(e.target.value as "USD" | "EUR")}
                                aria-label={t({ en: "Currency", fr: "Devise" })}
                            >
                                <option value="USD">{t({ en: "USD", fr: "USD" })}</option>
                                <option value="EUR">{t({ en: "EUR", fr: "EUR" })}</option>
                            </select>
                        </label>
                        {brouillon.map((ligne, i) => (
                            <div
                                key={i}
                                data-testid="ligne-de-prix"
                                className="grid gap-2 rounded border border-border p-3 sm:grid-cols-[8rem_1fr_9rem_auto]"
                            >
                                <select
                                    className="rounded border border-border bg-background px-2 py-1 text-sm"
                                    value={ligne.brique}
                                    onChange={(e) => changer(i, { brique: e.target.value as Brique })}
                                    aria-label={t({ en: "Component", fr: "Brique" })}
                                >
                                    {BRIQUES.map((b) => (
                                        <option key={b.valeur} value={b.valeur}>
                                            {t(b.libelle)}
                                        </option>
                                    ))}
                                </select>
                                <Input
                                    value={ligne.modele}
                                    onChange={(e) => changer(i, { modele: e.target.value })}
                                    placeholder={t({
                                        en: "model id as recorded (e.g. mistral-large-2512)",
                                        fr: "identifiant du modèle tel qu'enregistré (ex. mistral-large-2512)",
                                    })}
                                    aria-label={t({ en: "Model", fr: "Modèle" })}
                                />
                                <Input
                                    type="date"
                                    value={ligne.date_du_tarif}
                                    onChange={(e) => changer(i, { date_du_tarif: e.target.value })}
                                    aria-label={t({ en: "Rate date", fr: "Date du tarif" })}
                                />
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => setBrouillon((avant) => avant.filter((_, k) => k !== i))}
                                    aria-label={t({ en: "Remove the line", fr: "Retirer la ligne" })}
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                                <div className="grid gap-2 sm:col-span-4 sm:grid-cols-3">
                                    {PRIX_DE_LA_BRIQUE[ligne.brique].map((prix) => (
                                        <label key={prix.champ} className="space-y-1 text-xs text-muted-foreground">
                                            <span>
                                                {t(prix.libelle)} <code>{prix.champ}</code>
                                            </span>
                                            <Input
                                                type="number"
                                                min={0}
                                                step="any"
                                                value={ligne[prix.champ] ?? ""}
                                                onChange={(e) =>
                                                    changer(i, {
                                                        [prix.champ]: e.target.value === "" ? null : Number(e.target.value),
                                                    })
                                                }
                                                aria-label={t(prix.libelle)}
                                            />
                                        </label>
                                    ))}
                                </div>
                            </div>
                        ))}
                        <Button variant="outline" size="sm" onClick={() => setBrouillon((avant) => [...avant, ligneVide()])}>
                            <Plus className="mr-1 h-4 w-4" />
                            {t({ en: "Add a line", fr: "Ajouter une ligne" })}
                        </Button>
                        {fautes.length > 0 && (
                            <ul className="text-sm text-destructive" data-testid="fautes-table-des-prix">
                                {fautes.map((f) => (
                                    <li key={f}>{f}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}
                <DialogFooter>
                    <Button variant="outline" onClick={onFermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()} disabled={enCours || table === null || fautes.length > 0}>
                        {t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
