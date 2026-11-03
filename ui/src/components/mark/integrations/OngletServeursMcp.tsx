"use client";

/**
 * [.mark] U3 sexies point 6 (E73, E74) : Intégrations › Serveurs MCP.
 *
 * Un serveur se branche UNE fois et apporte tous ses outils, qui apparaissent dans Outils, marqués MCP. Transport :
 * HTTP en flux (Streamable HTTP) ou SSE (le `MCPClient` de Pipecat sait les deux). En-têtes libres (texte, variable,
 * secret), délais de connexion et de lecture, « Tester la connexion » (découverte des outils, rien d'écrit), réglage
 * de chaque outil (Autorisé, Confirmer avec l'appelant, Désactivé : un outil désactivé n'est jamais proposé au
 * modèle) et le comportement commun à tous ses outils.
 */
import { notifier } from "@/components/mark/notifications";
import { ActionDePage } from "./action-de-page";
import { Plus, Server } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { createToolApiV1ToolsPost, listToolsApiV1ToolsGet, testerLaConnexionMcpApiV1ToolsMcpTesterPost, updateToolApiV1ToolsToolUuidPut } from "@/client/sdk.gen";
import type { ToolResponse } from "@/client/types.gen";
import { CredentialSelector } from "@/components/http";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { useLangue } from "../langue/langue";
import { type Config, configDe, definitionAvec, liste, nombre, texte } from "../outils/modele";
import { OngletComportement } from "../outils/OngletComportement";
import { BlocEntetes } from "../outils/OngletsHttp";
import { EtatVide } from "../studio/etat-vide";
import { BlocChamp, Champs, FenetreOnglets, LigneChamp, Segmente } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Cellule, Ligne, Tableau } from "../studio/tableau";

type Reglage = "autorise" | "confirmer" | "desactive";
type Decouvert = { name: string; description?: string };

export function OngletServeursMcp() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [serveurs, setServeurs] = useState<ToolResponse[] | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [ouvert, setOuvert] = useState<ToolResponse | "nouveau" | null>(null);
    const dejaLu = useRef(false);

    const relire = useCallback(async () => {
        const r = await listToolsApiV1ToolsGet({ query: { status: "active,draft", category: "mcp" } });
        if (r.error || !r.data) return setErreur(detailFromError(r.error, "Servers unreadable"));
        setErreur(null);
        setServeurs(r.data);
    }, []);
    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [loading, user, relire]);

    if (erreur) return <EtatVide cas="erreur" reessayer={() => void relire()} />;
    if (!serveurs) return <EtatVide cas="chargement" />;
    return (
        <div>
            <ActionDePage onglet="mcp">
                <Button onClick={() => setOuvert("nouveau")}>
                    <Plus className="size-4" aria-hidden /> {t({ en: "Add an MCP server", fr: "Ajouter un serveur MCP" })}
                </Button>
            </ActionDePage>
            {serveurs.length === 0 ? (
                <EtatVide cas="premier" icone={Server} titre={t({ en: "No MCP server", fr: "Aucun serveur MCP" })} />
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Server", fr: "Serveur" }) },
                        { titre: t({ en: "Connection", fr: "Connexion" }) },
                        { titre: t({ en: "Tools", fr: "Outils" }), droite: true },
                    ]}
                >
                    {serveurs.map((s) => {
                        const c = configDe(s);
                        return (
                            <Ligne key={s.tool_uuid} onClick={() => setOuvert(s)}>
                                <Cellule principale sous={texte(c, "url")}>
                                    {s.name}
                                </Cellule>
                                <Cellule>{texte(c, "transport") === "sse" ? t({ en: "SSE", fr: "SSE" }) : t({ en: "Streamable HTTP", fr: "Streamable HTTP" })}</Cellule>
                                <Cellule droite>{liste<Decouvert>(c, "discovered_tools").length}</Cellule>
                            </Ligne>
                        );
                    })}
                </Tableau>
            )}
            {ouvert && <FenetreServeur serveur={ouvert === "nouveau" ? null : ouvert} fermer={() => setOuvert(null)} apres={() => void relire()} />}
        </div>
    );
}

function FenetreServeur({ serveur, fermer, apres }: { serveur: ToolResponse | null; fermer: () => void; apres: () => void }) {
    const { t } = useLangue();
    const libelles = { connexion: t({ en: "Connection", fr: "Connexion" }), outils: t({ en: "Tools", fr: "Outils" }), comportement: t({ en: "Behaviour", fr: "Comportement" }) };
    const [onglet, setOnglet] = useState<keyof typeof libelles>("connexion");
    const [nom, setNom] = useState(serveur?.name ?? "");
    const [config, setConfig] = useState<Config>(
        serveur ? configDe(serveur) : { transport: "streamable_http", url: "", timeout_secs: 30, sse_read_timeout_secs: 300, tools_filter: [], reglages_outils: {} },
    );
    const [decouverts, setDecouverts] = useState<Decouvert[]>(liste<Decouvert>(config, "discovered_tools"));
    const [message, setMessage] = useState<string | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const pose = (m: Config) => setConfig((x) => ({ ...x, ...m }));
    const reglages = (config.reglages_outils ?? {}) as Record<string, Reglage>;

    const tester = async () => {
        setMessage(null);
        setErreur(null);
        const r = await testerLaConnexionMcpApiV1ToolsMcpTesterPost({
            body: {
                url: texte(config, "url"),
                transport: texte(config, "transport") === "sse" ? "sse" : "streamable_http",
                timeout_secs: nombre(config, "timeout_secs", 30),
                sse_read_timeout_secs: nombre(config, "sse_read_timeout_secs", 300),
                credential_uuid: texte(config, "credential_uuid") || null,
                en_tetes_ext: liste<NonNullable<Parameters<typeof testerLaConnexionMcpApiV1ToolsMcpTesterPost>[0]["body"]["en_tetes_ext"]>[number]>(config, "en_tetes_ext"),
            },
        });
        if (r.error || !r.data) return setErreur(detailFromError(r.error, "Test failed"));
        if (!r.data.ok) return setErreur(r.data.erreur ?? t({ en: "The server did not answer.", fr: "Le serveur n'a pas répondu." }));
        const trouves = r.data.outils ?? [];
        setDecouverts(trouves);
        pose({ discovered_tools: trouves });
        setMessage(t({ en: `Connected: ${trouves.length} tool(s) found.`, fr: `Connecté : ${trouves.length} outil(s) trouvé(s).` }));
    };

    const enregistrer = async () => {
        if (!nom.trim()) return setErreur(t({ en: "Give the server a name.", fr: "Donnez un nom au serveur." }));
        if (!/^https?:\/\//i.test(texte(config, "url"))) return setErreur(t({ en: "The address must start with http:// or https://", fr: "L'adresse doit commencer par http:// ou https://" }));
        const definition = serveur ? definitionAvec(serveur, config) : { schema_version: 1, type: "mcp", config };
        const r = serveur
            ? await updateToolApiV1ToolsToolUuidPut({ path: { tool_uuid: serveur.tool_uuid }, body: { name: nom.trim(), definition: definition as never } })
            : await createToolApiV1ToolsPost({ body: { name: nom.trim(), category: "mcp", definition: definition as never } });
        if (r.error) return setErreur(detailFromError(r.error, "Failed to save the server"));
        notifier.succes({ fr: "Serveur enregistré.", en: "Server saved." });
        apres();
        fermer();
    };

    return (
        <FenetreOnglets
            fermer={fermer}
            titre={serveur ? serveur.name : t({ en: "Connect an MCP server", fr: "Brancher un serveur MCP" })}
            onglets={Object.values(libelles)}
            onglet={libelles[onglet]}
            changerOnglet={(l) => setOnglet((Object.keys(libelles) as (keyof typeof libelles)[]).find((k) => libelles[k] === l) ?? "connexion")}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            onValider={() => void enregistrer()}
            pied={erreur ? <span className="text-sm text-destructive">{erreur}</span> : message ? <span className="text-sm text-muted-foreground">{message}</span> : undefined}
        >
            {onglet === "connexion" && (
                <Champs>
                    <BlocChamp libelle={t({ en: "Name", fr: "Nom" })}>
                        <Input value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t({ en: "Server name", fr: "Nom du serveur" })} />
                    </BlocChamp>
                    <LigneChamp libelle={t({ en: "Transport", fr: "Transport" })}>
                        <Segmente valeur={texte(config, "transport") === "sse" ? "SSE" : "HTTP"} options={["HTTP", "SSE"]} changer={(v) => pose({ transport: v === "SSE" ? "sse" : "streamable_http" })} />
                    </LigneChamp>
                    <BlocChamp libelle={t({ en: "Address", fr: "Adresse" })}>
                        <Input value={texte(config, "url")} onChange={(e) => pose({ url: e.target.value })} placeholder="https://…" aria-label={t({ en: "Server address", fr: "Adresse du serveur" })} />
                    </BlocChamp>
                    <BlocChamp libelle={t({ en: "Credential", fr: "Identifiant" })}>
                        <CredentialSelector
                            value={texte(config, "credential_uuid")}
                            onChange={(v: string) => pose({ credential_uuid: v || null })}
                            showLabel={false}
                            placeholder={t({ en: "No authentication", fr: "Aucune authentification" })}
                            description=""
                        />
                    </BlocChamp>
                    <BlocEntetes config={config} pose={pose} />
                    <LigneChamp libelle={t({ en: "Connection timeout (s)", fr: "Délai de connexion (s)" })}>
                        <Input className="h-8 w-24 text-right" value={String(nombre(config, "timeout_secs", 30))} onChange={(e) => pose({ timeout_secs: Math.min(120, Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1)) })} aria-label={t({ en: "Connection timeout", fr: "Délai de connexion" })} />
                    </LigneChamp>
                    <LigneChamp libelle={t({ en: "Read timeout (s)", fr: "Délai de lecture (s)" })}>
                        <Input className="h-8 w-24 text-right" value={String(nombre(config, "sse_read_timeout_secs", 300))} onChange={(e) => pose({ sse_read_timeout_secs: Math.min(900, Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1)) })} aria-label={t({ en: "Read timeout", fr: "Délai de lecture" })} />
                    </LigneChamp>
                    <div className="py-3">
                        <Button variant="outline" onClick={() => void tester()}>
                            {t({ en: "Test the connection", fr: "Tester la connexion" })}
                        </Button>
                    </div>
                </Champs>
            )}
            {onglet === "outils" &&
                (decouverts.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "No tool discovered yet: test the connection.", fr: "Aucun outil découvert : testez la connexion." })}</p>
                ) : (
                    <Champs>
                        {decouverts.map((d) => (
                            <LigneChamp
                                key={d.name}
                                libelle={
                                    <span>
                                        <span className="font-mono">{d.name}</span>
                                        <span className="block text-xs font-normal text-muted-foreground">{d.description}</span>
                                    </span>
                                }
                            >
                                <Liste
                                    valeur={reglages[d.name] ?? "autorise"}
                                    changer={(v) => pose({ reglages_outils: { ...reglages, [d.name]: v as Reglage } })}
                                    options={[
                                        { valeur: "autorise", libelle: t({ en: "Allowed", fr: "Autorisé" }) },
                                        { valeur: "confirmer", libelle: t({ en: "Confirm with the caller", fr: "Confirmer avec l'appelant" }) },
                                        { valeur: "desactive", libelle: t({ en: "Disabled", fr: "Désactivé" }) },
                                    ]}
                                    className="w-56"
                                />
                            </LigneChamp>
                        ))}
                    </Champs>
                ))}
            {onglet === "comportement" && <OngletComportement categorie="mcp" config={config} pose={pose} />}
        </FenetreOnglets>
    );
}
