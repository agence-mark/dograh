"use client";

/**
 * [.mark] Clôture D2 (É69, maquette `chat-builder.tsx`) : en tête du chat, « Tours 1 à N résumés (contexte à 70 %, date) », dépliable sur le
 * texte du résumé. Le builder résume les vieux tours quand le chat approche la limite de son cerveau (seuil réglable dans les réglages du
 * Labo) ; la personne sait ainsi ce qui n'est plus lu tel quel. Rien n'est inventé : le nombre et la date viennent du serveur.
 */
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";

export type DonneesResume = { tours_resumes?: number; resume?: string | null; resume_le?: string | null };

const jourHeure = (iso: string | null | undefined, langue: "fr" | "en") => {
    const ms = iso ? Date.parse(iso) : NaN;
    if (Number.isNaN(ms)) return "";
    return new Date(ms).toLocaleString(langue === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};

export function ToursResumes({ fil }: { fil: DonneesResume }) {
    const { t, langue } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    const n = fil.tours_resumes ?? 0;
    if (n <= 0) return null;
    const date = jourHeure(fil.resume_le, langue);
    return (
        <div data-tours-resumes>
            <button
                type="button"
                aria-expanded={ouvert}
                onClick={() => setOuvert((v) => !v)}
                className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-left text-xs text-muted-foreground hover:font-medium"
            >
                {ouvert ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
                {t({
                    en: `Turns 1 to ${n} summarized${date ? ` (context at 70 %, ${date})` : ""}`,
                    fr: `Tours 1 à ${n} résumés${date ? ` (contexte à 70 %, ${date})` : ""}`,
                })}
            </button>
            {ouvert && (
                <p className="px-3 pt-2 text-xs whitespace-pre-wrap text-muted-foreground">
                    {fil.resume ? `${t({ en: "Summary", fr: "Résumé" })} : ${fil.resume}` : t({ en: "The summary is not available.", fr: "Le résumé n'est pas disponible." })}
                </p>
            )}
        </div>
    );
}
