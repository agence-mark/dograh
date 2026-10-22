"use client";

/**
 * [.mark] Chantier cloture-code-avant-migration, lot 6 : la section « Conservation des appels » du theme
 * « Donnees du client », a cote de la section « Conservation » existante (celle-ci regle les durees des tables
 * de la base du client ; celle-la, ce que Dograh garde de CHAQUE appel : verbatim, copies, audio).
 *
 * Les defauts sont ceux de .mark (decision d'Evan) et viennent du serveur : purge oui, 6 mois, audio non,
 * audio 6 mois s'il est enregistre, essai a blanc oui. L'essai a blanc compte ce que la tache de nuit effacerait
 * sans rien effacer ; le dernier passage s'affiche ici pour qu'on le lise avant de decocher l'essai.
 *
 * ⛔ Aucun texte sans champ reel : chaque ligne est un champ de `ReglagesConservationAppels`, ou le bilan du
 * dernier passage, ou l'etat du plafond de l'installation (`ENABLE_CALL_RECORDING_UPLOAD`).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
    getConservationDesAppelsApiV1OrganizationsConservationAppelsGet,
    putConservationDesAppelsApiV1OrganizationsConservationAppelsPut,
} from "@/client/sdk.gen";
import type { ReglagesConservationAppels, VueConservationAppels } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { type Texte, useLangue } from "../langue/langue";

export const MOIS_MIN = 1;
export const MOIS_MAX = 120;

/** Les champs reglables de la section, dans l'ordre d'affichage (un test les compare au client genere). */
export const CHAMPS_CONSERVATION_APPELS = [
    "purge_activee",
    "duree_mois",
    "audio_enregistre",
    "audio_duree_mois",
    "essai_a_blanc",
] as const;

const moisValide = (n: unknown) => Number.isInteger(n) && (n as number) >= MOIS_MIN && (n as number) <= MOIS_MAX;

export const useConservationAppels = () => {
    const { user, loading: authLoading } = useAuth();
    const [vue, setVue] = useState<VueConservationAppels | null>(null);
    const [brouillon, setBrouillon] = useState<ReglagesConservationAppels | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const dejaLu = useRef(false);

    const lire = useCallback(async () => {
        const reponse = await getConservationDesAppelsApiV1OrganizationsConservationAppelsGet();
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Call retention settings unreadable"));
            return;
        }
        if (!reponse.data) return;
        setErreur(null);
        setVue(reponse.data);
        setBrouillon(reponse.data.reglages);
    }, []);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void lire();
    }, [authLoading, user, lire]);

    const modifie = Boolean(vue && brouillon && JSON.stringify(brouillon) !== JSON.stringify(vue.reglages));
    const invalide = Boolean(brouillon && (!moisValide(brouillon.duree_mois) || !moisValide(brouillon.audio_duree_mois)));

    const enregistrer = async (succes: string) => {
        if (!brouillon || enCours) return;
        setEnCours(true);
        setErreur(null);
        try {
            const reponse = await putConservationDesAppelsApiV1OrganizationsConservationAppelsPut({ body: brouillon });
            if (reponse.error || !reponse.data) {
                setErreur(detailFromError(reponse.error, "Call retention settings refused"));
                return;
            }
            setVue(reponse.data);
            setBrouillon(reponse.data.reglages);
            toast.success(succes);
        } catch {
            setErreur("Call retention settings: the server did not answer");
        } finally {
            setEnCours(false);
        }
    };

    return { vue, brouillon, setBrouillon, erreur, enCours, modifie, invalide, enregistrer };
};

const TITRE_SECTION: Texte = { en: "Call retention", fr: "Conservation des appels" };

export const SectionConservationAppels = ({ etat }: { etat: ReturnType<typeof useConservationAppels> }) => {
    const { t, langue } = useLangue();
    const { vue, brouillon, setBrouillon, erreur, enCours, modifie, invalide, enregistrer } = etat;
    const poser = (partie: Partial<ReglagesConservationAppels>) =>
        setBrouillon((avant) => (avant ? { ...avant, ...partie } : avant));
    const passage = vue?.dernier_passage;

    return (
        <Intertitre
            id="donnees-conservation-appels"
            titre={TITRE_SECTION}
            description={{
                en: "What Dograh keeps of each call: the verbatim and the copies (transcript, logs, context, annotations), and the audio. A nightly task empties what is older than the durations below; the call's row (cost, duration, state) stays.",
                fr: "Ce que Dograh garde de chaque appel : le verbatim et les copies (transcription, journaux, contexte, annotations), et l'audio. Une tâche de nuit vide ce qui dépasse les durées ci-dessous ; la ligne de l'appel (coût, durée, état) reste.",
            }}
        >
            {erreur && (
                <p className="text-sm text-destructive" role="alert" data-testid="erreur-conservation-appels">
                    {erreur}
                </p>
            )}
            {!brouillon || !vue ? (
                <p className="text-sm text-muted-foreground">{t({ en: "Loading...", fr: "Chargement..." })}</p>
            ) : (
                <>
                    <ChampReglage
                        cle="purge_activee"
                        idControle="conservation-appels-purge"
                        libelle={{ en: "Empty the copies of old calls", fr: "Vider les copies des anciens appels" }}
                        disposition="ligne"
                    >
                        <Switch
                            id="conservation-appels-purge"
                            checked={brouillon.purge_activee ?? true}
                            onCheckedChange={(v) => poser({ purge_activee: v })}
                        />
                    </ChampReglage>
                    <ChampReglage
                        cle="duree_mois"
                        idControle="conservation-appels-duree"
                        libelle={{ en: "Months kept: verbatim and copies", fr: "Mois de conservation : verbatim et copies" }}
                        bornes={bornesDe(MOIS_MIN, MOIS_MAX)}
                        aides={[{ en: "A month counts 30 days.", fr: "Un mois compte 30 jours." }]}
                        erreur={
                            moisValide(brouillon.duree_mois)
                                ? null
                                : { en: `A whole number from ${MOIS_MIN} to ${MOIS_MAX}.`, fr: `Un nombre entier de ${MOIS_MIN} à ${MOIS_MAX}.` }
                        }
                    >
                        <Input
                            id="conservation-appels-duree"
                            type="number"
                            min={MOIS_MIN}
                            max={MOIS_MAX}
                            value={brouillon.duree_mois ?? ""}
                            onChange={(e) => poser({ duree_mois: Number(e.target.value) })}
                        />
                    </ChampReglage>
                    <ChampReglage
                        cle="audio_enregistre"
                        idControle="conservation-appels-audio"
                        libelle={{ en: "Record the audio of the calls", fr: "Enregistrer l'audio des appels" }}
                        disposition="ligne"
                        aides={
                            vue.audio_autorise_par_l_installation
                                ? []
                                : [
                                      {
                                          en: "This installation forbids recording the audio (ENABLE_CALL_RECORDING_UPLOAD is off): nobody can switch it on.",
                                          fr: "Cette installation interdit d'enregistrer l'audio (ENABLE_CALL_RECORDING_UPLOAD est coupée) : personne ne peut l'allumer.",
                                      },
                                  ]
                        }
                    >
                        <Switch
                            id="conservation-appels-audio"
                            checked={brouillon.audio_enregistre ?? false}
                            disabled={!vue.audio_autorise_par_l_installation && !vue.reglages.audio_enregistre}
                            onCheckedChange={(v) => poser({ audio_enregistre: v })}
                        />
                    </ChampReglage>
                    <ChampReglage
                        cle="audio_duree_mois"
                        idControle="conservation-appels-audio-duree"
                        libelle={{ en: "Months kept: audio", fr: "Mois de conservation : audio" }}
                        bornes={bornesDe(MOIS_MIN, MOIS_MAX)}
                        aides={[
                            {
                                en: "Also applies to the audio recorded before it was switched off.",
                                fr: "S'applique aussi à l'audio enregistré avant qu'il soit coupé.",
                            },
                        ]}
                        erreur={
                            moisValide(brouillon.audio_duree_mois)
                                ? null
                                : { en: `A whole number from ${MOIS_MIN} to ${MOIS_MAX}.`, fr: `Un nombre entier de ${MOIS_MIN} à ${MOIS_MAX}.` }
                        }
                    >
                        <Input
                            id="conservation-appels-audio-duree"
                            type="number"
                            min={MOIS_MIN}
                            max={MOIS_MAX}
                            value={brouillon.audio_duree_mois ?? ""}
                            onChange={(e) => poser({ audio_duree_mois: Number(e.target.value) })}
                        />
                    </ChampReglage>
                    <ChampReglage
                        cle="essai_a_blanc"
                        idControle="conservation-appels-blanc"
                        libelle={{ en: "Dry run", fr: "Essai à blanc" }}
                        disposition="ligne"
                        aides={[
                            {
                                en: "On: the nightly task counts what it would empty and empties nothing. Untick it once the count has been read.",
                                fr: "Coché : la tâche de nuit compte ce qu'elle viderait et ne vide rien. Décochez après avoir lu le compte.",
                            },
                        ]}
                    >
                        <Switch
                            id="conservation-appels-blanc"
                            checked={brouillon.essai_a_blanc ?? true}
                            onCheckedChange={(v) => poser({ essai_a_blanc: v })}
                        />
                    </ChampReglage>

                    {passage ? (
                        <p className="text-sm" data-testid="dernier-passage-conservation">
                            {t({ en: "Last passage:", fr: "Dernier passage :" })}{" "}
                            <strong>{new Date(passage.passe_le).toLocaleString(langue === "fr" ? "fr-FR" : "en-GB")}</strong>
                            {" · "}
                            {passage.a_blanc ? t({ en: "dry run", fr: "essai à blanc" }) : t({ en: "emptied", fr: "vidé" })}
                            {" · "}
                            {passage.runs_texte} {t({ en: "calls (copies)", fr: "appels (copies)" })}
                            {" · "}
                            {passage.runs_audio} {t({ en: "calls (audio)", fr: "appels (audio)" })}
                            {" · "}
                            {passage.objets} {t({ en: "files", fr: "fichiers" })}
                            {(passage.echecs ?? 0) > 0 && (
                                <span className="text-destructive">
                                    {" · "}
                                    {passage.echecs} {t({ en: "left for tomorrow", fr: "repris demain" })}
                                </span>
                            )}
                            {passage.incomplet && <span>{" · "}{t({ en: "stopped on its time limit", fr: "arrêté à sa limite de temps" })}</span>}
                        </p>
                    ) : (
                        <p className="text-sm text-muted-foreground" data-testid="aucun-passage-conservation">
                            {t({ en: "No passage yet: the task runs every night.", fr: "Aucun passage pour l'instant : la tâche tourne chaque nuit." })}
                        </p>
                    )}

                    <Button
                        size="sm"
                        data-testid="enregistrer-conservation-appels"
                        disabled={enCours || !modifie || invalide}
                        onClick={() => void enregistrer(t({ en: "Call retention saved", fr: "Conservation des appels enregistrée" }))}
                    >
                        {t({ en: "Save call retention", fr: "Enregistrer la conservation des appels" })}
                    </Button>
                </>
            )}
        </Intertitre>
    );
};
