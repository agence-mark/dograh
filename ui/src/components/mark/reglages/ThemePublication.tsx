"use client";

/**
 * [.mark] Partie 3, sous-lot 3 (SE-12 / D-1) : le thème « Publication » des Réglages de l'organisation. Deux réglages qui n'avaient
 * pas d'écran : l'interrupteur du déploiement progressif (ÉTEINT par défaut : une publication vaut pour tous les appels) et la
 * position de chaque contrôle de la fenêtre « Publier » (Éteint, Prévient, Bloque). Un agent qui a ses propres réglages les garde ;
 * les autres reçoivent ceux de l'organisation à leur publication. Une ligne de l'organisation, un seul « Enregistrer ».
 */
import { Rocket } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { defautsDeLOrganisationApiV1BuilderPublicationOrganisationGet, reglerLesDefautsDeLOrganisationApiV1BuilderPublicationOrganisationPut } from "@/client/sdk.gen";
import type { CleControle, PositionControle } from "@/components/mark/agent/publication/types";
import { notifier } from "@/components/mark/notifications";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";

import { ChampReglage } from "../ecran/ChampReglage";
import { type ErreurNommee, Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { type ProprietesThemeOrganisation, useSignaler } from "../parametres-organisation/ThemesOrganisation";

export const TITRE_PUBLICATION: Texte = { en: "Publication", fr: "Publication" };

export interface DefautsDePublication {
    controles: Record<CleControle, PositionControle>;
    deploiement: { actif: boolean };
}

const POSITIONS: PositionControle[] = ["eteint", "previent", "bloque"];

export const CONTROLES: Array<{ cle: CleControle; libelle: Texte; aide: Texte }> = [
    {
        cle: "tests_obligatoires",
        libelle: { en: "Required tests", fr: "Tests obligatoires" },
        aide: { en: "Every required test of the agent, played on the draft. Blocks by default.", fr: "Chaque test obligatoire de l'agent, joué sur le brouillon. Bloquant par défaut." },
    },
    {
        cle: "bilan_du_prompt",
        libelle: { en: "Prompt health check", fr: "Bilan de santé du prompt" },
        aide: { en: "Contradictions, unknown variable, tool named but missing. Blocks by default.", fr: "Contradictions, variable inconnue, outil cité mais absent. Bloquant par défaut." },
    },
    {
        cle: "liste_vocale",
        libelle: { en: "Voice checklist", fr: "Liste de contrôle vocale" },
        aide: { en: "The points of the « Checks before publishing » library family. Off by default.", fr: "Les points de la famille « Contrôles avant publication » de la bibliothèque. Éteinte par défaut." },
    },
    {
        cle: "attaques",
        libelle: { en: "Attacks", fr: "Attaques" },
        aide: { en: "The last « Attack the agent » run on the draft. Off by default.", fr: "Le dernier passage de « Attaquer l'agent » sur le brouillon. Éteintes par défaut." },
    },
    {
        cle: "garde_fous",
        libelle: { en: "Safeguards", fr: "Garde-fous" },
        aide: { en: "At least one safety layer of the conversation is on. Off by default.", fr: "Au moins une couche de sécurité de la conversation est allumée. Éteints par défaut." },
    },
    // [.mark] Partie 3 (SA-L3a) : les lignes de « Prêt à publier » se règlent comme les autres contrôles.
    {
        cle: "variables",
        libelle: { en: "Prompt variables", fr: "Variables des prompts" },
        aide: { en: "Every {{variable}} the prompts read has a value. Blocks by default.", fr: "Chaque {{variable}} lue par les prompts a une valeur. Bloquantes par défaut." },
    },
    {
        cle: "briques",
        libelle: { en: "Models configured", fr: "Modèles configurés" },
        aide: { en: "Brain, transcription and voice are set. Blocks by default.", fr: "Cerveau, transcription et voix sont réglés. Bloquants par défaut." },
    },
    {
        cle: "outils",
        libelle: { en: "Tools connected", fr: "Outils branchés" },
        aide: { en: "Every tool a step carries exists and is active. Blocks by default.", fr: "Chaque outil porté par une étape existe et est actif. Bloquants par défaut." },
    },
    {
        cle: "sortie_d_impasse",
        libelle: { en: "Dead-end exit", fr: "Sortie d'impasse" },
        aide: { en: "The dead-end exit is on: its « Then » must lead somewhere. Blocks by default.", fr: "La sortie d'impasse est allumée : son « Ensuite » doit mener quelque part. Bloquante par défaut." },
    },
    {
        cle: "sans_effet",
        libelle: { en: "Settings with no effect", fr: "Réglages sans effet" },
        aide: { en: "A setting that is on and changes nothing in the call. Warns by default.", fr: "Un réglage allumé qui ne change rien à l'appel. Préviennent par défaut." },
    },
    {
        cle: "deux_webhooks",
        libelle: { en: "Two webhooks", fr: "Deux webhooks" },
        aide: { en: "Dograh's webhook and the .mark module both send after the call. Warns by default.", fr: "Le webhook de Dograh et le module .mark envoient tous deux après l'appel. Préviennent par défaut." },
    },
];

export const ThemePublication = ({ ouvert, onBasculer, signaler, plat, sansTitre, titre }: ProprietesThemeOrganisation) => {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [enregistre, setEnregistre] = useState<DefautsDePublication | null>(null);
    const [brouillon, setBrouillon] = useState<DefautsDePublication | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const dejaLu = useRef(false);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            const r = await defautsDeLOrganisationApiV1BuilderPublicationOrganisationGet();
            if (r.error || !r.data) {
                setErreur(echecAffiche(r.error));
                return;
            }
            const lu = r.data as DefautsDePublication;
            setEnregistre(lu);
            setBrouillon(lu);
        })();
    }, [authLoading, user]);

    const modifie = brouillon !== null && enregistre !== null && JSON.stringify(brouillon) !== JSON.stringify(enregistre);
    const erreurs: ErreurNommee[] = [];
    useSignaler("publication", modifie, false, signaler);

    const mot: Record<PositionControle, string> = {
        eteint: t({ en: "Off", fr: "Éteint" }),
        previent: t({ en: "Warns", fr: "Prévient" }),
        bloque: t({ en: "Blocks", fr: "Bloque" }),
    };

    const enregistrer = async () => {
        if (!brouillon || enCours) return;
        setEnCours(true);
        setErreur(null);
        const r = await reglerLesDefautsDeLOrganisationApiV1BuilderPublicationOrganisationPut({ body: brouillon });
        setEnCours(false);
        if (r.error || !r.data) {
            notifier.echec(
                { fr: "Réglages de publication non enregistrés. Réessayez.", en: "Publication settings not saved. Try again." },
                { erreur: r.error, reessayer: () => void enregistrer() },
            );
            return;
        }
        const ecrit = r.data as DefautsDePublication;
        setEnregistre(ecrit);
        setBrouillon(ecrit);
        notifier.succes({ fr: "Réglages de publication enregistrés.", en: "Publication settings saved." });
    };

    const lignes = brouillon
        ? [
              {
                  libelle: { en: "Progressive deployment", fr: "Déploiement progressif" },
                  valeur: brouillon.deploiement.actif ? t({ en: "On", fr: "Allumé" }) : t({ en: "Off", fr: "Éteint" }),
              },
              ...CONTROLES.map((c) => ({ libelle: c.libelle, valeur: mot[brouillon.controles[c.cle]] })),
          ]
        : [{ libelle: { en: "Progressive deployment", fr: "Déploiement progressif" }, valeur: erreur ?? t({ en: "Loading...", fr: "Chargement..." }) }];

    return (
        <Theme
            id="publication"
            plat={plat}
            sansTitre={sansTitre}
            icone={Rocket}
            titre={titre ?? TITRE_PUBLICATION}
            description={{
                en: "How a new version goes out for the agents of this organization: the share of calls it may take first, and what each check of the « Publish » window does. An agent that has its own settings keeps them.",
                fr: "Comment une nouvelle version sort pour les agents de cette organisation : la part d'appels qu'elle peut prendre d'abord, et ce que fait chaque contrôle de la fenêtre « Publier ». Un agent qui a ses propres réglages les garde.",
            }}
            resume={[brouillon ? (brouillon.deploiement.actif ? t({ en: "Progressive deployment on", fr: "Déploiement progressif allumé" }) : t({ en: "Progressive deployment off", fr: "Déploiement progressif éteint" })) : null]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={erreurs}
            lignes={lignes}
            enregistrement={brouillon ? { onEnregistrer: () => void enregistrer(), enCours, actifSansModification: false } : undefined}
        >
            {brouillon === null ? (
                <p className="text-sm text-muted-foreground">{erreur ?? t({ en: "Loading...", fr: "Chargement..." })}</p>
            ) : (
                <>
                    <ChampReglage
                        cle="publication.deploiement.actif"
                        idControle="publication-deploiement"
                        libelle={{ en: "Progressive deployment", fr: "Déploiement progressif" }}
                        aides={[
                            {
                                en: "Off: a publication is for all calls. On: the « Publish » window offers to give a new version only a share of the calls (10, 25 or 50 %); the previous version keeps the rest. A call gets its version when it starts, and the same caller always lands on the same one, on every path (incoming and outgoing calls, campaigns, the website widget, transfers). Nothing switches by itself.",
                                fr: "Éteint : une publication vaut pour tous les appels. Allumé : la fenêtre « Publier » propose de ne donner à une nouvelle version qu'une part des appels (10, 25 ou 50 %) ; l'ancienne version garde le reste. L'appel reçoit sa version à son début, et un même interlocuteur tombe toujours sur la même, sur tous les chemins (appels entrants et sortants, campagnes, widget du site, transferts). Rien ne bascule seul.",
                            },
                        ]}
                        disposition="ligne"
                    >
                        <Switch
                            id="publication-deploiement"
                            checked={brouillon.deploiement.actif}
                            onCheckedChange={(v) => setBrouillon({ ...brouillon, deploiement: { actif: v } })}
                        />
                    </ChampReglage>
                    {CONTROLES.map((c) => (
                        <ChampReglage key={c.cle} cle={`publication.controles.${c.cle}`} libelle={c.libelle} aides={[c.aide]}>
                            <Segmente
                                valeur={mot[brouillon.controles[c.cle]]}
                                options={POSITIONS.map((p) => mot[p])}
                                changer={(v) =>
                                    setBrouillon({ ...brouillon, controles: { ...brouillon.controles, [c.cle]: POSITIONS.find((p) => mot[p] === v) ?? brouillon.controles[c.cle] } })
                                }
                            />
                        </ChampReglage>
                    ))}
                </>
            )}
        </Theme>
    );
};
