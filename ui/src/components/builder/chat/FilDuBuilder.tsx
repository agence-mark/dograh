"use client";

/**
 * [.mark] builder partie 2, U5 : le chat du builder aux normes d'un agent IA.
 * Plan en cases, questions une par une, actions en lignes dépliables, Markdown, Arrêter / Reprendre, modifier et relancer le
 * dernier message, défilement automatique avec « revenir en bas », saisie flottante (pas de trait, fondu en bas du fil).
 * L'écran ne porte aucun état du travail : tout est relu depuis la table (rechargement sans perte).
 */
import { ArrowDown, ArrowLeft, ArrowUp, Pencil, RotateCw, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { AvertissementClaudeCode, EnDirect, LigneLecture, MarqueClaudeCode } from "@/components/mark/sources/marques";
import { LigneLive } from "@/components/mark/sources/useModifications";
import { useSources } from "@/components/mark/sources/useSources";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { BandeauDuFil } from "./BandeauDuFil";
import { CarteDuPlan, CarteQuestion, LigneAction } from "./cartes";
import { CarteCorrection, CarteDepense, CartePropositionTest, CarteRapport } from "./cartes-c2";
import type { EtapeDuPlan, LigneDuFil } from "./evenements";
import { Markdown } from "./Markdown";
import { RevueChampParChamp } from "./RevueChampParChamp";
import { CarteSousAgents, libelleEtat, ListeDesSousAgents, type SousAgent, useSousAgents } from "./SousAgents";
import { useFil } from "./useFil";

const T = {
    ecrire: { en: "Write to the builder...", fr: "Écrire au builder..." },
    envoyer: { en: "Send", fr: "Envoyer" },
    arreter: { en: "Stop", fr: "Arrêter" },
    reprendre: { en: "Resume", fr: "Reprendre" },
    arretee: { en: "Stopped", fr: "Arrêtée" },
    modifier: { en: "Edit and resend", fr: "Modifier et relancer" },
    relancer: { en: "Resend", fr: "Relancer" },
    annuler: { en: "Cancel", fr: "Annuler" },
    bas: { en: "Back to the bottom", fr: "Revenir en bas" },
    travaille: { en: "The builder is working...", fr: "Le builder travaille..." },
    changements: { en: "change(s) to validate", fr: "changement(s) à valider" },
    redemarrage: { en: "Stopped by a restart of the server.", fr: "Arrêtée par un redémarrage du serveur." },
    principale: { en: "Main conversation", fr: "Conversation principale" },
    lectureSeule: { en: "Read only: a sub-agent receives no message.", fr: "Lecture seule : un sous-agent ne reçoit pas de message." },
    revoir: { en: "See the changes", fr: "Voir les changements" },
    cacher: { en: "Hide the review", fr: "Masquer la relecture" },
    plafond: { en: "Ceiling reached: raise it in the builder settings, then resume.", fr: "Plafond atteint : relevez-le dans les réglages du builder, puis reprenez." },
} satisfies Record<string, Texte>;

export function FilDuBuilder({
    filId,
    lectureSeule: lectureSeuleDemandee = false,
    retour,
    entete = false,
}: {
    filId: number;
    lectureSeule?: boolean;
    retour?: () => void;
    /** K7 : la page entière du chat pose son bandeau (titre, état, jauge, Arrêter, Ouvrir l'agent) dans la barre du haut du cadre. */
    entete?: boolean;
}) {
    const { t, langue } = useLangue();
    const { fil, lignes, erreur, enCours: enCoursBrut, dernier, envoyer, arreter, reprendre, modifierDernier, rafraichir, repondreDepense } = useFil(filId);
    const { sources } = useSources();
    // U12 : une conversation menee dans Claude Code se lit seulement ; sur Claude Code, la saisie du chat de l'ecran est fermee.
    const claudeCode = fil?.genre === "claude_code";
    const lectureSeule = lectureSeuleDemandee || claudeCode;
    // Le travail d'une conversation Claude Code se fait dans Claude Code : ni « Le builder travaille... » ni dépense à afficher ici.
    const enCours = enCoursBrut && !claudeCode;
    const ferme = !claudeCode && sources?.builder === "claude_code";
    const [vu, setVu] = useState<number | null>(null);
    const [revue, setRevue] = useState(false);
    const sous = useSousAgents(filId, enCours && !lectureSeule);
    const [saisie, setSaisie] = useState("");
    const [edition, setEdition] = useState<string | null>(null);
    const [enBas, setEnBas] = useState(true);
    const zone = useRef<HTMLDivElement>(null);
    const fond = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (enBas) fond.current?.scrollIntoView?.({ block: "end" });
    }, [lignes, enBas]);

    const surDefilement = () => {
        const z = zone.current;
        if (z) setEnBas(z.scrollHeight - z.scrollTop - z.clientHeight < 80);
    };
    const envoi = async () => {
        const texte = saisie.trim();
        if (!texte || enCours || ferme) return;
        setSaisie("");
        setEnBas(true);
        await envoyer(texte);
    };
    const derniereQuestion = [...lignes].reverse().find((l) => l.genre === "carte" && l.carte.type === "question");

    const principal = (
        <div className={`relative mx-auto flex h-[calc(100vh-8rem)] w-full max-w-3xl flex-col pt-4 ${vu !== null ? "hidden" : ""}`}>
            {entete && fil && <BandeauDuFil fil={fil} enCours={enCours} lectureSeule={lectureSeule} arreter={() => void arreter()} reprendre={() => void reprendre()} />}
            {entete ? (
                <div className="empty:hidden pb-2">
                    <LigneLive objet={`conversation:${filId}`} />
                </div>
            ) : (
            <div className="flex items-center justify-between gap-2 pb-2">
                {lectureSeule && retour && (
                    <button type="button" className="flex cursor-pointer items-center gap-1 text-sm hover:font-semibold" onClick={retour}>
                        <ArrowLeft className="size-4" /> {t(T.principale)}
                    </button>
                )}
                <div className="flex min-w-0 flex-col">
                    <h1 className="truncate text-lg font-semibold">{fil?.titre ?? ""}</h1>
                    {claudeCode && (
                        <span className="flex items-center gap-2">
                            <MarqueClaudeCode par={fil?.auteur} />
                            {fil?.etat === "en_cours" && <EnDirect />}
                        </span>
                    )}
                    <LigneLive objet={`conversation:${filId}`} />
                </div>
                <p className="shrink-0 text-xs text-muted-foreground">
                    {lectureSeule && fil ? `${libelleEtat(fil.etat, langue)}${claudeCode ? "" : " · "}` : ""}
                    {fil && !claudeCode ? `${fil.jetons.toLocaleString()} · $${fil.cout.toFixed(2)} · ${Math.round(fil.jauge * 100)} %` : ""}
                    {fil && fil.changements > 0 ? ` · ${fil.changements} ${t(T.changements)}` : ""}
                </p>
            </div>
            )}
            <div ref={zone} onScroll={surDefilement} className="flex-1 space-y-3 overflow-y-auto pb-40">
                {lignes.map((l, i) => (
                    <Ligne
                        key={i}
                        ligne={l}
                        edition={edition}
                        peutModifier={!lectureSeule && !enCours && dernier?.id === (l.genre === "message" ? l.id : -1)}
                        modifier={() => setEdition(l.genre === "message" ? l.texte : "")}
                        questionActive={!lectureSeule && !enCours && l === derniereQuestion}
                        repondre={(texte) => void envoyer(texte)}
                        actif={!lectureSeule && !enCours}
                        accorder={(id, accord) => void repondreDepense(id, accord)}
                        filId={filId}
                        sousAgents={sous.sous_agents}
                        voir={setVu}
                        recharger={sous.recharger}
                    />
                ))}
                {edition !== null && (
                    <div className="space-y-2">
                        <Textarea rows={3} value={edition} onChange={(e) => setEdition(e.target.value)} />
                        <div className="flex gap-2">
                            <Button
                                size="sm"
                                disabled={!edition.trim()}
                                onClick={async () => {
                                    const texte = edition.trim();
                                    setEdition(null);
                                    await modifierDernier(texte);
                                }}
                            >
                                {t(T.relancer)}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setEdition(null)}>
                                {t(T.annuler)}
                            </Button>
                        </div>
                    </div>
                )}
                {enCours && <p className="text-sm text-muted-foreground">{t(T.travaille)}</p>}
                {erreur && <p className="text-sm text-destructive">{erreur}</p>}
                <div ref={fond} />
            </div>
            {!enBas && (
                <Button size="sm" variant="outline" className="absolute right-4 bottom-32 cursor-pointer" onClick={() => setEnBas(true)}>
                    <ArrowDown className="size-4" /> {t(T.bas)}
                </Button>
            )}
            {/* Saisie flottante : aucun trait entre le fil et la saisie, un fondu en bas du fil. */}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-background via-background/90 to-transparent pt-10">
                {claudeCode ? (
                    <div className="pointer-events-auto mx-auto max-w-3xl rounded-xl bg-card p-3 shadow-lg">
                        <LigneLecture />
                    </div>
                ) : lectureSeule ? (
                    <div className="pointer-events-auto mx-auto flex max-w-3xl items-center justify-between gap-2 rounded-xl bg-card p-3 text-sm text-muted-foreground shadow-lg">
                        <span>{t(T.lectureSeule)}</span>
                        {enCours && (
                            <Button size="sm" variant="outline" onClick={() => void arreter()}>
                                <Square className="size-4" /> {t(T.arreter)}
                            </Button>
                        )}
                    </div>
                ) : (
                <div className="pointer-events-auto mx-auto max-w-3xl overflow-hidden rounded-2xl border bg-card shadow-lg">
                    {fil && fil.changements > 0 && (
                        <div className="border-b">
                            <div className="flex items-center justify-between px-3 py-1.5 text-xs text-muted-foreground">
                                <span>
                                    {fil.changements} {t(T.changements)}
                                </span>
                                <button type="button" className="cursor-pointer hover:font-semibold" onClick={() => setRevue((v) => !v)}>
                                    {revue ? t(T.cacher) : t(T.revoir)}
                                </button>
                            </div>
                            {revue && (
                                <div className="px-3 pb-3">
                                    <RevueChampParChamp filId={filId} workflowId={fil.workflow_id ?? null} apres={() => void rafraichir()} />
                                </div>
                            )}
                        </div>
                    )}
                    {fil?.etat === "arretee" && (
                        <div className="flex items-center gap-2 px-3 pt-3 text-sm">
                            <span className="font-semibold">{t(T.arretee)}</span>
                            <Button size="sm" onClick={() => void reprendre()}>
                                <RotateCw className="size-4" /> {t(T.reprendre)}
                            </Button>
                        </div>
                    )}
                    <Textarea
                        rows={2}
                        className="resize-none rounded-none border-0 px-4 shadow-none focus-visible:ring-0"
                        value={saisie}
                        placeholder={t(T.ecrire)}
                        disabled={enCours || ferme}
                        onChange={(e) => setSaisie(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void envoi();
                        }}
                    />
                    <div className="flex items-center justify-end gap-2 px-3 pb-3">
                        <ListeDesSousAgents
                            filId={filId}
                            actifDansLeChat={fil?.sous_agents_actifs ?? true}
                            sousAgents={sous.sous_agents}
                            choisi={vu}
                            choisir={setVu}
                            recharger={sous.recharger}
                        />
                        {enCours ? (
                            <Button size="sm" variant="outline" onClick={() => void arreter()}>
                                <Square className="size-4" /> {t(T.arreter)}
                            </Button>
                        ) : (
                            <Button size="icon" className="size-8 rounded-full" disabled={!saisie.trim() || ferme} onClick={() => void envoi()} aria-label={t(T.envoyer)} title={t(T.envoyer)}>
                                <ArrowUp className="size-4" />
                            </Button>
                        )}
                    </div>
                </div>
                )}
                {!claudeCode && !lectureSeule && ferme && <AvertissementClaudeCode className="pointer-events-auto mx-auto mt-2 max-w-3xl" />}
            </div>
        </div>
    );
    return (
        <>
            {principal}
            {vu !== null && <FilDuBuilder filId={vu} lectureSeule retour={() => setVu(null)} />}
        </>
    );
}

function Ligne({
    ligne,
    peutModifier,
    modifier,
    questionActive,
    repondre,
    edition,
    actif,
    accorder,
    filId,
    sousAgents,
    voir,
    recharger,
}: {
    ligne: LigneDuFil;
    peutModifier: boolean;
    modifier: () => void;
    questionActive: boolean;
    repondre: (texte: string) => void;
    edition: string | null;
    actif: boolean;
    accorder: (id: string, accord: boolean) => void;
    filId: number;
    sousAgents: SousAgent[];
    voir: (id: number) => void;
    recharger: () => void;
}) {
    const { t } = useLangue();
    switch (ligne.genre) {
        case "message":
            return (
                <div className="group flex justify-end gap-2" data-role="user">
                    {peutModifier && edition === null && (
                        <button type="button" className="cursor-pointer text-muted-foreground opacity-0 group-hover:opacity-100" onClick={modifier} aria-label={t(T.modifier)} title={t(T.modifier)}>
                            <Pencil className="size-4" />
                        </button>
                    )}
                    <div className="max-w-[90%] rounded-2xl bg-foreground px-4 py-3 text-sm whitespace-pre-wrap text-background">{ligne.texte}</div>
                </div>
            );
        case "texte":
            return <Markdown texte={ligne.texte} />;
        case "action":
            return <LigneAction ligne={ligne} />;
        case "carte": {
            if (ligne.carte.type === "plan") return <CarteDuPlan etapes={ligne.carte.etapes as EtapeDuPlan[]} />;
            if (ligne.carte.type === "question") {
                return (
                    <CarteQuestion
                        question={String(ligne.carte.question)}
                        reponseProposee={String(ligne.carte.reponse_proposee)}
                        choix={(ligne.carte.choix as string[]) ?? []}
                        repondre={repondre}
                        active={questionActive}
                    />
                );
            }
            if (ligne.carte.type === "rapport") return <CarteRapport carte={ligne.carte} />;
            if (ligne.carte.type === "depense") {
                return <CarteDepense carte={ligne.carte} active={actif} repondre={(accord) => accorder(String(ligne.carte.id), accord)} />;
            }
            if (ligne.carte.type === "correction") return <CarteCorrection carte={ligne.carte} active={actif} repondre={repondre} />;
            if (ligne.carte.type === "proposition_test") return <CartePropositionTest carte={ligne.carte} />;
            if (ligne.carte.type === "delegation") {
                return <CarteSousAgents carte={ligne.carte} sousAgents={sousAgents} voir={voir} recharger={recharger} filId={filId} />;
            }
            return null;
        }
        case "erreur":
            return <p className="text-sm text-destructive">{ligne.message}</p>;
        case "fin":
            return (
                <p className="text-xs text-muted-foreground">
                    {ligne.raison === "redemarrage" ? t(T.redemarrage) : ligne.raison === "plafond" ? t(T.plafond) : t(T.arretee)}
                </p>
            );
        case "reprise":
            return null;
    }
}
