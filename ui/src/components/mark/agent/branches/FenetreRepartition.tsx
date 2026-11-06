"use client";

import { useState } from "react";

import { reglerLaRepartitionApiV1BuilderBranchesWorkflowIdRepartitionPut } from "@/client/sdk.gen";
import type { BranchesVue } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Curseur } from "@/components/ui/curseur";

/**
 * [.mark] Partie 3, SA-L3b (05 § 9 et § 12, maquette `FenetreRepartition`) : la répartition du trafic ENTRE BRANCHES, le seul
 * mécanisme de part des appels (le déploiement progressif en positions 10, 25, 50 est remplacé par un curseur de 1 à 99).
 * Chaque branche autre que la principale a son curseur (0 : aucun appel) ; la principale garde le reste, le total fait donc
 * toujours 100. Un appelant reste sur sa branche d'un appel à l'autre.
 */
export const MAX_BRANCHE = 99;

/** Les parts de l'écran vers celles du serveur : la principale prend le reste. */
export function partsAEnvoyer(vue: BranchesVue, parts: Record<number, number>): Record<number, number> {
    const resultat: Record<number, number> = {};
    let autres = 0;
    for (const b of vue.branches) {
        if (b.principale) continue;
        resultat[b.id] = parts[b.id] ?? 0;
        autres += resultat[b.id];
    }
    const principale = vue.branches.find((b) => b.principale);
    if (principale) resultat[principale.id] = 100 - autres;
    return resultat;
}

/** Pose une part en gardant au moins 1 % à la principale : la somme des autres branches ne dépasse jamais 99. */
export function poser(parts: Record<number, number>, id: number, valeur: number): Record<number, number> {
    const autres = Object.entries(parts).reduce((s, [k, v]) => (Number(k) === id ? s : s + v), 0);
    return { ...parts, [id]: Math.max(0, Math.min(Math.round(valeur), MAX_BRANCHE - autres)) };
}

export function FenetreRepartition({
    agentId,
    ouverte,
    fermer,
    vue,
    apres,
}: {
    agentId: number;
    ouverte: boolean;
    fermer: () => void;
    vue: BranchesVue;
    apres: () => void;
}) {
    const { t } = useLangue();
    const autres = vue.branches.filter((b) => !b.principale);
    const principale = vue.branches.find((b) => b.principale);
    const [parts, setParts] = useState<Record<number, number>>(() => Object.fromEntries(autres.map((b) => [b.id, b.part])));
    const somme = autres.reduce((s, b) => s + (parts[b.id] ?? 0), 0);
    const reste = 100 - somme;
    const eteinte = !vue.repartition_active;
    return (
        <FenetreChamps
            ouverte={ouverte}
            fermer={fermer}
            titre={t({ en: "Traffic split", fr: "Répartition du trafic" })}
            info={t({
                en: "Give a share of the calls to a branch, compare, then merge. A caller stays on the same branch from one call to the next. The total is always 100%: the main branch keeps the rest.",
                fr: "Donnez une part des appels à une branche, comparez, puis fusionnez. Un appelant reste sur la même branche d'un appel à l'autre. Le total fait toujours 100 % : la principale garde le reste.",
            })}
            valider={t({ en: "Apply", fr: "Appliquer" })}
            sections={[]}
            corps={
                <div className="space-y-5">
                    {eteinte && (
                        <p role="status" className="text-sm text-muted-foreground">
                            {t({
                                en: "The traffic split is off for this agent: turn it on in Settings > Publication to give a branch some calls.",
                                fr: "La répartition est éteinte pour cet agent : allumez-la dans Réglages > Publication pour donner des appels à une branche.",
                            })}
                        </p>
                    )}
                    {autres.length === 0 && (
                        <p className="text-sm text-muted-foreground">
                            {t({ en: "No other branch yet: every call goes to the main branch.", fr: "Aucune autre branche : tous les appels vont à la principale." })}
                        </p>
                    )}
                    <ul className="space-y-5">
                        {autres.map((b) => (
                            <li key={b.id} className="space-y-1.5">
                                <div className="flex items-center gap-2 text-sm">
                                    <label htmlFor={`part-${b.id}`} className="flex-1 font-medium">
                                        {b.nom}
                                    </label>
                                    <span className="w-24 text-right tabular-nums" data-part={b.id}>
                                        {(parts[b.id] ?? 0) > 0 ? `${parts[b.id]} %` : t({ en: "No calls", fr: "Aucun appel" })}
                                    </span>
                                </div>
                                <Curseur
                                    id={`part-${b.id}`}
                                    min={0}
                                    max={MAX_BRANCHE}
                                    step={1}
                                    value={parts[b.id] ?? 0}
                                    disabled={eteinte}
                                    onChange={(e) => setParts((p) => poser(p, b.id, Number(e.target.value)))}
                                    aria-valuetext={`${parts[b.id] ?? 0} %`}
                                    className="w-full"
                                />
                            </li>
                        ))}
                    </ul>
                    <div className="flex items-center gap-3 border-t pt-3 text-sm">
                        <span className="flex-1 font-medium">{principale?.nom ?? t({ en: "Main", fr: "Principale" })}</span>
                        <span className="tabular-nums" data-part-principale>
                            {reste} %
                        </span>
                    </div>
                    <p className="text-xs text-muted-foreground tabular-nums">{t({ en: "Total", fr: "Total" })} 100 %</p>
                </div>
            }
            onValider={async () => {
                const r = await reglerLaRepartitionApiV1BuilderBranchesWorkflowIdRepartitionPut({
                    path: { workflow_id: agentId },
                    body: { parts: partsAEnvoyer(vue, parts) },
                });
                if (r.error) {
                    notifier.echec({ fr: "Répartition refusée. Relisez les parts.", en: "Split refused. Check the shares." }, { erreur: r.error });
                    return false;
                }
                notifier.succes({ fr: "Répartition enregistrée. Les appelants déjà servis gardent leur branche.", en: "Split saved. Callers already served keep their branch." });
                apres();
                return true;
            }}
        />
    );
}
