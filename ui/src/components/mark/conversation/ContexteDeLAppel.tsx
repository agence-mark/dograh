"use client";

/**
 * [.mark] Correctifs écran 11 et 12 : l'onglet « Contexte » d'un appel, en trois parties lisibles (plus de JSON) :
 *  - Contexte initial : ce que le code a posé au décrochage (établissement, date, état d'ouverture, horaires…), dit en français ;
 *  - Contexte recueilli : les champs de la fiche de l'agent, dans l'ordre de la fiche (lus dans l'analyse du run) ; sans fiche lue, les
 *    clés du contexte qui ne sont pas techniques ;
 *  - Identifiants : agent, version, appel, commit.
 * Les horaires gardent leurs retours à la ligne (`whitespace-pre-line`). Le JSON complet reste derrière « Copier ». Aucun objet n'est
 * rendu tel quel : tout passe par `valeurEnClair`.
 */
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { copyTextToClipboard } from "@/lib/clipboard";

import { LigneNue } from "../fenetre-du-run/FenetreDuRun";
import type { AnalyseDuRun } from "../fenetre-du-run/types";
import { type Texte, useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { NOMS_RESERVES } from "../SectionFiche";
import { lireUnCode } from "./issue";
import { valeurEnClair } from "./valeur-en-clair";

type Contexte = Record<string, unknown> | null | undefined;

/** Les infos utiles du contexte initial, dans l'ordre où elles se disent. */
const LIBELLES_INITIAL: [string, Texte][] = [
    ["etablissement", { en: "Site", fr: "Établissement" }],
    ["adresse_etablissement", { en: "Address", fr: "Adresse" }],
    ["date_appel", { en: "Date of the call", fr: "Date de l'appel" }],
    ["heure_appel", { en: "Time of the call", fr: "Heure de l'appel" }],
    ["etat_ouverture", { en: "State at pick-up", fr: "État à l'appel" }],
    ["reouverture", { en: "Reopening", fr: "Réouverture" }],
    ["horaires_ouverture", { en: "Opening hours", fr: "Horaires" }],
    ["caller_number", { en: "Caller number", fr: "Numéro de l'appelant" }],
    ["called_number", { en: "Number called", fr: "Numéro appelé" }],
    ["direction", { en: "Direction", fr: "Sens de l'appel" }],
];
const ETATS: Record<string, Texte> = {
    OUVERT: { en: "Open", fr: "Ouvert" },
    FERME: { en: "Closed", fr: "Fermé" },
    PAUSE: { en: "Break", fr: "Pause" },
    SUR_RENDEZ_VOUS: { en: "By appointment", fr: "Sur rendez-vous" },
};
const SENS: Record<string, Texte> = {
    inbound: { en: "Incoming", fr: "Entrant" },
    outbound: { en: "Outgoing", fr: "Sortant" },
};
/** Ce que le serveur pose et que personne n'a à lire ici : l'annonce dite (déjà dans la transcription) et les clés techniques. */
const MASQUEES = new Set(["annonce_ouverture", "annonce_pause", "annonce_fermeture"]);

export type LigneDeContexte = { cle: string; libelle: string; valeur: string; multiligne?: boolean };

/** Le contexte initial en lignes lisibles : les infos connues d'abord, puis les variables propres à l'agent ; les clés techniques sont écartées. */
export function lignesDuContexteInitial(contexte: Contexte, t: (x: Texte) => string, oui_non: readonly [string, string]): LigneDeContexte[] {
    if (!contexte) return [];
    const connues = new Set(LIBELLES_INITIAL.map(([cle]) => cle));
    const lignes: LigneDeContexte[] = [];
    for (const [cle, libelle] of LIBELLES_INITIAL) {
        const brut = contexte[cle];
        let valeur = valeurEnClair(brut, oui_non);
        if (!valeur) continue;
        if (cle === "etat_ouverture" && ETATS[valeur.toUpperCase()]) valeur = t(ETATS[valeur.toUpperCase()]);
        if (cle === "direction" && SENS[valeur.toLowerCase()]) valeur = t(SENS[valeur.toLowerCase()]);
        lignes.push({ cle, libelle: t(libelle), valeur, multiligne: cle === "horaires_ouverture" || valeur.includes("\n") });
    }
    for (const [cle, brut] of Object.entries(contexte)) {
        if (connues.has(cle) || MASQUEES.has(cle) || NOMS_RESERVES.includes(cle)) continue;
        const valeur = valeurEnClair(brut, oui_non);
        if (valeur) lignes.push({ cle, libelle: lireUnCode(cle), valeur, multiligne: valeur.includes("\n") });
    }
    return lignes;
}

/** Le contexte recueilli : les champs de la fiche dans l'ordre de la fiche (vides dits « non renseigné ») ; sans fiche lue, le contexte filtré. */
export function lignesDuContexteRecueilli(
    contexte: Contexte,
    analyse: AnalyseDuRun | null,
    oui_non: readonly [string, string],
): { lignes: LigneDeContexte[]; vides: string[] } {
    const champs = analyse?.record?.status === "ok" ? (analyse.record.fields ?? []) : [];
    if (champs.length > 0) {
        const lignes: LigneDeContexte[] = [];
        const vides: string[] = [];
        for (const c of champs) {
            const valeur = c.empty ? "" : valeurEnClair(c.value, oui_non);
            if (valeur) lignes.push({ cle: c.name, libelle: lireUnCode(c.name), valeur, multiligne: valeur.includes("\n") });
            else vides.push(lireUnCode(c.name));
        }
        return { lignes, vides };
    }
    const lignes: LigneDeContexte[] = [];
    for (const [cle, brut] of Object.entries(contexte ?? {})) {
        if (NOMS_RESERVES.includes(cle)) continue;
        const valeur = valeurEnClair(brut, oui_non);
        if (valeur) lignes.push({ cle, libelle: lireUnCode(cle), valeur, multiligne: valeur.includes("\n") });
    }
    return { lignes, vides: [] };
}

function BoutonCopier({ json }: { json: unknown }) {
    const { t } = useLangue();
    const [copie, setCopie] = useState(false);
    const copier = async () => {
        try {
            await copyTextToClipboard(JSON.stringify(json ?? {}, null, 2));
            setCopie(true);
            setTimeout(() => setCopie(false), 2000);
        } catch {
            notifier.echec({ fr: "Copie impossible.", en: "Could not copy." });
        }
    };
    return (
        <Button variant="ghost" size="sm" onClick={copier} className="cursor-pointer gap-2" data-testid="copier-json-contexte">
            {copie ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copie ? t({ en: "Copied", fr: "Copié" }) : t({ en: "Copy as JSON", fr: "Copier le JSON" })}
        </Button>
    );
}

function Partie({ titre, json, testId, children }: { titre: string; json?: unknown; testId: string; children: React.ReactNode }) {
    return (
        <section data-testid={testId}>
            <div className="flex min-h-9 items-center justify-between pb-1">
                <p className="text-base font-semibold">{titre}</p>
                {json !== undefined && json !== null && Object.keys(json as object).length > 0 && <BoutonCopier json={json} />}
            </div>
            {children}
        </section>
    );
}

const Lignes = ({ lignes }: { lignes: LigneDeContexte[] }) => (
    <div className="divide-y divide-border">
        {lignes.map((l) => (
            <LigneNue key={l.cle} libelle={l.libelle} testId="ligne-de-contexte">
                <span className={l.multiligne ? "whitespace-pre-line break-words" : "break-words"}>{l.valeur}</span>
            </LigneNue>
        ))}
    </div>
);

export function ContexteDeLAppel({
    initial,
    recueilli,
    analyse,
    idAgent,
    idAppel,
    versionAgent,
}: {
    initial: Contexte;
    recueilli: Contexte;
    analyse: AnalyseDuRun | null;
    idAgent: string;
    idAppel: string;
    versionAgent: number | null;
}) {
    const { t } = useLangue();
    const ouiNon = [t({ en: "yes", fr: "oui" }), t({ en: "no", fr: "non" })] as const;
    const lignesInitial = lignesDuContexteInitial(initial, t, ouiNon);
    const { lignes: lignesRecueilli, vides } = lignesDuContexteRecueilli(recueilli, analyse, ouiNon);
    const commit = analyse?.summary?.version?.commit ?? null;
    const aucune = <p className="py-3 text-sm text-muted-foreground">{t({ en: "No data", fr: "Aucune donnée" })}</p>;
    return (
        <div className="space-y-8" data-onglet-contexte-en-clair>
            <Partie titre={t({ en: "Initial context", fr: "Contexte initial" })} json={initial} testId="contexte-initial">
                {lignesInitial.length === 0 ? aucune : <Lignes lignes={lignesInitial} />}
            </Partie>
            <Partie titre={t({ en: "Gathered context", fr: "Contexte recueilli" })} json={recueilli} testId="contexte-recueilli">
                {lignesRecueilli.length === 0 && vides.length === 0 ? aucune : <Lignes lignes={lignesRecueilli} />}
                {vides.length > 0 && (
                    <p className="py-2 text-sm text-muted-foreground" data-testid="champs-non-renseignes">
                        {t({ en: "Not filled in: ", fr: "Non renseigné : " })}
                        {vides.join(", ")}
                    </p>
                )}
            </Partie>
            <Partie titre={t({ en: "Identifiers", fr: "Identifiants" })} testId="contexte-identifiants">
                <div className="divide-y divide-border">
                    <LigneNue libelle={t({ en: "Agent", fr: "Agent" })}>{idAgent}</LigneNue>
                    <LigneNue libelle={t({ en: "Version", fr: "Version" })}>{versionAgent != null ? `v${versionAgent}` : "–"}</LigneNue>
                    <LigneNue libelle={t({ en: "Call", fr: "Appel" })}>{idAppel}</LigneNue>
                    <LigneNue libelle={t({ en: "Deployed commit", fr: "Commit déployé" })}>
                        <code>{commit ? commit.slice(0, 8) : "–"}</code>
                    </LigneNue>
                </div>
            </Partie>
        </div>
    );
}
