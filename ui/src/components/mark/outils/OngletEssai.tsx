"use client";

/**
 * [.mark] U3 sexies point 4 (E74) : l'essai de tous les types d'outils.
 *
 * Un outil qui lit s'essaie directement. Un outil qui écrit chez le client s'essaie sur une réponse simulée (requête
 * HTTP, action de logiciel) ou sur un compte de test (le serveur refuse l'essai direct). Un outil MCP s'essaie sur un
 * compte de test, un outil de ce serveur à la fois. « Premier essai validé par une personne » : le bouton n'apparaît
 * qu'après un essai réussi, et la validation est écrite par le serveur.
 */
import { Check } from "lucide-react";
import { useState } from "react";

import { essayerUnOutilApiV1ToolsToolUuidEssaiPost, validerLePremierEssaiApiV1ToolsToolUuidPremierEssaiPost } from "@/client/sdk.gen";
import type { ToolResponse, VerdictEssai } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { notifier } from "@/components/mark/notifications";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { useLangue } from "../langue/langue";
import { BlocChamp, Champs, LigneChamp, Segmente } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { type Config, liste, premierEssaiValide } from "./modele";

type Mode = "direct" | "simule" | "compte_de_test";

export function OngletEssai({
    outil,
    config,
    ecrit,
    modifie,
    apres,
}: {
    outil: ToolResponse;
    config: Config;
    ecrit: boolean;
    modifie: boolean;
    apres: () => void;
}) {
    const { t } = useLangue();
    const categorie = outil.category;
    const decouverts = liste<{ name: string }>(config, "discovered_tools");
    const [arguments_, setArguments] = useState(categorie === "calculator" ? '{"expression": "2 * (3 + 4)"}' : "{}");
    const [outilMcp, setOutilMcp] = useState(decouverts[0]?.name ?? "");
    const [mode, setMode] = useState<Mode>(categorie === "mcp" ? "compte_de_test" : "simule");
    const [verdict, setVerdict] = useState<VerdictEssai | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    const modes: { id: Mode; libelle: string }[] =
        categorie === "mcp"
            ? [{ id: "compte_de_test", libelle: t({ en: "Test account", fr: "Compte de test" }) }]
            : [
                  { id: "simule", libelle: t({ en: "Simulated answer", fr: "Réponse simulée" }) },
                  { id: "compte_de_test", libelle: t({ en: "Test account", fr: "Compte de test" }) },
              ];
    const modeEffectif: Mode = ecrit ? mode : "direct";

    const essayer = async () => {
        let args: Record<string, unknown>;
        try {
            args = JSON.parse(arguments_ || "{}") as Record<string, unknown>;
        } catch {
            return setErreur(t({ en: "The arguments are not valid JSON.", fr: "Les arguments ne sont pas du JSON valide." }));
        }
        setErreur(null);
        setEnCours(true);
        const r = await essayerUnOutilApiV1ToolsToolUuidEssaiPost({
            path: { tool_uuid: outil.tool_uuid },
            body: { arguments: args, mode: modeEffectif, outil_mcp: categorie === "mcp" ? outilMcp || null : null },
        });
        setEnCours(false);
        if (r.error || !r.data) {
            setVerdict(null);
            return notifier.echec(ECHECS.outilEssai, { erreur: r.error });
        }
        setVerdict(r.data);
        apres();
    };

    const valider = async () => {
        const r = await validerLePremierEssaiApiV1ToolsToolUuidPremierEssaiPost({ path: { tool_uuid: outil.tool_uuid } });
        if (r.error) return notifier.echec(ECHECS.outilValiderEssai, { erreur: r.error });
        setErreur(null);
        notifier.succes({ fr: "Premier essai validé.", en: "First trial validated." });
        apres();
    };

    const dernier = (config.dernier_essai ?? null) as { reussi?: boolean } | null;
    const reussi = verdict?.reussi ?? dernier?.reussi ?? false;
    const valide = premierEssaiValide(config);

    return (
        <Champs>
            {modifie && (
                <p className="py-3 text-sm text-muted-foreground">
                    {t({ en: "Save the changes first: the trial runs the saved tool.", fr: "Enregistrez d'abord les modifications : l'essai joue l'outil enregistré." })}
                </p>
            )}
            {ecrit && (
                <LigneChamp
                    libelle={t({ en: "This tool writes", fr: "Cet outil écrit" })}
                    info={t({
                        en: "It is never tried for real on a client's data: use a simulated answer, or confirm that its credential is a test account.",
                        fr: "Il ne s'essaie jamais pour de vrai sur les données d'un client : réponse simulée, ou identifiant d'un compte de test confirmé.",
                    })}
                >
                    <Segmente valeur={modes.find((m) => m.id === modeEffectif)?.libelle ?? ""} options={modes.map((m) => m.libelle)} changer={(v) => setMode(modes.find((m) => m.libelle === v)!.id)} />
                </LigneChamp>
            )}
            {categorie === "mcp" && (
                <LigneChamp libelle={t({ en: "Server tool", fr: "Outil du serveur" })}>
                    <Liste valeur={outilMcp} changer={setOutilMcp} options={decouverts.map((d) => d.name)} className="w-56" taille="default" />
                </LigneChamp>
            )}
            <BlocChamp libelle={t({ en: "Arguments (JSON)", fr: "Arguments (JSON)" })}>
                <Textarea rows={4} className="font-mono text-xs" value={arguments_} onChange={(e) => setArguments(e.target.value)} aria-label={t({ en: "Arguments", fr: "Arguments" })} />
            </BlocChamp>
            <div className="flex items-center gap-3 py-3">
                <Button disabled={enCours || modifie} onClick={() => void essayer()}>
                    {enCours ? t({ en: "Trying…", fr: "Essai…" }) : t({ en: "Try", fr: "Essayer" })}
                </Button>
                {valide ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                        <Check className="size-4" /> {t({ en: "First trial validated by a person", fr: "Premier essai validé par une personne" })}
                    </span>
                ) : (
                    <Button variant="outline" disabled={!reussi} onClick={() => void valider()}>
                        {t({ en: "Validate the first trial", fr: "Valider le premier essai" })}
                    </Button>
                )}
            </div>
            {erreur && <p className="py-2 text-sm text-destructive">{erreur}</p>}
            {verdict && (
                <div className="space-y-2 py-3 text-sm" aria-label={t({ en: "Trial result", fr: "Résultat de l'essai" })}>
                    <p className="font-medium">
                        {verdict.reussi ? t({ en: "Trial succeeded", fr: "Essai réussi" }) : t({ en: "Trial failed", fr: "Essai en échec" })}
                        <span className="font-normal text-muted-foreground">
                            {" "}
                            · {verdict.duree_ms} ms{verdict.statut_http ? ` · HTTP ${verdict.statut_http}` : ""}
                            {verdict.simulee ? ` · ${t({ en: "simulated", fr: "simulé" })}` : ""}
                        </span>
                    </p>
                    <p className="text-muted-foreground">{verdict.message}</p>
                    {verdict.donnees != null && <pre className="max-h-64 overflow-auto rounded-md bg-muted/50 p-3 text-xs">{JSON.stringify(verdict.donnees, null, 2)}</pre>}
                    {Object.keys(verdict.copies ?? {}).length > 0 && (
                        <p className="text-xs text-muted-foreground">
                            {t({ en: "Written in the record:", fr: "Écrit dans la fiche :" })} {JSON.stringify(verdict.copies)}
                        </p>
                    )}
                </div>
            )}
        </Champs>
    );
}
