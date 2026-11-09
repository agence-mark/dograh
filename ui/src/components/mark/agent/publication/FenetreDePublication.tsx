"use client";

/**
 * [.mark] U11 : la fenêtre « Publier vX » (« Avant de publier », E81). « Publier » ouvre TOUJOURS cette fenêtre.
 * Onglets Contrôles et Ce qui change. Chaque contrôle se règle sur trois positions (Éteint · Prévient · Bloque) ; par défaut
 * seuls les tests obligatoires et le bilan du prompt bloquent (la garde d'avant). On peut toujours forcer : raison obligatoire,
 * écrite au journal avec la personne. Le déploiement progressif n'apparaît que s'il est allumé (éteint par défaut).
 * Forme de la maquette (`components/studio/avant-publier.tsx`) ; les données viennent du serveur, jamais d'un exemple.
 */
import { AlertTriangle, Play, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
    changementsDuBrouillonApiV1BuilderPublicationWorkflowIdChangementsGet,
    controlesDePublicationApiV1BuilderPublicationWorkflowIdGet,
    corrigerLaListeVocaleApiV1BuilderPublicationWorkflowIdListeVocaleCorrigerPost,
    lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet,
    ouvrirUnFilApiV1BuilderFilsPost,
    publishWorkflowApiV1WorkflowWorkflowIdPublishPost,
    reglerLaPublicationApiV1BuilderPublicationWorkflowIdReglagesPut,
} from "@/client/sdk.gen";
import { STATUT_PLAFOND, statutDe, TEXTES_PLAFOND } from "@/components/builder/chat/plafond-du-mois";
import { endroitDeLaLigne } from "@/components/mark/agent/pret/endroit";
import { ListePret } from "@/components/mark/agent/pret/ListePret";
import { useRecalculDuPret } from "@/components/mark/agent/pret/recalcul";
import { useCorrectionEnUnClic } from "@/components/mark/agent/pret/useCorrection";
import { usePublierLeGroupe } from "@/components/mark/groupe/PublierLeGroupe";
import { useLangue } from "@/components/mark/langue/langue";
import { phraseDuServeur } from "@/components/mark/langue/messages-serveur";
import { notifier } from "@/components/mark/notifications";
import { TEXTES_ETAPES } from "@/components/mark/reglages-agent/PreparationAgent";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp, Section, Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { BilanDeSante, PoidsDeLAgentSection } from "./BilanEtPoids";
import { CarteRelecture, DEMANDE_DE_RELECTURE } from "./CarteRelecture";
import { CONTROLES_FIXES, CONTROLES_INFORMATIFS } from "./types";
import type { CleControle, GenreDeChangement, PositionControle, StatutControle, VueDePublication, VueDesChangements } from "./types";

const POSITIONS: PositionControle[] = ["eteint", "previent", "bloque"];
const POINT: Record<StatutControle, "publie" | "attente" | "panne" | "fini"> = { ok: "publie", alerte: "attente", echec: "panne", eteint: "fini" };
const GENRES: Record<GenreDeChangement, { en: string; fr: string }> = {
    node_added: { en: "Step added", fr: "Étape ajoutée" },
    node_changed: { en: "Step changed", fr: "Étape changée" },
    node_removed: { en: "Step removed", fr: "Étape retirée" },
    link_added: { en: "Link added", fr: "Liaison ajoutée" },
    link_changed: { en: "Link changed", fr: "Liaison changée" },
    link_removed: { en: "Link removed", fr: "Liaison retirée" },
    setting_changed: { en: "Setting changed", fr: "Réglage changé" },
};

export function FenetreDePublication({
    agentId,
    version,
    branche = null,
    fermer,
    onPublie,
}: {
    agentId: number;
    version: number | null;
    /** Le nom de la branche ouverte (non principale) : la publication est celle de cette branche. */
    branche?: string | null;
    fermer: () => void;
    onPublie: () => void;
}) {
    const { t, langue } = useLangue();
    const [vue, setVue] = useState<VueDePublication | null>(null);
    const [erreur, setErreur] = useState(false);
    const [onglet, setOnglet] = useState("controles");
    const [corrections, setCorrections] = useState<string[]>([]);
    const [forcer, setForcer] = useState(false);
    const [raison, setRaison] = useState("");
    const [enCours, setEnCours] = useState(false);
    // [.mark] Partie 3 (SE-12) : « Ce qui change » (tableau avant / après), la relecture du builder, les spécialistes du groupe.
    const [changements, setChangements] = useState<VueDesChangements | "erreur" | null>(null);
    const [filDeRelecture, setFilDeRelecture] = useState<number | null>(null);
    const [relectureEnCours, setRelectureEnCours] = useState(false);
    const [specialistes, setSpecialistes] = useState<{ id: number; name: string }[]>([]);
    const [avecLeGroupe, setAvecLeGroupe] = useState(false);
    const [choisis, setChoisis] = useState<number[]>([]);
    const groupe = usePublierLeGroupe();
    const router = useRouter();

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
        variables: {
            fr: "Variables des prompts",
            en: "Prompt variables",
            info: {
                fr: "Chaque {{variable}} lue par les prompts a une valeur (modèle de l'agent ou extraction d'une étape). Bloque par défaut.",
                en: "Every {{variable}} the prompts read has a value (the agent's template or a step's extraction). Blocks by default.",
            },
        },
        briques: {
            fr: "Modèles configurés",
            en: "Models configured",
            info: {
                fr: "Cerveau, transcription et voix sont réglés (aucun fournisseur n'est appelé). Bloque par défaut.",
                en: "Brain, transcription and voice are set (no provider is called). Blocks by default.",
            },
        },
        outils: {
            fr: "Outils branchés",
            en: "Tools connected",
            info: {
                fr: "Chaque outil porté par une étape existe et est actif. Bloque par défaut.",
                en: "Every tool a step carries exists and is active. Blocks by default.",
            },
        },
        sans_effet: {
            fr: "Réglages sans effet",
            en: "Settings with no effect",
            info: {
                fr: "Un réglage allumé qui ne change rien à l'appel (règles sur une étape où le modèle décide, fiche éteinte, temps réel…). Prévient par défaut : une bonne pratique n'est pas un blocage.",
                en: "A setting that is on and changes nothing in the call (rules on a step where the model decides, record off, realtime…). Warns by default: a good practice is not a block.",
            },
        },
        sortie_d_impasse: {
            fr: "Sortie d'impasse",
            en: "Dead-end exit",
            info: {
                fr: "La sortie d'impasse est allumée : son « Ensuite » doit mener quelque part. Bloque par défaut.",
                en: "The dead-end exit is on: its « Then » must lead somewhere. Blocks by default.",
            },
        },
        deux_webhooks: {
            fr: "Deux webhooks",
            en: "Two webhooks",
            info: {
                fr: "Le webhook de Dograh et le module webhook .mark envoient tous deux après l'appel. Prévient par défaut.",
                en: "Dograh's webhook and the .mark webhook module both send after the call. Warns by default.",
            },
        },
        annonce_ia: {
            fr: "Annonce « vous parlez à une IA »",
            en: "Announcement « you are talking to an AI »",
            info: {
                fr: "Vérifie que l'annonce est dite en tête de chaque appel (allumée par défaut, texte et interrupteur dans le thème Phrases). Éteint ou Prévient, jamais Bloque.",
                en: "Checks that the announcement is said at the start of every call (on by default, text and switch in the Phrases theme). Off or Warns, never Blocks.",
            },
        },
        // Lot « façon Tala par motif » : les contrôles de rédaction, par le même réglage que les autres.
        valeur_en_dur: {
            fr: "Valeur écrite en dur",
            en: "Value written in the prompt",
            info: {
                fr: "Un montant, un délai chiffré ou un prénom donné en exemple dans un prompt. Prévient par défaut : une bonne pratique n'est pas un blocage.",
                en: "An amount, a figure delay or a first name given as an example in a prompt. Warns by default: a good practice is not a block.",
            },
        },
        verbe_ecran: {
            fr: "Verbe d'écran",
            en: "Screen verb",
            info: {
                fr: "« Afficher », « cliquer », « à l'écran » dans un prompt d'agent vocal. Prévient par défaut.",
                en: "« Display », « click », « on the screen » in a voice agent prompt. Warns by default.",
            },
        },
        action_sans_outil: {
            fr: "Action promise sans outil",
            en: "Action promised without a tool",
            info: {
                fr: "« Enregistrer », « réserver », « annuler », « envoyer » dans une étape sans aucun outil qui écrit. Prévient par défaut.",
                en: "« Save », « book », « cancel », « send » in a step with no tool that writes. Warns by default.",
            },
        },
        sortie_non_citee: {
            fr: "Sortie non citée",
            en: "Exit not named",
            info: {
                fr: "Une étape à deux sorties de travail ou plus dont le texte ne cite aucune étape visée. Prévient par défaut.",
                en: "A step with two work exits or more whose text names none of the steps it leads to. Warns by default.",
            },
        },
        poids_agent: {
            fr: "Poids de l'agent",
            en: "Agent weight",
            info: {
                fr: "Ce que le cerveau lit à chaque réplique, comparé au seuil réglé avec le cerveau (Briques). Informe, ne bloque jamais.",
                en: "What the brain reads at each reply, compared with the threshold set with the brain (Services). Informs, never blocks.",
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
    const recalcul = useRecalculDuPret((x) => x.n);
    useEffect(() => {
        void charger();
    }, [charger, recalcul]);
    const { corriger: corrigerUnReglage, enCours: corrigerEnCours } = useCorrectionEnUnClic(agentId, charger);

    // Les spécialistes ne se proposent que dans la fenêtre du PRINCIPAL de leur groupe (un agent seul ou un spécialiste : rien).
    useEffect(() => {
        let vivant = true;
        void (async () => {
            const r = await lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet({ path: { workflow_id: agentId } });
            if (!vivant || r.error || !r.data || r.data.principal?.id !== agentId) return;
            const liste = (r.data.specialises ?? []).map((m) => ({ id: m.id, name: m.name }));
            setSpecialistes(liste);
            setChoisis(liste.map((m) => m.id));
        })();
        return () => {
            vivant = false;
        };
    }, [agentId]);

    const chargerLesChangements = useCallback(async () => {
        setChangements(null);
        const r = await changementsDuBrouillonApiV1BuilderPublicationWorkflowIdChangementsGet({ path: { workflow_id: agentId } });
        setChangements(r.error || !r.data ? "erreur" : (r.data as VueDesChangements));
    }, [agentId]);
    useEffect(() => {
        if (onglet === "changements" && changements === null) void chargerLesChangements();
    }, [onglet, changements, chargerLesChangements]);

    const demanderLaRelecture = async () => {
        if (relectureEnCours) return;
        setRelectureEnCours(true);
        const r = await ouvrirUnFilApiV1BuilderFilsPost({ body: { message: t(DEMANDE_DE_RELECTURE), workflow_id: agentId, demarrage: null } });
        setRelectureEnCours(false);
        if (r.error && statutDe(r) === STATUT_PLAFOND) {
            notifier.avertissement(TEXTES_PLAFOND.notification, { groupe: "plafond-du-mois" });
            return;
        }
        if (r.error || !r.data) {
            notifier.echec(
                { fr: "Le builder n'a pas pu relire. Réessayez ou ouvrez le Chat.", en: "The builder could not read the changes. Try again or open the Chat." },
                { erreur: r.error },
            );
            return;
        }
        setFilDeRelecture(r.data.id);
    };

    const regler = async (cle: CleControle, position: PositionControle) => {
        if (!vue) return;
        // Les contrôles à position fixe (annonce, étiquettes, blocs) n'ont pas de réglage : ils ne repartent pas.
        const controles = Object.fromEntries(vue.controles.filter((c) => !CONTROLES_FIXES.includes(c.cle)).map((c) => [c.cle, c.position])) as Record<string, PositionControle>;
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
            body: { forcer: avecForce, raison: avecForce ? raison.trim() : null },
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
            branche === null
                ? { fr: "Agent publié.", en: "Agent published." }
                : { fr: `Version publiée sur la branche « ${branche} ».`, en: `Version published on the branch "${branche}".` },
            { groupe: "publication-agent" },
        );
        // Les spécialistes cochés partent après le principal (ses contrôles, sa raison de forcer, sa part d'appels sont passés) ;
        // chacun dit son résultat, un refus s'arrête au premier et se dit.
        if (avecLeGroupe && choisis.length > 0) await groupe.publier(agentId, { specialises: choisis, avecLePrincipal: false });
        onPublie();
        fermer();
    };

    // La fenêtre se ferme avant d'aller à l'étape visée (sans étape connue : le parcours de l'agent).
    const allerALEtape = (noeudId: string | null) => {
        fermer();
        router.push(noeudId ? `/workflow/${agentId}?etape=${encodeURIComponent(noeudId)}` : `/workflow/${agentId}`);
    };

    const bloque = vue?.bloque ?? false;
    const titre = `${t({ en: "Publish", fr: "Publier" })}${version != null ? ` v${version}` : ""}${branche ? ` · ${branche}` : ""}`;
    const sous = !vue
        ? undefined
        : bloque
          ? t({ en: "A blocking check fails: publishing asks to be forced.", fr: "Un contrôle bloquant échoue : la publication demande d'être forcée." })
          : t({ en: "No blocking check fails.", fr: "Aucun contrôle bloquant n'échoue." });

    return (
        <>
            <FenetreOnglets centree
                fermer={fermer}
                titre={titre}
                sous={sous}
                onglets={[T.controles, T.changements]}
                onglet={onglet === "controles" ? T.controles : T.changements}
                changerOnglet={(o) => setOnglet(o === T.controles ? "controles" : "changements")}
                valider={bloque ? null : t({ en: "Publish", fr: "Publier" })}
                modifie={false} // rien ne se saisit ici : la raison du forçage a sa propre fenêtre
                onValider={() => void publier(false)}
                desactiver={!vue || enCours || groupe.enCours}
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
                        <Section titre={t({ en: "Ready to publish", fr: "Prêt à publier" })}>
                            <ListePret
                                lignes={vue.lignes ?? []}
                                textesDesEtapes={TEXTES_ETAPES}
                                enCours={corrigerEnCours}
                                corriger={(_, c) => void corrigerUnReglage(c)}
                                regler={(ligne) => {
                                    // La fenêtre se ferme avant d'aller à l'endroit exact (étape, onglet ou thème des Réglages).
                                    fermer();
                                    router.push(endroitDeLaLigne(ligne, agentId).adresse);
                                }}
                            />
                        </Section>
                        <BilanDeSante agentId={agentId} version={version} defauts={vue.defauts_du_prompt ?? []} ouvrirEtape={allerALEtape} />
                        {vue.poids && (
                            <PoidsDeLAgentSection
                                poids={vue.poids}
                                ouvrirEtape={allerALEtape}
                                regler={() => {
                                    fermer();
                                    router.push(`/workflow/${agentId}/settings?theme=briques`);
                                }}
                            />
                        )}
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
                                    if (!nom) return null; // étiquettes et blocs : leur ligne est dans « Prêt à publier »
                                    const positions = CONTROLES_INFORMATIFS.includes(c.cle) ? POSITIONS.filter((p) => p !== "bloque") : POSITIONS;
                                    return (
                                        <tr key={c.cle} data-controle={c.cle}>
                                            <td className="py-3">
                                                <span className="inline-flex items-center gap-1.5 font-medium">
                                                    {t(nom)}
                                                    <Info>{t(nom.info)}</Info>
                                                </span>
                                                {c.problemes.map((p, i) => (
                                                    <span key={`${i}-${p}`} className="block text-xs text-muted-foreground">
                                                        {phraseDuServeur(p, c.details?.[i], langue)}
                                                    </span>
                                                ))}
                                            </td>
                                            <td className="pl-4 whitespace-nowrap">
                                                <PointEtat etat={POINT[c.statut]}>{T.mots[c.statut]}</PointEtat>
                                            </td>
                                            <td className="pl-4 text-right">
                                                <Segmente
                                                    valeur={T.positions[c.position]}
                                                    options={positions.map((p) => T.positions[p])}
                                                    changer={(v) => void regler(c.cle, positions.find((p) => T.positions[p] === v) ?? c.position)}
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
                        {specialistes.length > 0 && (
                            <Section titre={t({ en: "Group", fr: "Groupe" })}>
                                <Champs>
                                    <LigneChamp
                                        libelle={t({ en: "Publish the specialists of the group too", fr: "Publier aussi les spécialistes du groupe" })}
                                        info={t({
                                            en: "After this agent, each specialist ticked below is published with the same gesture, one by one, stopping at the first refusal. Those you leave unticked stay as drafts.",
                                            fr: "Après cet agent, chaque spécialiste coché ci-dessous est publié du même geste, un par un, en s'arrêtant au premier refus. Ceux que vous laissez décochés restent en brouillon.",
                                        })}
                                    >
                                        <Switch
                                            aria-label={t({ en: "Publish the specialists of the group too", fr: "Publier aussi les spécialistes du groupe" })}
                                            checked={avecLeGroupe}
                                            onCheckedChange={setAvecLeGroupe}
                                        />
                                    </LigneChamp>
                                    {avecLeGroupe &&
                                        specialistes.map((m) => (
                                            <div key={m.id} className="flex items-center gap-3 py-2.5 text-sm" data-specialiste={m.id}>
                                                <Checkbox
                                                    aria-label={`${t({ en: "Publish", fr: "Publier" })} ${m.name}`}
                                                    checked={choisis.includes(m.id)}
                                                    onCheckedChange={(c) => setChoisis(c ? [...choisis, m.id] : choisis.filter((i) => i !== m.id))}
                                                />
                                                <span>{m.name}</span>
                                            </div>
                                        ))}
                                </Champs>
                            </Section>
                        )}
                    </>
                ) : (
                    <div className="text-sm">
                        {changements === null ? (
                            <EtatVide cas="chargement" lignes={4} />
                        ) : changements === "erreur" ? (
                            <EtatVide cas="erreur" reessayer={() => void chargerLesChangements()} />
                        ) : (
                            <>
                                <p className="flex items-center gap-1.5 pb-2 text-muted-foreground" data-changements-en-tete>
                                    {changements.version_publiee == null ? (
                                        t({ en: "The draft: nothing is published yet", fr: "Le brouillon : rien n'est encore publié" })
                                    ) : (
                                        <>
                                            {t({ en: `Draft compared with v${changements.version_publiee}, published`, fr: `Brouillon comparé à v${changements.version_publiee}, publiée` })}{" "}
                                            <DateRelative valeur={changements.publiee_le} />
                                        </>
                                    )}
                                    <Info>
                                        {t({
                                            en: "One line per change, with the text before and after. « Compare » in Versions shows the same two versions side by side.",
                                            fr: "Une ligne par changement, avec le texte avant et après. « Comparer » dans Versions montre les deux mêmes versions côte à côte.",
                                        })}
                                    </Info>
                                </p>
                                {changements.lignes.length === 0 ? (
                                    <p className="border-t py-3 text-muted-foreground">{t({ en: "No change: the draft is the published version.", fr: "Aucun changement : le brouillon est la version publiée." })}</p>
                                ) : (
                                    <table className="w-full table-fixed" data-tableau="changements">
                                        <thead className="border-b text-xs text-muted-foreground">
                                            <tr>
                                                <th className="w-56 py-2 text-left font-normal">{t({ en: "Where", fr: "Où" })}</th>
                                                <th className="pl-4 text-left font-normal">{t({ en: "Before", fr: "Avant" })}</th>
                                                <th className="pl-4 text-left font-normal">{t({ en: "After", fr: "Après" })}</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {changements.lignes.map((l, i) => (
                                                <tr key={`${l.genre}-${l.ou}-${l.champ}-${i}`} className="align-top" data-changement={l.genre}>
                                                    <td className="py-3 pr-2">
                                                        <span className="block font-medium break-words">{l.ou}</span>
                                                        <span className="block text-xs text-muted-foreground">
                                                            {t(GENRES[l.genre])}
                                                            {l.champ ? ` · ${l.champ}` : ""}
                                                        </span>
                                                    </td>
                                                    <td className="py-3 pl-4 break-words whitespace-pre-wrap text-muted-foreground">{l.avant || "–"}</td>
                                                    <td className="py-3 pl-4 break-words whitespace-pre-wrap">{l.apres || "–"}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                                {changements.total > changements.lignes.length && (
                                    <p className="pt-2 text-xs text-muted-foreground">
                                        {t({
                                            en: `${changements.lignes.length} of ${changements.total} changes shown. « Compare » in Versions has them all.`,
                                            fr: `${changements.lignes.length} changements sur ${changements.total}. « Comparer » dans Versions les montre tous.`,
                                        })}
                                    </p>
                                )}
                                <Button variant="ghost" size="sm" className="-ml-2 mt-3" disabled={relectureEnCours || filDeRelecture !== null} onClick={() => void demanderLaRelecture()}>
                                    <Sparkles className="size-4" /> {t({ en: "Ask the builder to review", fr: "Demander au builder de relire" })}
                                </Button>
                                {filDeRelecture !== null && <CarteRelecture filId={filDeRelecture} />}
                            </>
                        )}
                    </div>
                )}
            </FenetreOnglets>
            {forcer && vue && (
                <FenetreOnglets centree
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
                                        <span className="text-foreground">{NOMS[c.cle] ? t(NOMS[c.cle]) : c.libelle}</span> · {c.problemes.map((p, i) => phraseDuServeur(p, c.details?.[i], langue)).join(" ; ")}
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
