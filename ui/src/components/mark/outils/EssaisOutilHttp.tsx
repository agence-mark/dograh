"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 5.1) : le bloc « Essais » de l'écran d'un outil HTTP.
 * Nombre d'essais (0 à 2), attente entre deux essais, case « sans risque de doublon », et l'aperçu délai × essais
 * avec le tableau des quatre cas. Le délai de l'outil est le champ « Timeout » de l'écran d'origine, lu ici.
 * L'échec final passe par la règle « Un outil échoue » du thème Phrases de l'agent.
 */
import { Info, RefreshCw } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { type Texte, useLangue } from "../langue/langue";
import { ATTENTE_MAX_S, casRelances, delaiTotalS, ESSAIS_MAX, type EssaisOutil } from "./essais-outil";

const TEXTES = {
    titre: { en: "Retries", fr: "Essais" },
    intro: {
        en: "What the code does when the tool does not answer or the service is down.",
        fr: "Ce que fait le code quand l'outil ne répond pas ou que le service est en panne.",
    },
    reessayer: { en: "Retry", fr: "Réessayer" },
    fois: { en: "time(s)", fr: "fois" },
    apres: { en: "after", fr: "après" },
    secondes: { en: "s", fr: "s" },
    doublon: {
        en: "This tool can be called again without risk of a duplicate (a lookup, a search)",
        fr: "Cet outil peut être relancé sans risque de doublon (lecture, recherche)",
    },
    doublonAide: {
        en: "Unchecked (a tool that writes): called again only when the request never left (connection refused, unknown host).",
        fr: "Décoché (outil qui écrit) : relancé seulement si la requête n'est pas partie (connexion refusée, nom introuvable).",
    },
    apercu: { en: "Preview", fr: "Aperçu" },
    cas: { en: "Case", fr: "Cas" },
    relance: { en: "Called again?", fr: "Relancé ?" },
    pasPartie: {
        en: "The request did not leave (connection refused, unknown host)",
        fr: "La requête n'est pas partie (connexion refusée, nom introuvable)",
    },
    delai: { en: "No answer within the deadline", fr: "Pas de réponse dans le délai" },
    erreur5xx: { en: "Service error (5xx)", fr: "Erreur du service (5xx)" },
    refus4xx: {
        en: "Refusal (4xx) or an answer that says it failed",
        fr: "Refus du service (4xx) ou réponse qui dit un échec",
    },
    oui: { en: "yes", fr: "oui" },
    non: { en: "no", fr: "non" },
    jamais: { en: "never", fr: "jamais" },
    apresDernier: {
        en: "After the last attempt: the rule « A tool fails » of the agent's Phrases theme (sentence, note in the record, transfer).",
        fr: "Après le dernier essai : la règle « Un outil échoue » du thème Phrases de l'agent (phrase, note dans la fiche, transfert).",
    },
} satisfies Record<string, Texte>;

export const EssaisOutilHttp = ({
    valeur,
    onChange,
    timeoutMs,
}: {
    valeur: EssaisOutil;
    onChange: (suivant: EssaisOutil) => void;
    timeoutMs: number;
}) => {
    const { t } = useLangue();
    const cas = casRelances(valeur);
    const total = delaiTotalS(timeoutMs, valeur);
    const delai = (timeoutMs || 5000) / 1000;
    return (
        <Card data-bloc="essais-outil">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <RefreshCw className="h-4 w-4" />
                    {t(TEXTES.titre)}
                </CardTitle>
                <p className="text-sm text-muted-foreground">{t(TEXTES.intro)}</p>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Label htmlFor="outil_essais">{t(TEXTES.reessayer)}</Label>
                    <Select value={String(valeur.essais)} onValueChange={(v: string) => onChange({ ...valeur, essais: Number(v) })}>
                        <SelectTrigger id="outil_essais" className="w-20">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {Array.from({ length: ESSAIS_MAX + 1 }, (_, n) => (
                                <SelectItem key={n} value={String(n)}>
                                    {n}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <span>{t(TEXTES.fois)}</span>
                    {valeur.essais > 0 && (
                        <>
                            <span>{t(TEXTES.apres)}</span>
                            <Input
                                id="outil_attente_entre_essais"
                                aria-label={t({ en: "Wait between two attempts (s)", fr: "Attente entre deux essais (s)" })}
                                type="number"
                                className="h-9 w-20"
                                min={0}
                                max={ATTENTE_MAX_S}
                                step="0.5"
                                value={valeur.attente_entre_essais_s}
                                onChange={(e) => {
                                    const n = Number(e.target.value.replace(",", "."));
                                    if (Number.isFinite(n)) {
                                        onChange({ ...valeur, attente_entre_essais_s: Math.max(0, Math.min(ATTENTE_MAX_S, n)) });
                                    }
                                }}
                            />
                            <span>{t(TEXTES.secondes)}</span>
                        </>
                    )}
                </div>
                <div className="flex items-start gap-2 text-sm">
                    <Checkbox
                        id="outil_sans_risque_de_doublon"
                        className="mt-0.5"
                        checked={valeur.sans_risque_de_doublon}
                        onCheckedChange={(coche) => onChange({ ...valeur, sans_risque_de_doublon: coche === true })}
                    />
                    <div>
                        <Label htmlFor="outil_sans_risque_de_doublon" className="font-medium">
                            {t(TEXTES.doublon)}
                        </Label>
                        <p className="text-xs text-muted-foreground">{t(TEXTES.doublonAide)}</p>
                    </div>
                </div>
                <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-sm" data-apercu="essais-outil">
                    <p className="font-semibold">{t(TEXTES.apercu)}</p>
                    <p data-ligne="delai-total">
                        {valeur.essais === 0
                            ? t({
                                  en: `A single request, ${delai} s at most (the Timeout above).`,
                                  fr: `Une seule requête, ${delai} s au plus (le « Timeout » ci-dessus).`,
                              })
                            : t({
                                  en: `${delai} s × ${valeur.essais + 1} requests + ${valeur.attente_entre_essais_s} s × ${valeur.essais} wait(s) = ${total} s at most.`,
                                  fr: `${delai} s × ${valeur.essais + 1} requêtes + ${valeur.attente_entre_essais_s} s × ${valeur.essais} attente(s) = ${total} s au plus.`,
                              })}
                    </p>
                    <table className="w-full text-xs">
                        <thead className="text-left text-muted-foreground">
                            <tr>
                                <th className="py-1 pr-2">{t(TEXTES.cas)}</th>
                                <th className="py-1">{t(TEXTES.relance)}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {(
                                [
                                    ["pasPartie", cas.pasPartie],
                                    ["delai", cas.delai],
                                    ["erreur5xx", cas.erreur5xx],
                                    ["refus4xx", cas.refus4xx],
                                ] as const
                            ).map(([cle, relance]) => (
                                <tr key={cle} className="border-t" data-cas={cle}>
                                    <td className="py-1 pr-2">{t(TEXTES[cle])}</td>
                                    <td className="py-1">
                                        {cle === "refus4xx" ? t(TEXTES.jamais) : relance ? t(TEXTES.oui) : t(TEXTES.non)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span>{t(TEXTES.apresDernier)}</span>
                    </p>
                </div>
            </CardContent>
        </Card>
    );
};
