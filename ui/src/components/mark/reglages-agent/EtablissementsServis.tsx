"use client";

/**
 * [.mark] The establishments this agent serves (chantier l-agent-travaille, L1, E2, E3).
 *
 * Read-only: an agent serves an establishment through its numbers (Telephony), and the values
 * shown are those its calls will read, resolved by the SERVER with the functions of the call
 * (E8: one rule on screen and in the code), the agent's draft hours and address included. Each
 * value says where it comes from: this agent, the establishment, or the organization.
 *
 * Lot 11 (agents-specialises): an agent that chose a fiche reads that fiche ALONE (origin « fiche »,
 * nothing inherited), and its numbers are its own: the screen reads them under the menu of the fiche.
 * The read is shared (`useEtablissementsDeLagent`) so the menu's numbers and this list cost one request.
 */
import { useEffect, useState } from "react";

import { postEtablissementsDeLagentApiV1OrganizationsEtablissementsAgentPost } from "@/client/sdk.gen";
import type { AdresseEtablissement, EtablissementsDeLagent, ValeurHeritee } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

import { type Texte, useLangue } from "../langue/langue";

const ORIGINES: Record<NonNullable<ValeurHeritee["origine"]>, Texte> = {
    fiche: { en: "the fiche of this agent", fr: "la fiche de cet agent" },
    agent: { en: "this agent", fr: "cet agent" },
    etablissement: { en: "the establishment", fr: "l'établissement" },
    // F-8: no longer sent for an establishment (it inherits nothing); kept for the type.
    organisation: { en: "the organization", fr: "l'organisation" },
    aucune: { en: "none", fr: "aucune" },
};

const LIGNES: Array<{ cle: "horaires_ouverture" | "adresse" | "annonce_fermeture" | "annonce_pause" | "numero_transfert"; libelle: Texte }> = [
    { cle: "horaires_ouverture", libelle: { en: "Opening hours", fr: "Horaires d'ouverture" } },
    { cle: "adresse", libelle: { en: "Address", fr: "Adresse" } },
    { cle: "annonce_fermeture", libelle: { en: "Closing sentence", fr: "Phrase de fermeture" } },
    { cle: "annonce_pause", libelle: { en: "Break sentence", fr: "Phrase de pause" } },
    { cle: "numero_transfert", libelle: { en: "Transfer number", fr: "Numéro de transfert" } },
];

/** What the server resolves for this agent (its draft hours, address and chosen fiche included). */
export const useEtablissementsDeLagent = (
    workflowId: number | undefined,
    horaires: string | null,
    adresse: AdresseEtablissement | null,
    fiche: string | null = null,
) => {
    const { user, loading: authLoading } = useAuth();
    // Whether someone is signed in, not WHO: the hook now lives in a theme that renders often, and an
    // effect keyed on the user object would restart its timer at every render.
    const connecte = Boolean(user);
    const [vue, setVue] = useState<EtablissementsDeLagent | null>(null);
    const [erreur, setErreur] = useState(false);
    const cle = JSON.stringify([workflowId, horaires, adresse, fiche]);

    useEffect(() => {
        if (authLoading || !connecte || workflowId === undefined) return;
        let annule = false;
        const minuterie = setTimeout(async () => {
            const reponse = await postEtablissementsDeLagentApiV1OrganizationsEtablissementsAgentPost({
                body: {
                    workflow_id: workflowId,
                    horaires_ouverture: horaires,
                    adresse_etablissement: adresse ?? null,
                    // Sent only when a fiche is chosen: an agent without one asks exactly as before.
                    ...(fiche ? { etablissement_id: fiche } : {}),
                },
            });
            if (annule) return;
            setErreur(Boolean(reponse.error));
            setVue(reponse.data ?? null);
        }, 300);
        return () => {
            annule = true;
            clearTimeout(minuterie);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [authLoading, connecte, cle]);

    return { vue, erreur };
};

/** The numbers of the agent (Telephony), read only: they belong to the agent, the fiche to the place (C4). */
export const NumerosDeLagent = ({ vue }: { vue: EtablissementsDeLagent | null }) => {
    const { t } = useLangue();
    if (vue === null) return null;
    const numeros = vue.numeros_de_lagent ?? [];
    return (
        <p className="text-xs text-muted-foreground" data-testid="numeros-de-lagent">
            {t({ en: "Numbers of this agent (Telephony):", fr: "Numéros de cet agent (Telephony) :" })}{" "}
            <span className="font-mono text-foreground">{numeros.length > 0 ? numeros.join(", ") : t({ en: "none", fr: "aucun" })}</span>
        </p>
    );
};

export const EtablissementsServis = ({
    vue,
    erreur,
}: {
    vue: EtablissementsDeLagent | null;
    erreur: boolean;
}) => {
    const { t } = useLangue();

    if (erreur) {
        return <p className="text-sm text-destructive">{t({ en: "Establishments unreadable.", fr: "Établissements illisibles." })}</p>;
    }
    if (vue === null) return <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>;
    if (vue.fiche_introuvable) {
        return (
            <p className="text-sm text-destructive" data-testid="fiche-introuvable">
                {t({
                    en: "The fiche chosen for this agent no longer exists: its calls read no establishment. Choose another one, or none.",
                    fr: "La fiche choisie pour cet agent n'existe plus : ses appels ne lisent aucun établissement. Choisissez-en une autre, ou aucune.",
                })}
            </p>
        );
    }
    if (vue.etablissements?.length === 0) {
        return (
            <p className="text-sm text-muted-foreground" data-testid="aucun-etablissement-servi">
                {t({
                    en: "This agent serves no establishment: its calls read its own values, then the organization's, as before.",
                    fr: "Cet agent ne sert aucun établissement : ses appels lisent ses propres valeurs, puis celles de l'organisation, comme avant.",
                })}
            </p>
        );
    }
    return (
        <div className="space-y-3" data-testid="etablissements-servis">
            {(vue.etablissements ?? []).map((e) => (
                <div key={e.id} className="rounded border border-border p-3">
                    <p className="text-sm font-medium">
                        {e.nom}{" "}
                        {/* A fiche has no numbers on screen (C4): they are the agent's, shown under the menu. */}
                        {!vue.fiche_de_lagent && <span className="font-mono text-xs text-muted-foreground">{(e.numeros ?? []).join(", ")}</span>}
                    </p>
                    <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
                        {LIGNES.map(({ cle: champ, libelle }) => {
                            const valeur = e[champ];
                            return (
                                <div key={champ} className="contents">
                                    <dt className="text-muted-foreground">{t(libelle)}</dt>
                                    <dd className={valeur?.origine === "agent" ? "" : "text-muted-foreground"}>
                                        <span className="whitespace-pre-line">{valeur?.valeur || "—"}</span>{" "}
                                        <span className="text-xs">({t(ORIGINES[valeur?.origine ?? "aucune"])})</span>
                                    </dd>
                                </div>
                            );
                        })}
                    </dl>
                </div>
            ))}
            {(vue.numeros_sans_etablissement ?? []).length > 0 && (
                <p className="text-xs text-muted-foreground">
                    {t({ en: "Numbers of no establishment (calls as before):", fr: "Numéros d'aucun établissement (appels comme avant) :" })}{" "}
                    <span className="font-mono">{(vue.numeros_sans_etablissement ?? []).join(", ")}</span>
                </p>
            )}
        </div>
    );
};
