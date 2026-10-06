"use client";

/**
 * [.mark] The establishments this agent serves (chantier l-agent-travaille, L1, E2, E3).
 *
 * Read-only: an agent serves an establishment through its numbers (Telephony), and the values
 * shown are those its calls will read, resolved by the SERVER with the functions of the call
 * (E8: one rule on screen and in the code), the agent's draft hours and address included. Each
 * value says where it comes from: this agent, the establishment, or the organization.
 */
import { useEffect, useState } from "react";

import { postEtablissementsDeLagentApiV1OrganizationsEtablissementsAgentPost } from "@/client/sdk.gen";
import type { AdresseEtablissement, EtablissementsDeLagent, ValeurHeritee } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

import { type Texte, useLangue } from "../langue/langue";

const ORIGINES: Record<NonNullable<ValeurHeritee["origine"]>, Texte> = {
    agent: { en: "this agent", fr: "cet agent" },
    etablissement: { en: "the establishment", fr: "l'établissement" },
    organisation: { en: "inherited from the organization", fr: "hérité de l'organisation" },
    aucune: { en: "none", fr: "aucune" },
};

const LIGNES: Array<{ cle: "horaires_ouverture" | "adresse" | "annonce_fermeture" | "annonce_pause" | "numero_transfert"; libelle: Texte }> = [
    { cle: "horaires_ouverture", libelle: { en: "Opening hours", fr: "Horaires d'ouverture" } },
    { cle: "adresse", libelle: { en: "Address", fr: "Adresse" } },
    { cle: "annonce_fermeture", libelle: { en: "Closing sentence", fr: "Phrase de fermeture" } },
    { cle: "annonce_pause", libelle: { en: "Break sentence", fr: "Phrase de pause" } },
    { cle: "numero_transfert", libelle: { en: "Transfer number", fr: "Numéro de transfert" } },
];

export const EtablissementsServis = ({
    workflowId,
    horaires,
    adresse,
}: {
    workflowId: number;
    horaires: string | null;
    adresse: AdresseEtablissement | null;
}) => {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [vue, setVue] = useState<EtablissementsDeLagent | null>(null);
    const [erreur, setErreur] = useState(false);
    const cle = JSON.stringify([workflowId, horaires, adresse]);

    useEffect(() => {
        if (authLoading || !user) return;
        let annule = false;
        const minuterie = setTimeout(async () => {
            const reponse = await postEtablissementsDeLagentApiV1OrganizationsEtablissementsAgentPost({
                body: { workflow_id: workflowId, horaires_ouverture: horaires, adresse_etablissement: adresse ?? null },
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
    }, [authLoading, user, cle]);

    if (erreur) {
        return <p className="text-sm text-destructive">{t({ en: "Establishments unreadable.", fr: "Établissements illisibles." })}</p>;
    }
    if (vue === null) return <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>;
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
                        {e.nom} <span className="font-mono text-xs text-muted-foreground">{(e.numeros ?? []).join(", ")}</span>
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
