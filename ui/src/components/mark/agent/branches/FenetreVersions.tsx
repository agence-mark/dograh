"use client";

import { changerLaProtection } from "@/components/mark/equipe/api-cloture";
import { GitMerge, History, Lock, Undo2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
    epinglerLaPrincipaleApiV1BuilderBranchesWorkflowIdPrincipaleVersionPut,
    protegerLaPrincipaleApiV1BuilderBranchesWorkflowIdPrincipaleProtectionPut,
} from "@/client/sdk.gen";
import type { BranchesVue } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";

/**
 * [.mark] Partie 3, SA-L3b (maquette `PanneauVersions`) : les branches, leurs versions immuables et les brouillons (un par personne
 * et par branche). Ouverte par « Toutes les versions » en bas du menu de la version. La maquette la loge dans le panneau de droite ;
 * le panneau unique n'existe pas encore dans le fork (sous-lot 19, L7) : elle prend la fenêtre à pied des autres écrans en attendant.
 * SA-L3c : « Mettre à jour » et « Fusionner » (fenêtre à part), « Comparer », la protection de la principale et « Revenir à la vN »
 * sur la principale (elle sert alors cette version) sont ici.
 */
export function FenetreVersions({
    agentId,
    ouverte,
    fermer,
    vue,
    ouverteId,
    ouvrir,
    repartition,
    fusionner,
    mettreAJour,
    apres,
}: {
    agentId: number;
    ouverte: boolean;
    fermer: () => void;
    vue: BranchesVue;
    /** La branche ouverte dans l'onglet (`null` : la principale). */
    ouverteId: number | null;
    ouvrir: (brancheId: number | null) => void;
    repartition: () => void;
    fusionner: (brancheId: number) => void;
    mettreAJour: (brancheId: number) => void;
    /** Après une écriture : relire les branches. */
    apres: () => void;
}) {
    const { t } = useLangue();
    const courante = vue.branches.find((b) => (ouverteId === null ? b.principale : b.id === ouverteId)) ?? vue.branches[0];
    const [vueId, setVueId] = useState<number>(courante.id);
    const choisie = vue.branches.find((b) => b.id === vueId) ?? courante;
    const [envoi, setEnvoi] = useState(false);
    const revenirA = async (numero: number) => {
        setEnvoi(true);
        try {
            const r = await epinglerLaPrincipaleApiV1BuilderBranchesWorkflowIdPrincipaleVersionPut({ path: { workflow_id: agentId }, body: { version: numero } });
            if (r.error) return notifier.echec({ en: "Could not go back to this version. Try again.", fr: "Retour à cette version impossible. Réessayez." }, { erreur: r.error });
            notifier.succes({ en: `The main branch now serves v${numero}. Publishing again follows the new version.`, fr: `La principale sert maintenant la v${numero}. Une nouvelle publication reprend la nouvelle version.` });
            apres();
        } finally {
            setEnvoi(false);
        }
    };
    // Clôture, lot B (D5) : « Protéger la version en ligne » est un réglage par agent. `null` : on revient à la règle par défaut (allumée chez un
    // client à la première publication par une personne, éteinte au Labo). Chaque changement est journalisé par le serveur.
    const proteger = async (protegee: boolean | null) => {
        setEnvoi(true);
        try {
            const r = await changerLaProtection(agentId, protegee);
            if (r.error) return notifier.echec({ en: "The protection could not be changed. Try again.", fr: "La protection n'a pas pu être changée. Réessayez." }, { erreur: r.error });
            notifier.succes(
                protegee === null
                    ? { en: "Back to the default rule.", fr: "Retour à la règle par défaut." }
                    : protegee
                      ? { en: "Live version protected.", fr: "Version en ligne protégée." }
                      : { en: "Protection lifted.", fr: "Protection levée." },
            );
            apres();
        } finally {
            setEnvoi(false);
        }
    };
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
                                {b.principale && b.protegee && <Lock className="ml-1.5 inline size-3 text-muted-foreground" aria-hidden />}
                            </button>
                            {b.principale ? (
                                <>
                                    <Button variant="ghost" size="sm" className="h-7 hover:font-semibold" disabled={envoi} onClick={() => void proteger(!b.protegee)}>
                                        {b.protegee ? t({ en: "Lift protection", fr: "Lever la protection" }) : t({ en: "Protect the live version", fr: "Protéger la version en ligne" })}
                                    </Button>
                                    {(b as { protection_reglee?: boolean | null }).protection_reglee != null && (
                                        <Button variant="ghost" size="sm" className="h-7 hover:font-semibold" disabled={envoi} onClick={() => void proteger(null)}>
                                            {t({ en: "Default rule", fr: "Règle par défaut" })}
                                        </Button>
                                    )}
                                </>
                            ) : (
                                <>
                                    <Button variant="ghost" size="sm" className="h-7 hover:font-semibold" onClick={() => mettreAJour(b.id)}>
                                        {t({ en: "Update", fr: "Mettre à jour" })}
                                    </Button>
                                    <Button variant="outline" size="sm" className="h-7 gap-1" onClick={() => fusionner(b.id)} disabled={b.version_en_ligne === null}>
                                        <GitMerge className="size-3.5" /> {t({ en: "Merge", fr: "Fusionner" })}
                                    </Button>
                                </>
                            )}
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
                <Button asChild variant="outline" size="sm" className="mt-2 h-7">
                    <Link href={`/agents/${agentId}/comparer`}>{t({ en: "Compare two branches or versions", fr: "Comparer deux branches ou versions" })}</Link>
                </Button>
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
                            {choisie.principale && v.numero !== choisie.version_en_ligne && v.numero !== null && (
                                <Button variant="ghost" size="sm" className="h-7 gap-1 hover:font-semibold" disabled={envoi} onClick={() => void revenirA(v.numero as number)}>
                                    <Undo2 className="size-3.5" /> {t({ en: `Go back to v${v.numero}`, fr: `Revenir à la v${v.numero}` })}
                                </Button>
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
