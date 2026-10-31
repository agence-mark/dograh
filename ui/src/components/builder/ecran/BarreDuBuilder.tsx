"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): the two buttons the builder adds to the editor's top bar.
 * « Builder AI » opens or closes the side panel; « Tests » leads to the agent's « Tests and corrections » page
 * (`/workflow/<id>/tests`, built by the tests chantier: only the link is here).
 */
import { FlaskConical, Sparkles } from "lucide-react";
import Link from "next/link";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";

const T = {
    builder: { en: "Builder AI", fr: "Builder IA" },
    tests: { en: "Tests", fr: "Tests" },
} satisfies Record<string, Texte>;

export function BarreDuBuilder({ ouvert, onToggle, testsHref }: { ouvert: boolean; onToggle: () => void; testsHref: string }) {
    const { t } = useLangue();
    return (
        <>
            <Button
                type="button"
                variant={ouvert ? "default" : "outline"}
                className="flex items-center gap-2 border-border"
                aria-pressed={ouvert}
                data-bouton="builder-ia"
                aria-label={t(T.builder)}
                title={t(T.builder)}
                onClick={onToggle}
            >
                <Sparkles className="h-4 w-4" aria-hidden />
                <span className="hidden 2xl:inline">{t(T.builder)}</span>
            </Button>
            <Button asChild variant="outline" className="flex items-center gap-2 border-border">
                <Link href={testsHref} data-bouton="tests" aria-label={t(T.tests)} title={t(T.tests)}>
                    <FlaskConical className="h-4 w-4" aria-hidden />
                    <span className="hidden 2xl:inline">{t(T.tests)}</span>
                </Link>
            </Button>
        </>
    );
}
