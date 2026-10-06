"use client";

/**
 * [.mark] The establishment a test plays (chantier l-agent-travaille, L2, E3).
 *
 * A browser, keyboard or simulated test has no called number: the establishment is the one
 * chosen here, else the first this agent serves through its numbers, else the organization's
 * first (resolved by the server). Shown only when the organization has establishments: an
 * organization without any sees exactly the test window of before.
 */
import { useEffect, useRef, useState } from "react";

import { getEtablissementsApiV1OrganizationsEtablissementsGet } from "@/client/sdk.gen";
import type { Etablissement } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

import { useLangue } from "../langue/langue";

export const PREMIER = "";

export function ChoixEtablissementEssai({
    valeur,
    onChange,
    desactive,
}: {
    valeur: string;
    onChange: (id: string) => void;
    desactive?: boolean;
}) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [liste, setListe] = useState<Etablissement[]>([]);
    const dejaLu = useRef(false);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            const reponse = await getEtablissementsApiV1OrganizationsEtablissementsGet();
            setListe(reponse.data?.etablissements ?? []);
        })();
    }, [authLoading, user]);

    if (liste.length === 0) return null;
    return (
        <label className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-testid="choix-etablissement-essai">
            {t({ en: "Establishment played", fr: "Établissement joué" })}
            <select
                className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                value={valeur}
                disabled={desactive}
                onChange={(e) => onChange(e.target.value)}
                aria-label={t({ en: "Establishment played", fr: "Établissement joué" })}
            >
                <option value={PREMIER}>{t({ en: "The agent's first (as on its numbers)", fr: "Le premier de l'agent (selon ses numéros)" })}</option>
                {liste.map((e) => (
                    <option key={e.id} value={e.id}>
                        {e.nom}
                    </option>
                ))}
            </select>
        </label>
    );
}
