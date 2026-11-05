"use client";

/**
 * [.mark] Partie 3, sous-lot 6: the banner of the agent alerts on the Tests tab. It shows the latest alert « a version does worse than
 * the previous one » and points to « To improve » (origin Deployment). It reads, it never decides: no button here rolls a version
 * back, publishes or removes anything (« never an automatic switch »). A failed read shows nothing (the Schedule window says it).
 */
import { TriangleAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { lireLesAlertesApiV1BuilderAlertesWorkflowIdGet } from "@/client/sdk.gen";
import { adressesDe } from "@/components/builder/chat/adresses";
import { useLangue } from "@/components/mark/langue/langue";

import type { AlerteLevee } from "./PlanifierLaSuite";

export function BandeauDAlertes({ agentId, version }: { agentId: number; version?: number }) {
    const { t } = useLangue();
    const adresses = adressesDe(usePathname() ?? "/labo");
    const [alerte, setAlerte] = useState<AlerteLevee | null>(null);

    useEffect(() => {
        let vivant = true;
        void lireLesAlertesApiV1BuilderAlertesWorkflowIdGet({ path: { workflow_id: agentId } })
            .then((r) => {
                if (!vivant || r.error || !r.data) return;
                const levees = ((r.data as unknown as { levees?: AlerteLevee[] }).levees ?? []).filter((a) => version === undefined || a.version >= version);
                setAlerte(levees[0] ?? null);
            })
            .catch(() => undefined);
        return () => {
            vivant = false;
        };
    }, [agentId, version]);

    if (!alerte) return null;
    return (
        <div role="status" data-testid="bandeau-d-alerte" className="flex items-start gap-3 rounded-xl border border-(--signal-danger)/40 bg-(--signal-danger)/10 px-4 py-3 text-sm">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-(--signal-danger)" aria-hidden />
            <p className="flex-1">
                <span className="font-medium">
                    {t({ en: `Version ${alerte.version} does worse than version ${alerte.contre}.`, fr: `La version ${alerte.version} fait moins bien que la version ${alerte.contre}.` })}
                </span>{" "}
                <span className="text-muted-foreground">{alerte.resume}</span>{" "}
                <span className="text-muted-foreground">{t({ en: "Nothing was changed: it is yours to decide.", fr: "Rien n'a été changé : c'est à vous de décider." })}</span>
            </p>
            <Link href={adresses.aAmeliorer} className="shrink-0 font-medium text-(--acc) hover:font-semibold">
                {t({ en: "Open To improve", fr: "Ouvrir À améliorer" })}
            </Link>
        </div>
    );
}
