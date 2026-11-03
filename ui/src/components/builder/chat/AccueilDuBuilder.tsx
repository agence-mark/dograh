"use client";

/**
 * [.mark] builder partie 2, U5 (E50) : l'accueil du Labo. Les cartes de démarrage sont des DONNÉES (famille « Démarrages du
 * builder » de la bibliothèque, les 4 plus utilisés hors Rejeté). Un clic remplit la saisie (modifiable) ; la saisie demande ce
 * qui manque (un agent, des fichiers texte) et « Envoyer » reste grisé, raison au survol, tant qu'il manque quelque chose.
 */
import { ArrowUp, Bot, FileText, FlaskConical, MessageSquare, Paperclip, Settings2, Sparkles, Wrench, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
    getWorkflowsSummaryApiV1WorkflowSummaryGet,
    lireLeCerveauApiV1BuilderCerveauGet,
    lireLesDemarragesApiV1BuilderDemarragesGet,
    ouvrirUnFilApiV1BuilderFilsPost,
    type VueDemarrage,
} from "@/client";
import { SectionAAmeliorer } from "@/components/mark/ameliorer/SectionAAmeliorer";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { AvertissementClaudeCode } from "@/components/mark/sources/marques";
import { useSources } from "@/components/mark/sources/useSources";
import { useMoi } from "@/components/mark/studio/moi";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { FenetreFichier } from "../fichier/FenetreFichier";
import { useAdressesDuBuilder } from "./adresses";
import { ListeDesFils } from "./ListeDesFils";

const T = {
    titreClient: { en: "What do we build for", fr: "Que construit-on pour" },
    bonjour: { en: "Hello", fr: "Bonjour" },
    queConstruit: { en: "what do we build?", fr: "que construit-on ?" },
    joindreCourt: { en: "Attach", fr: "Joindre" },
    parChat: { en: "per chat", fr: "par chat" },
    gerer: { en: "Manage the starters", fr: "Gérer les démarrages" },
    chat: { en: "Chat", fr: "Chat" },
    toutVoir: { en: "See all", fr: "Tout voir" },
    envoyerRaccourci: { en: "Send (Ctrl + Enter)", fr: "Envoyer (Ctrl + Entrée)" },
    fermeInfo: { en: "Sending is closed: the builder works in Claude Code.", fr: "Envoi fermé : le builder travaille dans Claude Code." },
    ecrire: {
        en: "Describe the agent, paste an audit note, or ask for a fix.",
        fr: "Décris l'agent, colle une note d'audit, ou demande une correction.",
    },
    envoyer: { en: "Send", fr: "Envoyer" },
    agent: { en: "Agent", fr: "Agent" },
    choisir: { en: "Choose an agent", fr: "Choisir un agent" },
    joindre: { en: "Attach files", fr: "Joindre les fichiers" },
    retirer: { en: "Remove", fr: "Retirer" },
    demarrage: { en: "Starter", fr: "Démarrage" },
    manqueAgent: { en: "Choose an agent first.", fr: "Choisissez d'abord un agent." },
    manqueFichiers: { en: "Attach the files first (text, Markdown, JSON, CSV).", fr: "Joignez d'abord les fichiers (texte, Markdown, JSON, CSV)." },
    manqueTexte: { en: "Write a request first.", fr: "Écrivez d'abord une demande." },
    modele: { en: "Brain", fr: "Cerveau" },
    plafond: { en: "ceiling", fr: "plafond" },
    reglages: { en: "Builder settings", fr: "Réglages du builder" },
    echec: { en: "The conversation could not be opened.", fr: "La conversation n'a pas pu être ouverte." },
    recentes: { en: "Recent conversations", fr: "Conversations récentes" },
} satisfies Record<string, Texte>;

const ICONES = { agent: Bot, amelioration: Wrench, test: FlaskConical, fichier: FileText, etincelle: Sparkles } as const;
const TAILLE_FICHIERS_MAX = 100_000;

type Agent = { id: number; name: string };

export function AccueilDuBuilder() {
    const { t } = useLangue();
    const router = useRouter();
    const adresses = useAdressesDuBuilder();
    const { user, loading: authLoading } = useAuth();
    const [cartes, setCartes] = useState<VueDemarrage[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [modele, setModele] = useState<{ modele: string; plafond: number } | null>(null);
    const [choisi, setChoisi] = useState<VueDemarrage | null>(null);
    const [saisie, setSaisie] = useState("");
    const [agentId, setAgentId] = useState<number | null>(null);
    const [fichiers, setFichiers] = useState<{ nom: string; texte: string; fichier: File }[]>([]);
    const [ouvert, setOuvert] = useState<File | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const entree = useRef<HTMLInputElement>(null);
    const moi = useMoi();
    const { sources } = useSources();
    // E105 : le builder est sur Claude Code, l'accueil garde sa saisie et ses cartes ; l'envoi est ferme, la carte rouge le dit.
    const ferme = sources?.builder === "claude_code";

    useEffect(() => {
        if (authLoading || !user) return;
        void (async () => {
            const [d, a, c] = await Promise.all([
                lireLesDemarragesApiV1BuilderDemarragesGet(),
                getWorkflowsSummaryApiV1WorkflowSummaryGet(),
                lireLeCerveauApiV1BuilderCerveauGet(),
            ]);
            if (d.data) setCartes(d.data);
            if (Array.isArray(a.data)) setAgents(a.data as Agent[]);
            if (c.data) setModele({ modele: c.data.modele ?? "", plafond: c.data.plafond_depense ?? 0 });
        })();
    }, [authLoading, user]);

    const besoinAgent = choisi ? choisi.besoin === "agent" || choisi.besoin === "agent et fichiers" : false;
    const besoinFichiers = choisi ? choisi.besoin === "fichiers" || choisi.besoin === "agent et fichiers" : false;
    const nomAgent = agents.find((a) => a.id === agentId)?.name;
    const manque = !saisie.trim()
        ? t(T.manqueTexte)
        : besoinAgent && agentId === null
          ? t(T.manqueAgent)
          : besoinFichiers && fichiers.length === 0
            ? t(T.manqueFichiers)
            : null;

    const choisirLaCarte = (c: VueDemarrage) => {
        setChoisi(c);
        setSaisie(nomAgent ? c.demande.replaceAll("{agent}", nomAgent) : c.demande);
    };
    const choisirAgent = (id: number | null) => {
        setAgentId(id);
        const nom = agents.find((a) => a.id === id)?.name;
        if (choisi && nom) setSaisie(choisi.demande.replaceAll("{agent}", nom));
    };
    const joindre = async (liste: FileList | null) => {
        if (!liste) return;
        const lus = await Promise.all(Array.from(liste).map(async (f) => ({ nom: f.name, texte: (await f.text()).slice(0, TAILLE_FICHIERS_MAX), fichier: f })));
        setFichiers((avant) => [...avant, ...lus]);
    };
    const envoyer = async () => {
        if (manque || ferme) return;
        const message = [saisie.trim(), ...fichiers.map((f) => `\n[Fichier : ${f.nom}]\n${f.texte}`)].join("\n");
        const r = await ouvrirUnFilApiV1BuilderFilsPost({ body: { message, workflow_id: agentId, demarrage: choisi?.slug ?? null } });
        if (r.error || !r.data) {
            setErreur(detailFromError(r.error, t(T.echec)));
            return;
        }
        router.push(adresses.fil(r.data.id));
    };

    const envoiFerme = manque !== null || ferme;
    const raisonEnvoi = ferme ? t(T.fermeInfo) : manque ?? t(T.envoyerRaccourci);
    return (
        <PageStudio>
            <section className="space-y-6 pt-2">
                <div className="space-y-2 text-center">
                    <Sparkles className="mx-auto size-7 text-(--acc)" aria-hidden />
                    <h1 className="text-3xl font-semibold tracking-tight">
                        {adresses.client
                            ? `${t(T.titreClient)} ${adresses.nomDuClient ?? "…"} ?`
                            : `${moi?.prenom ? `${t(T.bonjour)} ${moi.prenom}` : t(T.bonjour)}, ${t(T.queConstruit)}`}
                    </h1>
                </div>
                <div className="relative mx-auto max-w-3xl rounded-2xl border bg-card shadow-sm">
                    {choisi && (
                        <div className="flex items-center gap-2 px-4 pt-3 text-xs text-muted-foreground">
                            <Sparkles className="size-3.5 text-(--acc)" aria-hidden />
                            {t(T.demarrage)} « {choisi.titre} »
                            <button type="button" className="ml-auto inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted hover:font-semibold" onClick={() => setChoisi(null)}>
                                <X className="size-3" /> {t(T.retirer)}
                            </button>
                        </div>
                    )}
                    <textarea
                        value={saisie}
                        aria-label={t(T.ecrire)}
                        placeholder={t(T.ecrire)}
                        onChange={(e) => setSaisie(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void envoyer();
                        }}
                        className="min-h-24 w-full resize-none bg-transparent px-5 pt-3 pb-2 text-[15px] outline-none placeholder:text-muted-foreground"
                    />
                    {(besoinAgent || fichiers.length > 0) && (
                        <div className="flex flex-wrap items-center gap-2 px-4 pb-2">
                            {besoinAgent && (
                                <span className="flex items-center gap-2 text-sm">
                                    <span className="text-muted-foreground">{t(T.agent)}</span>
                                    <select
                                        aria-label={t(T.agent)}
                                        className="min-w-64 cursor-pointer rounded-md border bg-background px-2 py-1 text-sm"
                                        value={agentId ?? ""}
                                        onChange={(e) => choisirAgent(e.target.value ? Number(e.target.value) : null)}
                                    >
                                        <option value="">{t(T.choisir)}</option>
                                        {agents.map((a) => (
                                            <option key={a.id} value={a.id}>
                                                {a.name}
                                            </option>
                                        ))}
                                    </select>
                                </span>
                            )}
                            {fichiers.map((f) => (
                                <span key={f.nom} className="flex items-center gap-1 text-sm text-muted-foreground">
                                    <button type="button" className="cursor-pointer hover:font-semibold" onClick={() => setOuvert(f.fichier)}>
                                        {f.nom}
                                    </button>
                                    <button type="button" className="cursor-pointer" aria-label={t(T.retirer)} onClick={() => setFichiers((l) => l.filter((x) => x !== f))}>
                                        <X className="size-3.5" />
                                    </button>
                                </span>
                            ))}
                        </div>
                    )}
                    <div className="flex items-center gap-2 px-3 pb-3">
                        <input ref={entree} type="file" multiple accept=".txt,.md,.json,.csv,.html,text/*" className="hidden" onChange={(e) => void joindre(e.target.files)} />
                        <Button size="sm" variant="ghost" className="cursor-pointer gap-1.5" onClick={() => entree.current?.click()}>
                            <Paperclip className="size-4" /> {t(T.joindreCourt)}
                        </Button>
                        {modele &&
                            (adresses.reglages ? (
                                <Link href={adresses.reglages} className="text-xs text-muted-foreground hover:font-semibold">
                                    {modele.modele || "-"} · ${modele.plafond.toFixed(2)} {t(T.parChat)}
                                </Link>
                            ) : (
                                <span className="text-xs text-muted-foreground">
                                    {modele.modele || "-"} · ${modele.plafond.toFixed(2)} {t(T.parChat)}
                                </span>
                            ))}
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <span className="ml-auto">
                                    <Button size="icon" className="size-8 rounded-full" disabled={envoiFerme} aria-label={t(T.envoyer)} onClick={() => void envoyer()}>
                                        <ArrowUp className="size-4" />
                                    </Button>
                                </span>
                            </TooltipTrigger>
                            <TooltipContent>{raisonEnvoi}</TooltipContent>
                        </Tooltip>
                    </div>
                    {ouvert && <FenetreFichier nom={ouvert.name} fichier={ouvert} fermer={() => setOuvert(null)} />}
                </div>
                {ferme && <AvertissementClaudeCode className="mx-auto -mt-2 max-w-3xl" />}
                {erreur && <p className="mx-auto max-w-3xl text-sm text-destructive">{erreur}</p>}
                <div className="mx-auto max-w-3xl space-y-2">
                    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                        {cartes.map((c) => {
                            const Icone = ICONES[c.icone as keyof typeof ICONES] ?? Sparkles;
                            return (
                                <button
                                    key={c.slug}
                                    type="button"
                                    data-demarrage={c.slug}
                                    onClick={() => choisirLaCarte(c)}
                                    className={`cursor-pointer rounded-xl border bg-card p-4 text-left transition-[scale,box-shadow] duration-200 ease-out hover:shadow-md motion-safe:hover:scale-[1.02] ${choisi?.slug === c.slug ? "border-foreground" : ""}`}
                                >
                                    <Icone className="mb-3 size-5 text-(--acc)" />
                                    <span className="block text-sm font-medium">{c.titre}</span>
                                    <span className="block text-xs text-muted-foreground">{c.phrase}</span>
                                </button>
                            );
                        })}
                    </div>
                    {!adresses.client && (
                        <div className="flex justify-end">
                            <Link href="/labo/bibliotheque?famille=demarrages-builder" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:font-semibold">
                                <Settings2 className="size-3.5" aria-hidden /> {t(T.gerer)}
                            </Link>
                        </div>
                    )}
                </div>
            </section>
            <SectionAAmeliorer lien={adresses.aAmeliorer} />
            <section>
                <div className="flex items-center gap-2 pb-3">
                    <MessageSquare className="size-4 text-muted-foreground" aria-hidden />
                    <h2 className="text-base font-semibold">{t(T.chat)}</h2>
                    <Link href={adresses.liste} className="ml-auto text-sm text-(--acc) hover:font-semibold">
                        {t(T.toutVoir)}
                    </Link>
                </div>
                <ListeDesFils limite={3} variante="accueil" />
            </section>
        </PageStudio>
    );
}
