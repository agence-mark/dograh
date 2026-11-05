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
    getDepenseDesRolesApiV1AppelSimuleDepenseGet,
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet,
    saveReglagesAppelantSimuleApiV1AppelSimuleReglagesPut,
} from "@/client";
import type { DepenseDesRoles, DepenseDuRole, ReglagesAppelantSimule, RoleSimule, VoixSimulee } from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { SelecteurCle } from "../cles/FenetreCles";
import { type Texte, useLangue } from "../langue/langue";
import { Info } from "../studio/marques";
import { montant } from "./montant";

// Suggestions only (`MODELES_SIMULATEUR`, api/schemas/appel_simule.py): the server accepts any « provider/model » (U6).
export const MODELES_SIMULATEUR: string[] = [
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
const BUDGET_MAX = 100000;

/** The settings as read, with every part present (the server fills the defaults; the generated
 * type leaves them optional). */
type Role = Required<Pick<RoleSimule, "modele" | "consigne" | "temperature" | "source" | "actif" | "budget_mois">> & { identifiant: string | null };
export type ReglagesComplets = Omit<ReglagesAppelantSimule, "appelant" | "juge" | "voix"> & {
    appelant: Role;
    juge: Role;
    voix: Required<Pick<VoixSimulee, "voix">> & { identifiant: string | null };
};

const role = (r: RoleSimule | undefined): Role => ({
    source: r?.source ?? "cle_api",
    modele: r?.modele ?? "mistral/mistral-small-latest",
    consigne: r?.consigne ?? "",
    temperature: r?.temperature ?? 0,
    identifiant: r?.identifiant ?? null,
    // Partie 3, lot 12 (SE-23) : chaque rôle a son interrupteur (éteint par défaut) et son budget du mois (0 = aucun plafond).
    actif: r?.actif ?? false,
    budget_mois: r?.budget_mois ?? 0,
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
    for (const [nom, rl] of [
        [t({ en: "Caller", fr: "Appelant" }), r.appelant],
        [t({ en: "Judge", fr: "Juge" }), r.juge],
    ] as const)
        if (typeof rl.budget_mois !== "number" || Number.isNaN(rl.budget_mois) || rl.budget_mois < 0 || rl.budget_mois > BUDGET_MAX)
            fautes.push(t({ en: `${nom} budget: between 0 and ${BUDGET_MAX}`, fr: `Budget ${nom.toLowerCase()} : entre 0 et ${BUDGET_MAX}` }));
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
    juge = false,
    depense,
    onChange,
}: {
    titre: Texte;
    role: Role;
    juge?: boolean;
    depense: DepenseDuRole | null;
    onChange: (morceau: Partial<Role>) => void;
}) {
    const { t, langue } = useLangue();
    return (
        <fieldset className="space-y-2 rounded border border-border p-3" data-role={juge ? "juge" : "appelant"}>
            <legend className="px-1 text-sm font-medium">{t(titre)}</legend>
            <div className="flex items-center justify-between gap-3 text-sm">
                <span className="flex items-center gap-1.5">
                    {t({ en: "Switched on", fr: "Activé" })}
                    <Info>
                        {t({
                            en: "Off by default: a switched-off role makes no call to its model and spends nothing.",
                            fr: "Éteint par défaut : un rôle éteint ne fait aucun appel à son modèle et ne dépense rien.",
                        })}
                    </Info>
                </span>
                <Switch
                    aria-label={`${t(titre)} · ${t({ en: "Switched on", fr: "Activé" })}`}
                    checked={role.actif}
                    onCheckedChange={(v) => onChange({ actif: v })}
                />
            </div>
            <label className="block space-y-1 text-xs text-muted-foreground">
                <span>
                    {t({ en: "Source", fr: "Source" })}{" "}
                    {/* RA-B R6 : le code ne restreint rien ; une bulle rappelle le bon principe (aucun blocage, aucun avertissement). */}
                    {juge ? (
                        <Info>
                            {t({
                                en: "Good practice, not a rule: choose a judge model different from the agent's and the builder's, so the judge does not grade its own work. Every verdict says which model judged it.",
                                fr: "Bonne pratique, pas une règle : choisissez pour le juge un modèle différent de celui de l'agent et du builder, pour qu'il ne note pas son propre travail. Chaque verdict dit quel modèle l'a jugé.",
                            })}
                        </Info>
                    ) : (
                        role.source === "claude_code" && (
                            <Info>
                                {t({
                                    en: "Played by a Claude Code session, with no API call.",
                                    fr: "Joué par une session Claude Code, sans appel d'API.",
                                })}
                            </Info>
                        )
                    )}
                </span>
                <ListeDeroulante
                    className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                    value={role.source}
                    onChange={(e) => onChange({ source: e.target.value as Role["source"] })}
                    aria-label={`${t(titre)} · ${t({ en: "Source", fr: "Source" })}`}
                >
                    <option value="cle_api">{t({ en: "API key", fr: "Clé d'API" })}</option>
                    <option value="claude_code">{t({ en: "Claude Code (subscription)", fr: "Claude Code (abonnement)" })}</option>
                </ListeDeroulante>
            </label>
            {role.source === "cle_api" && (
                <SelecteurCle
                    fournisseur="mistral"
                    valeur={role.identifiant}
                    libelle={{
                        en: `${t(titre)} · model key`,
                        fr: `${t(titre)} · clé du modèle`,
                    }}
                    onChange={(uuid) => onChange({ identifiant: uuid })}
                />
            )}
            <div className="grid gap-2 sm:grid-cols-2">
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Model", fr: "Modèle" })}</span>
                    <ListeDeroulante
                        className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                        value={role.modele}
                        onChange={(e) => onChange({ modele: e.target.value })}
                        aria-label={`${t(titre)} · ${t({ en: "Model", fr: "Modèle" })}`}
                    >
                        {(MODELES_SIMULATEUR.includes(role.modele) ? MODELES_SIMULATEUR : [role.modele, ...MODELES_SIMULATEUR]).map((m) => (
                            <option key={m} value={m}>
                                {m}
                            </option>
                        ))}
                    </ListeDeroulante>
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
            <div className="grid gap-2 sm:grid-cols-2">
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Monthly budget (0 = no cap)", fr: "Budget du mois (0 = aucun plafond)" })}</span>
                    <Input
                        type="number"
                        min={0}
                        max={BUDGET_MAX}
                        step="0.5"
                        value={role.budget_mois}
                        onChange={(e) => onChange({ budget_mois: Number(e.target.value) })}
                        aria-label={`${t(titre)} · ${t({ en: "Monthly budget", fr: "Budget du mois" })}`}
                    />
                </label>
                <p className="self-end text-xs text-muted-foreground" data-depense-du-role>
                    {depense === null
                        ? "…"
                        : depense.atteint
                          ? t({
                                en: `Budget reached: ${montant(depense.cout, langue)} spent this month`,
                                fr: `Budget atteint : ${montant(depense.cout, langue)} dépensés ce mois-ci`,
                            })
                          : t({
                                en: `${montant(depense.cout, langue)} spent this month (${depense.appels ?? 0} calls)`,
                                fr: `${montant(depense.cout, langue)} dépensés ce mois-ci (${depense.appels ?? 0} appels)`,
                            })}
                </p>
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
    const [depense, setDepense] = useState<DepenseDesRoles | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!ouverte) return;
        let annule = false;
        setErreur(null);
        setBrouillon(null);
        setDepense(null);
        (async () => {
            // Les deux lectures partent ensemble ; la dépense n'est qu'une indication (une panne ne bloque rien).
            const [reglages, suivi] = await Promise.all([
                getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet(),
                getDepenseDesRolesApiV1AppelSimuleDepenseGet(),
            ]);
            if (annule) return;
            if (!suivi.error && suivi.data) setDepense(suivi.data);
            if (reglages.error) {
                setErreur(echecAffiche(reglages.error, ECHECS.appelSimuleDepense));
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
            setErreur(echecAffiche(reponse.error, ECHECS.appelantSimuleEnregistrer));
            return;
        }
        notifier.succes({ fr: "Réglages de l'appelant simulé enregistrés.", en: "Simulated caller settings saved." });
        onFermer();
    };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer())}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl" data-testid="modale-reglages-appelant-simule">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Simulated caller settings", fr: "Réglages de l'appelant simulé" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "For the whole organization. The simulated caller and the judge use a Mistral key of an organization other than the agent's, so they never eat its quota. Each has its own model, key, switch and monthly budget. Keys are added, picked and deleted with « Keys… ».",
                            fr: "Pour toute l'organisation. L'appelant simulé et le juge utilisent une clé Mistral d'une autre organisation que celle de l'agent, pour ne jamais manger son quota. Chacun a son modèle, sa clé, son interrupteur et son budget du mois. Les clés s'ajoutent, se choisissent et se suppriment avec « Clés… ».",
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
                        <Role
                            titre={{ en: "Simulated caller", fr: "Appelant simulé" }}
                            role={brouillon.appelant}
                            depense={depense?.appelant ?? null}
                            onChange={(m) => changer({ appelant: { ...brouillon.appelant, ...m } })}
                        />
                        <Role
                            titre={{ en: "Judge", fr: "Juge" }}
                            juge
                            role={brouillon.juge}
                            depense={depense?.juge ?? null}
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
