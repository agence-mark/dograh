"use client";

/**
 * [.mark] U3 sexies point 1 (E73) : « Nouvel outil », une carte par type (les huit catégories du fork).
 *
 * « Outil MCP » renvoie à Intégrations › Serveurs MCP : un serveur se branche une fois et apporte tous ses outils.
 * Les autres types demandent un nom (et, selon le type, l'action d'un logiciel branché ou l'agent visé), puis
 * l'outil est créé avec la définition par défaut du fork et sa fenêtre s'ouvre.
 */
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
    createIntegrationDefinition,
    createToolDefinition,
    createTransferAgentDefinition,
    DEFAULT_TRANSFER_AGENT_MESSAGE,
    getCategoryConfig,
    type ToolCategory,
} from "@/app/tools/config";
import { createToolApiV1ToolsPost, getWorkflowsSummaryApiV1WorkflowSummaryGet } from "@/client/sdk.gen";
import type { CreateToolRequest, ToolResponse } from "@/client/types.gen";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { ChampsCreationIntegration } from "../connecteurs/ConfigOutilIntegration";
import type { ConfigIntegration } from "../connecteurs/useConnecteurs";
import { useLangue } from "../langue/langue";
import { BlocChamp, Champs,FenetreOnglets } from "../studio/fenetre-onglets";
import { espaceDe } from "../studio/navigation-studio";
import { Liste } from "../studio/liste";
import { LIBELLES_TYPE, type TypeOutil } from "./modele";
import { notifier } from "@/components/mark/notifications";

const ORDRE: TypeOutil[] = ["integration", "http_api", "mcp", "transfer_call", "transfer_agent", "end_call", "native", "calculator"];
// `native` (demande de rappel) se crée depuis l'agent : elle n'a pas de définition par défaut dans le fork.
const CREABLES = new Set<TypeOutil>(["integration", "http_api", "transfer_call", "transfer_agent", "end_call", "calculator"]);

const DESCRIPTIONS: Record<TypeOutil, { en: string; fr: string }> = {
    integration: { en: "Read or write in a connected software: calendar, CRM, tickets, SMS…", fr: "Lire ou écrire dans un logiciel branché : agenda, CRM, tickets, SMS…" },
    http_api: { en: "Call any web address, with its parameters, headers and credential.", fr: "Appeler n'importe quelle adresse web, avec ses paramètres, ses en-têtes et son identifiant." },
    mcp: { en: "The tools of an MCP server, discovered when it is connected.", fr: "Les outils d'un serveur MCP, découverts à son branchement." },
    end_call: { en: "Hang up, with or without a closing sentence, and note the reason.", fr: "Raccrocher, avec ou sans phrase de fin, et noter la raison." },
    transfer_call: { en: "Pass the call to a number, fixed or chosen from the conversation.", fr: "Passer l'appel à un numéro, fixe ou choisi selon la conversation." },
    transfer_agent: { en: "Hand the call to another agent of the organization.", fr: "Confier l'appel à un autre agent de l'organisation." },
    native: { en: "Record a call-back request with its required fields.", fr: "Enregistrer une demande de rappel avec les champs requis." },
    calculator: { en: "Calculate an amount or a duration without a mistake.", fr: "Calculer un montant ou une durée sans se tromper." },
};

export function FenetreNouvelOutil({ fermer, cree }: { fermer: () => void; cree: (o: ToolResponse) => void }) {
    const { t } = useLangue();
    const router = useRouter();
    const pathname = usePathname();
    const [type, setType] = useState<TypeOutil | null>(null);
    const [nom, setNom] = useState("");
    const [description, setDescription] = useState("");
    const [integration, setIntegration] = useState<ConfigIntegration | null>(null);
    const [agents, setAgents] = useState<{ id: number; name: string }[]>([]);
    const [agent, setAgent] = useState("");
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (type !== "transfer_agent") return;
        void getWorkflowsSummaryApiV1WorkflowSummaryGet().then((r) => setAgents(r.data ?? []));
    }, [type]);

    const choisir = (x: TypeOutil) => {
        if (x === "mcp") {
            router.push(`${espaceDe(pathname ?? "/labo").base}/integrations?onglet=mcp`);
            return;
        }
        if (CREABLES.has(x)) setType(x);
    };

    const creer = async () => {
        if (!type) return;
        if (!nom.trim()) return setErreur(t({ en: "Give the tool a name.", fr: "Donnez un nom à l'outil." }));
        if (type === "integration" && !integration) return setErreur(t({ en: "Choose the software and the action.", fr: "Choisissez le logiciel et l'action." }));
        if (type === "transfer_agent" && !agent) return setErreur(t({ en: "Choose the agent to transfer to.", fr: "Choisissez l'agent visé." }));
        const definition =
            type === "integration" && integration
                ? createIntegrationDefinition(integration)
                : type === "transfer_agent"
                  ? createTransferAgentDefinition({ workflow_id: Number(agent), message: DEFAULT_TRANSFER_AGENT_MESSAGE })
                  : createToolDefinition(type as ToolCategory);
        const cfg = getCategoryConfig(type as ToolCategory);
        const corps: CreateToolRequest = {
            name: nom.trim(),
            description: description.trim() || undefined,
            category: type as ToolCategory,
            icon: cfg?.iconName || "globe",
            icon_color: cfg?.iconColor || "#2a2a2a",
            definition,
        };
        setEnCours(true);
        const r = await createToolApiV1ToolsPost({ body: corps });
        setEnCours(false);
        if (r.error || !r.data) return setErreur(detailFromError(r.error, "Failed to create tool"));
        cree(r.data);
        notifier.succes({ fr: "Outil créé.", en: "Tool created." });
    };

    if (!type) {
        return (
            <FenetreOnglets
                fermer={fermer}
                titre={t({ en: "New tool", fr: "Nouvel outil" })}
                sous={t({ en: "Choose what the agent will be able to do.", fr: "Choisissez ce que l'agent pourra faire." })}
                valider={null}
            >
                <div className="grid gap-3 sm:grid-cols-2">
                    {ORDRE.map((x) => {
                        const creable = CREABLES.has(x) || x === "mcp";
                        return (
                            <button
                                key={x}
                                type="button"
                                disabled={!creable}
                                onClick={() => choisir(x)}
                                className="flex flex-col gap-0.5 rounded-xl border bg-background p-4 text-left transition-colors enabled:cursor-pointer enabled:hover:border-foreground/40 disabled:opacity-60"
                            >
                                <span className="text-sm font-medium">{t(LIBELLES_TYPE[x])}</span>
                                <span className="text-xs text-muted-foreground">
                                    {creable ? t(DESCRIPTIONS[x]) : t({ en: "Created from an agent's step.", fr: "Se crée depuis l'étape d'un agent." })}
                                </span>
                            </button>
                        );
                    })}
                </div>
            </FenetreOnglets>
        );
    }

    return (
        <FenetreOnglets
            fermer={() => setType(null)}
            titre={t(LIBELLES_TYPE[type])}
            sous={t(DESCRIPTIONS[type])}
            valider={enCours ? t({ en: "Creating…", fr: "Création…" }) : t({ en: "Create", fr: "Créer" })}
            desactiver={enCours}
            onValider={() => void creer()}
            pied={erreur ? <span className="text-sm text-destructive">{erreur}</span> : undefined}
        >
            <Champs>
                <BlocChamp libelle={t({ en: "Name", fr: "Nom" })}>
                    <Input value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t({ en: "Name", fr: "Nom" })} />
                </BlocChamp>
                <BlocChamp libelle={t({ en: "Description for the model", fr: "Description pour le modèle" })}>
                    <Input value={description} onChange={(e) => setDescription(e.target.value)} aria-label={t({ en: "Description", fr: "Description" })} />
                </BlocChamp>
                {type === "integration" && (
                    <BlocChamp libelle={t({ en: "Software and action", fr: "Logiciel et action" })}>
                        <ChampsCreationIntegration onChange={setIntegration} avecCompte />
                    </BlocChamp>
                )}
                {type === "transfer_agent" && (
                    <BlocChamp libelle={t({ en: "Agent", fr: "Agent" })}>
                        <Liste
                            valeur={agent}
                            changer={setAgent}
                            vide={t({ en: "Choose an agent", fr: "Choisir un agent" })}
                            options={agents.map((a) => ({ valeur: String(a.id), libelle: a.name }))}
                            className="w-72"
                            taille="default"
                        />
                    </BlocChamp>
                )}
            </Champs>
        </FenetreOnglets>
    );
}
