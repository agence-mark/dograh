"use client";

/**
 * [.mark] N2 : les réglages propres à un type d'outil, dans la FENÊTRE de l'outil (plus de page d'édition à part).
 *
 *  - Fin d'appel : phrase dite (aucune, écrite, enregistrée), raison de fin demandée au modèle ;
 *  - Transfert vers un agent : l'agent, le message de passage, l'accueil de l'agent reçu ;
 *  - Transfert d'appel : destination fixe, résolue par une requête ou choisie selon le contexte (règles dans l'ordre),
 *    phrase dite, délai, état de l'appel après un transfert réussi ;
 *  - Requête HTTP : format et modèle du corps, valeurs fixes (jamais données par le modèle) ;
 *  - Serveur MCP : adresse, identifiant, outils gardés ;
 *  - Action d'un logiciel : l'action et ses règles.
 *
 * Chaque réglage garde sa clé dans ``definition.config`` (rien ne change côté serveur) : cet écran lit et écrit les mêmes
 * clés que l'ancienne page. ``validerConfig`` rejoue ses refus avant l'enregistrement.
 */
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { getWorkflowsSummaryApiV1WorkflowSummaryGet, listRecordingsApiV1WorkflowRecordingsGet } from "@/client/sdk.gen";
import type { RecordingResponseSchema } from "@/client/types.gen";
import { RecordingSelect } from "@/components/flow/TextOrAudioInput";
import { CredentialSelector } from "@/components/http";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { ConfigOutilIntegration } from "../connecteurs/ConfigOutilIntegration";
import { type ConfigIntegration, type Connecteurs } from "../connecteurs/useConnecteurs";
import { useLangue } from "../langue/langue";
import { BlocChamp, Champs, LigneChamp, Section, Segmente } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { LignesEditables } from "./LignesEditables";
import { type Config, liste, nombre, texte } from "./modele";

type Pose = (modifs: Config) => void;

export const RAISON_DE_FIN_PAR_DEFAUT = "The reason for ending the call (e.g., 'voicemail_detected', 'issue_resolved', 'customer_requested')";
export const MESSAGE_DE_PASSAGE_PAR_DEFAUT = "Let me connect you with the right person. One moment please.";

const ADRESSE_MCP = /^https?:\/\/.+/i;

type Source = "static" | "dynamic" | "context_mapping";
type Phrase = "none" | "custom" | "audio";
type Fixe = { name: string; type: string; value_template: string; required?: boolean };
type Donnee = { name: string; type: string; description: string; required?: boolean };
type Route = { context_value: string; destination: string };
type Regle = { context_path: string; routes: Route[] };

const TYPES_DE_VALEUR = ["string", "number", "boolean", "object", "array"];

/** Les enregistrements de l'organisation, lus une fois : la liste des phrases enregistrées qu'une phrase peut dire. */
function useEnregistrements(actif: boolean): RecordingResponseSchema[] {
    const [liste, setListe] = useState<RecordingResponseSchema[]>([]);
    useEffect(() => {
        if (!actif) return;
        let vivant = true;
        void listRecordingsApiV1WorkflowRecordingsGet({ query: {} }).then((r) => {
            if (vivant && r.data) setListe(r.data.recordings);
        });
        return () => {
            vivant = false;
        };
    }, [actif]);
    return liste;
}

/** Le refus de l'enregistrement, avec la même règle que l'ancienne page ; ``null`` quand tout est en ordre. */
export function validerConfig(categorie: string, config: Config, t: (m: { en: string; fr: string }) => string): string | null {
    if (categorie === "transfer_agent" && !texte(config, "workflow_id") && !nombre(config, "workflow_id", 0)) {
        return t({ en: "Choose the agent to transfer to.", fr: "Choisissez l'agent vers lequel transférer." });
    }
    if (categorie === "transfer_call") {
        const source = (texte(config, "destination_source") || (config.resolver ? "dynamic" : "static")) as Source;
        if (source === "static" && !texte(config, "destination").trim()) {
            return t({ en: "Enter a transfer destination.", fr: "Saisissez une destination de transfert." });
        }
        if (source === "dynamic") {
            const resolveur = (config.resolver ?? {}) as Record<string, unknown>;
            if (!/^https?:\/\/.+/i.test(String(resolveur.url ?? "").trim())) {
                return t({ en: "The resolver address must start with http:// or https://.", fr: "L'adresse du résolveur doit commencer par http:// ou https://." });
            }
            const donnees = liste<Donnee>(resolveur, "parameters");
            if (donnees.some((p) => !p.name.trim() || !p.description.trim())) {
                return t({ en: "Every resolver argument needs a name and a description.", fr: "Chaque argument du résolveur a besoin d'un nom et d'une description." });
            }
            const noms = donnees.map((p) => p.name.trim());
            if (new Set(noms).size !== noms.length) return t({ en: "Resolver argument names must be unique.", fr: "Les noms des arguments du résolveur doivent être uniques." });
            const fixes = liste<Fixe>(resolveur, "preset_parameters");
            if (fixes.some((p) => !p.name.trim() || !p.value_template.trim())) {
                return t({ en: "Every fixed value of the resolver needs a name and a value.", fr: "Chaque valeur fixe du résolveur a besoin d'un nom et d'une valeur." });
            }
        }
        if (source === "context_mapping") {
            const regles = liste<Regle>((config.context_mapping ?? {}) as Config, "rules");
            if (regles.length === 0) return t({ en: "Add at least one routing rule.", fr: "Ajoutez au moins une règle d'aiguillage." });
            for (const [i, r] of regles.entries()) {
                if (!r.context_path.trim()) return t({ en: `Name the context field of rule ${i + 1}.`, fr: `Nommez le champ du contexte de la règle ${i + 1}.` });
                if (r.routes.length === 0 || r.routes.some((x) => !x.context_value.trim() || !x.destination.trim())) {
                    return t({ en: `Complete the value-to-destination lines of rule ${i + 1}.`, fr: `Complétez les lignes valeur et destination de la règle ${i + 1}.` });
                }
                const valeurs = r.routes.map((x) => x.context_value.trim().toLocaleLowerCase());
                if (new Set(valeurs).size !== valeurs.length) return t({ en: `Values must be unique in rule ${i + 1}.`, fr: `Les valeurs doivent être uniques dans la règle ${i + 1}.` });
            }
        }
    }
    if (categorie === "mcp") {
        if (!texte(config, "url").trim()) return t({ en: "Enter the MCP server address.", fr: "Saisissez l'adresse du serveur MCP." });
        if (!ADRESSE_MCP.test(texte(config, "url").trim())) return t({ en: "The address must start with http:// or https://.", fr: "L'adresse doit commencer par http:// ou https://." });
    }
    if (categorie === "http_api") {
        const fixes = liste<Fixe>(config, "preset_parameters");
        if (fixes.some((p) => !p.name.trim() || !p.value_template.trim())) {
            return t({ en: "Every fixed value needs a name and a value.", fr: "Chaque valeur fixe a besoin d'un nom et d'une valeur." });
        }
        if (config.body_template !== undefined && config.body_template !== null && (typeof config.body_template !== "object" || Array.isArray(config.body_template))) {
            return t({ en: "The body model must be a JSON object.", fr: "Le modèle du corps doit être un objet JSON." });
        }
    }
    return null;
}

// --- phrase dite (fin d'appel, transfert) -------------------------------------------------------------------------------------------------

function BlocPhrase({ config, pose, enregistrements }: { config: Config; pose: Pose; enregistrements: RecordingResponseSchema[] }) {
    const { t } = useLangue();
    const mode = (texte(config, "messageType") || "none") as Phrase;
    const libelles: Record<Phrase, string> = {
        none: t({ en: "Nothing", fr: "Rien" }),
        custom: t({ en: "A sentence", fr: "Une phrase" }),
        audio: t({ en: "A recording", fr: "Un enregistrement" }),
    };
    return (
        <>
            <LigneChamp libelle={t({ en: "Said before", fr: "Dite avant" })} info={t({ en: "What the agent says before it acts.", fr: "Ce que l'agent dit avant d'agir." })}>
                <Segmente
                    valeur={libelles[mode]}
                    options={Object.values(libelles)}
                    changer={(v) => {
                        const choisi = (Object.keys(libelles) as Phrase[]).find((k) => libelles[k] === v) ?? "none";
                        pose({ messageType: choisi, customMessage: choisi === "custom" ? texte(config, "customMessage") : undefined, audioRecordingId: choisi === "audio" ? texte(config, "audioRecordingId") || undefined : undefined });
                    }}
                />
            </LigneChamp>
            {mode === "custom" && (
                <BlocChamp libelle={t({ en: "The sentence", fr: "La phrase" })}>
                    <Textarea rows={2} value={texte(config, "customMessage")} onChange={(e) => pose({ customMessage: e.target.value })} aria-label={t({ en: "Sentence said", fr: "Phrase dite" })} />
                </BlocChamp>
            )}
            {mode === "audio" && (
                <BlocChamp libelle={t({ en: "The recording", fr: "L'enregistrement" })}>
                    <RecordingSelect value={texte(config, "audioRecordingId")} onChange={(id) => pose({ audioRecordingId: id || undefined })} recordings={enregistrements} />
                </BlocChamp>
            )}
        </>
    );
}

// --- fin d'appel --------------------------------------------------------------------------------------------------------------------------

export function OngletFinAppel({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const enregistrements = useEnregistrements(true);
    const raison = config.endCallReason === true;
    return (
        <Champs>
            <BlocPhrase config={config} pose={pose} enregistrements={enregistrements} />
            <LigneChamp
                libelle={t({ en: "Ask the model for a reason", fr: "Demander une raison au modèle" })}
                info={t({ en: "The model gives why it ends the call; it is kept in the call record.", fr: "Le modèle dit pourquoi il met fin à l'appel ; la raison est gardée dans la fiche de l'appel." })}
            >
                <Switch
                    checked={raison}
                    onCheckedChange={(v) => pose({ endCallReason: v, endCallReasonDescription: v ? texte(config, "endCallReasonDescription") || RAISON_DE_FIN_PAR_DEFAUT : undefined })}
                    aria-label={t({ en: "Ask the model for a reason", fr: "Demander une raison au modèle" })}
                />
            </LigneChamp>
            {raison && (
                <BlocChamp libelle={t({ en: "What the reason must say", fr: "Ce que la raison doit dire" })}>
                    <Textarea rows={2} value={texte(config, "endCallReasonDescription")} onChange={(e) => pose({ endCallReasonDescription: e.target.value })} aria-label={t({ en: "Reason description", fr: "Description de la raison" })} />
                </BlocChamp>
            )}
        </Champs>
    );
}

// --- transfert vers un agent --------------------------------------------------------------------------------------------------------------

export function OngletTransfertAgent({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const [agents, setAgents] = useState<{ id: number; name: string }[] | null>(null);
    useEffect(() => {
        let vivant = true;
        void getWorkflowsSummaryApiV1WorkflowSummaryGet({}).then((r) => {
            if (vivant) setAgents(r.error || !r.data ? [] : r.data.map((w) => ({ id: w.id, name: w.name })));
        });
        return () => {
            vivant = false;
        };
    }, []);
    const choisi = config.workflow_id ? String(config.workflow_id) : "";
    return (
        <Champs>
            <LigneChamp
                libelle={t({ en: "Transfer to agent", fr: "Transférer à l'agent" })}
                info={t({ en: "The caller stays connected and hears a ringer while the next agent is prepared; the conversation so far is passed on.", fr: "L'appelant reste en ligne et entend une sonnerie pendant que l'agent suivant se prépare ; la conversation est transmise." })}
            >
                <Liste
                    valeur={choisi}
                    changer={(v) => pose({ workflow_id: v ? Number(v) : undefined })}
                    options={(agents ?? []).map((a) => ({ valeur: String(a.id), libelle: a.name }))}
                    placeholder={agents === null ? t({ en: "Loading…", fr: "Chargement…" }) : t({ en: "Choose an agent", fr: "Choisir un agent" })}
                    libelle={t({ en: "Transfer to agent", fr: "Transférer à l'agent" })}
                    className="w-64"
                    taille="default"
                />
            </LigneChamp>
            <BlocChamp libelle={t({ en: "Handover message", fr: "Message de passage" })} info={t({ en: "Said to the caller as the call is handed over.", fr: "Dit à l'appelant au moment du passage." })}>
                <Input value={typeof config.message === "string" ? config.message : MESSAGE_DE_PASSAGE_PAR_DEFAUT} onChange={(e) => pose({ message: e.target.value })} aria-label={t({ en: "Handover message", fr: "Message de passage" })} />
            </BlocChamp>
            <LigneChamp libelle={t({ en: "Play the destination agent's greeting", fr: "Dire l'accueil de l'agent reçu" })}>
                <Switch checked={config.play_greeting !== false} onCheckedChange={(v) => pose({ play_greeting: v })} aria-label={t({ en: "Play the destination agent's greeting", fr: "Dire l'accueil de l'agent reçu" })} />
            </LigneChamp>
        </Champs>
    );
}

// --- transfert d'appel --------------------------------------------------------------------------------------------------------------------

export function OngletTransfertAppel({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const enregistrements = useEnregistrements(true);
    const resolveur = (config.resolver ?? {}) as Config;
    const source = (texte(config, "destination_source") || (config.resolver ? "dynamic" : "static")) as Source;
    const libellesSource: Record<Source, string> = {
        static: t({ en: "Fixed number", fr: "Numéro fixe" }),
        dynamic: t({ en: "Looked up by a request", fr: "Cherché par une requête" }),
        context_mapping: t({ en: "By the call's context", fr: "Selon le contexte de l'appel" }),
    };
    const poseResolveur = (m: Config) => pose({ resolver: { type: "http", ...resolveur, ...m } });
    const regles = liste<Regle>((config.context_mapping ?? {}) as Config, "rules");
    const poseRegles = (rules: Regle[]) => pose({ context_mapping: { ...((config.context_mapping ?? {}) as Config), rules } });
    // Les en-têtes se tapent en lignes ; la ligne vide reste visible tant qu'elle n'est pas remplie.
    const [enTetes, setEnTetes] = useState<{ key: string; value: string }[]>(() => Object.entries((resolveur.headers ?? {}) as Record<string, string>).map(([key, value]) => ({ key, value })));
    const changerEnTetes = (l: { key: string; value: string }[]) => {
        setEnTetes(l);
        const objet = Object.fromEntries(l.filter((h) => h.key && h.value).map((h) => [h.key, h.value]));
        poseResolveur({ headers: Object.keys(objet).length ? objet : undefined });
    };

    return (
        <div>
            <Champs>
                <LigneChamp
                    libelle={t({ en: "Where the call goes", fr: "Où part l'appel" })}
                    info={t({ en: "A fixed number, a number looked up by a request when the call is transferred, or a number chosen from a value of the call's context.", fr: "Un numéro fixe, un numéro cherché par une requête au moment du transfert, ou un numéro choisi selon une valeur du contexte de l'appel." })}
                >
                    <Segmente
                        valeur={libellesSource[source]}
                        options={Object.values(libellesSource)}
                        changer={(v) => {
                            const choisie = (Object.keys(libellesSource) as Source[]).find((k) => libellesSource[k] === v) ?? "static";
                            pose({
                                destination_source: choisie,
                                destination: choisie === "static" ? texte(config, "destination") : "",
                                resolver: choisie === "dynamic" ? { type: "http", ...resolveur } : undefined,
                                context_mapping: choisie === "context_mapping" ? { ...((config.context_mapping ?? {}) as Config), rules: regles.length ? regles : [{ context_path: "", routes: [{ context_value: "", destination: "" }] }] } : undefined,
                            });
                        }}
                    />
                </LigneChamp>
                {source === "static" && (
                    <BlocChamp libelle={t({ en: "Destination", fr: "Destination" })} info={t({ en: "E.164 number (+33…), SIP endpoint or in-group.", fr: "Numéro E.164 (+33…), point SIP ou groupe." })}>
                        <Input value={texte(config, "destination")} onChange={(e) => pose({ destination: e.target.value })} placeholder="+33…" aria-label={t({ en: "Transfer destination", fr: "Destination du transfert" })} />
                    </BlocChamp>
                )}
                <BlocPhrase config={config} pose={pose} enregistrements={enregistrements} />
                <LigneChamp libelle={t({ en: "Ring for (seconds)", fr: "Sonner pendant (secondes)" })}>
                    <Input
                        className="h-8 w-24 text-right"
                        value={String(nombre(config, "timeout", 30))}
                        onChange={(e) => pose({ timeout: Math.min(120, Math.max(5, Number(e.target.value.replace(/\D/g, "")) || 5)) })}
                        aria-label={t({ en: "Ring duration", fr: "Durée de sonnerie" })}
                    />
                </LigneChamp>
                <LigneChamp
                    libelle={t({ en: "Call disposition after a successful transfer", fr: "État de l'appel après un transfert réussi" })}
                    info={t({ en: "Recorded only when the transfer succeeds.", fr: "Noté seulement quand le transfert réussit." })}
                >
                    <Input className="h-8 w-48" maxLength={64} value={texte(config, "call_disposition")} onChange={(e) => pose({ call_disposition: e.target.value || undefined })} aria-label={t({ en: "Call disposition after a successful transfer", fr: "État de l'appel après un transfert réussi" })} />
                </LigneChamp>
            </Champs>

            {source === "dynamic" && (
                <Section titre={t({ en: "The request that finds the number", fr: "La requête qui trouve le numéro" })}>
                    <Champs>
                        <BlocChamp libelle={t({ en: "Resolver address", fr: "Adresse du résolveur" })}>
                            <Input value={texte(resolveur, "url")} onChange={(e) => poseResolveur({ url: e.target.value })} placeholder="https://…" aria-label={t({ en: "Resolver address", fr: "Adresse du résolveur" })} />
                        </BlocChamp>
                        <BlocChamp libelle={t({ en: "Credential", fr: "Identifiant" })}>
                            <CredentialSelector
                                value={texte(resolveur, "credential_uuid")}
                                onChange={(v: string) => poseResolveur({ credential_uuid: v || undefined })}
                                showLabel={false}
                                placeholder={t({ en: "No authentication", fr: "Aucune authentification" })}
                                description=""
                            />
                        </BlocChamp>
                        <LigneChamp libelle={t({ en: "Timeout (ms)", fr: "Délai (ms)" })}>
                            <Input className="h-8 w-28 text-right" value={String(nombre(resolveur, "timeout_ms", 3000))} onChange={(e) => poseResolveur({ timeout_ms: Math.max(100, Number(e.target.value.replace(/\D/g, "")) || 100) })} aria-label={t({ en: "Resolver timeout", fr: "Délai du résolveur" })} />
                        </LigneChamp>
                        <BlocChamp libelle={t({ en: "Sentence while it looks", fr: "Phrase pendant la recherche" })}>
                            <Input value={texte(resolveur, "wait_message")} onChange={(e) => poseResolveur({ wait_message: e.target.value || undefined })} aria-label={t({ en: "Wait sentence", fr: "Phrase d'attente" })} />
                        </BlocChamp>
                        <BlocChamp libelle={t({ en: "Headers", fr: "En-têtes" })}>
                            <LignesEditables<{ key: string; value: string }>
                                colonnes={[t({ en: "Name", fr: "Nom" }), t({ en: "Value", fr: "Valeur" })]}
                                lignes={enTetes}
                                changer={changerEnTetes}
                                vide={t({ en: "No header.", fr: "Aucun en-tête." })}
                                nouvelle={() => ({ key: "", value: "" })}
                                ajouter={t({ en: "Add a header", fr: "Ajouter un en-tête" })}
                                rendu={(h, maj) => [
                                    <Input key="k" className="h-8" value={h.key} onChange={(e) => maj({ key: e.target.value })} aria-label={t({ en: "Header name", fr: "Nom de l'en-tête" })} />,
                                    <Input key="v" className="h-8" value={h.value} onChange={(e) => maj({ value: e.target.value })} aria-label={t({ en: "Header value", fr: "Valeur de l'en-tête" })} />,
                                ]}
                            />
                        </BlocChamp>
                        <BlocChamp libelle={t({ en: "Arguments the model gives", fr: "Arguments donnés par le modèle" })}>
                            <LignesDonnees lignes={liste<Donnee>(resolveur, "parameters")} changer={(l) => poseResolveur({ parameters: l.length ? l : undefined })} />
                        </BlocChamp>
                        <BlocChamp libelle={t({ en: "Fixed values", fr: "Valeurs fixes" })} info={t({ en: "Values the model never sees: a text with variables such as {{initial_context.x}}.", fr: "Valeurs que le modèle ne voit jamais : un texte avec des variables comme {{initial_context.x}}." })}>
                            <LignesFixes lignes={liste<Fixe>(resolveur, "preset_parameters")} changer={(l) => poseResolveur({ preset_parameters: l.length ? l : undefined })} />
                        </BlocChamp>
                    </Champs>
                </Section>
            )}

            {source === "context_mapping" && (
                <Section
                    titre={t({ en: "Ordered context routing", fr: "Aiguillage selon le contexte, dans l'ordre" })}
                    info={t({ en: "The first rule whose value matches gives the destination; otherwise the fallback.", fr: "La première règle dont la valeur correspond donne la destination ; sinon le repli." })}
                >
                    <div className="space-y-4">
                        {regles.map((r, i) => (
                            <div key={i} className="rounded-lg border p-3">
                                <div className="flex items-center gap-2">
                                    <Input
                                        className="h-8"
                                        value={r.context_path}
                                        onChange={(e) => poseRegles(regles.map((x, j) => (j === i ? { ...x, context_path: e.target.value } : x)))}
                                        placeholder={t({ en: "Context field", fr: "Champ du contexte" })}
                                        aria-label={`${t({ en: "Context field", fr: "Champ du contexte" })} ${i + 1}`}
                                    />
                                    <Button variant="ghost" size="sm" disabled={i === 0} aria-label={`${t({ en: "Move rule up", fr: "Monter la règle" })} ${i + 1}`} onClick={() => poseRegles(permuter(regles, i, i - 1))}>
                                        ↑
                                    </Button>
                                    <Button variant="ghost" size="sm" disabled={i === regles.length - 1} aria-label={`${t({ en: "Move rule down", fr: "Descendre la règle" })} ${i + 1}`} onClick={() => poseRegles(permuter(regles, i, i + 1))}>
                                        ↓
                                    </Button>
                                    <button type="button" className="cursor-pointer text-muted-foreground hover:text-foreground" aria-label={`${t({ en: "Remove rule", fr: "Retirer la règle" })} ${i + 1}`} onClick={() => poseRegles(regles.filter((_, j) => j !== i))}>
                                        <Trash2 className="size-4" />
                                    </button>
                                </div>
                                <LignesEditables<Route>
                                    colonnes={[t({ en: "Value", fr: "Valeur" }), t({ en: "Destination", fr: "Destination" })]}
                                    lignes={r.routes}
                                    changer={(routes) => poseRegles(regles.map((x, j) => (j === i ? { ...x, routes } : x)))}
                                    vide={t({ en: "No line.", fr: "Aucune ligne." })}
                                    nouvelle={() => ({ context_value: "", destination: "" })}
                                    ajouter={t({ en: "Add a line", fr: "Ajouter une ligne" })}
                                    rendu={(x, maj, k) => [
                                        <Input key="v" className="h-8" value={x.context_value} onChange={(e) => maj({ context_value: e.target.value })} aria-label={`${t({ en: "Rule", fr: "Règle" })} ${i + 1} ${t({ en: "value", fr: "valeur" })} ${k + 1}`} />,
                                        <Input key="d" className="h-8" value={x.destination} onChange={(e) => maj({ destination: e.target.value })} aria-label={`${t({ en: "Rule", fr: "Règle" })} ${i + 1} ${t({ en: "destination", fr: "destination" })} ${k + 1}`} />,
                                    ]}
                                />
                            </div>
                        ))}
                        <Button variant="ghost" size="sm" className="-ml-2" onClick={() => poseRegles([...regles, { context_path: "", routes: [{ context_value: "", destination: "" }] }])}>
                            <Plus className="size-4" /> {t({ en: "Add a routing rule", fr: "Ajouter une règle d'aiguillage" })}
                        </Button>
                    </div>
                    <BlocChamp libelle={t({ en: "Fallback destination", fr: "Destination de repli" })} info={t({ en: "Used when no rule matched.", fr: "Utilisée quand aucune règle ne correspond." })}>
                        <Input
                            value={texte((config.context_mapping ?? {}) as Config, "fallback_destination")}
                            onChange={(e) => pose({ context_mapping: { ...((config.context_mapping ?? {}) as Config), rules: regles, fallback_destination: e.target.value || undefined } })}
                            aria-label={t({ en: "Fallback destination", fr: "Destination de repli" })}
                        />
                    </BlocChamp>
                </Section>
            )}
        </div>
    );
}

function permuter<T>(l: T[], de: number, vers: number): T[] {
    const copie = [...l];
    [copie[de], copie[vers]] = [copie[vers], copie[de]];
    return copie;
}

// --- lignes communes : valeurs que donne le modèle, valeurs fixes -----------------------------------------------------------------------------

export function LignesDonnees({ lignes, changer }: { lignes: Donnee[]; changer: (l: Donnee[]) => void }) {
    const { t } = useLangue();
    return (
        <LignesEditables<Donnee>
            colonnes={[t({ en: "Name", fr: "Nom" }), t({ en: "Type", fr: "Type" }), t({ en: "Description", fr: "Description" })]}
            lignes={lignes}
            changer={changer}
            vide={t({ en: "No argument.", fr: "Aucun argument." })}
            nouvelle={() => ({ name: "", type: "string", description: "", required: true })}
            ajouter={t({ en: "Add an argument", fr: "Ajouter un argument" })}
            rendu={(p, maj) => [
                <Input key="n" className="h-8" value={p.name} onChange={(e) => maj({ name: e.target.value })} aria-label={t({ en: "Argument name", fr: "Nom de l'argument" })} />,
                <Liste key="t" valeur={p.type} changer={(v) => maj({ type: v })} options={TYPES_DE_VALEUR} className="w-28" />,
                <Input key="d" className="h-8" value={p.description} onChange={(e) => maj({ description: e.target.value })} aria-label={t({ en: "Argument description", fr: "Description de l'argument" })} />,
            ]}
        />
    );
}

export function LignesFixes({ lignes, changer }: { lignes: Fixe[]; changer: (l: Fixe[]) => void }) {
    const { t } = useLangue();
    return (
        <LignesEditables<Fixe>
            colonnes={[t({ en: "Name", fr: "Nom" }), t({ en: "Type", fr: "Type" }), t({ en: "Value", fr: "Valeur" })]}
            lignes={lignes}
            changer={changer}
            vide={t({ en: "No fixed value.", fr: "Aucune valeur fixe." })}
            nouvelle={() => ({ name: "", type: "string", value_template: "", required: true })}
            ajouter={t({ en: "Add a fixed value", fr: "Ajouter une valeur fixe" })}
            rendu={(p, maj) => [
                <Input key="n" className="h-8" value={p.name} onChange={(e) => maj({ name: e.target.value })} aria-label={t({ en: "Fixed value name", fr: "Nom de la valeur fixe" })} />,
                <Liste key="t" valeur={p.type} changer={(v) => maj({ type: v })} options={TYPES_DE_VALEUR} className="w-28" />,
                <Input key="v" className="h-8" value={p.value_template} onChange={(e) => maj({ value_template: e.target.value })} aria-label={t({ en: "Fixed value", fr: "Valeur fixe" })} />,
            ]}
        />
    );
}

// --- requête HTTP : corps et valeurs fixes (s'ajoutent à l'onglet Paramètres) ---------------------------------------------------------------

export function BlocCorpsEtValeursFixes({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const methode = (texte(config, "method") || "POST").toUpperCase();
    const accepteUnCorps = ["POST", "PUT", "PATCH"].includes(methode);
    const modele = config.body_template && typeof config.body_template === "object" ? config.body_template : null;
    const actif = config.body_template !== undefined && config.body_template !== null;
    // Le JSON se tape tel quel ; il ne rentre dans la définition que lorsqu'il est un objet valide.
    const [saisie, setSaisie] = useState(modele ? JSON.stringify(modele, null, 2) : "{}");
    const [invalide, setInvalide] = useState(false);
    return (
        <>
            {accepteUnCorps && (
                <>
                    <LigneChamp
                        libelle={t({ en: "Body format", fr: "Format du corps" })}
                        info={t({ en: "JSON or form (key=value).", fr: "JSON ou formulaire (clé=valeur)." })}
                    >
                        <Segmente valeur={texte(config, "body_format") === "form" ? "form" : "json"} options={["json", "form"]} changer={(v) => pose({ body_format: v })} />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "Body model", fr: "Modèle du corps" })}
                        info={t({ en: "A JSON object with variables such as {{param}} or {{initial_context.x}}; without it the parameters of the body are sent as they are.", fr: "Un objet JSON avec des variables comme {{param}} ou {{initial_context.x}} ; sans lui, les paramètres du corps partent tels quels." })}
                    >
                        <Switch
                            checked={actif}
                            onCheckedChange={(v) => {
                                setInvalide(false);
                                if (v) {
                                    setSaisie("{}");
                                    pose({ body_template: {} });
                                } else pose({ body_template: undefined });
                            }}
                            aria-label={t({ en: "Use a body model", fr: "Utiliser un modèle de corps" })}
                        />
                    </LigneChamp>
                    {actif && (
                        <BlocChamp libelle={t({ en: "The model (JSON)", fr: "Le modèle (JSON)" })}>
                            <Textarea
                                rows={5}
                                className="font-mono text-xs"
                                value={saisie}
                                onChange={(e) => {
                                    setSaisie(e.target.value);
                                    try {
                                        const v = JSON.parse(e.target.value);
                                        if (v && typeof v === "object" && !Array.isArray(v)) {
                                            setInvalide(false);
                                            pose({ body_template: v });
                                        } else setInvalide(true);
                                    } catch {
                                        setInvalide(true);
                                    }
                                }}
                                aria-label={t({ en: "Body model", fr: "Modèle du corps" })}
                                aria-invalid={invalide}
                            />
                            {invalide && <p className="text-sm text-destructive">{t({ en: "Not a JSON object: the last valid model is kept.", fr: "Ce n'est pas un objet JSON : le dernier modèle valide est gardé." })}</p>}
                        </BlocChamp>
                    )}
                </>
            )}
            <BlocChamp
                libelle={t({ en: "Fixed values", fr: "Valeurs fixes" })}
                info={t({ en: "Sent with every request, never given by the model: a text with variables such as {{initial_context.x}}.", fr: "Envoyées à chaque requête, jamais données par le modèle : un texte avec des variables comme {{initial_context.x}}." })}
            >
                <LignesFixes lignes={liste<Fixe>(config, "preset_parameters")} changer={(l) => pose({ preset_parameters: l.length ? l : undefined })} />
            </BlocChamp>
        </>
    );
}

// --- serveur MCP --------------------------------------------------------------------------------------------------------------------------

export function OngletServeurMcp({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const filtre = liste<string>(config, "tools_filter");
    return (
        <Champs>
            <BlocChamp libelle={t({ en: "Server address", fr: "Adresse du serveur" })} info={t({ en: "Its tools become available to the agent.", fr: "Ses outils deviennent disponibles pour l'agent." })}>
                <Input value={texte(config, "url")} onChange={(e) => pose({ url: e.target.value })} placeholder="https://…" aria-label={t({ en: "MCP server address", fr: "Adresse du serveur MCP" })} />
            </BlocChamp>
            <BlocChamp libelle={t({ en: "Credential", fr: "Identifiant" })}>
                <CredentialSelector
                    value={texte(config, "credential_uuid")}
                    onChange={(v: string) => pose({ credential_uuid: v || undefined })}
                    showLabel={false}
                    placeholder={t({ en: "No authentication", fr: "Aucune authentification" })}
                    description=""
                />
            </BlocChamp>
            <BlocChamp libelle={t({ en: "Tools kept", fr: "Outils gardés" })} info={t({ en: "Names separated by commas. Empty: every tool of the server.", fr: "Des noms séparés par des virgules. Vide : tous les outils du serveur." })}>
                <Input
                    defaultValue={filtre.join(", ")}
                    onBlur={(e) => {
                        const l = e.target.value.split(",").map((x) => x.trim()).filter(Boolean);
                        pose({ tools_filter: l.length ? l : undefined });
                    }}
                    aria-label={t({ en: "Tools kept", fr: "Outils gardés" })}
                />
            </BlocChamp>
        </Champs>
    );
}

// --- action d'un logiciel -----------------------------------------------------------------------------------------------------------------

export function OngletActionLogiciel({ config, pose, connecteurs, valide }: { config: Config; pose: Pose; connecteurs: Connecteurs; valide: (v: boolean) => void }) {
    const { t } = useLangue();
    if (!config.connecteur) {
        return <p className="py-3 text-sm text-destructive">{t({ en: "This tool has no action: create it again from « Tools ».", fr: "Cet outil n'a pas d'action : recréez-le depuis « Outils »." })}</p>;
    }
    const sources = liste<string>(config, "sources_champs");
    const toutes = ["fiche", "traces", "greffier"];
    const etiquettes: Record<string, string> = {
        fiche: t({ en: "The record", fr: "La fiche" }),
        traces: t({ en: "The reading modules' traces", fr: "Les traces des modules de lecture" }),
        greffier: t({ en: "The clerk", fr: "Le greffier" }),
    };
    const actives = config.sources_champs === undefined ? toutes : sources;
    return (
        <div>
            <ConfigOutilIntegration
                connecteurs={connecteurs}
                valeur={config as unknown as ConfigIntegration}
                onChange={(v) => pose(v as unknown as Config)}
                onValide={valide}
            />
            <Champs>
                <BlocChamp
                    libelle={t({ en: "Where the required fields are looked for", fr: "Où chercher les champs requis" })}
                    info={t({ en: "In this order: the record, the traces of the reading modules, then the clerk's pass.", fr: "Dans cet ordre : la fiche, les traces des modules de lecture, puis le passage du greffier." })}
                >
                    <div className="flex flex-wrap gap-4">
                        {toutes.map((o) => (
                            <label key={o} className="flex cursor-pointer items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    checked={actives.includes(o)}
                                    onChange={(e) => pose({ sources_champs: toutes.filter((x) => (x === o ? e.target.checked : actives.includes(x))) })}
                                />
                                {etiquettes[o]}
                            </label>
                        ))}
                    </div>
                </BlocChamp>
            </Champs>
        </div>
    );
}

/** Les anciens en-têtes simples (nom, valeur) d'une requête créée avant les en-têtes à secret : affichés seulement s'il en reste. */
export function BlocEntetesAnciens({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const anciens = Object.entries((config.headers ?? {}) as Record<string, string>);
    const [lignes, setLignes] = useState<{ key: string; value: string }[]>(() => anciens.map(([key, value]) => ({ key, value })));
    if (anciens.length === 0 && lignes.length === 0) return null;
    const changer = (l: { key: string; value: string }[]) => {
        setLignes(l);
        const objet = Object.fromEntries(l.filter((h) => h.key && h.value).map((h) => [h.key, h.value]));
        pose({ headers: Object.keys(objet).length ? objet : undefined });
    };
    return (
        <BlocChamp libelle={t({ en: "Plain headers (older)", fr: "En-têtes simples (anciens)" })} info={t({ en: "Sent as written with every request; new headers go in « Headers » above.", fr: "Envoyés tels quels à chaque requête ; les nouveaux vont dans « En-têtes » ci-dessus." })}>
            <LignesEditables<{ key: string; value: string }>
                colonnes={[t({ en: "Name", fr: "Nom" }), t({ en: "Value", fr: "Valeur" })]}
                lignes={lignes}
                changer={changer}
                vide={t({ en: "No header.", fr: "Aucun en-tête." })}
                nouvelle={() => ({ key: "", value: "" })}
                ajouter={t({ en: "Add a header", fr: "Ajouter un en-tête" })}
                rendu={(h, maj) => [
                    <Input key="k" className="h-8" value={h.key} onChange={(e) => maj({ key: e.target.value })} aria-label={t({ en: "Plain header name", fr: "Nom de l'en-tête simple" })} />,
                    <Input key="v" className="h-8" value={h.value} onChange={(e) => maj({ value: e.target.value })} aria-label={t({ en: "Plain header value", fr: "Valeur de l'en-tête simple" })} />,
                ]}
            />
        </BlocChamp>
    );
}
