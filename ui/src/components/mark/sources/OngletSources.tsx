"use client";

/**
 * [.mark] U12 (E104) : l'onglet « Sources » des réglages du Labo, repris de la maquette (`OngletSources`) : une ligne par brique,
 * un choix segmenté « Claude Code » / « Clé d'API », un « ! » qui dit ce que change Claude Code, la ligne « Agent : toujours ses propres
 * clés ». Tout sur Claude Code au départ. Chaque changement dit son résultat par une notification.
 * Ajouté en chantier (provisoire, E-I1-1) : la ligne « Miroir de mes conversations Claude Code » (l'interrupteur par personne).
 */
import { Lock } from "lucide-react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Info } from "@/components/mark/studio/marques";

import { type Brique, BRIQUES, type Source, useMiroir, useSources } from "./useSources";

const T = {
    agent: { en: "Agent: always its own keys (transcription, model, voice)", fr: "Agent : toujours ses propres clés (transcription, modèle, voix)" },
    claudeCode: { en: "Claude Code", fr: "Claude Code" },
    cleApi: { en: "API key", fr: "Clé d'API" },
    suivent: { en: "The sub-agents follow the builder", fr: "Les sous-agents suivent le builder" },
    infoClaudeCode: {
        en: "The brick works when a Claude Code session is running and uses the person's subscription.",
        fr: "La brique travaille quand une session Claude Code tourne et consomme l'abonnement de la personne.",
    },
    infoMeme: {
        en: " For the caller and the judge: same model as the builder, played by sub-agents without its context.",
        fr: " Pour l'appelant et le juge : même modèle que le builder, joués par des sous-agents sans son contexte.",
    },
    infoCle: {
        en: "The brick calls its provider with the key set in the Labo settings (model, key and ceilings).",
        fr: "La brique appelle son fournisseur avec la clé réglée dans les réglages du Labo (modèle, clé et plafonds).",
    },
    ok: { en: "Source saved.", fr: "Source enregistrée." },
    echec: { en: "The source could not be saved. Try again.", fr: "La source n'a pas pu être enregistrée. Réessayez." },
    miroir: { en: "Mirror of my Claude Code conversations", fr: "Miroir de mes conversations Claude Code" },
    infoMiroir: {
        en: "Sends your messages, Claude's answers and the names of the dograh MCP actions (with a short summary) to the fork, read only, live. Never tool results or file contents; no secret leaves. It also needs the hooks installed on your machine.",
        fr: "Envoie vos messages, les réponses de Claude et les noms des actions du MCP dograh (avec un court résumé) au fork, en lecture seule et en direct. Jamais les résultats d'outils ni le contenu des fichiers ; aucun secret ne part. Il faut aussi que les hooks soient installés sur votre machine.",
    },
    allume: { en: "On", fr: "Allumé" },
    eteint: { en: "Off", fr: "Éteint" },
    miroirOk: { en: "Mirror setting saved.", fr: "Réglage du miroir enregistré." },
} satisfies Record<string, Texte>;

const LIBELLES: Record<Brique, Texte> = {
    builder: { en: "Builder", fr: "Builder" },
    appelant: { en: "Simulated caller", fr: "Appelant simulé" },
    juge_tests: { en: "Test judge", fr: "Juge des tests" },
    juge_appels: { en: "Real-call judge", fr: "Juge des vrais appels" },
    analyse: { en: "Call analysis", fr: "Analyse des appels" },
};
const MEME_MODELE: Brique[] = ["appelant", "juge_tests", "juge_appels"];

export function OngletSources() {
    const { t } = useLangue();
    const { sources, erreur, regler, relire } = useSources();
    const miroir = useMiroir();

    if (erreur) return <EtatVide cas="erreur" reessayer={() => void relire()} />;
    if (!sources) return <EtatVide cas="chargement" lignes={5} />;

    const changer = (brique: Brique, source: Source) =>
        notifier.suivre(regler(brique, source), {
            encours: { en: "Saving the source...", fr: "Enregistrement de la source..." },
            succes: T.ok,
            echec: T.echec,
            echecSi: (erreurServeur) => erreurServeur,
        });

    return (
        <div className="max-w-3xl">
            <p className="flex items-center gap-2 border-b py-3.5 text-sm text-muted-foreground">
                <Lock className="size-4" aria-hidden />
                {t(T.agent)}
            </p>
            {BRIQUES.map((b) => {
                const code = sources[b] === "claude_code";
                return (
                    <div key={b} className="flex items-start gap-4 border-b py-3.5">
                        <div className="min-w-0 flex-1">
                            <p className="flex items-center gap-1.5 text-sm font-medium">
                                {t(LIBELLES[b])}
                                <Info>
                                    {code ? t(T.infoClaudeCode) + (MEME_MODELE.includes(b) ? t(T.infoMeme) : "") : t(T.infoCle)}
                                </Info>
                            </p>
                            {b === "builder" && <p className="mt-0.5 text-xs text-muted-foreground">{t(T.suivent)}</p>}
                        </div>
                        <Segmente
                            valeur={code ? t(T.claudeCode) : t(T.cleApi)}
                            options={[t(T.claudeCode), t(T.cleApi)]}
                            changer={(v) => changer(b, v === t(T.claudeCode) ? "claude_code" : "cle_api")}
                        />
                    </div>
                );
            })}
            <div className="flex items-start gap-4 border-b py-3.5">
                <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-sm font-medium">
                        {t(T.miroir)}
                        <Info>{t(T.infoMiroir)}</Info>
                    </p>
                </div>
                {miroir.actif !== null && (
                    <Segmente
                        valeur={miroir.actif ? t(T.allume) : t(T.eteint)}
                        options={[t(T.allume), t(T.eteint)]}
                        changer={(v) =>
                            notifier.suivre(miroir.regler(v === t(T.allume)), {
                                encours: { en: "Saving...", fr: "Enregistrement..." },
                                succes: T.miroirOk,
                                echec: T.echec,
                                echecSi: (erreurServeur) => erreurServeur,
                            })
                        }
                    />
                )}
            </div>
        </div>
    );
}
