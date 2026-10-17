"use client";

/**
 * [.mark] Chantier agents-specialises, lot 12 (A5, A6, A7, A10, A18) : les réglages d'un GROUPE
 * d'agents, portés par l'agent principal.
 *
 * - intertitre « Agents spécialisés » (thème 1, Agent) : la liste des spécialisés (lecture, un lien
 *   vers chacun), le préchauffage, la passation sans résumé jusqu'à N messages, un seul renvoi vers
 *   un humain par appel, le plafond de passations par appel ;
 * - intertitre « Attente » (thème 5, Voix) : le son, la durée minimale, où elle s'applique (passation
 *   entre agents, transfert vers un humain), la phrase pont.
 *
 * Aucun nouveau thème : ce sont deux intertitres des thèmes existants. Un réglage absent affiche le
 * défaut d'un groupe (préchauffage allumé, 40 messages, un seul renvoi, plafond 6) ; il n'est écrit
 * que quand la partie est modifiée (E6). Les clés sont lues par le moteur de l'appel sur les
 * réglages du principal (``api/services/groupe/reglages_passation.py``, lot 6).
 *
 * Chez un spécialisé, les mêmes intertitres s'affichent en lecture (« Réglé sur l'agent principal »).
 */
import { ExternalLink, Loader2, Upload, X } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { getAmbientNoiseUploadUrlApiV1WorkflowAmbientNoiseUploadUrlPost } from "@/client/sdk.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { AttenteDuGroupe, WorkflowConfigurations } from "@/types/workflow-configurations";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { type Texte, useLangue } from "../langue/langue";
import { ZoneCommune } from "./contexte-groupe";
import { useGroupe } from "./contexte-groupe";

/** Les défauts d'un groupe, tels que le moteur les applique (``reglages_passation.py``). */
export const DEFAUTS_GROUPE = {
    passations_max_par_appel: 6,
    passation_sans_resume_jusqua: 40,
    prechauffage_agents: true,
    un_seul_renvoi_par_appel: true,
} as const;

export const DUREE_MIN_ATTENTE_DEFAUT_S = 1.2;
export const DELAI_PHRASE_PONT_DEFAUT_S = 2;
const TAILLE_MAX_SON = 10 * 1024 * 1024; // 10 Mo, comme le bruit d'ambiance

/** L'agent est-il le principal d'un groupe ? (la liste ``agents_specialises`` existe, même vide) */
export const estPrincipal = (c: Partial<WorkflowConfigurations>) => Array.isArray(c.agents_specialises);
export const estSpecialise = (c: Partial<WorkflowConfigurations>) => typeof c.agent_principal_id === "number";

/**
 * Le schéma du parcours est-il généré d'office ? Oui pour un accueil (``agents_specialises`` NON vide) ou un
 * spécialisé : la case est alors ignorée par le code (``reglage_allume`` du serveur, même règle).
 */
export const groupeForceLeSchema = (c: Partial<WorkflowConfigurations>) =>
    (Array.isArray(c.agents_specialises) && c.agents_specialises.length > 0) || estSpecialise(c);

export const AIDE_SCHEMA_TOUJOURS_ACTIF: Texte = {
    en: "Always on in a group: the flow map is generated whatever this switch says.",
    fr: "Toujours actif dans un groupe : le schéma est généré quoi que dise cette case.",
};

export const CLES_GROUPE = [
    "prechauffage_agents",
    "passation_sans_resume_jusqua",
    "un_seul_renvoi_par_appel",
    "passations_max_par_appel",
] as const;

/** Les valeurs affichées de la partie « Agents spécialisés » : l'enregistré, ou le défaut du groupe. */
export const extraireGroupe = (c: Partial<WorkflowConfigurations>) => ({
    prechauffage_agents: c.prechauffage_agents ?? DEFAUTS_GROUPE.prechauffage_agents,
    passation_sans_resume_jusqua: c.passation_sans_resume_jusqua ?? DEFAUTS_GROUPE.passation_sans_resume_jusqua,
    un_seul_renvoi_par_appel: c.un_seul_renvoi_par_appel ?? DEFAUTS_GROUPE.un_seul_renvoi_par_appel,
    passations_max_par_appel: c.passations_max_par_appel ?? DEFAUTS_GROUPE.passations_max_par_appel,
});
export type ReglagesGroupe = ReturnType<typeof extraireGroupe>;

/** Les valeurs affichées de la partie « Attente ». ``son`` : null = la sonnerie par défaut. */
export const extraireAttente = (c: Partial<WorkflowConfigurations>) => {
    const a: AttenteDuGroupe = c.attente ?? {};
    return {
        son: a.son ?? null,
        duree_min_s: a.duree_min_s ?? null,
        passation: a.passation ?? true,
        transfert_humain: a.transfert_humain ?? true,
        phrase_pont: a.phrase_pont ?? "",
        delai_phrase_pont_s: a.delai_phrase_pont_s ?? null,
        // Carried by its own key, ``transfert_humain`` (see ``chargeTransfertHumain``).
        phrase_mise_en_relation: c.transfert_humain?.phrase_mise_en_relation ?? "",
    };
};
export type ReglagesAttente = ReturnType<typeof extraireAttente>;

/**
 * Ce que la partie « Attente » écrit sous ``transfert_humain`` : la phrase seulement si elle est posée ;
 * vidée après avoir été posée, l'objet vide la remplace (rien d'autre ne l'efface).
 */
export const chargeTransfertHumain = (a: ReglagesAttente, enregistree: ReglagesAttente) => {
    const phrase = a.phrase_mise_en_relation.trim();
    if (phrase !== "") return { phrase_mise_en_relation: phrase };
    return enregistree.phrase_mise_en_relation.trim() !== "" ? {} : undefined;
};

/** Ce que la partie « Attente » écrit : seulement ce qui s'écarte de « rien » (le réglage reste creux). */
export const chargeAttente = (a: ReglagesAttente): AttenteDuGroupe => ({
    ...(a.son !== null ? { son: a.son } : {}),
    ...(a.duree_min_s !== null ? { duree_min_s: a.duree_min_s } : {}),
    passation: a.passation,
    transfert_humain: a.transfert_humain,
    ...(a.phrase_pont.trim() !== "" ? { phrase_pont: a.phrase_pont.trim() } : {}),
    ...(a.delai_phrase_pont_s !== null ? { delai_phrase_pont_s: a.delai_phrase_pont_s } : {}),
});

const TEXTES = {
    titreSpecialises: { en: "Specialised agents", fr: "Agents spécialisés" },
    descriptionSpecialises: {
        en: "The group's agents, the pre-warming and the limits of the hand-overs between them.",
        fr: "Les agents du groupe, le préchauffage et les limites des passations entre eux.",
    },
    liste: { en: "The group's specialised agents", fr: "Les agents spécialisés du groupe" },
    listeAide: {
        en: "Read only. Add one from the group's view in the agent list; each one is also created with its hand-over tool on the main agent.",
        fr: "En lecture. On en ajoute depuis la vue du groupe dans la liste d'agents ; chacun est créé avec son outil de passation chez le principal.",
    },
    aucunSpecialise: { en: "No specialised agent yet.", fr: "Aucun agent spécialisé pour l'instant." },
    cerveauPropre: { en: "own brain", fr: "cerveau propre" },
    prechauffage: { en: "Pre-warm the specialised agents at pick-up", fr: "Préchauffer les agents spécialisés au décroché" },
    prechauffageAide: {
        en: "Loads each agent's definition and tools ahead of time, so a hand-over costs little. The call has one voice, open from the start: no voice opens at a hand-over. On by default in a group.",
        fr: "Charge à l'avance la définition et les outils de chaque agent : une passation coûte peu. L'appel n'a qu'une voix, ouverte dès le début : aucune voix ne s'ouvre à la passation. Allumé par défaut dans un groupe.",
    },
    sansResume: { en: "Hand over the history without a summary up to (messages)", fr: "Passer l'historique sans résumé jusqu'à (messages)" },
    sansResumeAide: {
        en: "The next agent receives the last messages of the conversation, up to this number, and the hand-over note written by the code: no summary is ever written by a model. 0: a summary written by the model, as before. Default 40.",
        fr: "L'agent suivant reçoit les derniers messages de la conversation, jusqu'à ce nombre, et la note de passation écrite par le code : aucun résumé n'est jamais rédigé par un modèle. 0 : un résumé rédigé par le modèle, comme avant. Défaut 40.",
    },
    filetDeFin: { en: "End-of-call safety net", fr: "Filet de fin d'appel" },
    filetDeFinAide: {
        en: "When a specialised agent says a closing phrase (\"goodbye\", \"have a nice day\") and takes no exit, the code takes the exit that hands the call back to the main agent, which closes the call. The phrases are the \"Recognised closing phrases\" of the sentence catalogue. Off, nothing is done.",
        fr: "Quand un agent spécialisé dit une formule de fin (« au revoir », « bonne journée ») sans prendre de sortie, le code prend la sortie qui rend la main à l'agent principal, lequel clôt l'appel. Les formules sont les « Formules de fin reconnues » du catalogue de phrases. Éteint, rien n'est fait.",
    },
    unSeulRenvoi: { en: "One transfer to a person per call", fr: "Un seul renvoi vers un humain par appel" },
    unSeulRenvoiAide: {
        en: "After a failed transfer to a person, no other agent tries again: it goes on with the request and says its failure sentence. On by default in a group.",
        fr: "Après un transfert vers un humain échoué, aucun autre agent ne retente : il poursuit la demande avec sa phrase d'échec. Allumé par défaut dans un groupe.",
    },
    plafond: { en: "Hand-overs allowed per call", fr: "Passations autorisées par appel" },
    plafondAide: {
        en: "Past this limit the main agent takes the request itself. Never a hand-over to oneself. Default 6 (three subjects handled with their returns).",
        fr: "Au-delà, le principal prend la demande lui-même. Jamais de passation vers soi-même. Défaut 6 (trois motifs traités avec leurs retours).",
    },
    titreAttente: { en: "Waiting", fr: "Attente" },
    descriptionAttente: {
        en: "The sound played while the call is handed over, and where it applies.",
        fr: "Le son joué pendant qu'on passe l'appel, et où il s'applique.",
    },
    attenteNote: {
        en: "Towards an agent that is already built (pre-warmed, or the main agent kept warm) no waiting is played: only the first word of the target model is awaited. The sound plays only when the agent still has to be built.",
        fr: "Vers un agent déjà construit (préchauffé, ou le principal resté chaud), aucune attente n'est jouée : seul le premier mot du modèle cible est attendu. Le son ne joue que si l'agent doit encore être construit.",
    },
    son: { en: "Waiting sound", fr: "Son d'attente" },
    sonAide: {
        en: "Upload your own file, switch the sound off, or keep the default ringer.",
        fr: "Envoyez votre fichier, coupez le son, ou gardez la sonnerie par défaut.",
    },
    sonDefaut: { en: "Default ringer", fr: "Sonnerie par défaut" },
    sonAucun: { en: "No sound", fr: "Aucun son" },
    sonFichier: { en: "Own file", fr: "Fichier" },
    sonEnvoyer: { en: "Upload a sound", fr: "Envoyer un son" },
    sonRetirer: { en: "Remove the sound", fr: "Retirer le son" },
    sonTropLourd: { en: "File too large. Maximum 10 MB.", fr: "Fichier trop lourd. Maximum 10 Mo." },
    sonEchec: { en: "The upload failed.", fr: "L'envoi a échoué." },
    dureeMin: { en: "Minimum waiting time (seconds)", fr: "Durée minimale d'attente (secondes)" },
    dureeMinAide: {
        en: "A waiting sound is never cut before this. Empty: 1.2 s, as today.",
        fr: "Le son d'attente n'est jamais coupé avant. Vide : 1,2 s, comme aujourd'hui.",
    },
    attentePassation: { en: "Hand-over between agents", fr: "Passation entre agents" },
    attentePassationAide: {
        en: "Plays the sound when the next agent still has to be built.",
        fr: "Joue le son quand l'agent suivant doit encore être construit.",
    },
    attenteHumain: { en: "Transfer to a person", fr: "Transfert vers un humain" },
    attenteHumainAide: {
        en: "Plays the sound while the call is passed to a person's phone.",
        fr: "Joue le son pendant que l'appel est passé sur le téléphone d'une personne.",
    },
    phrasePont: { en: "Bridge phrase", fr: "Phrase pont" },
    phrasePontAide: {
        en: "Optional. A short sentence said by the call's voice, only if the hand-over lasts longer than the delay below: a safety net, not the solution. The agent handing over is not woken up to say it. Never said by a keyboard test, nor towards an agent already built. Empty: none.",
        fr: "Facultative. Une phrase courte dite par la voix de l'appel, seulement si la passation dure plus que le délai ci-dessous : un filet, pas la solution. L'agent qui passe la main n'est pas réveillé pour la dire. Jamais dite au clavier, ni vers un agent déjà construit. Vide : aucune.",
    },
    phraseMiseEnRelation: { en: "Hand-over sentence to a person", fr: "Phrase de mise en relation" },
    phraseMiseEnRelationAide: {
        en: "Optional. When a called agent arrives on a step that transfers the call to a person and the business is open, the code says this sentence itself, with the call's voice, then starts the transfer: the model is not asked for a reply. Empty: the model speaks, as before. If the transfer tool has its own message, that message is said instead. Never said by a keyboard test.",
        fr: "Facultative. Quand un agent appelé arrive sur une étape qui transfère l'appel vers une personne, entreprise ouverte, le code dit lui-même cette phrase, avec la voix de l'appel, puis lance le transfert : le modèle n'est pas sollicité. Vide : le modèle parle, comme avant. Si l'outil de transfert porte son propre message, c'est lui qui est dit. Jamais dite au clavier.",
    },
    delaiPhrasePont: { en: "Bridge phrase delay (seconds)", fr: "Délai de la phrase pont (secondes)" },
    delaiPhrasePontAide: {
        en: "The phrase is said once, if the hand-over is not done after this delay. Empty: 2 s.",
        fr: "La phrase est dite une fois, si la passation n'est pas faite après ce délai. Vide : 2 s.",
    },
} satisfies Record<string, Texte>;

export const TITRE_AGENTS_SPECIALISES = TEXTES.titreSpecialises;
export const TITRE_ATTENTE = TEXTES.titreAttente;

/** Lit un entier positif ou nul : ``undefined`` quand ce n'est pas un entier acceptable. */
const entier = (brut: string): number | undefined => {
    if (!/^\d+$/.test(brut.trim())) return undefined;
    const n = Number(brut);
    return Number.isSafeInteger(n) ? n : undefined;
};

export const IntertitreAgentsSpecialises = ({
    valeurs,
    onChange,
    filet = false,
    onFiletChange = () => undefined,
}: {
    valeurs: ReglagesGroupe;
    onChange: <K extends keyof ReglagesGroupe>(cle: K, valeur: ReglagesGroupe[K]) => void;
    /** Lot 2 d'orchestrateur-trois-cerveaux (B2): « End-of-call safety net », sa propre partie à l'enregistrement. */
    filet?: boolean;
    onFiletChange?: (coche: boolean) => void;
}) => {
    const { t } = useLangue();
    const { membres } = useGroupe();
    return (
        <Intertitre id="agent-agents-specialises" titre={TEXTES.titreSpecialises} description={TEXTES.descriptionSpecialises}>
            <ChampReglage cle="agents_specialises" libelle={TEXTES.liste} aides={[TEXTES.listeAide]}>
                {membres.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t(TEXTES.aucunSpecialise)}</p>
                ) : (
                    <ul className="space-y-1" data-liste="agents-specialises">
                        {membres.map((membre) => (
                            <li key={membre.id} className="flex items-center gap-2 text-sm">
                                <Link href={`/workflow/${membre.id}`} className="inline-flex items-center gap-1 underline">
                                    {membre.name}
                                    <ExternalLink className="h-3 w-3" aria-hidden />
                                </Link>
                                {membre.cerveau_propre && (
                                    <span className="rounded-md border bg-muted/40 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                                        {t(TEXTES.cerveauPropre)}
                                    </span>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </ChampReglage>
            <ChampReglage cle="prechauffage_agents" idControle="prechauffage_agents" libelle={TEXTES.prechauffage} aides={[TEXTES.prechauffageAide]} disposition="ligne">
                <Switch
                    id="prechauffage_agents"
                    checked={valeurs.prechauffage_agents}
                    onCheckedChange={(coche) => onChange("prechauffage_agents", coche)}
                />
            </ChampReglage>
            <ChampReglage
                cle="passation_sans_resume_jusqua"
                idControle="passation_sans_resume_jusqua"
                libelle={TEXTES.sansResume}
                aides={[TEXTES.sansResumeAide]}
                bornes={bornesDe(0)}
            >
                <Input
                    id="passation_sans_resume_jusqua"
                    type="number"
                    min="0"
                    step="1"
                    value={valeurs.passation_sans_resume_jusqua}
                    onChange={(e) => {
                        const n = entier(e.target.value);
                        if (n !== undefined) onChange("passation_sans_resume_jusqua", n);
                    }}
                />
            </ChampReglage>
            <ChampReglage
                cle="un_seul_renvoi_par_appel"
                idControle="un_seul_renvoi_par_appel"
                libelle={TEXTES.unSeulRenvoi}
                aides={[TEXTES.unSeulRenvoiAide]}
                disposition="ligne"
            >
                <Switch
                    id="un_seul_renvoi_par_appel"
                    checked={valeurs.un_seul_renvoi_par_appel}
                    onCheckedChange={(coche) => onChange("un_seul_renvoi_par_appel", coche)}
                />
            </ChampReglage>
            <ChampReglage
                cle="passations_max_par_appel"
                idControle="passations_max_par_appel"
                libelle={TEXTES.plafond}
                aides={[TEXTES.plafondAide]}
                bornes={bornesDe(0)}
            >
                <Input
                    id="passations_max_par_appel"
                    type="number"
                    min="0"
                    step="1"
                    value={valeurs.passations_max_par_appel}
                    onChange={(e) => {
                        const n = entier(e.target.value);
                        if (n !== undefined) onChange("passations_max_par_appel", n);
                    }}
                />
            </ChampReglage>
            <ChampReglage
                cle="filet_de_fin"
                idControle="filet_de_fin"
                libelle={TEXTES.filetDeFin}
                aides={[TEXTES.filetDeFinAide]}
                bornes={{ en: "Default: off", fr: "Par défaut : éteint" }}
                disposition="ligne"
            >
                <Switch id="filet_de_fin" checked={filet} onCheckedChange={onFiletChange} />
            </ChampReglage>
        </Intertitre>
    );
};

export const IntertitreAttente = ({
    valeurs,
    onChange,
    workflowId,
}: {
    valeurs: ReglagesAttente;
    onChange: <K extends keyof ReglagesAttente>(cle: K, valeur: ReglagesAttente[K]) => void;
    workflowId: number;
}) => {
    const { t } = useLangue();
    const entree = useRef<HTMLInputElement>(null);
    const [envoi, setEnvoi] = useState(false);
    const [erreurSon, setErreurSon] = useState<Texte | null>(null);
    const fichier = valeurs.son !== null && valeurs.son !== "aucun" ? valeurs.son : null;
    const choix: "defaut" | "aucun" | "fichier" = valeurs.son === "aucun" ? "aucun" : fichier ? "fichier" : "defaut";

    // Le dépôt de Dograh pour le bruit d'ambiance : une adresse signée, le fichier, la référence.
    const deposer = async (f: File) => {
        if (f.size > TAILLE_MAX_SON) {
            setErreurSon(TEXTES.sonTropLourd);
            return;
        }
        setEnvoi(true);
        setErreurSon(null);
        try {
            const res = await getAmbientNoiseUploadUrlApiV1WorkflowAmbientNoiseUploadUrlPost({
                body: { workflow_id: Number(workflowId), filename: f.name, mime_type: f.type || "audio/wav", file_size: f.size },
            });
            if (res.error || !res.data?.upload_url) throw new Error("upload url");
            const envoye = await fetch(res.data.upload_url, {
                method: "PUT",
                body: f,
                headers: { "Content-Type": f.type || "audio/wav" },
            });
            if (!envoye.ok) throw new Error("upload");
            onChange("son", {
                storage_key: res.data.storage_key,
                storage_backend: res.data.storage_backend,
                original_filename: f.name,
            });
        } catch {
            setErreurSon(TEXTES.sonEchec);
        } finally {
            setEnvoi(false);
            if (entree.current) entree.current.value = "";
        }
    };

    return (
        <Intertitre id="voix-attente" titre={TEXTES.titreAttente} description={TEXTES.descriptionAttente}>
            <p className="text-xs text-muted-foreground" data-note="attente-agent-construit">
                {t(TEXTES.attenteNote)}
            </p>
            <ChampReglage cle="attente.son" libelle={TEXTES.son} aides={[TEXTES.sonAide]}>
                <div className="space-y-2">
                    <div role="radiogroup" aria-label={t(TEXTES.son)} className="flex flex-wrap gap-4 text-sm">
                        {(
                            [
                                ["defaut", TEXTES.sonDefaut],
                                ["aucun", TEXTES.sonAucun],
                                ["fichier", TEXTES.sonFichier],
                            ] as const
                        ).map(([valeur, libelle]) => (
                            <label key={valeur} className="flex items-center gap-2">
                                <input
                                    type="radio"
                                    name="attente-son"
                                    checked={choix === valeur}
                                    onChange={() => {
                                        if (valeur === "defaut") onChange("son", null);
                                        else if (valeur === "aucun") onChange("son", "aucun");
                                        else entree.current?.click();
                                    }}
                                />
                                {t(libelle)}
                            </label>
                        ))}
                    </div>
                    <input
                        ref={entree}
                        type="file"
                        accept="audio/*"
                        className="hidden"
                        aria-label={t(TEXTES.sonEnvoyer)}
                        onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f) void deposer(f);
                        }}
                    />
                    {fichier && (
                        <div className="flex items-center gap-2 rounded-md border bg-muted/10 p-2">
                            <code className="flex-1 truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                                {fichier.original_filename ?? fichier.storage_key}
                            </code>
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="h-6 w-6 shrink-0 p-0"
                                aria-label={t(TEXTES.sonRetirer)}
                                onClick={() => onChange("son", null)}
                            >
                                <X className="h-3.5 w-3.5" />
                            </Button>
                        </div>
                    )}
                    {choix !== "fichier" && (
                        <Button type="button" variant="outline" size="sm" disabled={envoi} onClick={() => entree.current?.click()}>
                            {envoi ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Upload className="mr-2 h-3.5 w-3.5" />}
                            {t(TEXTES.sonEnvoyer)}
                        </Button>
                    )}
                    {erreurSon && <p className="text-xs text-destructive">{t(erreurSon)}</p>}
                </div>
            </ChampReglage>
            <ChampReglage
                cle="attente.duree_min_s"
                idControle="attente_duree_min_s"
                libelle={TEXTES.dureeMin}
                aides={[TEXTES.dureeMinAide]}
                bornes={bornesDe(0)}
            >
                <Input
                    id="attente_duree_min_s"
                    type="number"
                    min="0"
                    step="0.1"
                    placeholder={String(DUREE_MIN_ATTENTE_DEFAUT_S)}
                    value={valeurs.duree_min_s ?? ""}
                    onChange={(e) => {
                        if (e.target.value === "") {
                            onChange("duree_min_s", null);
                            return;
                        }
                        const n = Number(e.target.value);
                        if (Number.isFinite(n) && n >= 0) onChange("duree_min_s", n);
                    }}
                />
            </ChampReglage>
            <ChampReglage cle="attente.passation" idControle="attente_passation" libelle={TEXTES.attentePassation} aides={[TEXTES.attentePassationAide]} disposition="ligne">
                <Switch id="attente_passation" checked={valeurs.passation} onCheckedChange={(coche) => onChange("passation", coche)} />
            </ChampReglage>
            <ChampReglage cle="attente.transfert_humain" idControle="attente_transfert_humain" libelle={TEXTES.attenteHumain} aides={[TEXTES.attenteHumainAide]} disposition="ligne">
                <Switch id="attente_transfert_humain" checked={valeurs.transfert_humain} onCheckedChange={(coche) => onChange("transfert_humain", coche)} />
            </ChampReglage>
            <ChampReglage
                cle="transfert_humain.phrase_mise_en_relation"
                idControle="attente_phrase_mise_en_relation"
                libelle={TEXTES.phraseMiseEnRelation}
                aides={[TEXTES.phraseMiseEnRelationAide]}
            >
                <Input
                    id="attente_phrase_mise_en_relation"
                    value={valeurs.phrase_mise_en_relation}
                    onChange={(e) => onChange("phrase_mise_en_relation", e.target.value)}
                />
            </ChampReglage>
            <ChampReglage cle="attente.phrase_pont" idControle="attente_phrase_pont" libelle={TEXTES.phrasePont} aides={[TEXTES.phrasePontAide]}>
                <Input
                    id="attente_phrase_pont"
                    maxLength={300}
                    value={valeurs.phrase_pont}
                    onChange={(e) => onChange("phrase_pont", e.target.value)}
                />
            </ChampReglage>
            <ChampReglage
                cle="attente.delai_phrase_pont_s"
                idControle="attente_delai_phrase_pont_s"
                libelle={TEXTES.delaiPhrasePont}
                aides={[TEXTES.delaiPhrasePontAide]}
                bornes={bornesDe(0)}
            >
                <Input
                    id="attente_delai_phrase_pont_s"
                    type="number"
                    min="0"
                    step="0.1"
                    placeholder={String(DELAI_PHRASE_PONT_DEFAUT_S)}
                    value={valeurs.delai_phrase_pont_s ?? ""}
                    onChange={(e) => {
                        if (e.target.value === "") {
                            onChange("delai_phrase_pont_s", null);
                            return;
                        }
                        const n = Number(e.target.value);
                        if (Number.isFinite(n) && n >= 0) onChange("delai_phrase_pont_s", n);
                    }}
                />
            </ChampReglage>
        </Intertitre>
    );
};

/** Les deux intertitres, en lecture, quand l'agent est un spécialisé (réglés sur le principal). */
export const EnLecture = ({ children }: { children: React.ReactNode }) => <ZoneCommune lecture>{children}</ZoneCommune>;
