"use client";

import { History } from "lucide-react";
import { useState } from "react";

import type { BranchesVue } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";

/**
 * [.mark] Partie 3, SA-L3b (maquette `PanneauVersions`) : les branches, leurs versions immuables et les brouillons (un par personne
 * et par branche). Ouverte par « Toutes les versions » en bas du menu de la version. La maquette la loge dans le panneau de droite ;
 * le panneau unique n'existe pas encore dans le fork (sous-lot 19, L7) : elle prend la fenêtre à pied des autres écrans en attendant.
 * Fusionner, mettre à jour et comparer arrivent avec L3c.
 */
export function FenetreVersions({
    ouverte,
    fermer,
    vue,
    ouverteId,
    ouvrir,
    repartition,
}: {
    ouverte: boolean;
    fermer: () => void;
    vue: BranchesVue;
    /** La branche ouverte dans l'onglet (`null` : la principale). */
    ouverteId: number | null;
    ouvrir: (brancheId: number | null) => void;
    repartition: () => void;
}) {
    const { t } = useLangue();
    const courante = vue.branches.find((b) => (ouverteId === null ? b.principale : b.id === ouverteId)) ?? vue.branches[0];
    const [vueId, setVueId] = useState<number>(courante.id);
    const choisie = vue.branches.find((b) => b.id === vueId) ?? courante;
    const tous = vue.branches.flatMap((b) => b.brouillons.map((d) => ({ ...d, branche: b.nom })));
    return (
        <FenetreLarge
            ouverte={ouverte}
            fermer={fermer}
            titre={
                <span className="flex items-center gap-2">
                    <History className="size-4" /> {t({ en: "Versions", fr: "Versions" })}
                    <Info>
                        {t({
                            en: "A version is immutable: it keeps the flow, the prompts and the settings. Each person has their own draft on each branch.",
                            fr: "Une version est immuable : elle garde le graphe, les prompts et les réglages. Chaque personne a son brouillon par branche.",
                        })}
                    </Info>
                </span>
            }
            large={false}
            pied={
                <Button variant="outline" className="ml-auto" onClick={fermer}>
                    {t({ en: "Close", fr: "Fermer" })}
                </Button>
            }
        >
            <section>
                <div className="flex items-center pb-1">
                    <p className="flex-1 text-sm font-semibold">{t({ en: "Branches", fr: "Branches" })}</p>
                    <Button variant="ghost" size="sm" className="h-7 hover:font-semibold" onClick={repartition}>
                        {t({ en: "Traffic split", fr: "Répartition du trafic" })}
                    </Button>
                </div>
                <ul className="divide-y text-sm">
                    {vue.branches.map((b) => (
                        <li key={b.id} className="flex items-center gap-2 py-2">
                            <button
                                type="button"
                                onClick={() => setVueId(b.id)}
                                aria-pressed={b.id === choisie.id}
                                className={`flex-1 cursor-pointer text-left hover:font-semibold ${b.id === choisie.id ? "font-semibold" : ""}`}
                            >
                                <PointEtat etat={b.part > 0 ? "publie" : "brouillon"}>{b.nom}</PointEtat>
                                <span className="ml-2 text-xs text-muted-foreground">
                                    {b.part > 0 ? `${b.part} %` : t({ en: "no traffic", fr: "sans trafic" })}
                                    {b.protegee ? ` · ${t({ en: "protected", fr: "protégée" })}` : ""}
                                </span>
                            </button>
                            {b.id === courante.id ? (
                                <span className="text-xs text-muted-foreground">{t({ en: "Open", fr: "Ouverte" })}</span>
                            ) : (
                                <Button variant="outline" size="sm" className="h-7" onClick={() => ouvrir(b.principale ? null : b.id)}>
                                    {t({ en: "Open", fr: "Ouvrir" })}
                                </Button>
                            )}
                        </li>
                    ))}
                </ul>
            </section>

            <section>
                <p className="pb-1 text-sm font-semibold">
                    {t({ en: "Versions of", fr: "Versions de" })} « {choisie.nom} »
                </p>
                <ul className="divide-y text-sm">
                    {choisie.versions.map((v) => (
                        <li key={v.id} className="flex items-center gap-2 py-2.5">
                            <span className="font-semibold">v{v.numero}</span>
                            <span className="flex-1 text-muted-foreground">
                                <DateRelative valeur={v.publiee_le} />
                            </span>
                            {v.numero === choisie.version_en_ligne && (
                                <span className="text-xs text-muted-foreground">{t({ en: "live", fr: "en ligne" })}</span>
                            )}
                        </li>
                    ))}
                    {choisie.versions.length === 0 && (
                        <li className="py-3 text-muted-foreground">{t({ en: "No version published on this branch.", fr: "Aucune version publiée sur cette branche." })}</li>
                    )}
                </ul>
            </section>

            <section>
                <p className="pb-1 text-sm font-semibold">{t({ en: "Drafts", fr: "Brouillons" })}</p>
                <ul className="divide-y text-sm">
                    {tous.map((d) => (
                        <li key={d.id} className="flex items-center gap-2 py-2">
                            <span className="flex-1">
                                <span className="font-medium">{d.a_moi ? t({ en: "You", fr: "Vous" }) : t({ en: "Someone else", fr: "Une autre personne" })}</span>{" "}
                                {t({ en: "on", fr: "sur" })} {d.branche}
                            </span>
                            <span className="text-xs text-muted-foreground">v{d.numero}</span>
                        </li>
                    ))}
                    {tous.length === 0 && <li className="py-3 text-muted-foreground">{t({ en: "No draft.", fr: "Aucun brouillon." })}</li>}
                </ul>
            </section>
        </FenetreLarge>
    );
}
