"use client";

/**
 * [.mark] The simulated caller's settings (chantier langwatch-et-fenetre-du-run, lot 3, L13, L18,
 * Q1 to Q3), for the whole organization: the simulated caller's and the judge's model, prompt and
 * key; the caller's voice; how many calls at once; the size of a series and its spending cap.
 *
 * Keys are picked in the key library (`../cles/FenetreCles.tsx`, direct-et-passe-muette P15), where
 * they are also added and deleted; never stored in these settings. A modal (E4) working on a copy:
 * « Cancel » / « Save ».
 */
import { useEffect, useState } from "react";

import {
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet,
    saveReglagesAppelantSimuleApiV1AppelSimuleReglagesPut,
} from "@/client";
import type { ReglagesAppelantSimule, RoleSimule, VoixSimulee } from "@/client/types.gen";
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
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { SelecteurCle } from "../cles/FenetreCles";
import { type Texte, useLangue } from "../langue/langue";

// Same list as the server (`MODELES_SIMULATEUR`, api/schemas/appel_simule.py).
export const MODELES_SIMULATEUR: RoleSimule["modele"][] = [
    "mistral/mistral-small-latest",
    "mistral/mistral-medium-latest",
    "mistral/mistral-large-latest",
];
// Same bounds as the server (`ReglagesAppelantSimule`).
const BORNES = {
    simultanes: { min: 1, max: 3 },
    taille_max_serie: { min: 1, max: 50 },
    plafond: { min: 0.01, max: 200 },
};

/** The settings as read, with every part present (the server fills the defaults; the generated
 * type leaves them optional). */
type Role = Required<Pick<RoleSimule, "modele" | "consigne" | "temperature">> & { identifiant: string | null };
export type ReglagesComplets = Omit<ReglagesAppelantSimule, "appelant" | "juge" | "voix"> & {
    appelant: Role;
    juge: Role;
    voix: Required<Pick<VoixSimulee, "voix">> & { identifiant: string | null };
};

const role = (r: RoleSimule | undefined): Role => ({
    modele: r?.modele ?? "mistral/mistral-small-latest",
    consigne: r?.consigne ?? "",
    temperature: r?.temperature ?? 0,
    identifiant: r?.identifiant ?? null,
});

export const completer = (lu: ReglagesAppelantSimule): ReglagesComplets => ({
    ...lu,
    appelant: role(lu.appelant),
    juge: role(lu.juge),
    voix: { voix: lu.voix?.voix ?? "", identifiant: lu.voix?.identifiant ?? null },
});

export const fautesDesReglages = (r: ReglagesComplets, t: (texte: Texte) => string): string[] => {
    const fautes: string[] = [];
    if (!r.appelant.consigne.trim()) fautes.push(t({ en: "Caller prompt missing", fr: "Consigne de l'appelant manquante" }));
    if (!r.juge.consigne.trim()) fautes.push(t({ en: "Judge prompt missing", fr: "Consigne du juge manquante" }));
    if (r.appelant.identifiant !== r.juge.identifiant)
        fautes.push(
            t({
                en: "The caller and the judge use the same model key",
                fr: "L'appelant et le juge utilisent la même clé de modèle",
            }),
        );
    for (const [champ, { min, max }] of Object.entries(BORNES) as [keyof typeof BORNES, { min: number; max: number }][]) {
        const valeur = r[champ];
        if (typeof valeur !== "number" || Number.isNaN(valeur) || valeur < min || valeur > max)
            fautes.push(t({ en: `${champ}: between ${min} and ${max}`, fr: `${champ} : entre ${min} et ${max}` }));
    }
    return fautes;
};

function Role({
    titre,
    role,
    onChange,
}: {
    titre: Texte;
    role: Role;
    onChange: (morceau: Partial<Role>) => void;
}) {
    const { t } = useLangue();
    return (
        <fieldset className="space-y-2 rounded border border-border p-3">
            <legend className="px-1 text-sm font-medium">{t(titre)}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Model", fr: "Modèle" })}</span>
                    <select
                        className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                        value={role.modele}
                        onChange={(e) => onChange({ modele: e.target.value as Role["modele"] })}
                        aria-label={`${t(titre)} · ${t({ en: "Model", fr: "Modèle" })}`}
                    >
                        {MODELES_SIMULATEUR.map((m) => (
                            <option key={m} value={m}>
                                {m}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Temperature (0 to 1)", fr: "Température (0 à 1)" })}</span>
                    <Input
                        type="number"
                        min={0}
                        max={1}
                        step="0.1"
                        value={role.temperature ?? 0}
                        onChange={(e) => onChange({ temperature: Number(e.target.value) })}
                        aria-label={`${t(titre)} · ${t({ en: "Temperature", fr: "Température" })}`}
                    />
                </label>
            </div>
            <label className="block space-y-1 text-xs text-muted-foreground">
                <span>{t({ en: "Prompt", fr: "Consigne" })}</span>
                <Textarea
                    value={role.consigne}
                    onChange={(e) => onChange({ consigne: e.target.value })}
                    className="min-h-28 text-sm"
                    aria-label={`${t(titre)} · ${t({ en: "Prompt", fr: "Consigne" })}`}
                />
            </label>
        </fieldset>
    );
}

export function ModaleReglagesAppelantSimule({ ouverte, onFermer }: { ouverte: boolean; onFermer: () => void }) {
    const { t } = useLangue();
    const [brouillon, setBrouillon] = useState<ReglagesComplets | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!ouverte) return;
        let annule = false;
        setErreur(null);
        setBrouillon(null);
        (async () => {
            const reglages = await getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet();
            if (annule) return;
            if (reglages.error) {
                setErreur(detailFromError(reglages.error, "Simulated caller settings unreadable"));
                return;
            }
            setBrouillon(completer(reglages.data as ReglagesAppelantSimule));
        })();
        return () => {
            annule = true;
        };
    }, [ouverte]);

    const fautes = brouillon ? fautesDesReglages(brouillon, t) : [];
    const changer = (morceau: Partial<ReglagesComplets>) =>
        setBrouillon((avant) => (avant ? { ...avant, ...morceau } : avant));

    const enregistrer = async () => {
        if (!brouillon) return;
        setEnCours(true);
        setErreur(null);
        const reponse = await saveReglagesAppelantSimuleApiV1AppelSimuleReglagesPut({ body: brouillon });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Simulated caller settings not saved"));
            return;
        }
        onFermer();
    };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer())}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl" data-testid="modale-reglages-appelant-simule">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Simulated caller settings", fr: "Réglages de l'appelant simulé" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "For the whole organization. The simulated caller and the judge use a Mistral key of an organization other than the agent's, so they never eat its quota. Keys are added, picked and deleted with « Keys… ».",
                            fr: "Pour toute l'organisation. L'appelant simulé et le juge utilisent une clé Mistral d'une autre organisation que celle de l'agent, pour ne jamais manger son quota. Les clés s'ajoutent, se choisissent et se suppriment avec « Clés… ».",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert">
                        {erreur}
                    </p>
                )}
                {brouillon === null && !erreur ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : brouillon ? (
                    <div className="space-y-3">
                        <SelecteurCle
                            fournisseur="mistral"
                            valeur={brouillon.appelant.identifiant}
                            libelle={{ en: "Mistral key (caller and judge)", fr: "Clé Mistral (appelant et juge)" }}
                            onChange={(uuid) =>
                                changer({
                                    appelant: { ...brouillon.appelant, identifiant: uuid },
                                    juge: { ...brouillon.juge, identifiant: uuid },
                                })
                            }
                        />
                        <Role
                            titre={{ en: "Simulated caller", fr: "Appelant simulé" }}
                            role={brouillon.appelant}
                            onChange={(m) => changer({ appelant: { ...brouillon.appelant, ...m } })}
                        />
                        <Role
                            titre={{ en: "Judge", fr: "Juge" }}
                            role={brouillon.juge}
                            onChange={(m) => changer({ juge: { ...brouillon.juge, ...m } })}
                        />
                        <fieldset className="grid gap-2 rounded border border-border p-3 sm:grid-cols-2">
                            <legend className="px-1 text-sm font-medium">{t({ en: "Voice", fr: "Voix" })}</legend>
                            <label className="space-y-1 text-xs text-muted-foreground">
                                <span>{t({ en: "ElevenLabs voice id (a French voice)", fr: "Identifiant de voix ElevenLabs (une voix française)" })}</span>
                                <Input
                                    value={brouillon.voix.voix}
                                    onChange={(e) => changer({ voix: { ...brouillon.voix, voix: e.target.value } })}
                                    aria-label={t({ en: "ElevenLabs voice id", fr: "Identifiant de voix ElevenLabs" })}
                                />
                            </label>
                            <SelecteurCle
                                fournisseur="elevenlabs"
                                valeur={brouillon.voix.identifiant}
                                libelle={{ en: "ElevenLabs key (voice and transcription)", fr: "Clé ElevenLabs (voix et transcription)" }}
                                onChange={(uuid) => changer({ voix: { ...brouillon.voix, identifiant: uuid } })}
                            />
                        </fieldset>
                        <fieldset className="grid gap-2 rounded border border-border p-3 sm:grid-cols-3">
                            <legend className="px-1 text-sm font-medium">{t({ en: "Series", fr: "Séries" })}</legend>
                            <label className="space-y-1 text-xs text-muted-foreground">
                                <span>
                                    {t({
                                        en: "Calls at once (1 to 3; the Mistral limit holds 1)",
                                        fr: "Appels simultanés (1 à 3 ; la limite Mistral tient 1)",
                                    })}
                                </span>
                                <Input
                                    type="number"
                                    min={1}
                                    max={3}
                                    value={brouillon.simultanes ?? 1}
                                    onChange={(e) => changer({ simultanes: Number(e.target.value) })}
                                    aria-label={t({ en: "Calls at once", fr: "Appels simultanés" })}
                                />
                            </label>
                            <label className="space-y-1 text-xs text-muted-foreground">
                                <span>{t({ en: "Calls per series at most", fr: "Appels par série au plus" })}</span>
                                <Input
                                    type="number"
                                    min={1}
                                    max={50}
                                    value={brouillon.taille_max_serie ?? 10}
                                    onChange={(e) => changer({ taille_max_serie: Number(e.target.value) })}
                                    aria-label={t({ en: "Calls per series at most", fr: "Appels par série au plus" })}
                                />
                            </label>
                            <label className="space-y-1 text-xs text-muted-foreground">
                                <span>
                                    {t({
                                        en: "Spending cap of a series (price table currency)",
                                        fr: "Plafond de dépense d'une série (devise de la table des prix)",
                                    })}
                                </span>
                                <Input
                                    type="number"
                                    min={0.01}
                                    max={200}
                                    step="0.5"
                                    value={brouillon.plafond ?? 5}
                                    onChange={(e) => changer({ plafond: Number(e.target.value) })}
                                    aria-label={t({ en: "Spending cap", fr: "Plafond de dépense" })}
                                />
                            </label>
                        </fieldset>
                        {fautes.length > 0 && (
                            <ul className="text-sm text-destructive" data-testid="fautes-appelant-simule">
                                {fautes.map((f) => (
                                    <li key={f}>{f}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                ) : null}
                <DialogFooter>
                    <Button variant="outline" onClick={onFermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()} disabled={enCours || brouillon === null || fautes.length > 0}>
                        {t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
