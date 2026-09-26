"use client";

/**
 * [.mark] Theme « Voix »: how the agent's text is turned into speech
 * (convention § 2). Our voice settings (Speech Tuning) and, rebuilt from
 * Dograh's « General » (option B of D6), the ambient noise -- its audio file
 * included -- and the speech cache.
 */
import { Loader2, Pause, Play, Upload, Volume2, X } from "lucide-react";
import { useRef, useState } from "react";

import { getAmbientNoiseUploadUrlApiV1WorkflowAmbientNoiseUploadUrlPost } from "@/client/sdk.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAudioPlayback } from "@/hooks/useAudioPlayback";
import type { AmbientNoiseConfiguration } from "@/types/workflow-configurations";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { type CleCatalogue, erreursDuCatalogue, extraire, Reglage } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_VOIX = "voix";
export const TITRE_VOIX = { en: "Voice", fr: "Voix" };

export const CLES_VOIX_MARK = [
    "tts_markdown_filter_enabled",
    "tts_text_aggregation_mode",
    "tts_push_silence_after_stop",
    "tts_silence_time_s",
    "interdire_nom_appelant",
    "interdire_civilite_appelant",
    "tts_replacements",
] as const satisfies readonly CleCatalogue[];

const MAX_AMBIENT_NOISE_FILE_SIZE = 10 * 1024 * 1024; // 10MB

const extraireTout = (resolue: ProprietesThemeAgent["resolue"]) => ({
    ...extraire(resolue, CLES_VOIX_MARK),
    ambient_noise_configuration: resolue.ambient_noise_configuration as AmbientNoiseConfiguration,
    tts_cache_enabled: resolue.tts_cache_enabled,
});

export const ThemeVoix = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    workflowId,
}: ProprietesThemeAgent & { workflowId: number }) => {
    const { t } = useLangue();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireTout);
    const { afficher, visible } = useRevelation(ouvrir);
    const maj = (cle: keyof typeof brouillon) => (valeur: unknown) => setBrouillon((avant) => ({ ...avant, [cle]: valeur }));
    const ambiance = brouillon.ambient_noise_configuration;
    const setAmbiance = (suite: (avant: AmbientNoiseConfiguration) => AmbientNoiseConfiguration) =>
        setBrouillon((avant) => ({ ...avant, ambient_noise_configuration: suite(avant.ambient_noise_configuration) }));

    const [isUploadingAudio, setIsUploadingAudio] = useState(false);
    const [audioUploadError, setAudioUploadError] = useState<string | null>(null);
    const ambientFileInputRef = useRef<HTMLInputElement>(null);
    const { playingId, toggle: togglePlayback } = useAudioPlayback();

    const modifie = differe(brouillon, enregistre);
    const erreurs = erreursDuCatalogue(CLES_VOIX_MARK, brouillon);
    useEtatTheme(ID_THEME_VOIX, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_VOIX,
        resolue,
        workflowName,
        onSave,
        parties: [{ nom: { en: "Voice settings", fr: "Réglages de la voix" }, modifie, config: () => brouillon, apres: resynchroniser }],
    });

    // Dograh's upload, as « General » did it: a presigned URL, the file, then
    // the storage reference in the configuration.
    const handleAmbientFileUpload = async (file: File) => {
        if (file.size > MAX_AMBIENT_NOISE_FILE_SIZE) {
            setAudioUploadError(
                t({
                    en: `File too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum is 10MB.`,
                    fr: `Fichier trop lourd (${(file.size / (1024 * 1024)).toFixed(1)} Mo). Maximum 10 Mo.`,
                }),
            );
            return;
        }
        setIsUploadingAudio(true);
        setAudioUploadError(null);
        try {
            const res = await getAmbientNoiseUploadUrlApiV1WorkflowAmbientNoiseUploadUrlPost({
                body: {
                    workflow_id: Number(workflowId),
                    filename: file.name,
                    mime_type: file.type || "audio/wav",
                    file_size: file.size,
                },
            });
            if (res.error || !res.data?.upload_url) {
                throw new Error("Failed to get upload URL");
            }
            const data = res.data;
            const uploadRes = await fetch(data.upload_url, {
                method: "PUT",
                body: file,
                headers: { "Content-Type": file.type || "audio/wav" },
            });
            if (!uploadRes.ok) {
                throw new Error("File upload failed");
            }
            setAmbiance((prev) => ({
                ...prev,
                storage_key: data.storage_key,
                storage_backend: data.storage_backend,
                original_filename: file.name,
            }));
        } catch (err) {
            setAudioUploadError(err instanceof Error ? err.message : "Upload failed");
        } finally {
            setIsUploadingAudio(false);
            if (ambientFileInputRef.current) ambientFileInputRef.current.value = "";
        }
    };

    const r = (cle: (typeof CLES_VOIX_MARK)[number], condition = true) => {
        const { affiche, note } = visible(cle, condition);
        return affiche ? <Reglage key={cle} cle={cle} valeur={brouillon[cle]} onChange={maj(cle)} note={note} /> : null;
    };

    const motParMot = brouillon.tts_text_aggregation_mode !== "sentence";

    return (
        <Theme
            id={ID_THEME_VOIX}
            icone={Volume2}
            titre={TITRE_VOIX}
            description={{ en: "How the agent's text is turned into speech.", fr: "Comment le texte de l'agent devient de la parole." }}
            resume={[
                brouillon.tts_text_aggregation_mode === "sentence"
                    ? t({ en: "Sentence by sentence", fr: "Phrase par phrase" })
                    : t({ en: "Word by word", fr: "Mot par mot" }),
                `${((brouillon.tts_replacements as string[]) ?? []).length} ${t({ en: "pronunciation fixes", fr: "corrections de prononciation" })}`,
                Boolean(brouillon.interdire_civilite_appelant) && t({ en: "No titles", fr: "Sans civilité" }),
                ambiance.enabled && t({ en: "Ambience", fr: "Ambiance" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre id="voix-envoi" titre={{ en: "Sending text to the voice", fr: "Envoi du texte à la voix" }}>
                {r("tts_markdown_filter_enabled")}
                {r("tts_text_aggregation_mode")}
                {r("tts_push_silence_after_stop")}
                {r("tts_silence_time_s", Boolean(brouillon.tts_push_silence_after_stop))}
            </Intertitre>

            <Intertitre id="voix-formules" titre={{ en: "Caller's name and title", fr: "Nom et civilité de l'appelant" }}>
                {r("interdire_nom_appelant")}
                {r("interdire_civilite_appelant")}
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "Enforced in code, not by the prompt: five rewrites of the instructions in two days still left the name spoken in 2 voice runs out of 5. Each switch works on its own.",
                        fr: "Appliqué par le code, pas par le prompt : cinq réécritures des consignes en deux jours laissaient encore le nom prononcé dans 2 appels sur 5. Chaque interrupteur agit seul.",
                    })}
                </p>
                {motParMot && (Boolean(brouillon.interdire_nom_appelant) || Boolean(brouillon.interdire_civilite_appelant)) && (
                    <p className="text-xs text-destructive">
                        {t({
                            en: "⚠ Inert right now: the text above is sent to the voice word by word, and a name is split across several words. Switch back to \"Sentence by sentence\" for these to have any effect.",
                            fr: "⚠️ Sans effet en ce moment : le texte part vers la voix mot par mot, et un nom est découpé en plusieurs mots. Repassez sur « Phrase par phrase » pour qu'ils agissent.",
                        })}
                    </p>
                )}
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "What these switches do not cover. The first name is not filtered. A SPELLED name is deliberately left alone. Both are inert when the text goes to the voice word by word. The name is only known once it has been extracted, so anything said before that is untouched. A name written in lower case is left alone, so a name at the very start of a sentence may survive. They act on what is SAID: the call record and the caller's own transcript keep the name, while the agent's side of the transcript is written from what it actually said, so it loses the name too.",
                        fr: "Ce que ces interrupteurs ne couvrent pas. Le prénom n'est pas filtré. Un nom ÉPELÉ est volontairement laissé. Les deux sont sans effet quand le texte part vers la voix mot par mot. Le nom n'est connu qu'une fois extrait : ce qui est dit avant n'est pas touché. Un nom écrit en minuscules est laissé, donc un nom tout en début de phrase peut passer. Ils agissent sur ce qui est DIT : la fiche et la transcription de l'appelant gardent le nom, tandis que la transcription de l'agent est écrite d'après ce qu'il a vraiment dit, et perd donc le nom aussi.",
                    })}
                </p>
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "Writing the prompt. With the name switch on, have the agent confirm a name by SPELLING it back (\"D - U - P - O - N - T, is that right?\"), never by saying it, otherwise the confirmation has nothing left to confirm (\"is that right?\").",
                        fr: "Rédaction du prompt. Avec l'interrupteur du nom allumé, faire confirmer un nom en l'ÉPELANT (« D - U - P - O - N - T, c'est bien ça ? »), jamais en le disant, sinon la confirmation n'a plus rien à confirmer (« c'est bien ça ? »).",
                    })}
                </p>
            </Intertitre>

            <Intertitre id="voix-prononciation" titre={{ en: "Pronunciation", fr: "Prononciation" }}>
                {r("tts_replacements")}
            </Intertitre>

            <Intertitre
                id="voix-ambiance"
                titre={{ en: "Ambient Noise", fr: "Bruit d'ambiance" }}
                description={{
                    en: "Add background ambient noise to make the conversation sound more natural.",
                    fr: "Ajoute un bruit de fond pour rendre la conversation plus naturelle.",
                }}
            >
                <ChampReglage
                    cle="ambient_noise_configuration.enabled"
                    idControle="ambient-noise-enabled"
                    libelle={{ en: "Use Ambient Noise", fr: "Utiliser un bruit d'ambiance" }}
                    disposition="ligne"
                >
                    <Switch
                        id="ambient-noise-enabled"
                        checked={ambiance.enabled}
                        onCheckedChange={(checked) => setAmbiance((prev) => ({ ...prev, enabled: checked }))}
                    />
                </ChampReglage>
                {ambiance.enabled && (
                    <>
                        <ChampReglage
                            cle="ambient_noise_configuration.volume"
                            idControle="ambient-volume"
                            libelle={{ en: "Volume", fr: "Volume" }}
                            bornes={bornesDe(0, 1)}
                        >
                            <Input
                                id="ambient-volume"
                                type="number"
                                step="0.1"
                                min="0"
                                max="1"
                                value={ambiance.volume}
                                onChange={(e) => {
                                    const value = parseFloat(e.target.value);
                                    if (!isNaN(value)) setAmbiance((prev) => ({ ...prev, volume: value }));
                                }}
                            />
                        </ChampReglage>
                        <ChampReglage
                            cle="ambient_noise_configuration.storage_key"
                            libelle={{ en: "Custom Audio File", fr: "Fichier audio personnalisé" }}
                            aides={[
                                {
                                    en: "Upload your own audio file or use the default office ambience.",
                                    fr: "Envoyez votre propre fichier ou gardez l'ambiance de bureau par défaut.",
                                },
                            ]}
                        >
                            {ambiance.storage_key ? (
                                <div className="flex items-center gap-2 rounded-md border bg-muted/10 p-2">
                                    <code className="flex-1 truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                                        {ambiance.original_filename || t({ en: "Custom audio", fr: "Audio personnalisé" })}
                                    </code>
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="ghost"
                                        className="h-6 w-6 shrink-0 p-0"
                                        aria-label={t({ en: "Play the ambient audio", fr: "Écouter l'audio d'ambiance" })}
                                        onClick={async () => {
                                            try {
                                                await togglePlayback("ambient-noise", ambiance.storage_key!, ambiance.storage_backend);
                                            } catch {
                                                setAudioUploadError(t({ en: "Failed to play audio", fr: "Lecture impossible" }));
                                            }
                                        }}
                                    >
                                        {playingId === "ambient-noise" ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                                    </Button>
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="ghost"
                                        className="h-6 w-6 shrink-0 p-0"
                                        aria-label={t({ en: "Remove the custom audio", fr: "Retirer l'audio personnalisé" })}
                                        onClick={() => setAmbiance((prev) => ({ enabled: prev.enabled, volume: prev.volume }))}
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            ) : (
                                <div>
                                    <input
                                        ref={ambientFileInputRef}
                                        type="file"
                                        accept="audio/*"
                                        onChange={(e) => {
                                            const file = e.target.files?.[0];
                                            if (file) handleAmbientFileUpload(file);
                                        }}
                                        className="hidden"
                                    />
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        className="text-sm font-normal"
                                        onClick={() => ambientFileInputRef.current?.click()}
                                        disabled={isUploadingAudio}
                                    >
                                        {isUploadingAudio ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                                        {isUploadingAudio
                                            ? t({ en: "Uploading...", fr: "Envoi..." })
                                            : t({ en: "Upload audio file (max 10MB)", fr: "Envoyer un fichier audio (10 Mo max)" })}
                                    </Button>
                                </div>
                            )}
                            {audioUploadError && <p className="text-xs text-destructive">{audioUploadError}</p>}
                            {!ambiance.storage_key && (
                                <p className="text-xs italic text-muted-foreground">
                                    {t({ en: "Using default office ambience", fr: "Ambiance de bureau par défaut" })}
                                </p>
                            )}
                        </ChampReglage>
                    </>
                )}
            </Intertitre>

            <Intertitre id="voix-cache" titre={{ en: "Speech Caching", fr: "Cache de la voix" }}>
                <ChampReglage
                    cle="tts_cache_enabled"
                    idControle="tts-cache-enabled"
                    libelle={{ en: "Enable Speech Caching", fr: "Mettre en cache la voix" }}
                    aides={[
                        {
                            en: "Reuse generated audio for repeated phrases to reduce response time and speech generation costs. Cached audio expires after 24 hours. Currently available with MiniMax TTS.",
                            fr: "Réutilise l'audio déjà généré pour les phrases répétées, pour répondre plus vite et payer moins. Expire après 24 h. Disponible aujourd'hui avec MiniMax seulement.",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch
                        id="tts-cache-enabled"
                        checked={brouillon.tts_cache_enabled}
                        onCheckedChange={(checked) => maj("tts_cache_enabled")(checked)}
                    />
                </ChampReglage>
            </Intertitre>
        </Theme>
    );
};
