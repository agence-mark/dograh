"use client";

/**
 * [.mark] builder partie 2, U5 (E96, E97) : les sous-agents du builder dans le fil.
 * Une carte par délégation (terminés sur total, coût, une ligne par sous-agent : état, Arrêter, Voir, résumé dépliable, Tout arrêter).
 * Aucune fenêtre : « Voir » bascule le fil sur la conversation du sous-agent (lecture seule), le fil principal reste monté.
 * Une icône dans la saisie liste la conversation principale puis chaque sous-agent, avec l'interrupteur « Sous-agents dans ce chat ».
 */
import { Check, ChevronRight, Loader2, Square, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    arreterTousLesSousAgentsApiV1BuilderFilsFilIdSousAgentsArreterPost,
    arreterUnFilApiV1BuilderFilsFilIdArreterPost,
    listerLesSousAgentsApiV1BuilderFilsFilIdSousAgentsGet,
    reglerLInterrupteurApiV1BuilderFilsFilIdSousAgentsInterrupteurPut,
} from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

/** Une écriture de ce fichier dit son résultat (le client ne lève pas sur une erreur HTTP : on lit `error`). */
const dire = (appel: Promise<{ error?: unknown }>, succes: { en: string; fr: string }) =>
    appel.then((r) => {
        if (r.error) notifier.echec({ en: "The action failed. Try again.", fr: "L'action a échoué. Réessayez." });
        else notifier.succes(succes);
    });

const T = {
    titre: { en: "Sub-agents", fr: "Sous-agents" },
    aide: {
        en: "A sub-agent is a copy of the builder given one precise task. It only reads and tests, never writes, and reports back to the builder.",
        fr: "Un sous-agent est une copie du builder à qui on confie une tâche précise. Il lit et teste seulement, il n'écrit jamais, et il rend compte au builder.",
    },
    termines: { en: "done", fr: "terminés" },
    voir: { en: "View", fr: "Voir" },
    arreter: { en: "Stop", fr: "Arrêter" },
    toutArreter: { en: "Stop all", fr: "Tout arrêter" },
    principale: { en: "Main conversation", fr: "Conversation principale" },
    dansCeChat: { en: "Sub-agents in this chat", fr: "Sous-agents dans ce chat" },
    off: { en: "Off: the builder does everything itself, one task after the other.", fr: "Éteint : le builder fait tout lui-même, à la suite." },
    etats: {
        en: { terminee: "Done", en_cours: "Working", nouvelle: "Waiting", arretee: "Stopped", erreur: "Error" },
        fr: { terminee: "Terminé", en_cours: "Au travail", nouvelle: "En file", arretee: "Arrêté", erreur: "Erreur" },
    },
} as const;

export type SousAgent = {
    id: number;
    delegation: string | null;
    titre: string;
    usage: string | null;
    etat: string;
    modele: string | null;
    cout: number;
    resume: string | null;
    en_cours: boolean;
};

const actif = (s: SousAgent) => s.etat === "en_cours" || s.etat === "nouvelle";

export function libelleEtat(etat: string, langue: "en" | "fr"): string {
    const tous = T.etats[langue] as Record<string, string>;
    return tous[etat] ?? etat;
}

/** Interroge la liste tant qu'un sous-agent travaille (ou que la délégation n'est pas finie). */
export function useSousAgents(filId: number, vivant: boolean) {
    const [etat, setEtat] = useState<{ actif: boolean; sous_agents: SousAgent[] }>({ actif: true, sous_agents: [] });
    const charger = useCallback(async () => {
        const r = await listerLesSousAgentsApiV1BuilderFilsFilIdSousAgentsGet({ path: { fil_id: filId } });
        if (r.data) setEtat(r.data as { actif: boolean; sous_agents: SousAgent[] });
    }, [filId]);
    useEffect(() => {
        void charger();
        if (!vivant) return;
        const minuteur = setInterval(() => void charger(), 1500);
        return () => clearInterval(minuteur);
    }, [charger, vivant]);
    return { ...etat, recharger: charger };
}

export function CarteSousAgents({
    carte,
    sousAgents,
    voir,
    recharger,
    filId,
}: {
    carte: { [cle: string]: unknown };
    sousAgents: SousAgent[];
    voir: (id: number) => void;
    recharger: () => void;
    filId: number;
}) {
    const { t, langue } = useLangue();
    const groupe = sousAgents.filter((s) => s.delegation === carte.id);
    const finis = groupe.filter((s) => !actif(s)).length;
    const cout = groupe.reduce((n, s) => n + s.cout, 0);
    const arreter = async (id: number) => {
        await dire(arreterUnFilApiV1BuilderFilsFilIdArreterPost({ path: { fil_id: id } }), { en: "Sub-agent stopped.", fr: "Sous-agent arrêté." });
        recharger();
    };
    return (
        <section className="my-2 space-y-1 py-1" data-carte="delegation">
            <div className="flex items-center gap-2">
                <h4 className="text-sm font-semibold">
                    {t(T.titre)} · {String(carte.usage)}
                </h4>
                <Info>{t(T.aide)}</Info>
                <span className="text-xs text-muted-foreground">
                    {finis}/{Number(carte.total)} {t(T.termines)} · ${cout.toFixed(2)}
                </span>
                {groupe.some(actif) && (
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                            await dire(arreterTousLesSousAgentsApiV1BuilderFilsFilIdSousAgentsArreterPost({ path: { fil_id: filId } }), { en: "Sub-agents stopped.", fr: "Sous-agents arrêtés." });
                            recharger();
                        }}
                    >
                        <Square className="size-3.5" /> {t(T.toutArreter)}
                    </Button>
                )}
            </div>
            <ul className="space-y-1">
                {groupe.map((s) => (
                    <LigneSousAgent key={s.id} s={s} etat={libelleEtat(s.etat, langue)} voir={() => voir(s.id)} arreter={() => void arreter(s.id)} />
                ))}
            </ul>
        </section>
    );
}

function LigneSousAgent({ s, etat, voir, arreter }: { s: SousAgent; etat: string; voir: () => void; arreter: () => void }) {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    return (
        <li className="text-sm" data-sous-agent={s.id} data-etat={s.etat}>
            <div className="flex items-center gap-2">
                <button type="button" className="cursor-pointer" aria-label={s.titre} onClick={() => setOuvert((v) => !v)}>
                    <ChevronRight className={`size-3.5 transition-transform ${ouvert ? "rotate-90" : ""}`} />
                </button>
                {actif(s) ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5 text-(--etat-fait)" />}
                <span className="font-semibold">{s.titre}</span>
                <span className="text-xs text-muted-foreground">
                    {etat} · ${s.cout.toFixed(2)}
                </span>
                {actif(s) && (
                    <button type="button" className="cursor-pointer text-xs hover:font-semibold" onClick={arreter}>
                        {t(T.arreter)}
                    </button>
                )}
                <button type="button" className="cursor-pointer text-xs hover:font-semibold" onClick={voir}>
                    {t(T.voir)}
                </button>
            </div>
            {ouvert && s.resume ? <p className="mt-1 ml-6 text-sm whitespace-pre-wrap text-muted-foreground">{s.resume}</p> : null}
        </li>
    );
}

/** L'icône de la saisie : la liste attachée (conversation principale puis chaque sous-agent) et l'interrupteur du chat. */
export function ListeDesSousAgents({
    filId,
    actifDansLeChat,
    sousAgents,
    choisi,
    choisir,
    recharger,
}: {
    filId: number;
    actifDansLeChat: boolean;
    sousAgents: SousAgent[];
    choisi: number | null;
    choisir: (id: number | null) => void;
    recharger: () => void;
}) {
    const { t, langue } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    if (sousAgents.length === 0) return null;
    const travaillent = sousAgents.filter(actif).length;
    return (
        <div className="relative">
            <Button size="sm" variant="ghost" aria-label={t(T.titre)} onClick={() => setOuvert((v) => !v)}>
                {travaillent > 0 ? <Loader2 className="size-4 animate-spin" /> : <Users className="size-4" />}
                {travaillent > 0 ? `${sousAgents.length - travaillent} / ${sousAgents.length}` : null}
            </Button>
            {ouvert && (
                <div className="absolute right-0 bottom-full z-10 mb-2 w-72 space-y-1 rounded-xl bg-popover p-2 text-sm shadow-lg" data-liste="sous-agents">
                    <button type="button" className={`block w-full cursor-pointer text-left hover:font-semibold ${choisi === null ? "font-semibold" : ""}`} onClick={() => choisir(null)}>
                        {t(T.principale)}
                    </button>
                    {sousAgents.map((s) => (
                        <button
                            key={s.id}
                            type="button"
                            className={`flex w-full cursor-pointer items-center gap-2 text-left hover:font-semibold ${choisi === s.id ? "font-semibold" : ""}`}
                            onClick={() => choisir(s.id)}
                        >
                            {actif(s) ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
                            <span className="truncate">{s.titre}</span>
                            <span className="ml-auto text-xs text-muted-foreground">{libelleEtat(s.etat, langue)}</span>
                        </button>
                    ))}
                    <div className="flex items-center gap-2 pt-1">
                        <Switch
                            checked={actifDansLeChat}
                            aria-label={t(T.dansCeChat)}
                            onCheckedChange={async (valeur) => {
                                await dire(reglerLInterrupteurApiV1BuilderFilsFilIdSousAgentsInterrupteurPut({ path: { fil_id: filId }, body: { actif: valeur } }), valeur ? { en: "Sub-agents on for this chat.", fr: "Sous-agents activés pour ce chat." } : { en: "Sub-agents off for this chat.", fr: "Sous-agents coupés pour ce chat." });
                                recharger();
                            }}
                        />
                        <span>{t(T.dansCeChat)}</span>
                    </div>
                    {!actifDansLeChat && <p className="text-xs text-muted-foreground">{t(T.off)}</p>}
                </div>
            )}
        </div>
    );
}
