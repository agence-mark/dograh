"use client";

import { Inbox, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
    lireFilApiV1RelationClientsOrganizationIdFilsFilIdGet,
    listerFilsApiV1RelationFilsGet,
    modifierFilApiV1RelationClientsOrganizationIdFilsFilIdPatch,
    repondreApiV1RelationClientsOrganizationIdFilsFilIdMessagesPost,
} from "@/client/sdk.gen";
import type { FilOut } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Liste } from "@/components/mark/studio/liste";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { ETATS_DEMANDE, MarqueEtat, quand } from "./commun";

type Filtre = "a_traiter" | "moi" | "tous";

/**
 * [.mark] Messages (E92, E93) : la boîte à trois colonnes. Les fils à gauche (À traiter, À moi, Tous, recherche), la
 * conversation au centre (répondre au client ou écrire une note interne), le client à droite. Une demande de logiciel
 * est un fil comme un autre, avec son état propre. `client` fige la boîte sur un client (fiche d'un client).
 */
export function BoiteMessages({ client, filInitial }: { client?: number; filInitial?: number | null }) {
    const { t } = useLangue();
    const [filtre, setFiltre] = useState<Filtre>("a_traiter");
    const [q, setQ] = useState("");
    const [fils, setFils] = useState<FilOut[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [actif, setActif] = useState<{ organisation: number; id: number } | null>(null);

    const charger = useCallback(() => {
        listerFilsApiV1RelationFilsGet({
            query: {
                a_traiter: filtre === "a_traiter",
                suivi: filtre === "moi" ? "moi" : undefined,
                client,
                q: q.trim() || undefined,
            },
        }).then((res) => {
            if (res.error || !res.data) return setErreur(true);
            setErreur(false);
            setFils(res.data);
        });
    }, [filtre, q, client]);

    useEffect(() => {
        const minuteur = setTimeout(charger, q ? 250 : 0);
        return () => clearTimeout(minuteur);
    }, [charger, q]);

    useEffect(() => {
        if (filInitial && fils && !actif) {
            const f = fils.find((x) => x.id === filInitial);
            if (f) setActif({ organisation: f.organization_id, id: f.id });
        }
    }, [filInitial, fils, actif]);

    if (erreur) return <EtatVide cas="erreur" reessayer={charger} />;
    if (fils === null) return <EtatVide cas="chargement" />;

    return (
        <div className="grid h-[calc(100vh-14rem)] min-h-[420px] grid-cols-1 md:grid-cols-[20rem_1fr]">
            <div className="flex min-h-0 flex-col border-r pr-4">
                <div className="space-y-2 pb-3">
                    <div className="relative">
                        <Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" />
                        <Input
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            placeholder={t({ en: "Search", fr: "Rechercher" })}
                            className="pl-8"
                        />
                    </div>
                    <Liste
                        valeur={filtre}
                        changer={(v) => setFiltre(v as Filtre)}
                        options={[
                            { valeur: "a_traiter", libelle: t({ en: "To handle", fr: "À traiter" }) },
                            { valeur: "moi", libelle: t({ en: "Mine", fr: "À moi" }) },
                            { valeur: "tous", libelle: t({ en: "All", fr: "Tous" }) },
                        ]}
                    />
                </div>
                <div className="min-h-0 flex-1 divide-y overflow-y-auto">
                    {fils.length === 0 ? (
                        <EtatVide cas="premier" icone={Inbox} titre={t({ en: "No thread", fr: "Aucun fil" })} />
                    ) : (
                        fils.map((f) => (
                            <button
                                key={f.id}
                                type="button"
                                onClick={() => setActif({ organisation: f.organization_id, id: f.id })}
                                className={`flex w-full cursor-pointer flex-col gap-0.5 py-2.5 text-left hover:font-medium ${actif?.id === f.id ? "font-medium" : ""}`}
                            >
                                <span className="flex items-center justify-between gap-2">
                                    <span className="truncate text-sm">{f.sujet}</span>
                                    {!f.lu_par_mark && <span className="size-2 shrink-0 rounded-full bg-(--acc)" aria-label={t({ en: "Unread", fr: "Non lu" })} />}
                                </span>
                                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                                    <span className="truncate">{f.client}</span>
                                    <MarqueEtat etat={f.etat} />
                                    <span className="ml-auto shrink-0">{quand(f.modifie_le)}</span>
                                </span>
                                {f.dernier && <span className="truncate text-xs text-muted-foreground">{f.dernier.texte}</span>}
                            </button>
                        ))
                    )}
                </div>
            </div>
            <div className="min-h-0 pl-4">
                {actif ? (
                    <Conversation key={`${actif.organisation}-${actif.id}`} organisation={actif.organisation} id={actif.id} onChange={charger} />
                ) : (
                    <EtatVide cas="premier" icone={Inbox} titre={t({ en: "Pick a thread", fr: "Choisis un fil" })} />
                )}
            </div>
        </div>
    );
}

function Conversation({ organisation, id, onChange }: { organisation: number; id: number; onChange: () => void }) {
    const { t } = useLangue();
    const [fil, setFil] = useState<FilOut | null>(null);
    const [onglet, setOnglet] = useState<"mark" | "interne">("mark");
    const [texte, setTexte] = useState("");
    const [envoi, setEnvoi] = useState(false);

    const lire = useCallback(() => {
        lireFilApiV1RelationClientsOrganizationIdFilsFilIdGet({ path: { organization_id: organisation, fil_id: id } }).then((res) => {
            if (res.data) setFil(res.data);
            else toast.error(detailFromError(res.error, t({ en: "The thread could not be read", fr: "Le fil n'a pas pu être lu" })));
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [organisation, id]);
    useEffect(lire, [lire]);

    const changer = async (corps: { etat?: "nouveau" | "en_cours" | "repondu" | "clos"; suivi?: "moi" | "personne"; etat_demande?: "nouvelle" | "proposee" | "a_coder" | "refusee" }) => {
        const res = await modifierFilApiV1RelationClientsOrganizationIdFilsFilIdPatch({ path: { organization_id: organisation, fil_id: id }, body: corps });
        if (res.error) return toast.error(detailFromError(res.error, t({ en: "Change failed", fr: "Modification impossible" })));
        lire();
        onChange();
    };

    const envoyer = async () => {
        if (!texte.trim()) return;
        setEnvoi(true);
        const res = await repondreApiV1RelationClientsOrganizationIdFilsFilIdMessagesPost({
            path: { organization_id: organisation, fil_id: id },
            body: { cote: onglet, texte },
        });
        setEnvoi(false);
        if (res.error) return toast.error(detailFromError(res.error, t({ en: "Message not sent", fr: "Message non envoyé" })));
        setTexte("");
        lire();
        onChange();
    };

    if (!fil) return <EtatVide cas="chargement" />;
    return (
        <div className="flex h-full min-h-0 flex-col">
            <div className="flex flex-wrap items-center gap-2 border-b pb-3">
                <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{fil.sujet}</p>
                    <p className="text-xs text-muted-foreground">
                        {fil.client}
                        {fil.suivi_nom ? ` · ${t({ en: "Followed by", fr: "Suivi par" })} ${fil.suivi_nom}` : ""}
                    </p>
                </div>
                <MarqueEtat etat={fil.etat} />
                <Button variant="ghost" size="sm" onClick={() => changer({ suivi: fil.suivi_par ? "personne" : "moi" })}>
                    {fil.suivi_par ? t({ en: "Release", fr: "Lâcher" }) : t({ en: "Take it", fr: "Je m'en occupe" })}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => changer({ etat: fil.etat === "clos" ? "en_cours" : "clos" })}>
                    {fil.etat === "clos" ? t({ en: "Reopen", fr: "Rouvrir" }) : t({ en: "Close", fr: "Clore" })}
                </Button>
            </div>
            {fil.sorte === "demande_logiciel" && (
                <div className="flex flex-wrap items-center gap-2 border-b py-2 text-sm">
                    <span className="font-medium">{fil.logiciel}</span>
                    <Info>
                        {t({
                            en: "A software request. Propose it to the client when it is in the catalogue, mark it to build, or decline it.",
                            fr: "Une demande de logiciel. La proposer au client si elle est au catalogue, la marquer à coder, ou la refuser.",
                        })}
                    </Info>
                    <Liste
                        valeur={fil.etat_demande ?? "nouvelle"}
                        changer={(v) => changer({ etat_demande: v as "nouvelle" })}
                        options={Object.entries(ETATS_DEMANDE).map(([valeur, l]) => ({ valeur, libelle: t(l) }))}
                    />
                </div>
            )}
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto py-3">
                {(fil.messages ?? []).map((m) => (
                    <div key={m.id} className={`flex ${m.cote === "client" ? "justify-start" : "justify-end"}`}>
                        <div
                            className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${m.cote === "interne" ? "border border-dashed" : m.cote === "mark" ? "bg-(--acc) text-white" : "bg-muted"}`}
                        >
                            <p className="mb-0.5 text-[11px] opacity-80">
                                {m.auteur}
                                {m.cote === "interne" ? ` · ${t({ en: "internal note", fr: "note interne" })}` : ""} · {quand(m.cree_le)}
                            </p>
                            <p className="whitespace-pre-wrap">{m.texte}</p>
                        </div>
                    </div>
                ))}
            </div>
            <div className="space-y-2 border-t pt-3">
                <div className="flex items-center gap-1 text-sm">
                    {(["mark", "interne"] as const).map((o) => (
                        <button
                            key={o}
                            type="button"
                            onClick={() => setOnglet(o)}
                            className={`cursor-pointer rounded px-2 py-1 hover:font-medium ${onglet === o ? "font-medium underline-offset-4" : "text-muted-foreground"}`}
                        >
                            {o === "mark" ? t({ en: "Reply", fr: "Répondre" }) : t({ en: "Internal note", fr: "Note interne" })}
                        </button>
                    ))}
                    {onglet === "interne" && (
                        <Info>{t({ en: "Never shown to the client.", fr: "Jamais montrée au client." })}</Info>
                    )}
                </div>
                <Textarea value={texte} onChange={(e) => setTexte(e.target.value)} rows={3} />
                <div className="flex justify-end">
                    <Button size="sm" disabled={envoi || !texte.trim()} onClick={envoyer}>
                        {onglet === "mark" ? t({ en: "Send", fr: "Envoyer" }) : t({ en: "Add the note", fr: "Ajouter la note" })}
                    </Button>
                </div>
            </div>
        </div>
    );
}
