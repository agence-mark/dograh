"use client";

/**
 * [.mark] U3 sexies point 3 (E74) : le comportement commun aux types qui appellent l'extérieur.
 *
 * Phrase avant l'outil (Auto, Toujours, Jamais ; texte ou enregistrement), mode d'exécution (immédiat, après la
 * phrase, en arrière-plan pour un outil qui lit), interruption par l'appelant, son pendant l'outil, délai, seuil de
 * patience et phrase d'attente, phrase de repli. Une action de logiciel garde ses propres réglages d'avant (délai,
 * patience, repli) : les autres lignes ne lui sont pas proposées.
 */
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { useLangue } from "../langue/langue";
import { BlocChamp, Champs, LigneChamp, Segmente } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { type Config, ecritHttp, modeDePhrase, type ModePhrase, nombre, texte } from "./modele";

type Pose = (modifs: Config) => void;

export function OngletComportement({ categorie, config, pose }: { categorie: string; config: Config; pose: Pose }) {
    const { t } = useLangue();
    const integration = categorie === "integration";
    const mode = modeDePhrase(config);
    const modes: { id: ModePhrase; libelle: string }[] = [
        { id: "auto", libelle: t({ en: "Auto", fr: "Auto" }) },
        { id: "toujours", libelle: t({ en: "Always", fr: "Toujours" }) },
        { id: "jamais", libelle: t({ en: "Never", fr: "Jamais" }) },
    ];
    // Un outil qui lit peut tourner en arrière-plan ; le serveur le refuse pour un outil qui écrit.
    const peutTournerEnFond = categorie === "http_api" && !ecritHttp(config);
    const modeExecution = texte(config, "mode_execution") || "immediat";
    const type = texte(config, "customMessageType") === "audio" ? "audio" : "text";
    return (
        <Champs>
            {!integration && (
                <>
                    <LigneChamp
                        libelle={t({ en: "Sentence before the tool", fr: "Phrase avant l'outil" })}
                        info={t({
                            en: "Auto: said only if the tool is slow. Always: said first. Never: nothing is said.",
                            fr: "Auto : dite seulement si l'outil est lent. Toujours : dite d'abord. Jamais : rien n'est dit.",
                        })}
                    >
                        <Segmente
                            valeur={modes.find((m) => m.id === mode)!.libelle}
                            options={modes.map((m) => m.libelle)}
                            changer={(v) => pose({ phrase_avant_mode: modes.find((m) => m.libelle === v)!.id })}
                        />
                    </LigneChamp>
                    {mode !== "jamais" && (
                        <BlocChamp libelle={t({ en: "The sentence", fr: "La phrase" })}>
                            <div className="flex items-center gap-2">
                                <Segmente
                                    valeur={type === "audio" ? t({ en: "Recording", fr: "Enregistrement" }) : t({ en: "Text", fr: "Texte" })}
                                    options={[t({ en: "Text", fr: "Texte" }), t({ en: "Recording", fr: "Enregistrement" })]}
                                    changer={(v) => pose({ customMessageType: v === t({ en: "Recording", fr: "Enregistrement" }) ? "audio" : "text" })}
                                />
                                {type === "audio" ? (
                                    <Input
                                        className="h-8 w-32"
                                        value={texte(config, "customMessageRecordingId")}
                                        onChange={(e) => pose({ customMessageRecordingId: e.target.value.replace(/\D/g, "") || undefined })}
                                        placeholder={t({ en: "Recording no.", fr: "N° d'enregistrement" })}
                                        aria-label={t({ en: "Recording number", fr: "Numéro d'enregistrement" })}
                                    />
                                ) : (
                                    <Input
                                        className="h-8"
                                        value={texte(config, "customMessage")}
                                        onChange={(e) => pose({ customMessage: e.target.value || undefined })}
                                        aria-label={t({ en: "Sentence", fr: "Phrase" })}
                                    />
                                )}
                            </div>
                        </BlocChamp>
                    )}
                    <LigneChamp
                        libelle={t({ en: "Execution", fr: "Exécution" })}
                        info={t({
                            en: "Immediate: starts at once. After the sentence: starts when the sentence is finished. In the background: the model gets an immediate answer and the result lands in the call record (a tool that only reads).",
                            fr: "Immédiate : part tout de suite. Après la phrase : part quand la phrase est finie. En arrière-plan : le modèle reçoit une réponse immédiate et le résultat arrive dans la fiche (un outil qui lit seulement).",
                        })}
                    >
                        <Liste
                            valeur={modeExecution}
                            changer={(v) => pose({ mode_execution: v })}
                            options={[
                                { valeur: "immediat", libelle: t({ en: "Immediate", fr: "Immédiate" }) },
                                { valeur: "apres_la_phrase", libelle: t({ en: "After the sentence", fr: "Après la phrase" }) },
                                ...(peutTournerEnFond || modeExecution === "arriere_plan"
                                    ? [{ valeur: "arriere_plan", libelle: t({ en: "In the background", fr: "En arrière-plan" }) }]
                                    : []),
                            ]}
                            className="w-52"
                            taille="default"
                        />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "The caller may interrupt", fr: "L'appelant peut couper" })}
                        info={t({ en: "The caller may cut the sentence said before and while the tool works.", fr: "L'appelant peut couper la phrase dite avant et pendant l'outil." })}
                    >
                        <Switch checked={config.interruption_appelant === true} onCheckedChange={(v) => pose({ interruption_appelant: v })} aria-label={t({ en: "Interruption by the caller", fr: "Interruption par l'appelant" })} />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "Sound while the tool works", fr: "Son pendant l'outil" })}
                        info={t({ en: "A recording played once when the tool is past the patience threshold.", fr: "Un enregistrement joué une fois quand l'outil dépasse le seuil de patience." })}
                    >
                        <Input
                            className="h-8 w-32"
                            value={nombre(config, "son_pendant_enregistrement_id", 0) ? String(nombre(config, "son_pendant_enregistrement_id", 0)) : ""}
                            onChange={(e) => pose({ son_pendant_enregistrement_id: Number(e.target.value.replace(/\D/g, "")) || undefined })}
                            placeholder={t({ en: "Recording no.", fr: "N° d'enregistrement" })}
                            aria-label={t({ en: "Sound recording number", fr: "Numéro d'enregistrement du son" })}
                        />
                    </LigneChamp>
                </>
            )}
            {integration && (
                <LigneChamp libelle={t({ en: "Deadline (ms)", fr: "Délai (ms)" })}>
                    <Input
                        className="h-8 w-28 text-right"
                        value={String(nombre(config, "delai_ms", 5000))}
                        onChange={(e) => pose({ delai_ms: Math.min(15000, Math.max(500, Number(e.target.value.replace(/\D/g, "")) || 500)) })}
                        aria-label={t({ en: "Deadline", fr: "Délai" })}
                    />
                </LigneChamp>
            )}
            <LigneChamp
                libelle={t({ en: "Patience threshold (ms)", fr: "Seuil de patience (ms)" })}
                info={t({ en: "Past this time without an answer, the waiting sentence is said once.", fr: "Passé ce temps sans réponse, la phrase d'attente est dite une fois." })}
            >
                <Input
                    className="h-8 w-28 text-right"
                    value={String(nombre(config, "seuil_patience_ms", 1200))}
                    onChange={(e) => pose({ seuil_patience_ms: Math.min(15000, Number(e.target.value.replace(/\D/g, "")) || 0) })}
                    aria-label={t({ en: "Patience threshold", fr: "Seuil de patience" })}
                />
            </LigneChamp>
            <BlocChamp libelle={t({ en: "Waiting sentence", fr: "Phrase d'attente" })}>
                <Input value={texte(config, "phrase_attente")} onChange={(e) => pose({ phrase_attente: e.target.value || null })} aria-label={t({ en: "Waiting sentence", fr: "Phrase d'attente" })} />
            </BlocChamp>
            <BlocChamp
                libelle={t({ en: "Fallback sentence", fr: "Phrase de repli" })}
                info={t({ en: "Said when the tool fails (HTTP included).", fr: "Dite quand l'outil échoue (HTTP compris)." })}
            >
                <Input value={texte(config, "phrase_repli")} onChange={(e) => pose({ phrase_repli: e.target.value || null })} aria-label={t({ en: "Fallback sentence", fr: "Phrase de repli" })} />
            </BlocChamp>
        </Champs>
    );
}
