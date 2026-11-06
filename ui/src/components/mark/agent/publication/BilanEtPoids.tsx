"use client";

/**
 * [.mark] Lot « façon Tala par motif » (T2 et T3) : les deux sections de la fenêtre « Publier » qui suivent « Prêt à publier ».
 *
 * - « Bilan de santé du prompt » : une ligne par défaut de rédaction (K1 à K4) avec l'étape, l'extrait, un bouton qui mène à l'étape
 *   et « Ignorer pour cette version » (écrit au journal par le serveur, rangé pour la version par cet écran) ;
 * - « Poids de l'agent » (K5) : une ligne par étape, du plus lourd au plus léger, une jauge avec le trait du seuil s'il existe.
 *   Le poids informe, il ne bloque jamais ; sans seuil réglé (Réglages › Briques) on ne montre que les nombres.
 *
 * Forme de la maquette du lot (`components/studio/avant-publier.tsx`), les données viennent du serveur. Tout texte en {en, fr}.
 */
import { useState } from "react";

import { ignorerUnDefautApiV1BuilderPublicationWorkflowIdIgnorerUnDefautPost } from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Section } from "@/components/mark/studio/fenetre-onglets";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";

import type { DefautDuPrompt, PoidsDeLAgent } from "./types";

/** Le titre court de chaque défaut, et ce que le bouton propose (toujours : aller à l'étape, c'est là qu'on corrige). */
export const DEFAUTS: Record<string, { titre: Texte; info: Texte; bouton: Texte }> = {
    valeur_en_dur: {
        titre: { en: "Value written in the prompt", fr: "Valeur écrite en dur" },
        info: {
            en: "An amount, a figure delay or a first name given as an example. A value that changes belongs in a variable or an object, or the model copies it.",
            fr: "Un montant, un délai chiffré ou un prénom donné en exemple. Une valeur qui change va dans une variable ou un objet, sinon le modèle la recopie.",
        },
        bouton: { en: "Open the step", fr: "Ouvrir l'étape" },
    },
    verbe_ecran: {
        titre: { en: "Screen verb in a voice prompt", fr: "Verbe d'écran dans un prompt vocal" },
        info: {
            en: "« Display », « click », « on the screen »: the caller on the phone has no screen.",
            fr: "« Afficher », « cliquer », « à l'écran » : la personne au téléphone n'a pas d'écran.",
        },
        bouton: { en: "Open the step", fr: "Ouvrir l'étape" },
    },
    action_sans_outil: {
        titre: { en: "Action promised without a tool", fr: "Action promise sans outil" },
        info: {
            en: "The step says « save », « book », « cancel », « send » but carries no tool that writes: the model would say it did it.",
            fr: "L'étape dit « enregistrer », « réserver », « annuler », « envoyer » mais ne porte aucun outil qui écrit : le modèle dirait l'avoir fait.",
        },
        bouton: { en: "Add a tool", fr: "Poser un outil" },
    },
    sortie_non_citee: {
        titre: { en: "Exit the step does not name", fr: "Sortie que l'étape ne cite pas" },
        info: {
            en: "The step has two work exits or more but its text names none of the steps it leads to.",
            fr: "L'étape a deux sorties de travail ou plus mais son texte ne cite aucune des étapes visées.",
        },
        bouton: { en: "Open the step", fr: "Ouvrir l'étape" },
    },
};

/** Les défauts rangés « pour cette version » : gardés dans ce navigateur (confort), jamais ailleurs. */
const cleDeRangement = (agentId: number, version: number | null) => `mark.publication.ignores.${agentId}.${version ?? "brouillon"}`;
const empreinte = (d: DefautDuPrompt) => `${d.code}|${d.etape ?? ""}|${d.extrait ?? ""}`;

const lireLesIgnores = (agentId: number, version: number | null): string[] => {
    try {
        const brut = window.localStorage.getItem(cleDeRangement(agentId, version));
        const lu = brut ? (JSON.parse(brut) as unknown) : [];
        return Array.isArray(lu) ? lu.filter((x): x is string => typeof x === "string") : [];
    } catch {
        return [];
    }
};
const garderLesIgnores = (agentId: number, version: number | null, valeurs: string[]) => {
    try {
        window.localStorage.setItem(cleDeRangement(agentId, version), JSON.stringify(valeurs));
    } catch {
        /* rien : le confort ne casse jamais l'écran */
    }
};

export function BilanDeSante({
    agentId,
    version,
    defauts,
    ouvrirEtape,
}: {
    agentId: number;
    version: number | null;
    defauts: DefautDuPrompt[];
    /** Ferme la fenêtre puis mène à l'étape (ou, sans étape connue, au parcours). */
    ouvrirEtape: (noeudId: string | null) => void;
}) {
    const { t } = useLangue();
    const [ignores, setIgnores] = useState<string[]>(() => lireLesIgnores(agentId, version));
    const visibles = defauts.filter((d) => !ignores.includes(empreinte(d)));
    if (visibles.length === 0) return null;

    const ignorer = async (d: DefautDuPrompt) => {
        const r = await ignorerUnDefautApiV1BuilderPublicationWorkflowIdIgnorerUnDefautPost({
            path: { workflow_id: agentId },
            body: { code: d.code as never, etape: d.etape ?? null, extrait: d.extrait ?? null, version },
        });
        if (r.error) {
            notifier.echec({ fr: "Impossible de mettre ce point de côté. Réessayez.", en: "Could not set this point aside. Try again." }, { erreur: r.error });
            return;
        }
        const suite = [...ignores, empreinte(d)];
        setIgnores(suite);
        garderLesIgnores(agentId, version, suite);
        notifier.succes({ fr: "Point ignoré pour cette version, écrit au journal.", en: "Point ignored for this version, written to the journal." });
    };

    return (
        <div id="pret-sante" data-section="bilan-de-sante">
            <Section
                titre={t({ en: "Prompt health check", fr: "Bilan de santé du prompt" })}
                info={t({
                    en: "The faults the code finds in the prompts and the path of the draft, one per line, with the step that carries it. Each check is switched on, off or set to block in Settings › Publication › Writing checks.",
                    fr: "Les défauts relevés par le code dans les prompts et le parcours du brouillon, un par ligne, avec l'étape qui le porte. Chaque contrôle s'allume, s'éteint ou bloque dans Réglages › Publication › Contrôles de rédaction.",
                })}
            >
                <ul className="divide-y">
                    {visibles.map((d) => {
                        const texte = DEFAUTS[d.code];
                        if (!texte) return null;
                        const bloque = d.statut === "echec";
                        return (
                            <li key={empreinte(d)} data-defaut={d.code} className="flex items-start gap-3 py-3 text-sm">
                                <div className="min-w-0 flex-1">
                                    {d.etape && (
                                        <span className="block pb-1 text-xs text-muted-foreground">
                                            {t({ en: "Step", fr: "Étape" })} « {d.etape} »
                                        </span>
                                    )}
                                    <span className="inline-flex items-center gap-1.5 font-medium">
                                        {t(texte.titre)}
                                        <Info>{t(texte.info)}</Info>
                                    </span>
                                    {d.extrait && <span className="block pt-1 text-xs text-muted-foreground">« … {d.extrait} … »</span>}
                                </div>
                                <div className="flex shrink-0 flex-col items-end gap-1">
                                    <span className="pb-1 text-xs text-muted-foreground">{bloque ? t({ en: "blocks", fr: "bloque" }) : t({ en: "warns", fr: "prévient" })}</span>
                                    <Button size="sm" onClick={() => ouvrirEtape(d.noeud_id ?? null)}>
                                        {t(texte.bouton)}
                                    </Button>
                                    {!bloque && (
                                        <Button size="sm" variant="ghost" onClick={() => void ignorer(d)}>
                                            {t({ en: "Ignore for this version", fr: "Ignorer pour cette version" })}
                                        </Button>
                                    )}
                                </div>
                            </li>
                        );
                    })}
                </ul>
            </Section>
        </div>
    );
}

export function PoidsDeLAgentSection({ poids, regler, ouvrirEtape }: { poids: PoidsDeLAgent; regler: () => void; ouvrirEtape: (noeudId: string | null) => void }) {
    const { t, langue } = useLangue();
    if (!poids.actif || poids.etapes.length === 0) return null;
    const f = (n: number) => n.toLocaleString(langue === "fr" ? "fr-FR" : "en-US");
    const seuil = poids.poids_max;
    const echelle = Math.max(seuil ?? 0, ...poids.etapes.map((e) => e.total), 1);
    return (
        <div id="pret-poids" data-section="poids-de-l-agent">
            <Section
                titre={t({ en: "Agent weight", fr: "Poids de l'agent" })}
                info={t({
                    en: "What the brain reads at each reply: the general prompt, the prompt of the current step and the conditions of its exits (the call history comes on top). The longer it is, the more a small model risks forgetting a rule or missing a transition. The threshold is set with the brain, in Settings › Services; it warns, it never blocks.",
                    fr: "Ce que le cerveau lit à chaque réplique : le prompt général, le prompt de l'étape en cours et les conditions de ses sorties (l'historique de l'appel vient en plus). Plus c'est long, plus un petit modèle risque d'oublier une règle ou de rater un passage. Le seuil se règle avec le cerveau, dans Réglages › Briques ; il prévient, il ne bloque jamais.",
                })}
            >
                <p className="flex items-center gap-1.5 pb-2 text-xs text-muted-foreground" data-poids="seuil">
                    {seuil
                        ? t({ en: `Threshold of ${f(seuil)} characters, set with the brain`, fr: `Seuil de ${f(seuil)} caractères, réglé avec le cerveau` })
                        : t({ en: "No threshold set for this brain: the number of characters alone", fr: "Aucun seuil réglé pour ce cerveau : le nombre de caractères seul" })}
                    <Info>
                        {seuil
                            ? t({
                                  en: "Value set in Settings › Services › Size the brain handles. Above it the line turns « to read again »; publishing stays possible.",
                                  fr: "Valeur réglée dans Réglages › Briques › Taille supportée par le cerveau. Au-delà, la ligne passe en « à relire » ; la publication reste possible.",
                              })
                            : t({
                                  en: "Providers do not publish a threshold. It is measured on the bench, then set in Settings › Services › Size the brain handles; meanwhile, comparing the steps with each other is enough to spot the heaviest.",
                                  fr: "Les fournisseurs ne publient pas de seuil. Il se mesure au banc puis se règle dans Réglages › Briques › Taille supportée par le cerveau ; en attendant, comparer les étapes entre elles suffit à repérer la plus lourde.",
                              })}
                    </Info>
                </p>
                <table className="w-full text-sm" data-tableau="poids">
                    <thead>
                        <tr className="text-xs text-muted-foreground">
                            <th className="py-2 text-left font-normal">{t({ en: "Step", fr: "Étape" })}</th>
                            <th className="py-2 text-right font-normal">{t({ en: "General", fr: "Général" })}</th>
                            <th className="py-2 text-right font-normal">{t({ en: "Step", fr: "Étape" })}</th>
                            <th className="py-2 text-right font-normal">{t({ en: "Conditions", fr: "Conditions" })}</th>
                            <th className="py-2 text-right font-normal">{t({ en: "Per reply", fr: "Par réplique" })}</th>
                            <th className="w-[28%] py-2 pl-4 text-left font-normal">{t({ en: "Gauge", fr: "Jauge" })}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y border-t">
                        {poids.etapes.map((e) => {
                            const au = seuil !== null && e.total > seuil;
                            return (
                                <tr key={e.noeud_id} data-etape-poids={e.noeud_id} data-au-dessus={au ? "oui" : "non"}>
                                    <td className="py-2.5 pr-3">
                                        <button type="button" className="cursor-pointer text-left hover:font-semibold" onClick={() => ouvrirEtape(e.noeud_id)}>
                                            {e.etape}
                                        </button>
                                    </td>
                                    <td className="py-2.5 text-right text-muted-foreground tabular-nums">{f(e.general)}</td>
                                    <td className="py-2.5 text-right text-muted-foreground tabular-nums">{f(e.texte)}</td>
                                    <td className="py-2.5 text-right text-muted-foreground tabular-nums">
                                        {f(e.conditions)}
                                        <span className="text-xs"> · {e.nb_conditions}</span>
                                    </td>
                                    <td className={`py-2.5 text-right tabular-nums ${au ? "font-semibold text-destructive" : "font-medium"}`}>{f(e.total)}</td>
                                    <td className="py-2.5 pl-4">
                                        <div
                                            className="relative h-1.5 w-full rounded-full bg-muted"
                                            role="img"
                                            aria-label={t({
                                                en: `${f(e.total)} characters${seuil ? ` of ${f(seuil)}` : ""}`,
                                                fr: `${f(e.total)} caractères${seuil ? ` sur ${f(seuil)}` : ""}`,
                                            })}
                                        >
                                            <div className={`h-full rounded-full ${au ? "bg-destructive" : "bg-foreground/70"}`} style={{ width: `${Math.round((e.total / echelle) * 100)}%` }} />
                                            {seuil !== null && <div className="absolute -top-1 h-3.5 w-px bg-foreground" style={{ left: `${Math.round((seuil / echelle) * 100)}%` }} />}
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
                <div className="flex justify-end pt-2">
                    <Button size="sm" variant="ghost" onClick={regler}>
                        {seuil ? t({ en: "Change the threshold", fr: "Régler le seuil" }) : t({ en: "Set a threshold", fr: "Régler un seuil" })}
                    </Button>
                </div>
            </Section>
        </div>
    );
}
