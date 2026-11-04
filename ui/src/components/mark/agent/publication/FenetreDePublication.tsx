"use client";

/**
 * [.mark] U11 : la fenêtre « Publier vX » (« Avant de publier », E81). « Publier » ouvre TOUJOURS cette fenêtre.
 * Onglets Contrôles et Ce qui change. Chaque contrôle se règle sur trois positions (Éteint · Prévient · Bloque) ; par défaut
 * seuls les tests obligatoires et le bilan du prompt bloquent (la garde d'avant). On peut toujours forcer : raison obligatoire,
 * écrite au journal avec la personne. Le déploiement progressif n'apparaît que s'il est allumé (éteint par défaut).
 * Forme de la maquette (`components/studio/avant-publier.tsx`) ; les données viennent du serveur, jamais d'un exemple.
 */
import { AlertTriangle, Play } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    controlesDePublicationApiV1BuilderPublicationWorkflowIdGet,
    corrigerLaListeVocaleApiV1BuilderPublicationWorkflowIdListeVocaleCorrigerPost,
    publishWorkflowApiV1WorkflowWorkflowIdPublishPost,
    reglerLaPublicationApiV1BuilderPublicationWorkflowIdReglagesPut,
} from "@/client/sdk.gen";
import { adresseOnglet } from "@/components/mark/agent/onglets-agent";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp, Section, Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";

import type { CleControle, PositionControle, StatutControle, VueDePublication } from "./types";

const POSITIONS: PositionControle[] = ["eteint", "previent", "bloque"];
const PARTS = [10, 25, 50];
const POINT: Record<StatutControle, "publie" | "attente" | "panne" | "fini"> = { ok: "publie", alerte: "attente", echec: "panne", eteint: "fini" };

export function FenetreDePublication({
    agentId,
    version,
    fermer,
    onPublie,
}: {
    agentId: number;
    version: number | null;
    fermer: () => void;
    onPublie: () => void;
}) {
    const { t } = useLangue();
    const [vue, setVue] = useState<VueDePublication | null>(null);
    const [erreur, setErreur] = useState(false);
    const [onglet, setOnglet] = useState("controles");
    const [corrections, setCorrections] = useState<string[]>([]);
    const [part, setPart] = useState<number | null>(null);
    const [forcer, setForcer] = useState(false);
    const [raison, setRaison] = useState("");
    const [enCours, setEnCours] = useState(false);

    const T = {
        controles: t({ en: "Checks", fr: "Contrôles" }),
        changements: t({ en: "What changes", fr: "Ce qui change" }),
        positions: {
            eteint: t({ en: "Off", fr: "Éteint" }),
            previent: t({ en: "Warns", fr: "Prévient" }),
            bloque: t({ en: "Blocks", fr: "Bloque" }),
        } satisfies Record<PositionControle, string>,
        mots: {
            ok: t({ en: "passed", fr: "réussi" }),
            alerte: t({ en: "to see", fr: "à voir" }),
            echec: t({ en: "failed", fr: "échec" }),
            eteint: t({ en: "off", fr: "éteint" }),
        } satisfies Record<StatutControle, string>,
    };
    const NOMS: Record<CleControle, { fr: string; en: string; info: { fr: string; en: string } }> = {
        tests_obligatoires: {
            fr: "Tests obligatoires",
            en: "Required tests",
            info: { fr: "Chaque test obligatoire de l'agent, joué sur le brouillon. Bloquant par défaut.", en: "Every required test of the agent, played on the draft. Blocks by default." },
        },
        bilan_du_prompt: {
            fr: "Bilan de santé du prompt",
            en: "Prompt health check",
            info: {
                fr: "Lu par le code : contradictions, variable inconnue, outil cité mais absent. Ne garde que les agents suivis par le builder.",
                en: "Read by the code: contradictions, unknown variable, tool named but missing. Only guards the agents the builder follows.",
            },
        },
        liste_vocale: {
            fr: "Liste de contrôle vocale",
            en: "Voice checklist",
            info: {
                fr: "Les points de la famille « Contrôles avant publication » de la bibliothèque, lus sur les réglages de l'agent. Simulation d'abord : rien n'est corrigé sans votre accord.",
                en: "The points of the « Checks before publishing » library family, read on the agent's settings. Simulation first: nothing is fixed without your agreement.",
            },
        },
        attaques: {
            fr: "Attaques",
            en: "Attacks",
            info: {
                fr: "Le dernier passage de « Attaquer l'agent » sur ce brouillon. « Non testé » n'est jamais compté comme tenu.",
                en: "The last « Attack the agent » run on this draft. « Not tested » never counts as held.",
            },
        },
        garde_fous: {
            fr: "Garde-fous",
            en: "Safeguards",
            info: { fr: "Au moins une couche de sécurité de la conversation est allumée (thème Sécurité des réglages).", en: "At least one safety layer of the conversation is on (Safety theme of the settings)." },
        },
    };

    const charger = useCallback(async () => {
        const r = await controlesDePublicationApiV1BuilderPublicationWorkflowIdGet({ path: { workflow_id: agentId } });
        if (r.error || !r.data) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setVue(r.data as VueDePublication);
    }, [agentId]);
    useEffect(() => {
        void charger();
    }, [charger]);

    const regler = async (cle: CleControle, position: PositionControle) => {
        if (!vue) return;
        const controles = Object.fromEntries(vue.controles.map((c) => [c.cle, c.position])) as Record<string, PositionControle>;
        const r = await reglerLaPublicationApiV1BuilderPublicationWorkflowIdReglagesPut({
            path: { workflow_id: agentId },
            body: { controles: { ...controles, [cle]: position }, deploiement: { actif: vue.deploiement_actif } },
        });
        if (r.error) {
            notifier.echec({ fr: "Réglage impossible. Réessayez.", en: "Could not save the setting. Try again." }, { erreur: r.error });
            return;
        }
        await charger();
    };

    const corriger = async () => {
        const r = await corrigerLaListeVocaleApiV1BuilderPublicationWorkflowIdListeVocaleCorrigerPost({
            path: { workflow_id: agentId },
            body: { ids: corrections },
        });
        if (r.error) {
            notifier.echec({ fr: "Correction impossible.", en: "Could not fix." }, { erreur: r.error });
            return;
        }
        notifier.succes({ fr: "Points corrigés dans le brouillon. Contrôles rejoués.", en: "Points fixed in the draft. Checks played again." });
        setCorrections([]);
        await charger();
    };

    const publier = async (avecForce: boolean) => {
        if (enCours) return;
        setEnCours(true);
        const r = await publishWorkflowApiV1WorkflowWorkflowIdPublishPost({
            path: { workflow_id: agentId },
            body: { forcer: avecForce, raison: avecForce ? raison.trim() : null, pourcentage: part },
        });
        setEnCours(false);
        if (r.error) {
            notifier.echec(
                { fr: "Publication impossible. Relisez les contrôles.", en: "Could not publish. Read the checks again." },
                { erreur: r.error, reessayer: () => void publier(avecForce), groupe: "publication-agent" },
            );
            await charger();
            return;
        }
        notifier.succes(
            part === null ? { fr: "Agent publié.", en: "Agent published." } : { fr: `Agent publié sur ${part} % des appels.`, en: `Agent published on ${part}% of the calls.` },
            { groupe: "publication-agent" },
        );
        onPublie();
        fermer();
    };

    const bloque = vue?.bloque ?? false;
    const titre = `${t({ en: "Publish", fr: "Publier" })}${version != null ? ` v${version}` : ""}`;
    const sous = !vue
        ? undefined
        : bloque
          ? t({ en: "A blocking check fails: publishing asks to be forced.", fr: "Un contrôle bloquant échoue : la publication demande d'être forcée." })
          : t({ en: "No blocking check fails.", fr: "Aucun contrôle bloquant n'échoue." });

    return (
        <>
            <FenetreOnglets
                fermer={fermer}
                titre={titre}
                sous={sous}
                onglets={[T.controles, T.changements]}
                onglet={onglet === "controles" ? T.controles : T.changements}
                changerOnglet={(o) => setOnglet(o === T.controles ? "controles" : "changements")}
                valider={bloque ? null : part !== null ? `${t({ en: "Publish on", fr: "Publier sur" })} ${part} %` : t({ en: "Publish", fr: "Publier" })}
                onValider={() => void publier(false)}
                desactiver={!vue || enCours}
                modifie={part !== null}
                pied={
                    <>
                        <Button variant="outline" onClick={() => void charger()}>
                            <Play className="size-4" /> {t({ en: "Play the checks again", fr: "Rejouer les contrôles" })}
                        </Button>
                        {bloque && (
                            <Button className="bg-destructive text-white hover:bg-destructive/90" onClick={() => setForcer(true)}>
                                <AlertTriangle className="size-4" /> {t({ en: "Force the publication", fr: "Forcer la publication" })}
                            </Button>
                        )}
                    </>
                }
            >
                {erreur ? (
                    <EtatVide cas="erreur" reessayer={() => void charger()} />
                ) : !vue ? (
                    <EtatVide cas="chargement" lignes={5} />
                ) : onglet === "controles" ? (
                    <>
                        <table className="w-full text-sm">
                            <thead className="border-b text-xs text-muted-foreground">
                                <tr>
                                    <th className="py-2 text-left font-normal">{t({ en: "Check", fr: "Contrôle" })}</th>
                                    <th className="pl-4 text-left font-normal">{t({ en: "Result", fr: "Résultat" })}</th>
                                    <th className="pl-4 text-right font-normal">{t({ en: "Set on", fr: "Réglé sur" })}</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y">
                                {vue.controles.map((c) => {
                                    const nom = NOMS[c.cle];
                                    return (
                                        <tr key={c.cle} data-controle={c.cle}>
                                            <td className="py-3">
                                                <span className="inline-flex items-center gap-1.5 font-medium">
                                                    {t(nom)}
                                                    <Info>{t(nom.info)}</Info>
                                                </span>
                                                {c.problemes.map((p) => (
                                                    <span key={p} className="block text-xs text-muted-foreground">
                                                        {p}
                                                    </span>
                                                ))}
                                            </td>
                                            <td className="pl-4 whitespace-nowrap">
                                                <PointEtat etat={POINT[c.statut]}>{T.mots[c.statut]}</PointEtat>
                                            </td>
                                            <td className="pl-4 text-right">
                                                <Segmente
                                                    valeur={T.positions[c.position]}
                                                    options={POSITIONS.map((p) => T.positions[p])}
                                                    changer={(v) => void regler(c.cle, POSITIONS.find((p) => T.positions[p] === v) ?? c.position)}
                                                />
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                        {vue.liste_vocale.length > 0 && (
                            <Section
                                titre={t({ en: "Voice checklist", fr: "Liste de contrôle vocale" })}
                                action={
                                    <Button size="sm" variant="outline" disabled={corrections.length === 0} onClick={() => void corriger()}>
                                        {t({ en: "Fix the ticked points", fr: "Corriger les points cochés" })}
                                    </Button>
                                }
                            >
                                <Champs>
                                    {vue.liste_vocale.map((p) => (
                                        <div key={p.id} className="flex items-start gap-3 py-2.5 text-sm" data-point={p.id}>
                                            {p.statut === "ecart" && p.corrections ? (
                                                <Checkbox
                                                    aria-label={`${t({ en: "Fix", fr: "Corriger" })} ${p.libelle}`}
                                                    checked={corrections.includes(p.id)}
                                                    onCheckedChange={(c) => setCorrections(c ? [...corrections, p.id] : corrections.filter((i) => i !== p.id))}
                                                />
                                            ) : (
                                                <span className="size-4 shrink-0" />
                                            )}
                                            <span className="flex-1">
                                                {p.libelle}
                                                {p.ecarts.map((e) => (
                                                    <span key={e.reglage} className="block text-xs text-muted-foreground">
                                                        {e.reglage} : {String(e.actuel)} ({e.attendu})
                                                    </span>
                                                ))}
                                            </span>
                                            {p.statut === "sans_equivalent" ? (
                                                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                                                    {t({ en: "no equivalent here", fr: "sans équivalent chez nous" })}
                                                    <Info>{p.raison}</Info>
                                                </span>
                                            ) : (
                                                <PointEtat etat={p.statut === "ok" ? "publie" : "attente"}>
                                                    {p.statut === "ok" ? T.mots.ok : T.mots.alerte}
                                                </PointEtat>
                                            )}
                                        </div>
                                    ))}
                                </Champs>
                            </Section>
                        )}
                        {vue.deploiement_actif && (
                            <Section titre={t({ en: "Deployment", fr: "Déploiement" })}>
                                <Champs>
                                    <LigneChamp
                                        libelle={t({ en: "Deployment", fr: "Déploiement" })}
                                        info={t({
                                            en: "A call gets its version when it starts, from the caller's number: the same caller always lands on the same version. The previous version keeps the rest of the calls. The checks above play the same way. Nothing switches by itself.",
                                            fr: "L'appel reçoit sa version à son début, d'après le numéro de l'appelant : un même appelant tombe toujours sur la même version. L'ancienne version garde le reste des appels. Les contrôles ci-dessus jouent de la même façon. Rien ne bascule seul.",
                                        })}
                                    >
                                        <Segmente
                                            valeur={part === null ? t({ en: "All calls", fr: "Pour tous les appels" }) : t({ en: "A share of the calls", fr: "Sur une part des appels" })}
                                            options={[t({ en: "All calls", fr: "Pour tous les appels" }), t({ en: "A share of the calls", fr: "Sur une part des appels" })]}
                                            changer={(v) => setPart(v === t({ en: "All calls", fr: "Pour tous les appels" }) ? null : (part ?? PARTS[0]))}
                                        />
                                    </LigneChamp>
                                    {part !== null && (
                                        <LigneChamp libelle={t({ en: "Share of the calls", fr: "Part des appels" })}>
                                            <Segmente valeur={`${part} %`} options={PARTS.map((p) => `${p} %`)} changer={(v) => setPart(parseInt(v, 10))} />
                                        </LigneChamp>
                                    )}
                                </Champs>
                            </Section>
                        )}
                    </>
                ) : (
                    <div className="space-y-3 text-sm">
                        <p className="flex items-center gap-1.5 text-muted-foreground">
                            {t({ en: "The draft compared with the published version", fr: "Le brouillon comparé à la version publiée" })}
                            <Info>
                                {t({
                                    en: "Each line opens on the text before and after, as « Compare » does in Versions.",
                                    fr: "Chaque ligne s'ouvre sur le texte avant et après, comme « Comparer » dans Versions.",
                                })}
                            </Info>
                        </p>
                        <Button variant="outline" asChild>
                            <Link href={adresseOnglet(agentId, "versions")}>{t({ en: "Compare in Versions", fr: "Comparer dans Versions" })}</Link>
                        </Button>
                    </div>
                )}
            </FenetreOnglets>
            {forcer && vue && (
                <FenetreOnglets
                    fermer={() => setForcer(false)}
                    titre={t({ en: "Force the publication", fr: "Forcer la publication" })}
                    sous={t({
                        en: "A blocking check fails. The reason is written to the journal with your name.",
                        fr: "Un contrôle bloquant échoue. La raison est écrite au journal avec votre nom.",
                    })}
                    valider={t({ en: "Publish anyway", fr: "Publier quand même" })}
                    desactiver={raison.trim().length < 5 || enCours}
                    modifie={raison.trim() !== ""}
                    onValider={() => void publier(true)}
                >
                    <Champs>
                        <div className="space-y-1 py-3">
                            <p className="text-sm font-medium">{t({ en: "What blocks", fr: "Ce qui bloque" })}</p>
                            {vue.controles
                                .filter((c) => c.statut === "echec")
                                .map((c) => (
                                    <p key={c.cle} className="text-sm text-muted-foreground">
                                        <span className="text-foreground">{t(NOMS[c.cle])}</span> · {c.problemes.join(" ; ")}
                                    </p>
                                ))}
                        </div>
                        <div className="space-y-2 py-3">
                            <label htmlFor="raison-forcer" className="text-sm font-medium">
                                {t({ en: "Why publish anyway", fr: "Pourquoi publier quand même" })}
                            </label>
                            <Textarea id="raison-forcer" rows={3} value={raison} onChange={(e) => setRaison(e.target.value)} />
                        </div>
                    </Champs>
                </FenetreOnglets>
            )}
        </>
    );
}
