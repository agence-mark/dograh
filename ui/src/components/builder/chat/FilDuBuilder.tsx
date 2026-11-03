"use client";

/**
 * [.mark] builder partie 2, U5 : le chat du builder aux normes d'un agent IA.
 * Plan en cases, questions une par une, actions en lignes dépliables, Markdown, Arrêter / Reprendre, modifier et relancer le
 * dernier message, défilement automatique avec « revenir en bas », saisie flottante (pas de trait, fondu en bas du fil).
 * L'écran ne porte aucun état du travail : tout est relu depuis la table (rechargement sans perte).
 */
import { ArrowDown, ArrowUp, Pencil, RotateCw, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { CarteDuPlan, CarteQuestion, LigneAction } from "./cartes";
import type { EtapeDuPlan, LigneDuFil } from "./evenements";
import { Markdown } from "./Markdown";
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
    plafond: { en: "Ceiling reached: raise it in the builder settings, then resume.", fr: "Plafond atteint : relevez-le dans les réglages du builder, puis reprenez." },
} satisfies Record<string, Texte>;

export function FilDuBuilder({ filId }: { filId: number }) {
    const { t } = useLangue();
    const { fil, lignes, erreur, enCours, dernier, envoyer, arreter, reprendre, modifierDernier } = useFil(filId);
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
        if (!texte || enCours) return;
        setSaisie("");
        setEnBas(true);
        await envoyer(texte);
    };
    const derniereQuestion = [...lignes].reverse().find((l) => l.genre === "carte" && l.carte.type === "question");

    return (
        <div className="relative flex h-[calc(100vh-8rem)] flex-col">
            <div className="flex items-center justify-between gap-2 pb-2">
                <h1 className="truncate text-lg font-semibold">{fil?.titre ?? ""}</h1>
                <p className="shrink-0 text-xs text-muted-foreground">
                    {fil ? `${fil.jetons.toLocaleString()} · $${fil.cout.toFixed(2)} · ${Math.round(fil.jauge * 100)} %` : ""}
                    {fil && fil.changements > 0 ? ` · ${fil.changements} ${t(T.changements)}` : ""}
                </p>
            </div>
            <div ref={zone} onScroll={surDefilement} className="flex-1 space-y-3 overflow-y-auto pb-40">
                {lignes.map((l, i) => (
                    <Ligne
                        key={i}
                        ligne={l}
                        edition={edition}
                        peutModifier={!enCours && dernier?.id === (l.genre === "message" ? l.id : -1)}
                        modifier={() => setEdition(l.genre === "message" ? l.texte : "")}
                        questionActive={!enCours && l === derniereQuestion}
                        repondre={(texte) => void envoyer(texte)}
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
                <div className="pointer-events-auto mx-auto max-w-3xl space-y-2 rounded-xl bg-card p-3 shadow-lg">
                    {fil?.etat === "arretee" && (
                        <div className="flex items-center gap-2 text-sm">
                            <span className="font-semibold">{t(T.arretee)}</span>
                            <Button size="sm" onClick={() => void reprendre()}>
                                <RotateCw className="size-4" /> {t(T.reprendre)}
                            </Button>
                        </div>
                    )}
                    <Textarea
                        rows={2}
                        value={saisie}
                        placeholder={t(T.ecrire)}
                        disabled={enCours}
                        onChange={(e) => setSaisie(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void envoi();
                        }}
                    />
                    <div className="flex justify-end gap-2">
                        {enCours ? (
                            <Button size="sm" variant="outline" onClick={() => void arreter()}>
                                <Square className="size-4" /> {t(T.arreter)}
                            </Button>
                        ) : (
                            <Button size="sm" disabled={!saisie.trim()} onClick={() => void envoi()} aria-label={t(T.envoyer)}>
                                <ArrowUp className="size-4" /> {t(T.envoyer)}
                            </Button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

function Ligne({
    ligne,
    peutModifier,
    modifier,
    questionActive,
    repondre,
    edition,
}: {
    ligne: LigneDuFil;
    peutModifier: boolean;
    modifier: () => void;
    questionActive: boolean;
    repondre: (texte: string) => void;
    edition: string | null;
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
                    <div className="max-w-[80%] rounded-xl bg-muted px-3 py-2 text-sm whitespace-pre-wrap">{ligne.texte}</div>
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
