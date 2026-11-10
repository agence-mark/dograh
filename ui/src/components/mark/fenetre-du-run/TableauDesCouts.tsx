"use client";

/**
 * [.mark] Partie 3, lot 14 (SE-18, G-1) : le tableau « Coûts d'un appel » de la maquette, en tête de l'onglet Coûts
 * (Cerveau, Transcription, Voix, Téléphonie, Total). Les identifiants et les cartes du fork restent dessous.
 * Les quantités viennent de la consommation enregistrée de l'appel ; le total n'existe que si l'organisation a une table
 * de prix (sinon la ligne le dit, jamais un chiffre inventé).
 */
import { useLangue } from "../langue/langue";
import { LigneNue } from "./FenetreDuRun";
import type { AnalyseDuRun } from "./types";

const somme = (lignes: object[] | undefined, cle: string) =>
    (lignes ?? []).reduce((s: number, l) => {
        const valeur = (l as Record<string, unknown>)[cle];
        return s + (typeof valeur === "number" ? valeur : 0);
    }, 0);

/** « 2 min 31 » : minutes et secondes, comme la maquette. */
export function dureeCourte(secondes: number, langue: "fr" | "en") {
    const s = Math.round(secondes);
    const m = Math.floor(s / 60);
    const reste = String(s % 60).padStart(2, "0");
    return m > 0 ? `${m} min ${reste}` : `${s} ${langue === "fr" ? "s" : "sec"}`;
}

const BRIQUES: Record<string, { en: string; fr: string }> = {
    llm: { en: "brain", fr: "cerveau" },
    stt: { en: "transcription", fr: "transcription" },
    tts: { en: "voice", fr: "voix" },
    telephony: { en: "telephony", fr: "téléphonie" },
};

/** Correctif écran point 10 : dit en clair quelles briques n'ont pas de prix, et où les saisir (la table de prix est un réglage d'organisation). */
export function PrixManquants({ sansPrix }: { sansPrix: { component: string; model: string }[] | undefined }) {
    const { t } = useLangue();
    const liste = (sansPrix ?? []).map((u) => `${u.model} (${BRIQUES[u.component] ? t(BRIQUES[u.component]) : u.component})`);
    return (
        <span className="mt-0.5 block text-muted-foreground" data-testid="prix-manquants">
            {liste.length > 0
                ? t({ en: `No price for: ${liste.join(", ")}.`, fr: `Pas de prix pour : ${liste.join(", ")}.` })
                : t({ en: "Some prices are missing.", fr: "Des prix manquent." })}{" "}
            {t({
                en: "Enter them in Settings > Organization > Run window: prices and thresholds.",
                fr: "À saisir dans Réglages › Organisation › Fenêtre d'appel : prix et seuils.",
            })}
        </span>
    );
}

export function TableauDesCouts({ analyse }: { analyse: AnalyseDuRun | null }) {
    const { t, langue } = useLangue();
    const f = analyse?.providers;
    const nombre = (n: number) => n.toLocaleString(langue === "fr" ? "fr-FR" : "en-US");
    const jetonsEntree = somme(f?.model?.usage, "prompt_tokens");
    const jetonsSortie = somme(f?.model?.usage, "completion_tokens");
    const secondesStt = somme(f?.transcription?.usage, "seconds");
    const caracteres = somme(f?.voice?.usage, "characters");
    const duree = f?.call_duration_secs ?? analyse?.summary?.duration_secs ?? null;
    const cout = analyse?.summary?.cost;
    const nonCapte = <span className="text-muted-foreground">{t({ en: "not captured", fr: "non capté" })}</span>;
    const capte = f?.status === "ok" || !!f;

    return (
        <section data-testid="tableau-des-couts">
            <p className="pb-1 text-base font-semibold">{t({ en: "Cost of a call", fr: "Coûts d'un appel" })}</p>
            <div className="divide-y divide-border">
                <LigneNue libelle={t({ en: "Brain", fr: "Cerveau" })}>
                    {capte
                        ? t({
                              en: `${nombre(jetonsEntree)} tokens in · ${nombre(jetonsSortie)} out`,
                              fr: `${nombre(jetonsEntree)} jetons en entrée · ${nombre(jetonsSortie)} en sortie`,
                          })
                        : nonCapte}
                </LigneNue>
                <LigneNue libelle={t({ en: "Transcription", fr: "Transcription" })}>{capte ? dureeCourte(secondesStt, langue) : nonCapte}</LigneNue>
                <LigneNue libelle={t({ en: "Voice", fr: "Voix" })}>
                    {capte ? t({ en: `${nombre(caracteres)} characters`, fr: `${nombre(caracteres)} caractères` }) : nonCapte}
                </LigneNue>
                <LigneNue libelle={t({ en: "Telephony", fr: "Téléphonie" })}>{duree ? dureeCourte(duree, langue) : nonCapte}</LigneNue>
                <LigneNue libelle={t({ en: "Total", fr: "Total" })} testId="cout-total">
                    {cout?.status === "ok" ? (
                        <>
                            <strong>
                                {cout.total?.toFixed(4)} {cout.currency}
                            </strong>
                            {cout.partial ? ` · ${t({ en: "partial", fr: "partiel" })}` : ""}
                            {cout.partial && <PrixManquants sansPrix={cout.unpriced} />}
                        </>
                    ) : (
                        <span className="text-muted-foreground">
                            {t({ en: "according to the organization's price table", fr: "selon la table de prix de l'organisation" })}
                        </span>
                    )}
                </LigneNue>
            </div>
        </section>
    );
}
