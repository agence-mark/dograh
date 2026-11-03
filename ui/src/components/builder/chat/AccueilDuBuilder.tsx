"use client";

/**
 * [.mark] builder partie 2, U5 (E50) : l'accueil du Labo. Les cartes de démarrage sont des DONNÉES (famille « Démarrages du
 * builder » de la bibliothèque, les 4 plus utilisés hors Rejeté). Un clic remplit la saisie (modifiable) ; la saisie demande ce
 * qui manque (un agent, des fichiers texte) et « Envoyer » reste grisé, raison au survol, tant qu'il manque quelque chose.
 */
import { Bot, FileText, FlaskConical, Sparkles, Wrench, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
    getWorkflowsSummaryApiV1WorkflowSummaryGet,
    lireLeCerveauApiV1BuilderCerveauGet,
    lireLesDemarragesApiV1BuilderDemarragesGet,
    ouvrirUnFilApiV1BuilderFilsPost,
    type VueDemarrage,
} from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { AvertissementClaudeCode } from "@/components/mark/sources/marques";
import { useSources } from "@/components/mark/sources/useSources";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { FenetreFichier } from "../fichier/FenetreFichier";
import { ListeDesFils } from "./ListeDesFils";

const T = {
    titre: { en: "Builder", fr: "Builder" },
    ecrire: { en: "Describe what to build or improve...", fr: "Décrivez ce qu'il faut construire ou améliorer..." },
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
        router.push(`/labo/builder/${r.data.id}`);
    };

    return (
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
            <TitrePage titre={t(T.titre)} />
            <div className="space-y-2 rounded-xl bg-card p-3 shadow-sm">
                {choisi && (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                        {t(T.demarrage)} « {choisi.titre} »
                        <button type="button" className="flex cursor-pointer items-center gap-0.5 hover:font-semibold" onClick={() => setChoisi(null)}>
                            <X className="size-3.5" /> {t(T.retirer)}
                        </button>
                    </p>
                )}
                <Textarea
                    rows={4}
                    value={saisie}
                    placeholder={t(T.ecrire)}
                    onChange={(e) => setSaisie(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void envoyer();
                    }}
                />
                <div className="flex flex-wrap items-center gap-2">
                    {(besoinAgent || agents.length > 0) && (
                        <select
                            aria-label={t(T.agent)}
                            className="cursor-pointer rounded-md border bg-background px-2 py-1 text-sm"
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
                    )}
                    <input ref={entree} type="file" multiple accept=".txt,.md,.json,.csv,.html,text/*" className="hidden" onChange={(e) => void joindre(e.target.files)} />
                    <Button size="sm" variant="outline" onClick={() => entree.current?.click()}>
                        <FileText className="size-4" /> {t(T.joindre)}
                    </Button>
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
                    <span className="ml-auto" />
                    {modele && (
                        <a href="/labo/reglages" className="text-xs text-muted-foreground hover:font-semibold">
                            {modele.modele || "-"} · {t(T.plafond)} ${modele.plafond.toFixed(2)}
                        </a>
                    )}
                    <Button size="sm" disabled={manque !== null || ferme} title={manque ?? undefined} onClick={() => void envoyer()}>
                        {t(T.envoyer)}
                    </Button>
                </div>
                {ferme && <AvertissementClaudeCode />}
                {ouvert && <FenetreFichier nom={ouvert.name} fichier={ouvert} fermer={() => setOuvert(null)} />}
                {erreur && <p className="text-sm text-destructive">{erreur}</p>}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {cartes.map((c) => {
                    const Icone = ICONES[c.icone as keyof typeof ICONES] ?? Sparkles;
                    return (
                        <button
                            key={c.slug}
                            type="button"
                            data-demarrage={c.slug}
                            onClick={() => choisirLaCarte(c)}
                            className={`flex cursor-pointer items-start gap-3 rounded-xl p-3 text-left hover:font-semibold ${choisi?.slug === c.slug ? "bg-muted" : ""}`}
                        >
                            <Icone className="mt-0.5 size-5 text-(--acc)" />
                            <span>
                                <span className="block text-sm font-semibold">{c.titre}</span>
                                <span className="block text-sm font-normal text-muted-foreground">{c.phrase}</span>
                            </span>
                        </button>
                    );
                })}
            </div>
            <section>
                <h2 className="mb-2 text-sm font-semibold">{t(T.recentes)}</h2>
                <ListeDesFils limite={5} />
            </section>
        </div>
    );
}
