"use client";

import { useEffect } from "react";

import { declarerAgentCourant } from "./notifier";

/** À appeler par l'écran d'un agent : le bouton « Publier » des notifications publiera cet agent. */
export function useAgentCourant(workflowId: number | null | undefined) {
    useEffect(() => {
        return declarerAgentCourant(workflowId ?? null);
    }, [workflowId]);
}
