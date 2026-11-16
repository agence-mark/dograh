"use client";

/**
 * [.mark] U3 sexies point 1 (E73) : la page Outils.
 *
 * Tableau (type, branché sur, accès, exécutions, réussite, agents), onglets Actifs / Brouillons / Archivés, filtre par
 * type, recherche, « Nouvel outil » (cartes par type) et la fenêtre d'un outil. Les chiffres sont ceux du serveur
 * (calculés sur les appels) ; un outil sans appel affiche « – ». Aucun bouton « demander un logiciel ».
 */
import { Folder, MoreHorizontal, Plus, Search, Wrench } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ToolResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/dateTime";

import { useConnecteurs } from "../connecteurs/useConnecteurs";
import { Initiales } from "../integrations/OngletLogiciels";
import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { EcranCaissePos } from "../restauration/simulation";
import { lireLEtat } from "../restauration/simulation-donnees";
import { EtatVide } from "../studio/etat-vide";
import { Liste } from "../studio/liste";
import { Info } from "../studio/marques";
import { Paginee } from "../studio/pagination";
import { PageStudio } from "../studio/shell-studio";
import { Cellule, Ligne, Tableau } from "../studio/tableau";
import { TitrePage } from "../studio/titre-page";
import { FenetreNouvelOutil } from "./FenetreNouvelOutil";
import { ColonneOutils, type Vue, VueKit } from "./ColonneOutils";
import { ajouterAuKit, type Dossier, descendance, type Kit, lireLesDossiers, lireLesKits, lireLesPropositions, type OutilRange, type PropositionDeKit, rangerUnOutil } from "./donnees-outils";
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
    // [.mark] Module Restauration, lot 20 (F11) : « Simulateurs › Caisse / POS », Labo seulement (la caisse de démo existe quand l'interrupteur est allumé et que le compte est au Labo).
    const { user, loading: authLoading } = useAuth();
    const [laboSimulateurs, setLaboSimulateurs] = useState(false);
    const parametres = useSearchParams();
    const simulateurLu = useRef(false);
    // [.mark] Lot 13 (F9) : la colonne de gauche (dossiers, kits, simulateurs) et la vue choisie.
    const [vue, setVue] = useState<Vue>({ sorte: "tous" });
    const [dossiers, setDossiers] = useState<Dossier[]>([]);
    const [kits, setKits] = useState<Kit[] | null>(null);
    const simulateur = laboSimulateurs && (vue.sorte === "simulateurs" || parametres?.get("simulateur") === "caisse");
    const [propositions, setPropositions] = useState<PropositionDeKit[]>([]);
    const rangement = useRef(false);
    const relireRangement = useMemo(
        () => async () => {
            const [d, k, p] = await Promise.all([lireLesDossiers(), lireLesKits(), lireLesPropositions()]);
            setDossiers(d.data ?? []);
            setPropositions(p.data ?? []);
            setKits(k.error ? null : (k.data ?? []));
        },
        [],
    );
    useEffect(() => {
        if (authLoading || !user || rangement.current) return;
        rangement.current = true;
        void relireRangement();
    }, [authLoading, user, relireRangement]);
    useEffect(() => {
        if (authLoading || !user || simulateurLu.current) return;
        simulateurLu.current = true;
        void lireLEtat().then((r) => setLaboSimulateurs(!r.error && r.data?.active === true));
    }, [authLoading, user]);

    const libelleType = (cat: string) => {
        const l = LIBELLES_TYPE[cat as TypeOutil];
        return l ? t(l) : cat;
    };

    // Le client généré ne porte pas encore `folder_id` (lot 11) : il se régénère à la fusion.
    const tous = useMemo(() => (outils ?? []) as OutilRange[], [outils]);
    const parStatut = (s: Statut) => tous.filter((o) => o.status === s);
    const types = useMemo(() => Array.from(new Set(tous.map((o) => o.category))), [tous]);
    const dossiersVoulus = vue.sorte === "dossier" ? descendance(dossiers, vue.id) : null;
    const liste = parStatut(statut).filter(
        (o) => (!dossiersVoulus || (o.folder_id != null && dossiersVoulus.has(o.folder_id))) && (!type || o.category === type) && `${o.name} ${o.description ?? ""}`.toLowerCase().includes(q.toLowerCase()),
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

    const kitVu = vue.sorte === "kit" ? kits?.find((k) => k.id === vue.id) : undefined;
    const apresRangement = (ok: { fr: string; en: string }) => (r: { error?: unknown }) => {
        if (r.error) return notifier.echec({ fr: "Action non faite. Réessayez.", en: "Action not done. Try again." });
        notifier.succes(ok);
        void relire();
        void relireRangement();
    };
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
                    <span className="flex items-center gap-2">
                        <Button onClick={() => setNouveau(true)}>
                            <Plus className="size-4" /> {t({ en: "New tool", fr: "Nouvel outil" })}
                        </Button>
                    </span>
                }
            />
            <div className="flex items-start gap-6">
            <ColonneOutils total={tous.length} propositions={propositions.length} vue={vue} choisir={setVue} dossiers={dossiers} kits={kits} laboSimulateurs={laboSimulateurs} relire={() => void relireRangement()} />
            {simulateur ? (
                <div className="min-w-0 flex-1"><EcranCaissePos /></div>
            ) : kitVu ? (
                <VueKit kit={kitVu} outils={tous} propositions={propositions.filter((p) => p.kit_id === kitVu.id)} relireOutils={() => void relire()} dossiers={dossiers} relire={() => void relireRangement()} apresSuppression={() => setVue({ sorte: "tous" })} />
            ) : (
            <div className="min-w-0 flex-1 space-y-4">
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
                                { titre: t({ en: "Connected to", fr: "Branché sur" }), secondaire: 2 },
                                {
                                    secondaire: 4,
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
                                { titre: t({ en: "Success", fr: "Réussite" }), droite: true, secondaire: 3 },
                                { titre: t({ en: "Agents", fr: "Agents" }), droite: true },
                                { titre: t({ en: "Modified", fr: "Modifié" }), droite: true, secondaire: 1 },
                                { titre: "" },
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
                                                    <span className="block font-medium">{o.name}</span>
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
                                        <td className="w-10 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <button type="button" className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label={t({ en: `Actions for ${o.name}`, fr: `Actions pour ${o.name}` })}>
                                                        <MoreHorizontal className="size-4" />
                                                    </button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end" className="w-56">
                                                    <DropdownMenuLabel className="text-xs text-muted-foreground">{t({ en: "Move to", fr: "Ranger dans" })}</DropdownMenuLabel>
                                                    {o.folder_id != null && (
                                                        <DropdownMenuItem className="cursor-pointer" onClick={() => void rangerUnOutil(o.tool_uuid, null).then(apresRangement({ fr: "Outil sorti du dossier.", en: "Tool taken out of the folder." }))}>
                                                            {t({ en: "No folder", fr: "Sans dossier" })}
                                                        </DropdownMenuItem>
                                                    )}
                                                    {dossiers.filter((d) => d.id !== o.folder_id).map((d) => (
                                                        <DropdownMenuItem key={d.id} className="cursor-pointer" onClick={() => void rangerUnOutil(o.tool_uuid, d.id).then(apresRangement({ fr: `Rangé dans « ${d.name} ».`, en: `Moved to “${d.name}”.` }))}>
                                                            {d.name}
                                                        </DropdownMenuItem>
                                                    ))}
                                                    {dossiers.length === 0 && <DropdownMenuItem disabled>{t({ en: "No folder yet", fr: "Aucun dossier" })}</DropdownMenuItem>}
                                                    {kits !== null && (
                                                        <>
                                                            <DropdownMenuSeparator />
                                                            <DropdownMenuLabel className="text-xs text-muted-foreground">{t({ en: "Add to a kit", fr: "Ajouter à un kit" })}</DropdownMenuLabel>
                                                            {kits.map((k) => (
                                                                <DropdownMenuItem key={k.id} className="cursor-pointer" onClick={() => void ajouterAuKit(k.id, o.tool_uuid).then(apresRangement({ fr: `Ajouté au kit « ${k.name} ».`, en: `Added to kit “${k.name}”.` }))}>
                                                                    {k.name}
                                                                </DropdownMenuItem>
                                                            ))}
                                                            {kits.length === 0 && <DropdownMenuItem disabled>{t({ en: "No kit yet", fr: "Aucun kit" })}</DropdownMenuItem>}
                                                        </>
                                                    )}
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </td>
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
                ) : vue.sorte === "dossier" && !q && !type ? (
                    // SA-29 (M54) : un dossier sans outil se dit « vide », il ne parle ni de l'onglet ni de filtres qu'on n'a pas posés.
                    <EtatVide
                        cas="premier"
                        icone={Folder}
                        titre={t({ en: "This folder is empty", fr: "Ce dossier est vide" })}
                        info={t({ en: "Put tools in it from the “⋯” menu of a tool: “Move to”.", fr: "Rangez-y des outils depuis le menu « ⋯ » d'un outil : « Ranger dans »." })}
                    />
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
            </div>
            )}
            </div>
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
