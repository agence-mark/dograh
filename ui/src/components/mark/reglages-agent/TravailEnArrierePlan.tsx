"use client";

/**
 * [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8, D10, D13): the « Background work » settings of an
 * agent, in the Services theme (« Briques »), next to « Own brain ».
 *
 * A second brain that works with tools while the conversation goes on, then hands its result back to
 * the agent. Five settings, all off or empty by default (the agent plays the call of before):
 *
 *   - `travail_actif`      the switch;
 *   - `travail_llm`        its model, chosen freely, provider included (the same generated form as the
 *                          clerk's; an empty field comes from the conversation model);
 *   - `travail_consigne`   its instructions (empty: none are added by the code, to be written with the team);
 *   - `travail_outils`     the tools it may use (the catalogue minus transfers and the end of the call:
 *                          the code never gives it those);
 *   - `travail_delai_max_s` how long it may work on one request.
 *
 * The theme has no Save button of its own (convention E6, « Briques »): each part saves at once, like
 * « Own brain » next to it. The model block's key comes back MASKED from the server and is restored on
 * save, as the clerk's is.
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { listToolsApiV1ToolsGet } from "@/client/sdk.gen";
import type { ToolResponse } from "@/client/types.gen";
import { ToolSelector } from "@/components/flow/ToolSelector";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import type { GreffierLlm, WorkflowConfigurations } from "@/types/workflow-configurations";

import { attributsDeBorne, texteHorsBornes } from "../bornes-reglages";
import { ChampReglage, texteBornes } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { useLangue } from "../langue/langue";
import { type BlocModele, ChampsFournisseurLlm } from "../modeles/ChampsFournisseurLlm";
import { type Enregistrer, RAPPEL_PUBLICATION_TEXTE } from "./enregistrement";
import { CerveauDeRepli } from "./GardeDuModele";

export const DELAI_PAR_DEFAUT_S = 60;
/** What the code never gives the background brain: it acts on the call itself. */
export const CATEGORIES_JAMAIS_DONNEES = ["transfer_call", "transfer_agent", "end_call", "mcp"];

/** The tools the selector offers: the catalogue minus what acts on the call. */
export const outilsOffertsAuFond = (outils: ToolResponse[]): ToolResponse[] =>
    outils.filter((o) => !CATEGORIES_JAMAIS_DONNEES.includes(String(o.category)));

export const TravailEnArrierePlan = ({
    resolue,
    workflowName,
    onSave,
}: {
    resolue: WorkflowConfigurations;
    workflowName: string;
    onSave: Enregistrer;
}) => {
    const { t } = useLangue();
    const { user, loading: chargementAuth } = useAuth();
    const rappel = t(RAPPEL_PUBLICATION_TEXTE);
    const actif = resolue.travail_actif === true;
    const modeleEnregistre = useMemo(() => (resolue.travail_llm ?? null) as GreffierLlm | null, [resolue.travail_llm]);
    const consigneEnregistree = resolue.travail_consigne ?? "";
    const outilsEnregistres = resolue.travail_outils ?? [];
    const delaiEnregistre = resolue.travail_delai_max_s ?? DELAI_PAR_DEFAUT_S;

    const [enregistrement, setEnregistrement] = useState(false);
    const enregistrer = async (patch: Partial<WorkflowConfigurations>, message: { en: string; fr: string }) => {
        setEnregistrement(true);
        try {
            await onSave({ ...resolue, ...patch }, workflowName);
            toast.success(`${t(message)} ${rappel}`);
        } finally {
            setEnregistrement(false);
        }
    };

    // ---- The model and the instructions (one dialog, like the clerk's) ----
    const [fenetre, setFenetre] = useState(false);
    const [blocEdite, setBlocEdite] = useState<BlocModele>({});
    const [consigne, setConsigne] = useState(consigneEnregistree);
    const modeleRelu = JSON.stringify([modeleEnregistre, consigneEnregistree]);
    useEffect(() => {
        const [bloc, texte] = JSON.parse(modeleRelu) as [GreffierLlm | null, string];
        setBlocEdite((bloc ?? {}) as BlocModele);
        setConsigne(texte);
    }, [modeleRelu]);
    const cleEnregistree = typeof blocEdite.api_key === "string" && blocEdite.api_key !== "";
    const enregistrerLeModele = async () => {
        await enregistrer(
            {
                travail_llm: Object.keys(blocEdite).length > 0 ? (blocEdite as GreffierLlm) : null,
                travail_consigne: consigne.trim() === "" ? null : consigne,
            },
            { en: "Background brain saved.", fr: "Cerveau de fond enregistré." },
        );
        setFenetre(false);
    };

    // ---- The tools ----
    const [outils, setOutils] = useState<ToolResponse[] | null>(null);
    useEffect(() => {
        if (!actif || chargementAuth || !user) return;
        let vivant = true;
        void listToolsApiV1ToolsGet({}).then((r) => {
            if (vivant) setOutils(outilsOffertsAuFond((r.data as ToolResponse[] | undefined) ?? []));
        });
        return () => {
            vivant = false;
        };
    }, [actif, chargementAuth, user]);
    const [outilsChoisis, setOutilsChoisis] = useState<string[]>(outilsEnregistres);
    const outilsRelus = JSON.stringify(outilsEnregistres);
    useEffect(() => setOutilsChoisis(JSON.parse(outilsRelus) as string[]), [outilsRelus]);

    // ---- The longest work ----
    const [delai, setDelai] = useState(String(delaiEnregistre));
    useEffect(() => setDelai(String(delaiEnregistre)), [delaiEnregistre]);
    const delaiNombre = delai.trim() === "" ? Number.NaN : Number(delai.replace(",", "."));
    const erreurDelai = texteHorsBornes("travail_delai_max_s", delaiNombre) ?? (Number.isInteger(delaiNombre) ? null : { en: "Enter a whole number of seconds.", fr: "Saisissez un nombre entier de secondes." });

    return (
        <Intertitre
            id="briques-travail"
            titre={{ en: "Background work", fr: "Travail en arrière-plan" }}
            description={{
                en: "A second brain works with tools while the conversation goes on, then hands its result back to the agent.",
                fr: "Un second cerveau travaille avec des outils pendant que la conversation continue, puis rend son résultat à l'agent.",
            }}
        >
            <ChampReglage
                cle="travail_actif"
                idControle="travail_actif"
                libelle={{ en: "Background work", fr: "Travail en arrière-plan" }}
                aides={[
                    {
                        en: "On: the agent gets one more tool to hand a request to the background brain. The microphone is never cut while it works; the agent keeps talking, then says the result. Off: nothing changes.",
                        fr: "Allumé : l'agent reçoit un outil de plus pour confier une demande au cerveau de fond. Le micro n'est jamais coupé pendant qu'il travaille ; l'agent continue de parler, puis dit le résultat. Éteint : rien ne change.",
                    },
                ]}
                disposition="ligne"
            >
                <Switch
                    id="travail_actif"
                    checked={actif}
                    disabled={enregistrement}
                    onCheckedChange={(coche) =>
                        void enregistrer(
                            { travail_actif: coche },
                            coche
                                ? { en: "Background work on.", fr: "Travail en arrière-plan allumé." }
                                : { en: "Background work off.", fr: "Travail en arrière-plan éteint." },
                        )
                    }
                />
            </ChampReglage>

            {actif && (
                <>
                    <ChampReglage
                        cle="travail_llm"
                        libelle={{ en: "Background model", fr: "Modèle de fond" }}
                        aides={[
                            {
                                en: "Chosen freely, provider included. An empty field comes from the conversation model; an empty key uses the conversation's key.",
                                fr: "Choisi librement, fournisseur compris. Un champ vide reprend le modèle de la conversation ; une clé vide reprend celle de la conversation.",
                            },
                        ]}
                    >
                        <div className="flex items-center justify-between gap-3 rounded border p-3 text-sm">
                            <span>
                                {(typeof modeleEnregistre?.model === "string" && modeleEnregistre.model) ||
                                    t({ en: "Conversation model", fr: "Modèle de la conversation" })}{" "}
                                ·{" "}
                                {typeof modeleEnregistre?.api_key === "string" && modeleEnregistre.api_key !== ""
                                    ? t({ en: "own key", fr: "clé propre" })
                                    : t({ en: "conversation's key", fr: "clé de la conversation" })}
                            </span>
                            <Button variant="outline" size="sm" onClick={() => setFenetre(true)}>
                                {t({ en: "Configure the background brain", fr: "Régler le cerveau de fond" })}
                            </Button>
                        </div>
                    </ChampReglage>

                    {/* fiabilite-orchestration, lot 4 (F20, F26): the background brain's fallback, troubleshooting only. */}
                    <CerveauDeRepli
                        cle="travail_llm_repli"
                        idPrefixe="travail_repli"
                        bouton={{ en: "Configure the background fallback brain", fr: "Régler le cerveau de repli du fond" }}
                        libelle={{ en: "Background fallback brain (troubleshooting)", fr: "Cerveau de repli du fond (dépannage)" }}
                        enregistre={(resolue.travail_llm_repli ?? null) as GreffierLlm | null}
                        enregistrer={enregistrer}
                        desactive={enregistrement}
                    />

                    <ChampReglage
                        cle="travail_consigne"
                        libelle={{ en: "Background instructions", fr: "Consigne du fond" }}
                        aides={[
                            {
                                en: "What the background brain is told before each request. Empty by default: the code adds none, they are written with the team.",
                                fr: "Ce qui est dit au cerveau de fond avant chaque demande. Vide par défaut : le code n'en ajoute aucune, elle se rédige avec l'équipe.",
                            },
                        ]}
                    >
                        <div className="flex items-center justify-between gap-3 rounded border p-3 text-sm">
                            <span>
                                {consigneEnregistree.trim() === ""
                                    ? t({ en: "No instructions", fr: "Aucune consigne" })
                                    : t({ en: "Own instructions", fr: "Consigne propre" })}
                            </span>
                            <Button variant="outline" size="sm" onClick={() => setFenetre(true)}>
                                {t({ en: "Edit the instructions", fr: "Modifier la consigne" })}
                            </Button>
                        </div>
                    </ChampReglage>

                    <ChampReglage
                        cle="travail_outils"
                        libelle={{ en: "Allowed tools", fr: "Outils autorisés" }}
                        aides={[
                            {
                                en: "The tools of your catalogue the background brain may use. Call transfers, agent handoffs and the end of the call are never given to it. Tools of an MCP server are not offered yet.",
                                fr: "Les outils de votre catalogue que le cerveau de fond peut utiliser. Les transferts d'appel, les passations et la fin d'appel ne lui sont jamais donnés. Les outils d'un serveur MCP ne sont pas encore proposés.",
                            },
                        ]}
                    >
                        <ToolSelector
                            value={outilsChoisis}
                            tools={outils ?? []}
                            showLabel={false}
                            disabled={enregistrement}
                            onChange={(uuids) => {
                                setOutilsChoisis(uuids);
                                void enregistrer(
                                    { travail_outils: uuids },
                                    { en: "Allowed tools saved.", fr: "Outils autorisés enregistrés." },
                                );
                            }}
                        />
                    </ChampReglage>

                    <ChampReglage
                        cle="travail_delai_max_s"
                        idControle="travail_delai_max_s"
                        libelle={{ en: "Max duration (s)", fr: "Durée maximale (s)" }}
                        bornes={texteBornes("travail_delai_max_s")}
                        erreur={erreurDelai}
                        aides={[
                            {
                                en: "Past this duration, the work is dropped and the agent is told it did not finish.",
                                fr: "Au-delà de cette durée, le travail est abandonné et l'agent est prévenu qu'il n'a pas abouti.",
                            },
                        ]}
                    >
                        <div className="flex items-center gap-2">
                            <Input
                                id="travail_delai_max_s"
                                type="number"
                                inputMode="numeric"
                                className="max-w-32"
                                {...attributsDeBorne("travail_delai_max_s")}
                                value={delai}
                                onChange={(e) => setDelai(e.target.value)}
                            />
                            <Button
                                variant="outline"
                                size="sm"
                                disabled={enregistrement || erreurDelai !== null || delaiNombre === delaiEnregistre}
                                onClick={() =>
                                    void enregistrer(
                                        { travail_delai_max_s: delaiNombre },
                                        { en: "Max duration saved.", fr: "Durée maximale enregistrée." },
                                    )
                                }
                            >
                                {t({ en: "Save the duration", fr: "Enregistrer la durée" })}
                            </Button>
                        </div>
                    </ChampReglage>
                </>
            )}

            <Dialog open={fenetre} onOpenChange={setFenetre}>
                <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>{t({ en: "Background brain", fr: "Cerveau de fond" })}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: "The model that works with tools while the conversation goes on. Empty fields come from the conversation model.",
                                fr: "Le modèle qui travaille avec des outils pendant que la conversation continue. Un champ vide reprend le modèle de la conversation.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        <ChampsFournisseurLlm bloc={blocEdite} onChange={setBlocEdite} idPrefixe="travail" />
                        <div className="space-y-1">
                            <div className="flex items-center justify-between gap-2">
                                <label htmlFor="travail_consigne" className="text-sm font-medium">
                                    {t({ en: "Instructions", fr: "Consigne" })}
                                </label>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={consigne === ""}
                                    onClick={() => setConsigne("")}
                                >
                                    {t({ en: "Back to the default", fr: "Revenir au défaut" })}
                                </Button>
                            </div>
                            <Textarea
                                id="travail_consigne"
                                rows={10}
                                value={consigne}
                                onChange={(e) => setConsigne(e.target.value)}
                                className="font-mono text-xs"
                            />
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "Empty by default: the code adds no instructions of its own, they are written with the team. The request it works on, and its tools, are always given by the code.",
                                    fr: "Vide par défaut : le code n'ajoute aucune consigne, elle se rédige avec l'équipe. La demande sur laquelle il travaille et ses outils sont toujours donnés par le code.",
                                })}
                            </p>
                            <p className="text-xs text-muted-foreground" data-cle-propre={cleEnregistree ? "oui" : "non"}>
                                {cleEnregistree
                                    ? t({ en: "Own API key saved (shown masked).", fr: "Clé API propre enregistrée (affichée masquée)." })
                                    : t({ en: "No own key: the conversation's key is used.", fr: "Pas de clé propre : celle de la conversation est utilisée." })}
                            </p>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setFenetre(false)}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button disabled={enregistrement} onClick={() => void enregistrerLeModele()}>
                            {t({ en: "Save the background brain", fr: "Enregistrer le cerveau de fond" })}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Intertitre>
    );
};
