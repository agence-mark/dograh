"use client";

import { GitBranch } from "lucide-react";

interface NodeTransitionMarkerProps {
    nodeName: string;
    // [.mark] Chantier agents-specialises (lot 2): set when another agent takes the call over.
    agentName?: string;
}

export function NodeTransitionMarker({ nodeName, agentName }: NodeTransitionMarkerProps) {
    return (
        <div className="flex items-center gap-2 py-2">
            <div className="h-px flex-1 bg-border" />
            <div className="inline-flex items-center gap-1.5 px-2 py-1 text-xs">
                <GitBranch className="h-3 w-3 text-muted-foreground" />
                {agentName ? (
                    <>
                        <span className="text-muted-foreground">Handed over to</span>
                        <span className="font-medium text-(--acc-text)">{agentName}</span>
                        <span className="text-muted-foreground">›</span>
                    </>
                ) : null}
                <span className="font-mono font-medium text-(--acc-text)">{nodeName}</span>
            </div>
            <div className="h-px flex-1 bg-border" />
        </div>
    );
}
