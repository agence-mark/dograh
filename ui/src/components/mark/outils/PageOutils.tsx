"use client";

/**
 * [.mark] U3 sexies point 1 (E73) : la page Outils.
 *
 * Tableau (type, branché sur, accès, exécutions, réussite, agents), onglets Actifs / Brouillons / Archivés, filtre par
 * type, recherche, « Nouvel outil » (cartes par type) et la fenêtre d'un outil. Les chiffres sont ceux du serveur
 * (calculés sur les appels) ; un outil sans appel affiche « – ». Aucun bouton « demander un logiciel ».
 */
import { Plus, Search, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ToolResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDate } from "@/lib/dateTime";

import { useConnecteurs } from "../connecteurs/useConnecteurs";
import { Initiales } from "../integrations/OngletLogiciels";
import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { EtatVide } from "../studio/etat-vide";
import { Liste } from "../studio/liste";
import { Info } from "../studio/marques";
import { Paginee } from "../studio/pagination";
import { PageStudio } from "../studio/shell-studio";
import { Cellule, Ligne, Tableau } from "../studio/tableau";
import { TitrePage } from "../studio/titre-page";
import { FenetreNouvelOutil } from "./FenetreNouvelOutil";
import { FenetreOutil } from "./FenetreOutil";
import { configDe, ecritHttp, LIBELLES_TYPE, texte,type TypeOutil } from "./modele";
import { useOutils } from "./useOutils";
import { VisuelOutil } from "./visuel";

type Statut = "active" | "draft" | "archived";
const STATUTS: { id: Statut; en: string; fr: string }[] = [
    { id: "active", en: "Active", fr: "Actifs" },
    { id: "draft", en: "Drafts", fr: "Brouillons" },
    { id: "archived", en: "Archived", fr: "Archivés" },
];

export function PageOutils() {
    const { t, langue } = useLangue();
    const { outils, stats, erreur, relire } = useOutils();
    const connecteurs = useConnecteurs();
    const [statut, setStatut] = useState<Statut>("active");
    const [type, setType] = useState("");
    const [q, setQ] = useState("");
    const [ouvert, setOuvert] = useState<string | null>(null);
    const [nouveau, setNouveau] = useState(false);

    const libelleType = (cat: string) => {
        const l = LIBELLES_TYPE[cat as TypeOutil];
        return l ? t(l) : cat;
    };

    const tous = useMemo(() => outils ?? [], [outils]);
    const parStatut = (s: Statut) => tous.filter((o) => o.status === s);
    const types = useMemo(() => Array.from(new Set(tous.map((o) => o.category))), [tous]);
    const liste = parStatut(statut).filter(
        (o) => (!type || o.category === type) && `${o.name} ${o.description ?? ""}`.toLowerCase().includes(q.toLowerCase()),
    );

    const brancheSur = (o: ToolResponse) => {
        const c = configDe(o);
        if (o.category === "integration") {
            return connecteurs.catalogue?.find((x) => x.nom === texte(c, "connecteur"))?.libelle ?? texte(c, "connecteur");
        }
        if (o.category === "mcp") {
            try {
                return new URL(texte(c, "url")).host;
            } catch {
                return "–";
            }
        }
        return "–";
    };
    const integrationDe = (o: ToolResponse) =>
        o.category === "integration" ? (connecteurs.catalogue?.find((x) => x.nom === texte(configDe(o), "connecteur"))?.integration ?? null) : null;
    const acces = (o: ToolResponse): string => {
        const c = configDe(o);
        let ecrit: boolean | null = null;
        if (o.category === "http_api") ecrit = ecritHttp(c);
        else if (o.category === "mcp") ecrit = true;
        else if (o.category === "integration") {
            const action = connecteurs.catalogue?.find((x) => x.nom === texte(c, "connecteur"))?.actions.find((a) => a.nom === texte(c, "action"));
            ecrit = action ? action.ecrit : null;
        }
        if (ecrit === null) return "–";
        return ecrit ? t({ en: "Writes", fr: "Écrit" }) : t({ en: "Reads", fr: "Lit" });
    };

    // [.mark] V2b : l'ancienne adresse d'un outil (`/labo/outils/<uuid>`) mène ici avec `?outil=<uuid>` : la fenêtre de
    // l'outil s'ouvre, sur le bon onglet d'état ; un outil qui n'existe plus le dit au lieu d'ouvrir une page vide.
    const adresseLue = useRef(false);
    useEffect(() => {
        if (outils === null || adresseLue.current) return;
        adresseLue.current = true;
        let demande: string | null = null;
        try {
            demande = new URLSearchParams(window.location.search).get("outil");
        } catch {
            return;
        }
        if (!demande) return;
        const outil = outils.find((o) => o.tool_uuid === demande);
        if (!outil) {
            notifier.avertissement({ fr: "Cet outil n'existe plus.", en: "This tool no longer exists." });
            return;
        }
        if (outil.status === "draft" || outil.status === "archived") setStatut(outil.status);
        setOuvert(outil.tool_uuid);
    }, [outils]);

    const ouvertOutil = ouvert ? tous.find((o) => o.tool_uuid === ouvert) : undefined;

    return (
        <PageStudio>
            <TitrePage
                titre={t({ en: "Tools", fr: "Outils" })}
                info={t({
                    en: "What the agent may do during the call. A tool belongs to the steps of an agent; a software action relies on an account connected in Integrations.",
                    fr: "Ce que l'agent a le droit de faire pendant l'appel. Un outil se rattache aux étapes d'un agent ; une action d'un logiciel s'appuie sur un compte branché dans Intégrations.",
                })}
                action={
                    <Button onClick={() => setNouveau(true)}>
                        <Plus className="size-4" /> {t({ en: "New tool", fr: "Nouvel outil" })}
                    </Button>
                }
            />
            <div role="tablist" className="flex items-center gap-1 border-b">
                {STATUTS.map((s) => (
                    <button
                        key={s.id}
                        type="button"
                        role="tab"
                        aria-selected={statut === s.id}
                        onClick={() => setStatut(s.id)}
                        className={`-mb-px cursor-pointer border-b-2 px-3 py-2.5 text-sm ${
                            statut === s.id ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:font-medium"
                        }`}
                    >
                        {t(s)} <span className="tabular-nums text-muted-foreground">{parStatut(s.id).length}</span>
                    </button>
                ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
                <div className="relative w-full max-w-72">
                    <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder={t({ en: "Search a tool", fr: "Rechercher un outil" })}
                        className="h-9 border-transparent bg-muted/50 pl-9 shadow-none focus-visible:bg-background"
                    />
                </div>
                <Liste
                    valeur={type}
                    changer={setType}
                    vide={t({ en: "All types", fr: "Tous les types" })}
                    options={types.map((c) => ({ valeur: c, libelle: libelleType(c) }))}
                    className="w-56"
                    taille="default"
                />
            </div>
            {erreur && <EtatVide cas="erreur" reessayer={() => void relire()} />}
            {!erreur && outils === null && <EtatVide cas="chargement" />}
            {!erreur && outils !== null && liste.length > 0 && (
                <Paginee liste={liste}>
                    {(page) => (
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Tool", fr: "Outil" }) },
                                { titre: t({ en: "Type", fr: "Type" }) },
                                { titre: t({ en: "Connected to", fr: "Branché sur" }) },
                                {
                                    titre: (
                                        <span className="inline-flex items-center gap-1.5">
                                            {t({ en: "Access", fr: "Accès" })}
                                            <Info>
                                                {t({
                                                    en: "« Writes »: the tool changes something at the client's; its first trial is validated by a person.",
                                                    fr: "« Écrit » : l'outil modifie quelque chose chez le client ; son premier essai est validé par une personne.",
                                                })}
                                            </Info>
                                        </span>
                                    ),
                                },
                                {
                                    titre: (
                                        <span className="inline-flex items-center gap-1.5">
                                            {t({ en: "Runs", fr: "Exécutions" })}
                                            <Info>{t({ en: "Over the last 30 days, computed on the calls.", fr: "Sur les 30 derniers jours, calculées à la volée sur les appels." })}</Info>
                                        </span>
                                    ),
                                    droite: true,
                                },
                                { titre: t({ en: "Success", fr: "Réussite" }), droite: true },
                                { titre: t({ en: "Agents", fr: "Agents" }), droite: true },
                                { titre: t({ en: "Modified", fr: "Modifié" }), droite: true },
                            ]}
                        >
                            {page.map((o) => {
                                const s = stats[o.tool_uuid];
                                return (
                                    <Ligne key={o.tool_uuid} onClick={() => setOuvert(o.tool_uuid)}>
                                        <td className="py-3">
                                            <span className="flex items-center gap-3">
                                                <VisuelOutil
                                                    categorie={o.category}
                                                    integration={integrationDe(o)}
                                                    connecteur={texte(configDe(o), "connecteur")}
                                                    initiales={<Initiales nom={o.name.replace(/_/g, " ")} taille={32} />}
                                                />
                                                <span className="min-w-0">
                                                    <span className="block font-mono font-medium">{o.name}</span>
                                                    {o.description && <span className="block max-w-80 truncate text-xs text-muted-foreground">{o.description}</span>}
                                                </span>
                                            </span>
                                        </td>
                                        <Cellule>{libelleType(o.category)}</Cellule>
                                        <Cellule>{brancheSur(o)}</Cellule>
                                        <Cellule>{acces(o)}</Cellule>
                                        <Cellule droite>{s ? s.executions : "–"}</Cellule>
                                        <Cellule droite>{s && s.reussite !== null ? `${s.reussite} %` : "–"}</Cellule>
                                        <Cellule droite>{s ? s.nb_agents : "–"}</Cellule>
                                        <Cellule droite>{(o.updated_at ?? o.created_at) ? formatDate(o.updated_at ?? o.created_at ?? "", null, langue) : "–"}</Cellule>
                                    </Ligne>
                                );
                            })}
                        </Tableau>
                    )}
                </Paginee>
            )}
            {!erreur && outils !== null && liste.length === 0 &&
                (tous.length === 0 && !q && !type ? (
                    <EtatVide cas="premier" icone={Wrench} titre={t({ en: "No tool", fr: "Aucun outil" })} />
                ) : (
                    <EtatVide
                        cas="filtre"
                        recherche={q || (type ? libelleType(type) : t(STATUTS.find((s) => s.id === statut)!))}
                        effacer={() => {
                            setQ("");
                            setType("");
                        }}
                    />
                ))}
            {ouvertOutil && (
                <FenetreOutil
                    outil={ouvertOutil}
                    resume={stats[ouvertOutil.tool_uuid]}
                    fermer={() => setOuvert(null)}
                    apresEcriture={() => void relire()}
                />
            )}
            {nouveau && (
                <FenetreNouvelOutil
                    fermer={() => setNouveau(false)}
                    cree={(o) => {
                        setNouveau(false);
                        void relire().then(() => setOuvert(o.tool_uuid));
                    }}
                />
            )}
        </PageStudio>
    );
}
