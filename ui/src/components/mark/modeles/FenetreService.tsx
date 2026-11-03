"use client";

/**
 * [.mark] La fenêtre d'un service (U3, E35) : cerveau, transcription, voix, plongement, temps réel. La MÊME fenêtre
 * sert l'organisation (Brancher › Modèles et clés) et l'agent (Réglages de l'agent).
 *
 * Elle ne dessine aucun champ : elle monte `ServiceConfigurationForm` sur UN seul service (`segments`), donc le
 * fournisseur, le modèle, la clé et les champs du fournisseur viennent du schéma du serveur (`registry.py`). Un
 * fournisseur ajouté au serveur apparaît ici sans toucher à cet écran. Les réglages rares sont déjà rangés par le
 * formulaire en sous-menus repliés (`mark_groupe`) : c'est le « Avancé » de la maquette, sans second mécanisme.
 *
 * - Portée « agent » : l'héritage de l'organisation est l'interrupteur « Remplacer » du formulaire (mode `override`),
 *   avec le résumé de ce que l'agent hérite tant qu'il est éteint. Le plongement n'est pas remplaçable par un agent.
 * - Portée « organisation » : le formulaire en mode `global`.
 * - « Tester la connexion » appelle la vérification du fork (`/user/configurations/user/validate`, TTL 0 pour forcer
 *   la vérification) sur la configuration ENREGISTRÉE de l'organisation : rien n'est envoyé à un fournisseur tant
 *   qu'on n'a pas cliqué, et un test n'écrit rien.
 */
import { CheckCircle2, LoaderCircle, Plug } from "lucide-react";
import { useState } from "react";

import { validateUserConfigurationsApiV1UserConfigurationsUserValidateGet } from "@/client/sdk.gen";
import { ServiceConfigurationForm,type ServiceSegment } from "@/components/ServiceConfigurationForm";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";
import type { ModelOverrides } from "@/types/workflow-configurations";

import { type Texte, useLangue } from "../langue/langue";
import { FenetreOnglets } from "../studio/fenetre-onglets";

const TITRES: Record<ServiceSegment, Texte> = {
    llm: { en: "Brain", fr: "Cerveau" },
    tts: { en: "Voice", fr: "Voix" },
    stt: { en: "Transcription", fr: "Transcription" },
    embeddings: { en: "Embedding", fr: "Plongement" },
    realtime: { en: "Realtime model", fr: "Modèle temps réel" },
};

const T = {
    tester: { en: "Test the connection", fr: "Tester la connexion" },
    essai: { en: "Testing...", fr: "Vérification..." },
    valide: { en: "The connection works.", fr: "La connexion fonctionne." },
    echec: { en: "The connection could not be checked", fr: "La connexion n'a pas pu être vérifiée" },
} satisfies Record<string, Texte>;

export type FenetreServiceProps = {
    service: ServiceSegment;
    fermer: () => void;
    /** Reçoit la configuration du formulaire (la forme que `ServiceConfigurationForm` produit). */
    enregistrer: (configuration: Record<string, unknown>) => Promise<void>;
} & (
    | { portee: "organisation"; remplacementsAgent?: undefined }
    | { portee: "agent"; remplacementsAgent?: ModelOverrides }
);

export function FenetreService(props: FenetreServiceProps) {
    const { service, fermer, enregistrer, portee } = props;
    const { t } = useLangue();
    const [essai, setEssai] = useState<{ etat: "attente" | "ok" | "echec"; message?: string } | null>(null);

    const tester = async () => {
        setEssai({ etat: "attente" });
        try {
            const reponse = await validateUserConfigurationsApiV1UserConfigurationsUserValidateGet({
                query: { validity_ttl_seconds: 0 },
            });
            if (reponse.error) {
                setEssai({ etat: "echec", message: detailFromError(reponse.error, t(T.echec)) });
                return;
            }
            // Le fork rend une ligne par service dont la clé ou le modèle est refusé ; une liste vide = tout est bon.
            const refuse = (reponse.data?.status ?? []).find((s) => s.model === service);
            setEssai(refuse ? { etat: "echec", message: refuse.message } : { etat: "ok" });
        } catch (e) {
            setEssai({ etat: "echec", message: detailFromError(e, t(T.echec)) });
        }
    };

    return (
        <FenetreOnglets
            fermer={fermer}
            titre={t(TITRES[service])}
            valider={null}
            pied={
                <div className="flex items-center gap-3">
                    <Button type="button" variant="outline" className="cursor-pointer gap-1.5" onClick={() => void tester()} disabled={essai?.etat === "attente"}>
                        {essai?.etat === "attente" ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Plug className="size-4" aria-hidden />}
                        {essai?.etat === "attente" ? t(T.essai) : t(T.tester)}
                    </Button>
                    {essai?.etat === "ok" && (
                        <span className="flex items-center gap-1.5 text-sm" role="status" data-essai="ok">
                            <CheckCircle2 className="size-4 text-(--etat-fait)" aria-hidden />
                            {t(T.valide)}
                        </span>
                    )}
                    {essai?.etat === "echec" && (
                        <span className="max-w-md truncate text-sm text-destructive" role="alert" data-essai="echec" title={essai.message}>
                            {essai.message}
                        </span>
                    )}
                </div>
            }
        >
            <ServiceConfigurationForm
                mode={portee === "agent" ? "override" : "global"}
                segments={[service]}
                forceRealtime={service === "realtime"}
                currentOverrides={portee === "agent" ? props.remplacementsAgent : undefined}
                onSave={enregistrer}
            />
        </FenetreOnglets>
    );
}
