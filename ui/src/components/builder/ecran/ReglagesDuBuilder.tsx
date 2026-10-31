"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): the builder's settings: which brain (provider format, model, address), its key,
 * the ceiling of a conversation, and the person's own preferences (layer 3 of the permanent context).
 *
 * ⛔ The key is written, never read back: the field starts empty, says « a key is saved » when there is one, and an
 * empty field leaves the saved key alone. Only members of the .mark team may change the brain (the server decides).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
    ecrireLesPreferencesApiV1BuilderPreferencesPut,
    lireLeCerveauApiV1BuilderCerveauGet,
    lireLesPreferencesApiV1BuilderPreferencesGet,
    reglerLeCerveauApiV1BuilderCerveauPut,
} from "@/client";
import type { VueReglagesCerveau } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

const T = {
    titre: { en: "Builder settings", fr: "Réglages du builder" },
    description: {
        en: "The brain that builds your agents. The cost is the one of the key you give; the key is kept encrypted and never shown again.",
        fr: "Le cerveau qui construit vos agents. Le coût est celui de la clé que vous donnez ; elle est gardée chiffrée et n'est jamais réaffichée.",
    },
    fournisseur: { en: "Provider format", fr: "Format du fournisseur" },
    anthropic: { en: "Anthropic (Claude)", fr: "Anthropic (Claude)" },
    openai: { en: "OpenAI-compatible (OpenAI, Mistral, Gemini...)", fr: "Compatible OpenAI (OpenAI, Mistral, Gemini...)" },
    modele: { en: "Model", fr: "Modèle" },
    adresse: { en: "Address (https, optional)", fr: "Adresse (https, facultative)" },
    adresseAide: { en: "Empty: the provider's usual address.", fr: "Vide : l'adresse habituelle du fournisseur." },
    cle: { en: "Key", fr: "Clé" },
    clePosee: { en: "A key is saved. Leave empty to keep it.", fr: "Une clé est enregistrée. Laissez vide pour la garder." },
    cleAbsente: { en: "No key saved yet.", fr: "Aucune clé enregistrée." },
    plafondDepense: { en: "Spending ceiling per conversation ($, 0 = none)", fr: "Plafond de dépense par conversation ($, 0 = aucun)" },
    plafondJetons: { en: "Token ceiling per conversation", fr: "Plafond de jetons par conversation" },
    preferences: { en: "My preferences (how I like to work)", fr: "Mes préférences (ma façon de travailler)" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    annuler: { en: "Close", fr: "Fermer" },
    enregistre: { en: "Settings saved.", fr: "Réglages enregistrés." },
    echec: { en: "The settings could not be saved.", fr: "Les réglages n'ont pas pu être enregistrés." },
} satisfies Record<string, Texte>;

export function ReglagesDuBuilder({ ouvert, onOuvertChange }: { ouvert: boolean; onOuvertChange: (ouvert: boolean) => void }) {
    const { t } = useLangue();
    const [lus, setLus] = useState<VueReglagesCerveau | null>(null);
    const [format, setFormat] = useState<"anthropic" | "openai">("anthropic");
    const [modele, setModele] = useState("");
    const [adresse, setAdresse] = useState("");
    const [cle, setCle] = useState("");
    const [plafondDepense, setPlafondDepense] = useState("2");
    const [plafondJetons, setPlafondJetons] = useState("1500000");
    const [preferences, setPreferences] = useState("");
    const [erreur, setErreur] = useState<string | null>(null);
    const [occupe, setOccupe] = useState(false);

    useEffect(() => {
        if (!ouvert) return;
        void (async () => {
            const [cerveau, prefs] = await Promise.all([lireLeCerveauApiV1BuilderCerveauGet(), lireLesPreferencesApiV1BuilderPreferencesGet()]);
            if (cerveau.data) {
                setLus(cerveau.data);
                setFormat(cerveau.data.format ?? "anthropic");
                setModele(cerveau.data.modele ?? "");
                setAdresse(cerveau.data.adresse ?? "");
                setPlafondDepense(String(cerveau.data.plafond_depense ?? 2));
                setPlafondJetons(String(cerveau.data.plafond_jetons ?? 1_500_000));
            }
            if (prefs.data) setPreferences(prefs.data.texte ?? "");
            setCle(""); // never filled in: the key is not readable
        })();
    }, [ouvert]);

    const enregistrer = async () => {
        setOccupe(true);
        setErreur(null);
        const reponse = await reglerLeCerveauApiV1BuilderCerveauPut({
            body: {
                ...(lus ?? {}),
                format,
                modele: modele.trim(),
                adresse: adresse.trim(),
                plafond_depense: Number(plafondDepense) || 0,
                plafond_jetons: Number(plafondJetons) || 1_500_000,
                cle: cle.trim() || null,
            } as never,
        });
        if (reponse.error) {
            setOccupe(false);
            setErreur(detailFromError(reponse.error, t(T.echec)));
            return;
        }
        await ecrireLesPreferencesApiV1BuilderPreferencesPut({ body: { texte: preferences } });
        setOccupe(false);
        setCle("");
        setLus(reponse.data ?? null);
        toast.success(t(T.enregistre));
    };

    return (
        <Dialog open={ouvert} onOpenChange={onOuvertChange}>
            <DialogContent className="sm:max-w-lg" data-modale="reglages-du-builder">
                <DialogHeader>
                    <DialogTitle>{t(T.titre)}</DialogTitle>
                    <DialogDescription>{t(T.description)}</DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div className="space-y-1">
                        <Label htmlFor="builder-format">{t(T.fournisseur)}</Label>
                        <select
                            id="builder-format"
                            className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                            value={format}
                            onChange={(e) => setFormat(e.target.value as "anthropic" | "openai")}
                        >
                            <option value="anthropic">{t(T.anthropic)}</option>
                            <option value="openai">{t(T.openai)}</option>
                        </select>
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="builder-modele">{t(T.modele)}</Label>
                        <Input id="builder-modele" value={modele} onChange={(e) => setModele(e.target.value)} />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="builder-adresse">{t(T.adresse)}</Label>
                        <Input id="builder-adresse" value={adresse} onChange={(e) => setAdresse(e.target.value)} />
                        <p className="text-xs text-muted-foreground">{t(T.adresseAide)}</p>
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="builder-cle">{t(T.cle)}</Label>
                        <Input
                            id="builder-cle"
                            type="password"
                            autoComplete="off"
                            value={cle}
                            onChange={(e) => setCle(e.target.value)}
                            placeholder={lus?.cle_posee ? "••••••••" : ""}
                        />
                        <p className="text-xs text-muted-foreground" data-cle-posee={lus?.cle_posee ? "oui" : "non"}>
                            {lus?.cle_posee ? t(T.clePosee) : t(T.cleAbsente)}
                        </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1">
                            <Label htmlFor="builder-plafond-depense">{t(T.plafondDepense)}</Label>
                            <Input id="builder-plafond-depense" inputMode="decimal" value={plafondDepense} onChange={(e) => setPlafondDepense(e.target.value)} />
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="builder-plafond-jetons">{t(T.plafondJetons)}</Label>
                            <Input id="builder-plafond-jetons" inputMode="numeric" value={plafondJetons} onChange={(e) => setPlafondJetons(e.target.value)} />
                        </div>
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="builder-preferences">{t(T.preferences)}</Label>
                        <Textarea id="builder-preferences" value={preferences} onChange={(e) => setPreferences(e.target.value)} className="min-h-20" />
                    </div>
                    {erreur && <p role="alert" className="text-sm text-destructive">{erreur}</p>}
                </div>
                <DialogFooter>
                    <Button type="button" variant="outline" onClick={() => onOuvertChange(false)}>{t(T.annuler)}</Button>
                    <Button type="button" disabled={occupe || !modele.trim()} onClick={() => void enregistrer()}>{t(T.enregistrer)}</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
