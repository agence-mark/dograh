"use client";

/**
 * [.mark] V1b : le lecteur de la page d'une conversation, à la forme de la maquette (carte : lecture, ondes, pistes).
 * Trois cas : deux pistes séparées (appelant / agent, avec choix de la piste et téléchargement de chacune), un seul
 * enregistrement (lecture et ondes), aucun enregistrement (le lecteur est là, éteint, et le dit).
 */
import { Bot, Download, Loader2, Pause, Play } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { downloadFile, getSignedUrl } from '@/lib/files';
import { cn } from '@/lib/utils';

import { useLangue } from '../langue/langue';

const WAVEFORM_BAR_COUNT = 96;
type SplitTrackPlaybackMode = 'both' | 'user' | 'bot';

function buildWaveformPeaks(audioBuffer: AudioBuffer) {
    const channel = audioBuffer.getChannelData(0);
    const samplesPerBar = Math.max(1, Math.floor(channel.length / WAVEFORM_BAR_COUNT));

    return Array.from({ length: WAVEFORM_BAR_COUNT }, (_, index) => {
        const start = index * samplesPerBar;
        const end = Math.min(start + samplesPerBar, channel.length);
        let sum = 0;

        for (let i = start; i < end; i += 1) {
            sum += channel[i] * channel[i];
        }

        const rms = Math.sqrt(sum / Math.max(1, end - start));
        return Math.max(0.08, Math.min(1, rms * 5));
    });
}

async function loadWaveformPeaks(url: string) {
    const response = await fetch(url);
    const audioData = await response.arrayBuffer();
    const AudioContextConstructor =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext })
            .webkitAudioContext;

    if (!AudioContextConstructor) return null;

    const audioContext = new AudioContextConstructor();
    try {
        const decoded = await audioContext.decodeAudioData(audioData);
        return buildWaveformPeaks(decoded);
    } finally {
        void audioContext.close();
    }
}

function getAudioDuration(audio: HTMLAudioElement | null) {
    return audio && Number.isFinite(audio.duration) ? audio.duration : 0;
}

function getAudioTimelineState(audios: HTMLAudioElement[]) {
    const duration = Math.max(0, ...audios.map((audio) => getAudioDuration(audio)));
    const currentTime = Math.max(0, ...audios.map((audio) => audio.currentTime));

    return { duration, currentTime };
}

function syncAudioCurrentTime(audio: HTMLAudioElement, startTime: number) {
    const duration = getAudioDuration(audio);
    audio.currentTime = Math.min(startTime, duration || startTime);
}

function WaveformLane({
    peaks,
    track,
    position,
    isActive,
}: {
    peaks: number[] | null;
    track: 'user' | 'bot';
    position: 'top' | 'bottom';
    isActive: boolean;
}) {
    return (
        <div
            className={cn(
                'absolute left-3 right-3 flex gap-0.5',
                isActive ? 'opacity-85' : 'opacity-25',
                position === 'top' ? 'top-5 h-12 items-end' : 'bottom-5 h-12 items-start'
            )}
        >
            {peaks ? (
                peaks.map((peak, index) => (
                    <span
                        key={`${track}-${index}`}
                        className={cn(
                            'min-h-1 flex-1 rounded-full',
                            track === 'user' ? 'bg-muted-foreground' : 'bg-foreground'
                        )}
                        style={{ height: `${Math.round(peak * 100)}%` }}
                    />
                ))
            ) : (
                <div className="my-auto h-px w-full bg-border" />
            )}
        </div>
    );
}

export function SplitTracksSection({
    userRecordingUrl,
    botRecordingUrl,
}: {
    userRecordingUrl: string;
    botRecordingUrl: string;
}) {
    const userAudioRef = useRef<HTMLAudioElement | null>(null);
    const botAudioRef = useRef<HTMLAudioElement | null>(null);
    const { t } = useLangue();
    const [signedUrls, setSignedUrls] = useState<{ user: string | null; bot: string | null }>({
        user: null,
        bot: null,
    });
    const [peaks, setPeaks] = useState<{ user: number[] | null; bot: number[] | null }>({
        user: null,
        bot: null,
    });
    const [isLoading, setIsLoading] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [playbackMode, setPlaybackMode] = useState<SplitTrackPlaybackMode>('both');

    const getPlaybackAudios = (mode: SplitTrackPlaybackMode) => {
        const audios: HTMLAudioElement[] = [];

        if (mode !== 'bot' && userAudioRef.current) {
            audios.push(userAudioRef.current);
        }

        if (mode !== 'user' && botAudioRef.current) {
            audios.push(botAudioRef.current);
        }

        return audios;
    };

    useEffect(() => {
        let isActive = true;
        const userAudio = userAudioRef.current;
        const botAudio = botAudioRef.current;

        userAudio?.pause();
        botAudio?.pause();
        setSignedUrls({ user: null, bot: null });
        setPeaks({ user: null, bot: null });
        setIsPlaying(false);
        setProgress(0);
        setPlaybackMode('both');
        setIsLoading(true);

        async function loadTracks() {
            try {
                const [userUrl, botUrl] = await Promise.all([
                    getSignedUrl(userRecordingUrl, true),
                    getSignedUrl(botRecordingUrl, true),
                ]);
                if (!isActive) return;

                setSignedUrls({ user: userUrl, bot: botUrl });
                if (!userUrl || !botUrl) return;

                const [userPeaks, botPeaks] = await Promise.all([
                    loadWaveformPeaks(userUrl),
                    loadWaveformPeaks(botUrl),
                ]);

                if (isActive) {
                    setPeaks({ user: userPeaks, bot: botPeaks });
                }
            } catch (error) {
                console.error('Error loading split track waveforms:', error);
            } finally {
                if (isActive) {
                    setIsLoading(false);
                }
            }
        }

        void loadTracks();

        return () => {
            isActive = false;
            userAudio?.pause();
            botAudio?.pause();
        };
    }, [userRecordingUrl, botRecordingUrl]);

    useEffect(() => {
        if (!isPlaying) return;

        let frameId: number;
        const updateProgress = () => {
            const activeAudios: HTMLAudioElement[] = [];

            if (playbackMode !== 'bot' && userAudioRef.current) {
                activeAudios.push(userAudioRef.current);
            }

            if (playbackMode !== 'user' && botAudioRef.current) {
                activeAudios.push(botAudioRef.current);
            }

            const { duration, currentTime } = getAudioTimelineState(activeAudios);

            setProgress(duration > 0 ? Math.min(1, currentTime / duration) : 0);
            frameId = window.requestAnimationFrame(updateProgress);
        };

        frameId = window.requestAnimationFrame(updateProgress);
        return () => window.cancelAnimationFrame(frameId);
    }, [isPlaying, playbackMode]);

    const pauseTracks = () => {
        userAudioRef.current?.pause();
        botAudioRef.current?.pause();
        setIsPlaying(false);
    };

    const handleTrackEnded = () => {
        const activeAudios = getPlaybackAudios(playbackMode);
        const activeTracksDone = activeAudios.length > 0 && activeAudios.every((audio) => audio.ended);

        if (activeTracksDone) {
            setIsPlaying(false);
            setProgress(1);
        }
    };

    const handlePlaybackModeChange = async (nextMode: SplitTrackPlaybackMode) => {
        if (nextMode === playbackMode) return;

        const { currentTime } = getAudioTimelineState(getPlaybackAudios(playbackMode));
        const nextAudios = getPlaybackAudios(nextMode);
        const { duration } = getAudioTimelineState(nextAudios);
        const startTime = duration > 0 && currentTime >= duration - 0.1 ? 0 : currentTime;

        userAudioRef.current?.pause();
        botAudioRef.current?.pause();
        nextAudios.forEach((audio) => syncAudioCurrentTime(audio, startTime));
        setPlaybackMode(nextMode);
        setProgress(duration > 0 ? Math.min(1, startTime / duration) : 0);

        if (!isPlaying) return;

        if (nextAudios.length === 0) {
            setIsPlaying(false);
            return;
        }

        try {
            await Promise.all(nextAudios.map((audio) => audio.play()));
            setIsPlaying(true);
        } catch (error) {
            pauseTracks();
            console.error('Error switching split track playback:', error);
        }
    };

    const handleTrackButtonClick = (track: 'user' | 'bot') => {
        const nextMode = playbackMode === track ? 'both' : track;
        void handlePlaybackModeChange(nextMode);
    };

    const togglePlayback = async () => {
        const playbackAudios = getPlaybackAudios(playbackMode);
        if (!canPlay || playbackAudios.length === 0) return;

        if (isPlaying) {
            pauseTracks();
            return;
        }

        const { duration, currentTime } = getAudioTimelineState(playbackAudios);
        const startTime = duration > 0 && currentTime >= duration - 0.1 ? 0 : currentTime;

        userAudioRef.current?.pause();
        botAudioRef.current?.pause();
        playbackAudios.forEach((audio) => syncAudioCurrentTime(audio, startTime));

        try {
            await Promise.all(playbackAudios.map((audio) => audio.play()));
            setIsPlaying(true);
        } catch (error) {
            pauseTracks();
            console.error('Error playing split tracks:', error);
        }
    };

    const canPlay =
        playbackMode === 'both'
            ? Boolean(signedUrls.user && signedUrls.bot)
            : playbackMode === 'user'
                ? Boolean(signedUrls.user)
                : Boolean(signedUrls.bot);
    const progressPercent = Math.round(progress * 1000) / 10;
    const userTrackActive = playbackMode !== 'bot';
    const botTrackActive = playbackMode !== 'user';
    const playbackTargetLabel =
        playbackMode === 'both'
            ? t({ en: 'both tracks', fr: 'les deux pistes' })
            : playbackMode === 'user'
              ? t({ en: 'the caller track', fr: "la piste de l'appelant" })
              : t({ en: 'the agent track', fr: "la piste de l'agent" });

    return (
        <div className="flex items-center gap-4 rounded-xl border bg-card p-4" data-lecteur-conversation>
            <audio ref={userAudioRef} src={signedUrls.user ?? undefined} preload="metadata" className="hidden" onEnded={handleTrackEnded} />
            <audio ref={botAudioRef} src={signedUrls.bot ?? undefined} preload="metadata" className="hidden" onEnded={handleTrackEnded} />
            <Button
                type="button"
                size="icon"
                className="rounded-full"
                onClick={togglePlayback}
                disabled={!canPlay}
                aria-label={`${isPlaying ? t({ en: 'Pause', fr: 'Pause' }) : t({ en: 'Play', fr: 'Lecture' })} : ${playbackTargetLabel}`}
            >
                {isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />}
            </Button>
            <div className="relative h-10 min-w-0 flex-1 overflow-hidden">
                <WaveformLane peaks={peaks.user} track="user" position="top" isActive={userTrackActive} />
                <WaveformLane peaks={peaks.bot} track="bot" position="bottom" isActive={botTrackActive} />
                {canPlay && (
                    <div className="pointer-events-none absolute inset-0">
                        <div className="absolute bottom-0 top-0 w-px bg-foreground/50" style={{ left: `${progressPercent}%` }} />
                    </div>
                )}
                {isLoading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/70 text-xs text-muted-foreground">
                        <Loader2 className="mr-2 size-3.5 animate-spin" />
                    </div>
                )}
            </div>
            <span className="inline-flex rounded-md border p-0.5 text-xs" role="group" aria-label={t({ en: 'Playback tracks', fr: 'Pistes à écouter' })}>
                <button
                    type="button"
                    aria-pressed={playbackMode === 'both'}
                    onClick={() => playbackMode !== 'both' && handleTrackButtonClick(playbackMode === 'user' ? 'user' : 'bot')}
                    className={cn('cursor-pointer rounded px-2 py-0.5', playbackMode === 'both' ? 'bg-foreground text-background' : 'text-muted-foreground hover:font-medium')}
                >
                    {t({ en: 'Both tracks', fr: 'Les deux pistes' })}
                </button>
                <button
                    type="button"
                    aria-pressed={playbackMode === 'user'}
                    aria-label={playbackMode === 'user' ? t({ en: 'Play both tracks', fr: 'Écouter les deux pistes' }) : t({ en: 'Play the caller track only', fr: "Écouter la piste de l'appelant seule" })}
                    onClick={() => handleTrackButtonClick('user')}
                    className={cn('cursor-pointer rounded px-2 py-0.5', playbackMode === 'user' ? 'bg-foreground text-background' : 'text-muted-foreground hover:font-medium')}
                >
                    {t({ en: 'Caller', fr: 'Appelant' })}
                </button>
                <button
                    type="button"
                    aria-pressed={playbackMode === 'bot'}
                    aria-label={playbackMode === 'bot' ? t({ en: 'Play both tracks', fr: 'Écouter les deux pistes' }) : t({ en: 'Play the agent track only', fr: "Écouter la piste de l'agent seule" })}
                    onClick={() => handleTrackButtonClick('bot')}
                    className={cn('cursor-pointer rounded px-2 py-0.5', playbackMode === 'bot' ? 'bg-foreground text-background' : 'text-muted-foreground hover:font-medium')}
                >
                    {t({ en: 'Agent', fr: 'Agent' })}
                </button>
            </span>
            <span className="flex items-center">
                <Button type="button" variant="ghost" size="icon" className="size-8" title={t({ en: 'Download the caller track', fr: "Télécharger la piste de l'appelant" })} aria-label={t({ en: 'Download the caller track', fr: "Télécharger la piste de l'appelant" })} onClick={() => downloadFile(userRecordingUrl)}>
                    <Download className="size-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="size-8" title={t({ en: 'Download the agent track', fr: "Télécharger la piste de l'agent" })} aria-label={t({ en: 'Download the agent track', fr: "Télécharger la piste de l'agent" })} onClick={() => downloadFile(botRecordingUrl)}>
                    <Bot className="size-4" />
                </Button>
            </span>
        </div>
    );
}

/** Un seul enregistrement : lecture, ondes lues sur le fichier, curseur de lecture, téléchargement. */
function LecteurUnique({ recordingUrl }: { recordingUrl: string }) {
    const { t } = useLangue();
    const audio = useRef<HTMLAudioElement | null>(null);
    const [adresse, setAdresse] = useState<string | null>(null);
    const [pics, setPics] = useState<number[] | null>(null);
    const [charge, setCharge] = useState(true);
    const [enLecture, setEnLecture] = useState(false);
    const [progres, setProgres] = useState(0);

    useEffect(() => {
        let actif = true;
        setAdresse(null);
        setPics(null);
        setCharge(true);
        setEnLecture(false);
        setProgres(0);
        (async () => {
            try {
                const url = await getSignedUrl(recordingUrl, true);
                if (!actif) return;
                setAdresse(url);
                if (url) {
                    const lus = await loadWaveformPeaks(url);
                    if (actif) setPics(lus);
                }
            } catch (error) {
                console.error('Error loading the recording waveform:', error);
            } finally {
                if (actif) setCharge(false);
            }
        })();
        return () => {
            actif = false;
            audio.current?.pause();
        };
    }, [recordingUrl]);

    useEffect(() => {
        if (!enLecture) return;
        let image: number;
        const suivre = () => {
            const { duration, currentTime } = getAudioTimelineState(audio.current ? [audio.current] : []);
            setProgres(duration > 0 ? Math.min(1, currentTime / duration) : 0);
            image = window.requestAnimationFrame(suivre);
        };
        image = window.requestAnimationFrame(suivre);
        return () => window.cancelAnimationFrame(image);
    }, [enLecture]);

    const basculer = async () => {
        const lecteur = audio.current;
        if (!lecteur || !adresse) return;
        if (enLecture) {
            lecteur.pause();
            setEnLecture(false);
            return;
        }
        if (lecteur.ended) lecteur.currentTime = 0;
        try {
            await lecteur.play();
            setEnLecture(true);
        } catch (error) {
            setEnLecture(false);
            console.error('Error playing the recording:', error);
        }
    };

    return (
        <div className="flex items-center gap-4 rounded-xl border bg-card p-4" data-lecteur-conversation="unique">
            <audio
                ref={audio}
                src={adresse ?? undefined}
                preload="metadata"
                className="hidden"
                onEnded={() => {
                    setEnLecture(false);
                    setProgres(1);
                }}
            />
            <Button
                type="button"
                size="icon"
                className="rounded-full"
                onClick={basculer}
                disabled={!adresse}
                aria-label={enLecture ? t({ en: 'Pause', fr: 'Pause' }) : t({ en: 'Play', fr: 'Lecture' })}
            >
                {enLecture ? <Pause className="size-4" /> : <Play className="size-4" />}
            </Button>
            <div className="relative h-10 min-w-0 flex-1 overflow-hidden">
                <div className="absolute inset-x-3 inset-y-0 flex items-center gap-0.5">
                    {pics ? (
                        pics.map((pic, i) => (
                            <span
                                key={i}
                                className="min-h-1 flex-1 rounded-full bg-foreground/70"
                                style={{ height: `${Math.round(pic * 100)}%` }}
                            />
                        ))
                    ) : (
                        <div className="h-px w-full bg-border" />
                    )}
                </div>
                {adresse && (
                    <div className="pointer-events-none absolute inset-0">
                        <div
                            className="absolute bottom-0 top-0 w-px bg-foreground/50"
                            style={{ left: `${Math.round(progres * 1000) / 10}%` }}
                        />
                    </div>
                )}
                {charge && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/70 text-xs text-muted-foreground">
                        <Loader2 className="mr-2 size-3.5 animate-spin" />
                    </div>
                )}
            </div>
            <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8"
                title={t({ en: 'Download the recording', fr: "Télécharger l'enregistrement" })}
                aria-label={t({ en: 'Download the recording', fr: "Télécharger l'enregistrement" })}
                onClick={() => downloadFile(recordingUrl)}
            >
                <Download className="size-4" />
            </Button>
        </div>
    );
}

/** Aucun enregistrement : le lecteur est là, éteint, il dit pourquoi (état vide, jamais une carte absente). */
function LecteurVide({ ecrit }: { ecrit: boolean }) {
    const { t } = useLangue();
    return (
        <div className="flex items-center gap-4 rounded-xl border bg-card p-4" data-lecteur-conversation="vide">
            <Button type="button" size="icon" className="rounded-full" disabled aria-label={t({ en: 'Play', fr: 'Lecture' })}>
                <Play className="size-4" />
            </Button>
            <div className="flex h-10 min-w-0 flex-1 items-center">
                <div className="h-px w-full bg-border" />
            </div>
            <span className="text-sm text-muted-foreground">
                {ecrit
                    ? t({ en: 'Written conversation: no audio', fr: "Conversation écrite : pas d'audio" })
                    : t({ en: 'No recording for this call', fr: 'Aucun enregistrement pour cet appel' })}
            </span>
        </div>
    );
}

export function LecteurConversation({
    pisteAppelant,
    pisteAgent,
    enregistrement,
    ecrit,
}: {
    pisteAppelant: string | null;
    pisteAgent: string | null;
    enregistrement: string | null;
    /** Une conversation au clavier : jamais d'audio. */
    ecrit: boolean;
}) {
    if (pisteAppelant && pisteAgent) return <SplitTracksSection userRecordingUrl={pisteAppelant} botRecordingUrl={pisteAgent} />;
    if (enregistrement) return <LecteurUnique recordingUrl={enregistrement} />;
    return <LecteurVide ecrit={ecrit} />;
}
