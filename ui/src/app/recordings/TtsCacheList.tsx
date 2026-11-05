"use client";

import { AudioLines, Loader2, Play, RefreshCw, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
    clearTtsCacheApiV1TtsCacheDelete,
    invalidateTtsCacheEntryApiV1TtsCacheEntryIdDelete,
    listTtsCacheApiV1TtsCacheGet,
    previewTtsCacheApiV1TtsCacheEntryIdAudioGet,
} from "@/client/sdk.gen";
import type { ListTtsCacheApiV1TtsCacheGetData, TtsCacheEntry } from "@/client/types.gen";
import { useFormeMaquette } from "@/components/mark/ecran/forme-maquette";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Liste } from "@/components/mark/studio/liste";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { Info } from "@/components/mark/studio/marques";
import { BarrePagination } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrganizationTimezone } from "@/hooks/useOrganizationTimezone";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dateTime";

const PAGE_SIZE = 25;
const SORT_OPTIONS = [
    { value: "recent", label: "Recently used", sort: "last_used", order: "desc" },
    { value: "most_used", label: "Most reused", sort: "usage", order: "desc" },
    { value: "least_used", label: "Least reused", sort: "usage", order: "asc" },
    { value: "longest", label: "Longest first", sort: "duration", order: "desc" },
    { value: "shortest", label: "Shortest first", sort: "duration", order: "asc" },
] as const;

const LIBELLE_TRI = {
    recent: { en: "Recently used", fr: "Utilisées récemment" },
    most_used: { en: "Most reused", fr: "Les plus rejouées" },
    least_used: { en: "Least reused", fr: "Les moins rejouées" },
    longest: { en: "Longest first", fr: "Les plus longues" },
    shortest: { en: "Shortest first", fr: "Les plus courtes" },
} as const;

export default function TtsCacheList() {
    const { user, loading: authLoading } = useAuth();
    const maquette = useFormeMaquette();
    const { t } = useLangue();
    const timezone = useOrganizationTimezone();
    const [entries, setEntries] = useState<TtsCacheEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState("");
    const [sortValue, setSortValue] = useState("recent");
    const [minDuration, setMinDuration] = useState("");
    const [maxDuration, setMaxDuration] = useState("");
    const [offset, setOffset] = useState(0);
    const [refresh, setRefresh] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [removing, setRemoving] = useState<string | null>(null);
    const [preview, setPreview] = useState<{ id: string; url: string } | null>(null);
    const [previewLoading, setPreviewLoading] = useState<string | null>(null);
    const previewRequest = useRef<AbortController | null>(null);
    const previewUrl = useRef<string | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    const stopPreview = useCallback(() => {
        previewRequest.current?.abort();
        audioRef.current?.pause();
        if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
        previewUrl.current = null;
        setPreview(null);
        setPreviewLoading(null);
    }, []);

    useEffect(() => stopPreview, [stopPreview]);

    const invalidDuration = (minDuration !== "" && (!Number.isFinite(Number(minDuration)) || Number(minDuration) < 0))
        || (maxDuration !== "" && (!Number.isFinite(Number(maxDuration)) || Number(maxDuration) < 0))
        || (minDuration !== "" && maxDuration !== "" && Number(minDuration) > Number(maxDuration));

    useEffect(() => {
        if (authLoading || !user) return;
        stopPreview();
        if (invalidDuration) {
            setError("Enter finite, non-negative durations: minimum must not exceed maximum.");
            setLoading(false);
            return;
        }
        const controller = new AbortController();
        setLoading(true);
        setError(null);
        const timer = setTimeout(async () => {
            const selected = SORT_OPTIONS.find((option) => option.value === sortValue) ?? SORT_OPTIONS[0];
            const query: ListTtsCacheApiV1TtsCacheGetData["query"] = {
                search, sort: selected.sort, order: selected.order,
                min_duration: minDuration === "" ? undefined : Number(minDuration),
                max_duration: maxDuration === "" ? undefined : Number(maxDuration),
                offset, limit: PAGE_SIZE,
            };
            try {
                const result = await listTtsCacheApiV1TtsCacheGet({ query, signal: controller.signal });
                if (controller.signal.aborted) return;
                if (result.error || !result.data) {
                    setError(echecAffiche(result.error, ECHECS.cacheVoixListe));
                    setEntries([]);
                    return;
                }
                if (offset > 0 && offset >= result.data.total) {
                    setOffset(Math.max(0, Math.ceil(result.data.total / PAGE_SIZE) - 1) * PAGE_SIZE);
                    return;
                }
                setEntries(result.data.entries);
                setTotal(result.data.total);
            } catch {
                if (!controller.signal.aborted) setError("Could not load cached speech.");
            } finally {
                if (!controller.signal.aborted) setLoading(false);
            }
        }, 250);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [authLoading, user, search, sortValue, minDuration, maxDuration, invalidDuration, offset, refresh, stopPreview]);

    const handlePreview = async (entry: TtsCacheEntry) => {
        stopPreview();
        const controller = new AbortController();
        previewRequest.current = controller;
        setPreviewLoading(entry.id);
        try {
            const result = await previewTtsCacheApiV1TtsCacheEntryIdAudioGet({
                path: { entry_id: entry.id }, parseAs: "blob", signal: controller.signal,
            });
            if (controller.signal.aborted) return;
            if (result.error || !result.data) {
                notifier.echec({ fr: "Phrase expirée. Actualisez et réessayez.", en: "Phrase expired. Refresh and try again." }, { erreur: result.error });
                return;
            }
            const url = URL.createObjectURL(result.data);
            previewUrl.current = url;
            setPreview({ id: entry.id, url });
        } catch {
            if (!controller.signal.aborted) notifier.echec({ fr: "Lecture impossible. Réessayez.", en: "Could not play. Try again." });
        } finally {
            if (!controller.signal.aborted) setPreviewLoading(null);
        }
    };

    const handleInvalidate = async (entry?: TtsCacheEntry) => {
        const message = entry
            ? "Invalidate this cached speech? It will be synthesized again when next requested."
            : "Clear all cached speech for your organization? Speech will be synthesized again when requested.";
        if (!window.confirm(message)) return;
        stopPreview();
        setRemoving(entry?.id ?? "all");
        try {
            const result = entry
                ? await invalidateTtsCacheEntryApiV1TtsCacheEntryIdDelete({ path: { entry_id: entry.id } })
                : await clearTtsCacheApiV1TtsCacheDelete();
            if (result.error) {
                notifier.echec({ fr: "Phrase non invalidée. Réessayez.", en: "Phrase not invalidated. Try again." }, { erreur: result.error });
                return;
            }
            notifier.succes(entry ? { fr: "Phrase invalidée.", en: "Phrase invalidated." } : { fr: "Cache de l'organisation vidé.", en: "Organization cache cleared." });
            setRefresh((value) => value + 1);
        } catch {
            notifier.echec({ fr: "Phrase non invalidée. Réessayez.", en: "Phrase not invalidated. Try again." });
        } finally {
            setRemoving(null);
        }
    };

    // [.mark] K4b : la forme de la maquette (`OngletEcouteSons`) : titre + « ! », « Actualiser » et « Vider le cache » à droite,
    // un tableau nu. Les filtres du fork (recherche, tri, durées) restent sur une ligne au-dessus du tableau.
    if (maquette) {
        return (
            <section id="ecoute-cache-voix" data-testid="cache-voix">
                <TitreTableau
                    titre={t({ en: "Voice cache", fr: "Cache de la voix" })}
                    info={
                        <Info>
                            {t({
                                en: "Speech already said, kept to be replayed without going through the voice again. Invalidating a phrase has it redone at the next call that says it. Listening here does not count as a reuse.",
                                fr: "Les phrases déjà dites, gardées pour être rejouées sans repasser par la voix. Invalider une phrase la fait refaire au prochain appel qui la dit. Écouter ici ne compte pas comme une reprise.",
                            })}
                        </Info>
                    }
                    action={
                        <div className="flex gap-2">
                            <Button variant="ghost" size="sm" disabled={loading} onClick={() => setRefresh((value) => value + 1)}>
                                <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
                                {t({ en: "Refresh", fr: "Actualiser" })}
                            </Button>
                            <Button variant="outline" size="sm" disabled={loading || removing !== null} onClick={() => handleInvalidate()}>
                                {t({ en: "Clear the cache", fr: "Vider le cache" })}
                            </Button>
                        </div>
                    }
                />
                <div className="mt-6 flex flex-wrap items-center justify-end gap-2 pb-2">
                    <div className="relative">
                        <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            aria-label={t({ en: "Search cached speech", fr: "Chercher une phrase" })}
                            placeholder={t({ en: "A phrase, a model, a voice…", fr: "Une phrase, un modèle, une voix…" })}
                            maxLength={200}
                            className="h-8 w-64 pl-8"
                            value={search}
                            onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
                        />
                    </div>
                    <Liste
                        valeur={sortValue}
                        changer={(v) => { setSortValue(v); setOffset(0); }}
                        options={SORT_OPTIONS.map((o) => ({ valeur: o.value, libelle: t(LIBELLE_TRI[o.value]) }))}
                        className="w-56"
                    />
                    <Input id="tts-min-duration" aria-label={t({ en: "Min seconds", fr: "Durée minimale (secondes)" })} type="number" min="0" step="0.1" value={minDuration}
                        onChange={(e) => { setMinDuration(e.target.value); setOffset(0); }} placeholder={t({ en: "Min s", fr: "Min s" })} className="h-8 w-20 text-right" />
                    <Input id="tts-max-duration" aria-label={t({ en: "Max seconds", fr: "Durée maximale (secondes)" })} type="number" min="0" step="0.1" value={maxDuration}
                        onChange={(e) => { setMaxDuration(e.target.value); setOffset(0); }} placeholder={t({ en: "Max s", fr: "Max s" })} className="h-8 w-20 text-right" />
                </div>
                {error ? (
                    <EtatVide cas="erreur" compact reessayer={() => setRefresh((value) => value + 1)} />
                ) : loading ? (
                    <EtatVide cas="chargement" lignes={3} />
                ) : entries.length === 0 ? (
                    search ? (
                        <EtatVide cas="filtre" compact recherche={search} effacer={() => setSearch("")} />
                    ) : (
                        <EtatVide cas="premier" compact icone={AudioLines} titre={t({ en: "No cached speech yet", fr: "Aucune phrase en cache pour l'instant" })} info={t({ en: "Speech appears here after a successful synthesis in an agent with speech caching on.", fr: "Les phrases apparaissent ici après une synthèse réussie, chez un agent dont le cache de la voix est allumé." })} />
                    )
                ) : (
                    <>
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Phrase", fr: "Phrase" }) },
                                { titre: t({ en: "Voice", fr: "Voix" }) },
                                { titre: t({ en: "Length", fr: "Durée" }), droite: true },
                                { titre: t({ en: "Replayed", fr: "Rejouée" }), droite: true },
                                { titre: t({ en: "Last time", fr: "Dernière fois" }), droite: true },
                                { titre: "", droite: true },
                            ]}
                        >
                            {entries.map((entry) => (
                                <Ligne key={entry.id}>
                                    <Cellule principale>
                                        <span className="font-normal whitespace-pre-wrap break-words">{entry.text_preview || t({ en: "Cached speech", fr: "Phrase en cache" })}</span>
                                        {preview?.id === entry.id && (
                                            <audio ref={audioRef} controls autoPlay src={preview.url} className="mt-2 w-full max-w-sm" aria-label={t({ en: "Cached speech preview", fr: "Écoute de la phrase" })}
                                                onError={() => notifier.echec({ fr: "Lecture impossible. Réessayez.", en: "Could not play. Try again." })} />
                                        )}
                                    </Cellule>
                                    <Cellule>{[entry.provider, entry.model, entry.voice_id].filter(Boolean).join(" · ")}</Cellule>
                                    <Cellule droite>{entry.duration_seconds.toFixed(2)} s</Cellule>
                                    <Cellule droite>{entry.hit_count.toLocaleString()} {t({ en: "times", fr: "fois" })}</Cellule>
                                    <Cellule droite>{formatDateTime(entry.last_used_at, timezone)}</Cellule>
                                    <td className="pl-4 text-right">
                                        <span className="inline-flex gap-1">
                                            <Button variant="ghost" size="icon" className="size-7" disabled={previewLoading === entry.id || removing !== null}
                                                aria-label={`${t({ en: "Listen to", fr: "Écouter" })} ${entry.text_preview || ""}`} onClick={() => handlePreview(entry)}>
                                                {previewLoading === entry.id ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                                            </Button>
                                            <Button variant="ghost" size="sm" className="h-7" disabled={removing !== null}
                                                aria-label={`${t({ en: "Invalidate", fr: "Invalider" })} ${entry.text_preview || ""}`} onClick={() => handleInvalidate(entry)}>
                                                {removing === entry.id ? t({ en: "Invalidating…", fr: "Invalidation…" }) : t({ en: "Invalidate", fr: "Invalider" })}
                                            </Button>
                                        </span>
                                    </td>
                                </Ligne>
                            ))}
                        </Tableau>
                        <BarrePagination total={total} page={Math.floor(offset / PAGE_SIZE)} parPage={PAGE_SIZE} changerPage={(page) => setOffset(page * PAGE_SIZE)} />
                    </>
                )}
            </section>
        );
    }

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
                <div className="relative min-w-48 flex-1">
                    <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input aria-label="Search cached speech" placeholder="Search phrase, model, or voice…" maxLength={200}
                        className="pl-9" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
                </div>
                <div>
                    <label htmlFor="tts-cache-sort" className="mb-1 block text-xs text-muted-foreground">Sort by</label>
                    <ListeDeroulante id="tts-cache-sort" value={sortValue} onChange={(e) => { setSortValue(e.target.value); setOffset(0); }}
                        className="h-9 rounded-md border bg-background px-3 text-sm">
                        {SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </ListeDeroulante>
                </div>
                <div className="w-28">
                    <label htmlFor="tts-min-duration" className="mb-1 block text-xs text-muted-foreground">Min seconds</label>
                    <Input id="tts-min-duration" type="number" min="0" step="0.1" value={minDuration}
                        onChange={(e) => { setMinDuration(e.target.value); setOffset(0); }} placeholder="Any" />
                </div>
                <div className="w-28">
                    <label htmlFor="tts-max-duration" className="mb-1 block text-xs text-muted-foreground">Max seconds</label>
                    <Input id="tts-max-duration" type="number" min="0" step="0.1" value={maxDuration}
                        onChange={(e) => { setMaxDuration(e.target.value); setOffset(0); }} placeholder="Any" />
                </div>
                <Button variant="outline" size="icon" aria-label="Refresh cached speech" disabled={loading}
                    onClick={() => setRefresh((value) => value + 1)}>
                    <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                </Button>
                <Button variant="outline" disabled={loading || removing !== null} onClick={() => handleInvalidate()}>
                    <Trash2 className="mr-2 h-4 w-4" />{removing === "all" ? "Clearing…" : "Clear organization cache"}
                </Button>
            </div>
            <p className="text-xs text-muted-foreground">
                Reuses count speech requests served from cache. Listening here does not count as reuse or extend expiry.
            </p>
            {error ? <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-destructive">{error}</div>
                : loading ? <Skeleton className="h-40 w-full" />
                    : entries.length === 0 ? <div className="py-12 text-center text-muted-foreground">
                        <AudioLines className="mx-auto mb-3 h-10 w-10" />
                        <p>No cached speech found.</p>
                        <p className="mt-1 text-sm">Speech appears here after a successful synthesis in a workflow with Speech Caching enabled.</p>
                    </div>
                        : <>
                            <p className="text-sm text-muted-foreground">{total} cached phrase{total === 1 ? "" : "s"} matching your filters</p>
                            <div className="space-y-3">
                                {entries.map((entry) => (
                                    <div key={entry.id} className="rounded-lg border p-4">
                                        <div className="flex flex-wrap items-start justify-between gap-3">
                                            <div className="min-w-0 flex-1">
                                                <p className="whitespace-pre-wrap break-words text-sm">{entry.text_preview || "Cached speech"}</p>
                                                <p className="mt-1 break-words text-xs text-muted-foreground">{[entry.provider, entry.model, entry.voice_id].filter(Boolean).join(" · ")}</p>
                                                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                                                    <span>{entry.duration_seconds.toFixed(2)} seconds</span>
                                                    <span>{entry.hit_count.toLocaleString()} reuses</span>
                                                    <span>Last used {formatDateTime(entry.last_used_at, timezone)}</span>
                                                </div>
                                            </div>
                                            <div className="flex gap-2">
                                                <Button variant="outline" size="sm" disabled={previewLoading === entry.id || removing !== null}
                                                    aria-label={`Listen to ${entry.text_preview || "cached speech"}`} onClick={() => handlePreview(entry)}>
                                                    {previewLoading === entry.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}Listen
                                                </Button>
                                                <Button variant="ghost" size="sm" className="text-destructive" disabled={removing !== null}
                                                    aria-label={`Invalidate ${entry.text_preview || "cached speech"}`} onClick={() => handleInvalidate(entry)}>
                                                    <Trash2 className="mr-2 h-4 w-4" />{removing === entry.id ? "Invalidating…" : "Invalidate"}
                                                </Button>
                                            </div>
                                        </div>
                                        {preview?.id === entry.id && <audio ref={audioRef} controls autoPlay src={preview.url}
                                            className="mt-3 w-full" aria-label="Cached speech preview" onError={() => notifier.echec({ fr: "Lecture impossible. Réessayez.", en: "Could not play. Try again." })} />}
                                    </div>
                                ))}
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-sm text-muted-foreground">{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
                                <div className="flex gap-2">
                                    <Button variant="outline" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>Previous</Button>
                                    <Button variant="outline" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((value) => value + PAGE_SIZE)}>Next</Button>
                                </div>
                            </div>
                        </>}
        </div>
    );
}
