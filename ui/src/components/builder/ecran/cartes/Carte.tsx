"use client";

/** [.mark] builder-agent-vocal (lot 4): the frame every card of the builder panel shares. */
import type { ReactNode } from "react";

export function Carte({
    type,
    titre,
    aide,
    children,
}: {
    type: string;
    titre: string;
    aide?: string;
    children: ReactNode;
}) {
    return (
        <section className="my-2 rounded-lg border bg-card p-3 text-card-foreground" data-carte={type}>
            <h4 className="text-sm font-semibold">{titre}</h4>
            {aide && <p className="mb-2 text-xs text-muted-foreground">{aide}</p>}
            {children}
        </section>
    );
}
