"use client";

/**
 * [.mark] V2b (E51, E51 bis, E51 ter) : « Modèles et clés » comme la maquette, au lieu de l'écran de l'amont (BYOK,
 * onglets en anglais). Une carte par brique de l'organisation (transcription, cerveau, voix, plongement ; en temps
 * réel : le modèle temps réel, le cerveau et le plongement), un clic ouvre `FenetreService` ; dessous, le tableau des
 * clés. Même page au Labo et chez un client.
 *
 * Ce que la page lit : la configuration de modèles de l'organisation (clés masquées ou référencées, jamais lues), les
 * fournisseurs du serveur, le nombre d'agents qui remplacent chaque brique, la bibliothèque de clés (UNE lecture,
 * partagée par les cartes et le tableau). Ce qu'elle écrit : la configuration entière, par `construireCorps`.
 */
import { AudioLines, Brain, Ear, KeyRound, Layers, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get,
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet,
    getModelConfigurationV2RemplacementsApiV1OrganizationsModelConfigurationsV2RemplacementsGet,
    saveModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Put,
} from "@/client/sdk.gen";
import type { OrganizationAiModelConfigurationResponse } from "@/client/types.gen";
import type { ModelConfigurationDefaultsV2 } from "@/components/AIModelConfigurationV2Editor";
import type { ServiceSegment } from "@/components/ServiceConfigurationForm";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info } from "@/components/mark/studio/marques";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { Skeleton } from "@/components/ui/skeleton";
import { useUserConfig } from "@/context/UserConfigContext";
import { useAuth } from "@/lib/auth";

import { useCles, nomDu } from "../cles/FenetreCles";
import { TableauCles } from "../cles/TableauCles";
import { type Texte, useLangue } from "../langue/langue";
import {
    BRIQUES_DU_MODE,
    byokDefaults,
    ConfigurationIncomplete,
    construireCorps,
    existantDuMode,
    messageBriqueManquante,
    type ModeModeles,
    modeEnregistre,
    segmentsDeLaFenetre,
    vueDeLaBrique,
} from "./configuration-organisation";
import { FenetreService } from "./FenetreService";

const BRIQUES: Record<ServiceSegment, { nom: Texte; icone: LucideIcon }> = {
    stt: { nom: { en: "Transcription (STT)", fr: "Transcription (STT)" }, icone: Ear },
    llm: { nom: { en: "Brain (LLM)", fr: "Cerveau (LLM)" }, icone: Brain },
    tts: { nom: { en: "Voice (TTS)", fr: "Voix (TTS)" }, icone: AudioLines },
    embeddings: { nom: { en: "Embedding", fr: "Plongement" }, icone: Layers },
    realtime: { nom: { en: "Realtime model", fr: "Modèle temps réel" }, icone: AudioLines },
};

const T = {
    titre: { en: "Models and keys", fr: "Modèles et clés" },
    titreInfo: {
        en: "Agents inherit these models; an agent can replace one service, or all of them.",
        fr: "Les agents héritent de ces modèles ; un agent peut remplacer un service, ou tout.",
    },
    section: { en: "Organization models", fr: "Modèles de l'organisation" },
    sectionInfo: {
        en: "Agents inherit them; an agent can replace a service in its settings. BYOK mode: the keys are in the client's name.",
        fr: "Les agents en héritent ; un agent peut remplacer un service dans ses réglages. Mode BYOK : les clés sont au nom du client.",
    },
    chaine: { en: "STT / LLM / TTS", fr: "STT / LLM / TTS" },
    tempsReel: { en: "Realtime", fr: "Temps réel" },
    infoChaine: {
        en: "Three bricks in a row: transcription writes what the caller says, the brain answers, the voice says it. Each one is set, and replaced, on its own.",
        fr: "Trois briques à la suite : la transcription écrit ce que dit l'appelant, le cerveau répond, la voix le dit. Chacune se règle et se remplace à part.",
    },
    infoTempsReel: {
        en: "A single model listens, thinks and speaks. Transcription and voice are no longer used; the modules that read the transcript have no effect. The brain still extracts the variables and rates the call.",
        fr: "Un seul modèle écoute, réfléchit et parle. La transcription et la voix ne servent plus ; les modules qui lisent la transcription sont sans effet. Le cerveau extrait encore les variables et note l'appel.",
    },
    nonRegle: { en: "Not set", fr: "Non réglé" },
    cleSaisie: { en: "Typed key", fr: "Clé saisie" },
    aucuneCle: { en: "No key", fr: "Aucune clé" },
    cleSupprimee: { en: "Key deleted", fr: "Clé supprimée" },
    saved: { en: "Models saved.", fr: "Modèles enregistrés." },
    refuse: {
        en: "The provider refuses this configuration. Check the key and the model.",
        fr: "Le fournisseur refuse cette configuration. Vérifiez la clé et le modèle.",
    },
    droit: { en: "You are not allowed to change the models.", fr: "Vous n'avez pas le droit de changer les modèles." },
    echec: { en: "Could not save. Try again.", fr: "Enregistrement impossible. Réessayez." },
    lectureEchec: { en: "Could not save the models. Try again.", fr: "Les modèles n'ont pas été enregistrés. Réessayez." },
} satisfies Record<string, Texte>;

const remplacePar = (n: number): Texte => ({
    en: `replaced by ${n} agent${n > 1 ? "s" : ""}`,
    fr: `remplacé par ${n} agent${n > 1 ? "s" : ""}`,
});

export function PageModelesEtCles() {
    const { t } = useLangue();
    const auth = useAuth();
    const { refreshConfig } = useUserConfig();
    const lu = useRef(false);

    const [defauts, setDefauts] = useState<ModelConfigurationDefaultsV2 | null>(null);
    const [reponse, setReponse] = useState<OrganizationAiModelConfigurationResponse | null>(null);
    const [remplacements, setRemplacements] = useState<Record<string, number>>({});
    const [erreur, setErreur] = useState(false);
    const [mode, setMode] = useState<ModeModeles | null>(null);
    const [ouverte, setOuverte] = useState<ServiceSegment | null>(null);
    const { cles, erreur: erreurCles, recharger: rechargerCles } = useCles(undefined, !auth.loading && Boolean(auth.user));

    const charger = useCallback(async () => {
        setErreur(false);
        // Les trois lectures partent ensemble ; celle des remplacements n'est qu'une indication (une panne ne bloque rien).
        const [d, c, r] = await Promise.all([
            getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet(),
            getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get(),
            getModelConfigurationV2RemplacementsApiV1OrganizationsModelConfigurationsV2RemplacementsGet(),
        ]);
        if (d.error || c.error || !d.data || !c.data) {
            setErreur(true);
            return;
        }
        setDefauts(d.data as ModelConfigurationDefaultsV2);
        setReponse(c.data);
        setRemplacements(r.error ? {} : ((r.data as Record<string, number> | undefined) ?? {}));
        setMode((m) => m ?? modeEnregistre(c.data.configuration, c.data.effective_configuration));
    }, []);

    useEffect(() => {
        if (auth.loading || !auth.user || lu.current) return;
        lu.current = true;
        void charger();
    }, [auth.loading, auth.user, charger]);

    // Une ancienne adresse (`?onglet=cles`) amène sur le tableau des clés.
    useEffect(() => {
        if (!reponse) return;
        try {
            if (new URLSearchParams(window.location.search).get("onglet") === "cles") {
                document.getElementById("modeles-cles")?.scrollIntoView();
            }
        } catch {
            /* adresse illisible : la page reste en haut */
        }
    }, [reponse]);

    const existant = useMemo(
        () => (reponse && mode ? existantDuMode(reponse.configuration, reponse.effective_configuration, mode) : null),
        [reponse, mode],
    );
    const defautsDuServeur = useMemo(() => (defauts ? byokDefaults(defauts) : null), [defauts]);
    const segments = useMemo(
        () => (ouverte && mode && existant && defautsDuServeur ? segmentsDeLaFenetre(ouverte, mode, existant, defautsDuServeur) : []),
        [ouverte, mode, existant, defautsDuServeur],
    );

    const nomDeLaCle = (vue: ReturnType<typeof vueDeLaBrique>): string => {
        if (!vue) return "";
        if (vue.cle === null) return t(T.aucuneCle);
        if (vue.cle === "saisie") return t(T.cleSaisie);
        if (cles === null) return "…";
        return cles.find((c) => c.uuid === vue.cle)?.nom ?? t(T.cleSupprimee);
    };

    const enregistrer = async (sortie: Record<string, unknown>) => {
        if (!mode || !existant || !defautsDuServeur) return;
        let corps;
        try {
            corps = construireCorps(mode, existant, sortie, segments, defautsDuServeur);
        } catch (e) {
            if (e instanceof ConfigurationIncomplete) throw new Error(t(messageBriqueManquante(e.service)));
            throw e;
        }
        const r = await saveModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Put({ body: corps });
        if (r.error || !r.data) {
            const statut = r.response?.status;
            // Un refus de droits ne se « réessaie » pas : la notification le dit, au lieu de proposer de recommencer.
            notifier.echec(statut === 403 ? T.droit : T.lectureEchec, { erreur: r.error });
            throw new Error(t(statut === 403 ? T.droit : statut === 422 ? T.refuse : T.echec));
        }
        setReponse(r.data);
        void rechargerCles();
        await refreshConfig();
        notifier.succes(T.saved);
        setOuverte(null);
    };

    return (
        <PageStudio>
            <TitrePage titre={t(T.titre)} info={t(T.titreInfo)} />
            <p className="flex items-center gap-1.5 pt-2 font-medium">
                {t(T.section)}
                <Info>{t(T.sectionInfo)}</Info>
            </p>
            {erreur ? (
                <EtatVide cas="erreur" compact reessayer={() => void charger()} />
            ) : !reponse || !mode || !existant ? (
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-busy="true">
                    {[0, 1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-28 rounded-xl" />
                    ))}
                </div>
            ) : (
                <>
                    <div className="flex items-center gap-2">
                        <span className="inline-flex rounded-lg bg-muted p-0.5 text-sm" role="tablist">
                            {(["chaine", "temps-reel"] as const).map((m) => (
                                <button
                                    key={m}
                                    type="button"
                                    role="tab"
                                    aria-selected={mode === m}
                                    onClick={() => setMode(m)}
                                    className={`cursor-pointer rounded-md px-3 py-1 ${mode === m ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                                >
                                    {t(m === "chaine" ? T.chaine : T.tempsReel)}
                                </button>
                            ))}
                        </span>
                        <Info>{t(mode === "chaine" ? T.infoChaine : T.infoTempsReel)}</Info>
                    </div>
                    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="briques">
                        {BRIQUES_DU_MODE[mode].map((service) => {
                            const vue = vueDeLaBrique(existant, service);
                            const { nom, icone: Icone } = BRIQUES[service];
                            const n = remplacements[service] ?? 0;
                            return (
                                <button
                                    key={service}
                                    type="button"
                                    onClick={() => setOuverte(service)}
                                    data-brique={service}
                                    className="cursor-pointer rounded-xl border bg-card p-4 text-left transition-colors hover:border-foreground/40"
                                >
                                    <Icone className="mb-3 size-5 text-muted-foreground" aria-hidden />
                                    <p className="text-sm font-medium">{t(nom)}</p>
                                    {vue ? (
                                        <>
                                            <p className="text-xs text-muted-foreground">
                                                {[nomDu(vue.fournisseur), vue.modele].filter(Boolean).join(" · ")}
                                            </p>
                                            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                                                <KeyRound className="size-3" aria-hidden />
                                                {nomDeLaCle(vue)}
                                                {n > 0 && <span className="ml-auto">{t(remplacePar(n))}</span>}
                                            </p>
                                        </>
                                    ) : (
                                        <p className="text-xs text-muted-foreground">{t(T.nonRegle)}</p>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </>
            )}
            <div id="modeles-cles" className="pt-4">
                <TableauCles cles={cles} erreur={erreurCles} recharger={rechargerCles} onChange={() => void charger()} />
            </div>
            {ouverte && existant && defautsDuServeur && (
                <FenetreService
                    key={`${mode}-${ouverte}`}
                    service={ouverte}
                    portee="organisation"
                    segments={segments}
                    configurationDefaults={defautsDuServeur}
                    initialConfig={existant}
                    fermer={() => setOuverte(null)}
                    enregistrer={enregistrer}
                />
            )}
        </PageStudio>
    );
}
