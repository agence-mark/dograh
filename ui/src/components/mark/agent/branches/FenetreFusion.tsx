"use client";

import { ChevronDown, GitMerge } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
    apercuDeLaFusionApiV1BuilderBranchesWorkflowIdBranchIdFusionGet,
    apercuDeLaMiseAJourApiV1BuilderBranchesWorkflowIdBranchIdMiseAJourGet,
    defaireLaFusionApiV1BuilderBranchesWorkflowIdBranchIdFusionDefairePost,
    fusionnerUneBrancheApiV1BuilderBranchesWorkflowIdBranchIdFusionPost,
    mettreAJourUneBrancheApiV1BuilderBranchesWorkflowIdBranchIdMiseAJourPost,
} from "@/client/sdk.gen";
import type { ChampDeFusion, ProblemeDeFusion } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { motifDe, notifier } from "@/components/mark/notifications";
import { FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

/**
 * [.mark] Partie 3, SA-L3c (05 § 12, maquette `FenetreFusion`) : fusionner une branche dans la principale, ou la mettre à jour depuis la
 * principale. Même fenêtre, deux sens. L'aperçu est champ par champ (graphe, prompts, réglages, phrases, variables) ; chaque champ
 * changé des DEUX côtés est à trancher ici, jamais « le plus récent gagne » en silence : le bouton reste éteint tant qu'un conflit n'a
 * pas de choix. Sur une principale protégée, la fusion demande d'être « relue ». La maquette loge cette fenêtre dans le panneau de
 * droite ; le panneau unique n'existe pas encore (sous-lot 19, L7) : fenêtre centrée en attendant.
 *
 * Côtés : dans une fusion, la SOURCE est la branche (elle apporte) et la CIBLE la principale (elle reçoit) ; dans une mise à jour, la
 * SOURCE est la principale (elle apporte) et la CIBLE la branche (elle reçoit).
 */
export type SensDeFusion = "fusion" | "maj";

const T = {
    famille: {
        graphe: { en: "Flow", fr: "Graphe" },
        prompts: { en: "Prompts", fr: "Prompts" },
        reglages: { en: "Settings", fr: "Réglages" },
        phrases: { en: "Phrases", fr: "Phrases" },
        variables: { en: "Variables", fr: "Variables" },
    } satisfies Record<string, Texte>,
    probleme: {
        brouillon_en_attente: {
            en: "The main branch has an unpublished draft: publish or discard it first.",
            fr: "La principale a un brouillon non publié : publiez-le ou abandonnez-le d'abord.",
        },
        liaison_orpheline: { en: "A link would point to a removed step: change a choice.", fr: "Une liaison mènerait à une étape retirée : changez un choix." },
        etape_en_double: { en: "Two steps would share an identifier.", fr: "Deux étapes porteraient le même identifiant." },
        graphe_invalide: { en: "The merged flow would be invalid: change a choice.", fr: "Le graphe obtenu serait invalide : changez un choix." },
        declencheur_pris: { en: "A trigger address is already used by another agent.", fr: "Une adresse de déclencheur est déjà prise par un autre agent." },
    } satisfies Record<string, Texte>,
};

const famille = (cle: string, t: (x: Texte) => string) => t((T.famille as Record<string, Texte>)[cle] ?? { en: cle, fr: cle });

function valeurDe(v: string | null | undefined, t: (x: Texte) => string) {
    return v === null || v === undefined ? t({ en: "(absent)", fr: "(absent)" }) : v;
}

type Normalise = {
    champs: ChampDeFusion[];
    resume: { reprise: number; gardee: number; conflit: number };
    problemes: ProblemeDeFusion[];
    protegee: boolean;
    aJour: boolean;
    versionSource: number;
    versionCible: number;
    nomApporte: string;
    nomRecoit: string;
    trafic?: { de: number; vers: number; part: number };
    defaisable: boolean;
};

export function FenetreFusion({
    agentId,
    brancheId,
    sens,
    ouverte,
    fermer,
    apres,
}: {
    agentId: number;
    brancheId: number;
    sens: SensDeFusion;
    ouverte: boolean;
    fermer: () => void;
    /** Après une écriture réussie : relire les branches (et, pour une mise à jour, l'écran). */
    apres: (ecrit: SensDeFusion) => void;
}) {
    const { t } = useLangue();
    const maj = sens === "maj";
    const [apercu, setApercu] = useState<Normalise | null>(null);
    const [echec, setEchec] = useState(false);
    const [choix, setChoix] = useState<Record<string, "source" | "cible">>({});
    const [relue, setRelue] = useState(false);
    const [envoi, setEnvoi] = useState(false);
    const [gardes, setGardes] = useState(false);

    const lire = useCallback(async () => {
        setApercu(null);
        setEchec(false);
        setChoix({});
        setRelue(false);
        const path = { workflow_id: agentId, branch_id: brancheId };
        try {
            if (maj) {
                const r = await apercuDeLaMiseAJourApiV1BuilderBranchesWorkflowIdBranchIdMiseAJourGet({ path });
                if (r.error || !r.data) return setEchec(true);
                const d = r.data;
                setApercu({
                    champs: d.champs,
                    resume: d.resume,
                    problemes: d.problemes,
                    protegee: false,
                    aJour: d.a_jour,
                    versionSource: d.principale.id_version,
                    versionCible: d.branche.id_base ?? 0,
                    nomApporte: t({ en: "Main", fr: "Principale" }),
                    nomRecoit: d.branche.nom,
                    defaisable: false,
                });
            } else {
                const r = await apercuDeLaFusionApiV1BuilderBranchesWorkflowIdBranchIdFusionGet({ path });
                if (r.error || !r.data) return setEchec(true);
                const d = r.data;
                setApercu({
                    champs: d.champs,
                    resume: d.resume,
                    problemes: d.problemes,
                    protegee: d.relue_obligatoire,
                    aJour: false,
                    versionSource: d.branche.id_version,
                    versionCible: d.cible.id_version,
                    nomApporte: d.branche.nom,
                    nomRecoit: d.cible.nom === "Principale" ? t({ en: "Main", fr: "Principale" }) : d.cible.nom,
                    trafic: { de: d.trafic.part_principale, vers: d.trafic.part_principale_apres, part: d.trafic.part_branche },
                    defaisable: d.defaisable ?? false,
                });
            }
        } catch {
            setEchec(true);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- relu à l'ouverture ou quand la cible change, pas quand la langue change
    }, [agentId, brancheId, maj]);

    useEffect(() => {
        if (ouverte) void lire();
    }, [ouverte, lire]);

    const conflits = useMemo(() => (apercu?.champs ?? []).filter((c) => c.statut === "conflit"), [apercu]);
    const repris = useMemo(() => (apercu?.champs ?? []).filter((c) => c.statut === "reprise"), [apercu]);
    const gardees = useMemo(() => (apercu?.champs ?? []).filter((c) => c.statut === "gardee"), [apercu]);
    const reste = conflits.filter((c) => !choix[c.cle]).length;
    const bloque = !apercu || apercu.aJour || reste > 0 || (apercu.protegee && !relue) || apercu.problemes.length > 0 || envoi;

    const titre = !apercu
        ? maj
            ? t({ en: "Update from the main branch", fr: "Mettre à jour depuis la principale" })
            : t({ en: "Merge a branch", fr: "Fusionner une branche" })
        : maj
          ? t({ en: `Update “${apercu.nomRecoit}” from ${apercu.nomApporte}`, fr: `Mettre à jour « ${apercu.nomRecoit} » depuis ${apercu.nomApporte}` })
          : t({ en: `Merge “${apercu.nomApporte}” into ${apercu.nomRecoit}`, fr: `Fusionner « ${apercu.nomApporte} » dans ${apercu.nomRecoit}` });

    const refus = (statut: number | undefined, detail: unknown) => {
        const texte = motifDe(detail);
        if (statut === 409 && /changed since the preview/i.test(texte)) {
            notifier.avertissement({ en: "The agent changed since you opened this window. The preview was read again.", fr: "L'agent a changé depuis l'ouverture de la fenêtre. L'aperçu a été relu." });
            void lire();
        } else if (statut === 409 && /unpublished draft/i.test(texte)) {
            notifier.echec(T.probleme.brouillon_en_attente, { erreur: detail });
        } else if (/reviewed/i.test(texte)) {
            notifier.echec({ en: "A merge into a protected main branch must be reviewed: tick the box.", fr: "Une fusion dans une principale protégée doit être relue : cochez la case." }, { erreur: detail });
        } else {
            notifier.echec(
                maj
                    ? { en: "The update was refused. Check the choices and try again.", fr: "La mise à jour a été refusée. Relisez vos choix puis réessayez." }
                    : { en: "The merge was refused. Check the choices and try again.", fr: "La fusion a été refusée. Relisez vos choix puis réessayez." },
                { erreur: detail },
            );
        }
    };

    const valider = async () => {
        if (!apercu || bloque) return;
        setEnvoi(true);
        try {
            const path = { workflow_id: agentId, branch_id: brancheId };
            if (maj) {
                const r = await mettreAJourUneBrancheApiV1BuilderBranchesWorkflowIdBranchIdMiseAJourPost({
                    path,
                    body: { choix, version_principale: apercu.versionSource, base_attendue: apercu.versionCible || null },
                });
                if (r.error) return refus(r.response?.status, r.error);
                notifier.succes({
                    en: `“${apercu.nomRecoit}” is up to date. “Go back before” undoes it.`,
                    fr: `« ${apercu.nomRecoit} » est à jour. « Revenir avant » la défait.`,
                });
            } else {
                const r = await fusionnerUneBrancheApiV1BuilderBranchesWorkflowIdBranchIdFusionPost({
                    path,
                    body: { choix, relue, version_branche: apercu.versionSource, version_cible: apercu.versionCible },
                });
                if (r.error) return refus(r.response?.status, r.error);
                notifier.reversible(
                    { en: `“${apercu.nomApporte}” merged into ${apercu.nomRecoit} and archived.`, fr: `« ${apercu.nomApporte} » fusionnée dans ${apercu.nomRecoit} et archivée.` },
                    async () => {
                        const d = await defaireLaFusionApiV1BuilderBranchesWorkflowIdBranchIdFusionDefairePost({ path });
                        if (d.error) notifier.echec({ en: "The merge could not be undone: the agent was published since.", fr: "La fusion ne peut plus être défaite : l'agent a été publié depuis." }, { erreur: d.error });
                        apres("fusion");
                    },
                );
            }
            apres(sens);
            fermer();
        } catch (erreur) {
            notifier.echec({ en: "Could not reach the server. Try again.", fr: "Le serveur n'a pas répondu. Réessayez." }, { erreur });
        } finally {
            setEnvoi(false);
        }
    };

    return (
        <FenetreLarge
            ouverte={ouverte}
            fermer={fermer}
            large={false}
            testid="fenetre-fusion"
            titre={
                <span className="flex items-center gap-2">
                    <GitMerge className="size-4" /> {titre}
                    <Info>
                        {maj
                            ? t({
                                  en: "Brings the news of the main branch into this branch and keeps its own changes. Conflicts are chosen here, field by field: never “the latest wins” in silence.",
                                  fr: "Ramène dans la branche les nouveautés de la principale et garde ses propres changements. Les conflits se choisissent ici, champ par champ : jamais « le plus récent gagne » en silence.",
                              })
                            : t({
                                  en: "The merge creates a version on the main branch, takes over the branch's share of the calls and archives the branch. Conflicts are chosen here, field by field.",
                                  fr: "La fusion crée une version sur la principale, reprend la part des appels de la branche et archive la branche. Les conflits se choisissent ici, champ par champ.",
                              })}
                    </Info>
                </span>
            }
            pied={
                <>
                    <Button variant="outline" className="ml-auto" onClick={fermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button disabled={bloque} onClick={() => void valider()}>
                        {maj ? t({ en: "Update", fr: "Mettre à jour" }) : t({ en: "Merge", fr: "Fusionner" })}
                    </Button>
                </>
            }
        >
            {echec && (
                <p role="alert" className="text-sm text-muted-foreground">
                    {t({ en: "The preview could not be read. Close this window and try again.", fr: "L'aperçu n'a pas pu être lu. Fermez la fenêtre puis réessayez." })}
                </p>
            )}
            {!apercu && !echec && <p className="text-sm text-muted-foreground">{t({ en: "Reading the changes…", fr: "Lecture des changements…" })}</p>}
            {apercu?.aJour && (
                <p role="status" className="text-sm text-muted-foreground">
                    {t({ en: "This branch is already up to date with the main branch.", fr: "Cette branche est déjà à jour avec la principale." })}
                </p>
            )}
            {apercu && !apercu.aJour && (
                <div className="space-y-5">
                    {apercu.problemes.length > 0 && (
                        <ul role="alert" className="space-y-1 text-sm text-(--pastille-urgente)">
                            {apercu.problemes.map((p, i) => (
                                <li key={`${p.code}-${i}`}>{t((T.probleme as Record<string, Texte>)[p.code] ?? { en: p.code, fr: p.code })}</li>
                            ))}
                        </ul>
                    )}
                    {apercu.champs.length === 0 && apercu.problemes.length === 0 && (
                        <p className="text-sm text-muted-foreground">{t({ en: "No difference between the two sides.", fr: "Aucune différence entre les deux côtés." })}</p>
                    )}

                    {repris.length > 0 && (
                        <div>
                            <p className="pb-1 text-sm font-semibold">{t({ en: "What changes", fr: "Ce qui change" })}</p>
                            <ul className="divide-y text-sm">
                                {repris.map((c) => (
                                    <li key={c.cle} className="grid grid-cols-[110px_1fr] gap-x-4 py-2">
                                        <span className="pt-0.5 text-xs text-muted-foreground">{famille(c.famille, t)}</span>
                                        <span className="min-w-0">
                                            <span className="font-medium">{c.libelle}</span>
                                            <span className="block text-xs break-words text-muted-foreground">
                                                {valeurDe(c.cible, t)} <span aria-hidden>→</span> {valeurDe(c.source, t)}
                                            </span>
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {conflits.length > 0 && (
                        <div>
                            <p className="flex items-center gap-2 pb-1 text-sm font-semibold">
                                {t({ en: "To decide", fr: "À trancher" })} ({conflits.length - reste} / {conflits.length})
                                <Info>
                                    {t({
                                        en: "These fields changed on both sides since the starting point. Choose the value to keep.",
                                        fr: "Ces champs ont changé des deux côtés depuis le point de départ. Choisissez la valeur à garder.",
                                    })}
                                </Info>
                            </p>
                            <ul className="divide-y text-sm">
                                {conflits.map((c) => (
                                    <li key={c.cle} className="space-y-2 py-3" data-conflit={c.cle}>
                                        <p>
                                            <span className="text-xs text-muted-foreground">{famille(c.famille, t)} · </span>
                                            <span className="font-medium">{c.libelle}</span>
                                        </p>
                                        <div role="radiogroup" aria-label={c.libelle} className="grid gap-2 sm:grid-cols-2">
                                            {(
                                                [
                                                    ["cible", apercu.nomRecoit, c.cible],
                                                    ["source", apercu.nomApporte, c.source],
                                                ] as const
                                            ).map(([cote, nom, valeur]) => (
                                                <button
                                                    key={cote}
                                                    type="button"
                                                    role="radio"
                                                    aria-checked={choix[c.cle] === cote}
                                                    onClick={() => setChoix((x) => ({ ...x, [c.cle]: cote }))}
                                                    className={`cursor-pointer rounded-lg border p-2.5 text-left hover:font-semibold ${choix[c.cle] === cote ? "border-primary bg-muted dark:border-white" : "border-black/10 dark:border-white/15"}`}
                                                >
                                                    <span className="block text-xs text-muted-foreground">
                                                        {t({ en: "Keep", fr: "Garder" })} {nom}
                                                    </span>
                                                    <span className="block text-sm break-words">{valeurDe(valeur, t)}</span>
                                                </button>
                                            ))}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {gardees.length > 0 && (
                        <div>
                            <button
                                type="button"
                                aria-expanded={gardes}
                                onClick={() => setGardes(!gardes)}
                                className="flex cursor-pointer items-center gap-2 text-sm font-medium hover:font-semibold"
                            >
                                <ChevronDown className={`size-4 text-muted-foreground transition-transform ${gardes ? "" : "-rotate-90"}`} />
                                {t({ en: "Stays as it is", fr: "Reste comme avant" })}
                                <span className="text-xs font-normal text-muted-foreground">{gardees.length}</span>
                            </button>
                            {gardes && (
                                <ul className="divide-y text-sm">
                                    {gardees.map((c) => (
                                        <li key={c.cle} className="grid grid-cols-[110px_1fr] gap-x-4 py-2 text-muted-foreground">
                                            <span className="text-xs">{famille(c.famille, t)}</span>
                                            <span>{c.libelle}</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    )}

                    {!maj && apercu.trafic && (
                        <div className="space-y-1 text-sm">
                            <p className="font-semibold">{t({ en: "Effect on the calls", fr: "Effet sur le trafic" })}</p>
                            <p className="text-muted-foreground tabular-nums" data-trafic>
                                {apercu.nomRecoit} {apercu.trafic.de} % <span aria-hidden>→</span> {apercu.trafic.vers} %
                                {apercu.trafic.part > 0
                                    ? t({ en: ` (takes the ${apercu.trafic.part} % of “${apercu.nomApporte}”)`, fr: ` (reprend les ${apercu.trafic.part} % de « ${apercu.nomApporte} »)` })
                                    : ""}
                            </p>
                        </div>
                    )}

                    {apercu.protegee && (
                        <label className="flex items-start gap-2 text-sm">
                            <Checkbox className="mt-0.5" checked={relue} onCheckedChange={(v) => setRelue(v === true)} aria-label={t({ en: "Merge reviewed", fr: "Fusion relue" })} />
                            <span className="flex items-center gap-1.5">
                                {t({ en: "Merge reviewed, required", fr: "Fusion relue, obligatoire" })}
                                <Info>
                                    {t({
                                        en: "The main branch of a live client agent is protected: it is entered only by a reviewed merge.",
                                        fr: "La principale d'un agent client en ligne est protégée : on n'y entre que par une fusion relue.",
                                    })}
                                </Info>
                            </span>
                        </label>
                    )}
                </div>
            )}
        </FenetreLarge>
    );
}
