"use client";

/**
 * [.mark] Clôture, lot A (D22, D23) : les deux réglages de l'équipe qui se changent à l'écran, jamais en dur :
 *  - le message montré à la connexion d'un membre dont l'accès est bloqué (vide = le message par défaut, en deux langues) ;
 *  - la durée de garde du journal de l'équipe (12 mois par défaut, bornée par le serveur).
 * Chaque enregistrement dit son résultat par une notification (succès 4 s, échec qui reste).
 */
import { useEffect, useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { lireLesReglagesDeLEquipe, reglerLaDureeDuJournal, reglerLeMessageBloque, type ReglagesEquipe } from "./api-cloture";

const ECHEC: Texte = { fr: "Réglage non enregistré. Réessayez.", en: "Setting not saved. Try again." };

function useReglages() {
    const [reglages, setReglages] = useState<ReglagesEquipe | null>(null);
    useEffect(() => {
        lireLesReglagesDeLEquipe().then((res) => {
            if (res.data) setReglages(res.data);
        });
    }, []);
    return [reglages, setReglages] as const;
}

export function ReglageMessageBloque() {
    const { t } = useLangue();
    const [reglages, setReglages] = useReglages();
    const [fr, setFr] = useState<string | null>(null);
    const [en, setEn] = useState<string | null>(null);
    if (!reglages) return null;
    const defaut = reglages.message_acces_bloque.defaut;
    const valeurFr = fr ?? reglages.message_acces_bloque.fr;
    const valeurEn = en ?? reglages.message_acces_bloque.en;
    const enregistrer = async () => {
        const res = await reglerLeMessageBloque(valeurFr, valeurEn);
        if (res.error || !res.data) return notifier.echec(ECHEC, { erreur: res.error });
        setReglages(res.data);
        setFr(null);
        setEn(null);
        notifier.succes({ fr: "Message d'accès bloqué enregistré.", en: "Blocked-access message saved." });
    };
    return (
        <section className="mt-6 space-y-3" data-testid="message-acces-bloque">
            <h3 className="text-sm font-medium">{t({ en: "Message shown to a blocked member", fr: "Message montré à un membre bloqué" })}</h3>
            <p className="text-muted-foreground text-xs">
                {t({
                    en: "Shown at sign-in when a member's access is off. Empty: the default message.",
                    fr: "Montré à la connexion quand l'accès d'un membre est coupé. Vide : le message par défaut.",
                })}
            </p>
            <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                    <Label htmlFor="message-bloque-fr">{t({ en: "French", fr: "Français" })}</Label>
                    <Input id="message-bloque-fr" value={valeurFr} placeholder={defaut.fr} maxLength={300} onChange={(e) => setFr(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="message-bloque-en">{t({ en: "English", fr: "Anglais" })}</Label>
                    <Input id="message-bloque-en" value={valeurEn} placeholder={defaut.en} maxLength={300} onChange={(e) => setEn(e.target.value)} />
                </div>
            </div>
            <Button size="sm" variant="outline" onClick={enregistrer} disabled={fr === null && en === null}>
                {t({ en: "Save", fr: "Enregistrer" })}
            </Button>
        </section>
    );
}

export function ReglageDureeDuJournal() {
    const { t } = useLangue();
    const [reglages, setReglages] = useReglages();
    const [saisie, setSaisie] = useState<string | null>(null);
    if (!reglages) return null;
    const valeur = saisie ?? String(reglages.journal_mois);
    const mois = Number(valeur);
    const hors = !Number.isInteger(mois) || mois < reglages.journal_mois_min || mois > reglages.journal_mois_max;
    const enregistrer = async () => {
        const res = await reglerLaDureeDuJournal(mois);
        if (res.error || !res.data) return notifier.echec(ECHEC, { erreur: res.error });
        setReglages(res.data);
        setSaisie(null);
        notifier.succes({ fr: "Durée de garde du journal enregistrée.", en: "Journal retention saved." });
    };
    return (
        <div className="mb-4 flex flex-wrap items-end gap-2" data-testid="duree-du-journal">
            <div className="space-y-1">
                <Label htmlFor="duree-journal">{t({ en: "Kept for (months)", fr: "Gardé (mois)" })}</Label>
                <Input
                    id="duree-journal"
                    type="number"
                    className="w-28"
                    min={reglages.journal_mois_min}
                    max={reglages.journal_mois_max}
                    value={valeur}
                    aria-invalid={hors}
                    onChange={(e) => setSaisie(e.target.value)}
                />
            </div>
            <Button size="sm" variant="outline" onClick={enregistrer} disabled={saisie === null || hors}>
                {t({ en: "Save", fr: "Enregistrer" })}
            </Button>
            {hors && (
                <p role="alert" className="text-xs text-(--marque-danger-texte)">
                    {t({
                        en: `Between ${reglages.journal_mois_min} and ${reglages.journal_mois_max} months.`,
                        fr: `Entre ${reglages.journal_mois_min} et ${reglages.journal_mois_max} mois.`,
                    })}
                </p>
            )}
        </div>
    );
}
