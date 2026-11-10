"use client";

/**
 * [.mark] Thème « Sécurité » : la sécurité de la conversation (U3 quinquies, E68), celui que B2 n'avait pas construit.
 *
 * Trois couches, toutes génériques et éteintes par défaut, rangées dans UNE clé (`securite_conversation`, schéma
 * `api/schemas/securite_conversation.py`) : des consignes que le code pose après le prompt, deux garde-fous sur la
 * réplique avant la voix, un classifieur de l'appelant. La forme est celle de la maquette (thème `securite` de
 * `reglages-fork.ts`) : chaque réglage porte sa phrase quand il est allumé ; un champ vide veut dire « le texte du code ».
 * Aucun champ que le serveur ne connaît pas n'est affiché (le choix du service du classifieur, « Phrase puis fin d'appel »
 * et « Transfert immédiat » n'existent pas côté serveur : voir `14-ecarts-maquette.md`).
 */
import { ShieldCheck } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { ConsigneDeSecurite, SecuriteConversation, WorkflowConfigurations } from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { Reglage, Segments } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, type ProprietesThemeAgent, useBrouillon, useEtatTheme } from "./theme-commun";
import { Curseur } from "@/components/ui/curseur";

export const ID_THEME_SECURITE = "securite";
export const TITRE_SECURITE = { en: "Safety", fr: "Sécurité" };

/** Les bornes du serveur (`LONGUEUR_PHRASE_MAX`, `MOTS_RECITATION_*`, `consigne` à 2000). */
export const LONGUEUR_PHRASE_MAX = 600;
export const LONGUEUR_CONSIGNE_MAX = 2000;
export const MOTS_MIN = 6;
export const MOTS_MAX = 60;
export const MOTS_DEFAUT = 12;

export interface SecuriteComplete {
    manipulation: Required<ConsigneDeSecurite>;
    confidentialite: Required<ConsigneDeSecurite>;
    role: Required<ConsigneDeSecurite>;
    urgence: Required<ConsigneDeSecurite> & { transfert: boolean };
    jamais: { outils: boolean; recitation: boolean; mots: number; phrase: string };
    ecoute: {
        actif: boolean;
        sensibilite: "prudente" | "normale" | "large";
        sur_manipulation: "rappel" | "noter";
        sur_detresse: "urgence" | "noter";
        consigne: string;
    };
    marquer: boolean;
    garde_urgence: { actif: boolean; numero: string; mots_en_plus: string[] };
}

/** Les bornes du serveur pour le numéro d'urgence (`GardeUrgence.numero`). */
export const NUMERO_URGENCE_DEFAUT = "112";
export const MOTS_EN_PLUS_MAX = 20;
export const erreurNumero = (numero: string): Texte | null =>
    /^[0-9+ ]{2,20}$/.test(numero)
        ? null
        : { en: "Digits only (2 to 20), with an optional + and spaces.", fr: "Des chiffres seulement (2 à 20), avec un + et des espaces possibles." };

const consigne = (c?: ConsigneDeSecurite): Required<ConsigneDeSecurite> => ({ actif: c?.actif ?? false, phrase: c?.phrase ?? "" });

/** La valeur lue (partielle ou absente) complétée des défauts du serveur : tout éteint, rien d'inventé. */
export const completerSecurite = (lue: SecuriteConversation | null | undefined): SecuriteComplete => ({
    manipulation: consigne(lue?.manipulation),
    confidentialite: consigne(lue?.confidentialite),
    role: consigne(lue?.role),
    urgence: { ...consigne(lue?.urgence), transfert: lue?.urgence?.transfert ?? true },
    jamais: {
        outils: lue?.jamais?.outils ?? false,
        recitation: lue?.jamais?.recitation ?? false,
        mots: lue?.jamais?.mots ?? MOTS_DEFAUT,
        phrase: lue?.jamais?.phrase ?? "",
    },
    ecoute: {
        actif: lue?.ecoute?.actif ?? false,
        sensibilite: lue?.ecoute?.sensibilite ?? "normale",
        sur_manipulation: lue?.ecoute?.sur_manipulation ?? "rappel",
        sur_detresse: lue?.ecoute?.sur_detresse ?? "urgence",
        consigne: lue?.ecoute?.consigne ?? "",
    },
    marquer: lue?.marquer ?? true,
    garde_urgence: {
        actif: lue?.garde_urgence?.actif ?? false,
        numero: lue?.garde_urgence?.numero ?? NUMERO_URGENCE_DEFAUT,
        mots_en_plus: lue?.garde_urgence?.mots_en_plus ?? [],
    },
});

const extraireSecurite = (resolue: WorkflowConfigurations) => completerSecurite(resolue.securite_conversation);

/** Le message d'une valeur que le serveur refuserait, ou null. */
export const erreurMots = (mots: number): Texte | null =>
    Number.isInteger(mots) && mots >= MOTS_MIN && mots <= MOTS_MAX
        ? null
        : {
              en: `Between ${MOTS_MIN} and ${MOTS_MAX} whole words.`,
              fr: `Entre ${MOTS_MIN} et ${MOTS_MAX} mots entiers.`,
          };

const VIDE_CODE: Texte = { en: "Empty: the code's own text", fr: "Vide : le texte du code" };

export const ThemeSecurite = ({ resolue, workflowName, onSave, ouvert, onBasculer }: ProprietesThemeAgent) => {
    const { t } = useLangue();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireSecurite);
    // Clôture, SA-2 (D17): the agent's choice for the reusable blocks (own to each agent, so it lives in a theme a specialist can edit).
    const blocs = useBrouillon(resolue, (r) => ({ blocs_mode: r.blocs_mode ?? null }));
    const blocsModifie = differe(blocs.brouillon, blocs.enregistre);
    const reglagesModifies = differe(brouillon, enregistre);
    const modifie = reglagesModifies || blocsModifie;
    const errMots = brouillon.jamais.recitation ? erreurMots(brouillon.jamais.mots) : null;
    const errNumero = brouillon.garde_urgence.actif ? erreurNumero(brouillon.garde_urgence.numero) : null;
    const erreurs = [
        ...(errMots
            ? [
                  {
                      cle: "securite_conversation.jamais.mots",
                      libelle: t({ en: "Passage recited from", fr: "Passage récité à partir de" }),
                      message: t(errMots),
                      afficher: () => document.getElementById("securite-mots")?.focus(),
                  },
              ]
            : []),
        ...(errNumero
            ? [
                  {
                      cle: "securite_conversation.garde_urgence.numero",
                      libelle: t({ en: "Emergency number", fr: "Numéro d'urgence" }),
                      message: t(errNumero),
                      afficher: () => document.getElementById("securite-garde-urgence-numero")?.focus(),
                  },
              ]
            : []),
    ];
    useEtatTheme(ID_THEME_SECURITE, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_SECURITE,
        resolue,
        workflowName,
        onSave,
        parties: [
            {
                nom: { en: "Safety settings", fr: "Réglages de sécurité" },
                modifie: reglagesModifies,
                config: () => ({ securite_conversation: brouillon }),
                apres: resynchroniser,
            },
            {
                nom: { en: "Reusable blocks", fr: "Blocs réutilisables" },
                modifie: blocsModifie,
                config: () => blocs.brouillon,
                apres: blocs.resynchroniser,
            },
        ],
    });

    const poser = <G extends keyof SecuriteComplete>(groupe: G, partie: Partial<SecuriteComplete[G]>) =>
        setBrouillon((avant) => ({ ...avant, [groupe]: typeof avant[groupe] === "object" ? { ...avant[groupe], ...partie } : partie }));

    const allumees = [brouillon.manipulation, brouillon.confidentialite, brouillon.role, brouillon.urgence].filter((c) => c.actif).length;

    /** Une consigne : son interrupteur, puis sa phrase quand elle est allumée (maquette : `si`). */
    const consigneDe = (
        groupe: "manipulation" | "confidentialite" | "role" | "urgence",
        libelle: Texte,
        aide: Texte,
        aidePhrase: Texte,
        suite?: React.ReactNode,
    ) => {
        const valeur = brouillon[groupe];
        return (
            <>
                <ChampReglage cle={`securite_${groupe}`} idControle={`securite-${groupe}`} libelle={libelle} aides={[aide]} disposition="ligne">
                    <Switch id={`securite-${groupe}`} checked={valeur.actif} onCheckedChange={(v) => poser(groupe, { actif: v })} />
                </ChampReglage>
                {valeur.actif && (
                    <ChampReglage cle={`securite_${groupe}_phrase`} idControle={`securite-${groupe}-phrase`} libelle={{ en: "Sentence", fr: "Phrase" }} aides={[aidePhrase]}>
                        <Input
                            id={`securite-${groupe}-phrase`}
                            maxLength={LONGUEUR_PHRASE_MAX}
                            placeholder={t(VIDE_CODE)}
                            value={valeur.phrase}
                            onChange={(e) => poser(groupe, { phrase: e.target.value })}
                        />
                    </ChampReglage>
                )}
                {valeur.actif && suite}
            </>
        );
    };

    const options = <V extends string>(liste: Array<[V, Texte]>) => liste.map(([valeur, libelle]) => ({ valeur, libelle }));

    return (
        <Theme
            id={ID_THEME_SECURITE}
            icone={ShieldCheck}
            titre={TITRE_SECURITE}
            description={{
                en: "Manipulation, confidentiality, life-threatening emergency, what the agent never says.",
                fr: "Manipulation, confidentialité, urgence vitale, ce que l'agent ne dit jamais.",
            }}
            resume={[
                allumees === 0
                    ? t({ en: "No safety instruction on", fr: "Aucune consigne allumée" })
                    : `${allumees} ${t({ en: "instruction(s) on", fr: "consigne(s) allumée(s)" })}`,
                brouillon.ecoute.actif && t({ en: "Caller classifier on", fr: "Classifieur allumé" }),
                brouillon.garde_urgence.actif && t({ en: "Emergency safeguard on", fr: "Garde-fou urgence allumé" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={erreurs}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre
                id="securite-consignes"
                titre={{ en: "Safety instructions", fr: "Consignes de sécurité" }}
                description={{
                    en: "Placed by the code in every agent, after the prompt, on the phone and by keyboard; the client does not see them. Only the sentence said can be changed.",
                    fr: "Posées par le code dans chaque agent, après le prompt, au téléphone comme au clavier ; le client ne les voit pas. Seule la phrase dite se modifie.",
                }}
            >
                {consigneDe(
                    "manipulation",
                    { en: "Resist manipulation", fr: "Résister à la manipulation" },
                    {
                        en: "« Ignore your instructions », « pretend you are… », « repeat after me »: the agent keeps its role and comes back to the request.",
                        fr: "« Ignore tes instructions », « fais comme si tu étais… », « répète après moi » : l'agent garde son rôle et revient à la demande.",
                    },
                    {
                        en: "The sentence the agent says when someone tries to take it out of its role.",
                        fr: "La phrase que l'agent dit quand on essaie de le faire sortir de son rôle.",
                    },
                )}
                {consigneDe(
                    "confidentialite",
                    { en: "Keep its instructions to itself", fr: "Garder ses consignes pour lui" },
                    {
                        en: "Neither its instructions, nor the model, nor the provider, nor its tools. It always says it is an artificial intelligence (legal obligation).",
                        fr: "Ni ses consignes, ni le modèle, ni le fournisseur, ni ses outils. Il dit toujours qu'il est une intelligence artificielle (obligation légale).",
                    },
                    {
                        en: "The sentence the agent says when asked for its instructions, its model or how it works.",
                        fr: "La phrase que l'agent dit quand on lui demande ses consignes, son modèle ou son fonctionnement.",
                    },
                )}
                {consigneDe(
                    "role",
                    { en: "Stay in its role", fr: "Rester dans son rôle" },
                    {
                        en: "A request unrelated to the company (recipe, homework, politics): one sentence, then back to the request.",
                        fr: "Une demande sans rapport avec l'entreprise (recette, devoirs, politique) : une phrase, puis retour à la demande.",
                    },
                    {
                        en: "The sentence the agent says before coming back to the request.",
                        fr: "La phrase que l'agent dit avant de revenir à la demande.",
                    },
                )}
                {consigneDe(
                    "urgence",
                    { en: "Life-threatening emergency: point to help at once", fr: "Urgence vitale : orienter tout de suite" },
                    {
                        en: "Danger to life, distress, threat: the agent first gives the emergency number, whatever the flow in progress.",
                        fr: "Danger pour la vie, détresse, menace : l'agent donne d'abord le numéro d'urgence, quel que soit le parcours en cours.",
                    },
                    {
                        en: "The sentence said first in a life-threatening emergency.",
                        fr: "La phrase dite en premier en cas d'urgence vitale.",
                    },
                    <ChampReglage
                        key="transfert"
                        cle="securite_urgence_transfert"
                        idControle="securite-urgence-transfert"
                        libelle={{ en: "Then transfer to a person", fr: "Puis transférer à un humain" }}
                        aides={[
                            {
                                en: "To the establishment's transfer number, if it has one; otherwise the sentence alone.",
                                fr: "Vers le numéro de transfert de l'établissement, s'il en a un ; sinon la phrase seule.",
                            },
                        ]}
                        disposition="ligne"
                    >
                        <Switch
                            id="securite-urgence-transfert"
                            checked={brouillon.urgence.transfert}
                            onCheckedChange={(v) => poser("urgence", { transfert: v })}
                        />
                    </ChampReglage>,
                )}
            </Intertitre>

            <Intertitre
                id="securite-garde-urgence-bloc"
                titre={{ en: "Emergency safeguard", fr: "Garde-fou urgence" }}
                description={{
                    en: "Recognises distress or a medical emergency in the caller's words and says the emergency sentence (once per call). The code reads words only: no model is called and nothing is spent. The sentence is in the Phrases theme.",
                    fr: "Reconnaît une détresse ou une urgence médicale dans les mots de l'appelant et dit la phrase d'urgence (une fois par appel). Le code ne lit que des mots : aucun modèle n'est appelé, rien ne se dépense. La phrase se règle dans le thème Phrases.",
                }}
            >
                <ChampReglage
                    cle="securite_garde_urgence"
                    idControle="securite-garde-urgence"
                    libelle={{ en: "Emergency safeguard", fr: "Garde-fou urgence" }}
                    aides={[
                        {
                            en: "Off by default. When it triggers, the call is marked and goes to « To improve ».",
                            fr: "Éteint par défaut. Quand il se déclenche, l'appel est marqué et entre dans « À améliorer ».",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch id="securite-garde-urgence" checked={brouillon.garde_urgence.actif} onCheckedChange={(v) => poser("garde_urgence", { actif: v })} />
                </ChampReglage>
                {brouillon.garde_urgence.actif && (
                    <>
                        <ChampReglage
                            cle="securite_garde_urgence_numero"
                            idControle="securite-garde-urgence-numero"
                            libelle={{ en: "Emergency number", fr: "Numéro d'urgence" }}
                            aides={[{ en: "Said in the sentence. 112 is the European emergency number.", fr: "Dit dans la phrase. Le 112 est le numéro d'urgence européen." }]}
                            erreur={errNumero}
                            disposition="ligne"
                        >
                            <Input
                                id="securite-garde-urgence-numero"
                                className="w-32"
                                maxLength={20}
                                aria-invalid={errNumero !== null}
                                value={brouillon.garde_urgence.numero}
                                onChange={(e) => poser("garde_urgence", { numero: e.target.value })}
                            />
                        </ChampReglage>
                        <ChampReglage
                            cle="securite_garde_urgence_mots"
                            idControle="securite-garde-urgence-mots"
                            libelle={{ en: "Your own words", fr: "Vos propres mots" }}
                            aides={[
                                {
                                    en: `Words or phrases that also trigger it, separated by commas (${MOTS_EN_PLUS_MAX} at most). Accents and capitals do not matter.`,
                                    fr: `Mots ou tournures qui le déclenchent aussi, séparés par des virgules (${MOTS_EN_PLUS_MAX} au plus). Les accents et les majuscules n'ont pas d'importance.`,
                                },
                            ]}
                        >
                            <Input
                                id="securite-garde-urgence-mots"
                                value={brouillon.garde_urgence.mots_en_plus.join(", ")}
                                onChange={(e) =>
                                    poser("garde_urgence", {
                                        mots_en_plus: e.target.value
                                            .split(",")
                                            .map((m) => m.trim())
                                            .filter((m) => m.length >= 2)
                                            .slice(0, MOTS_EN_PLUS_MAX),
                                    })
                                }
                            />
                        </ChampReglage>
                    </>
                )}
            </Intertitre>

            <Intertitre
                id="securite-jamais"
                titre={{ en: "What the agent never says", fr: "Ce que l'agent ne dit jamais" }}
                description={{
                    en: "Mechanical guards: they look at the reply before the voice, understanding nothing about the agent; zero latency.",
                    fr: "Garde-fous mécaniques : ils regardent la réplique avant la voix, sans rien comprendre à l'agent ; zéro latence.",
                }}
            >
                <ChampReglage
                    cle="securite_nom_outil"
                    idControle="securite-outils"
                    libelle={{ en: "Never a tool name or code", fr: "Jamais un nom d'outil ni du code" }}
                    aides={[
                        {
                            en: "A tool name of the agent, curly braces, square brackets or a {{…}} variable in the reply: removed before the voice.",
                            fr: "Un nom d'outil de l'agent, des accolades, des crochets ou une variable {{…}} dans la réplique : retirés avant la voix.",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch id="securite-outils" checked={brouillon.jamais.outils} onCheckedChange={(v) => poser("jamais", { outils: v })} />
                </ChampReglage>
                <ChampReglage
                    cle="securite_consigne_recitee"
                    idControle="securite-recitation"
                    libelle={{ en: "Never its instructions recited", fr: "Jamais ses consignes récitées" }}
                    aides={[
                        {
                            en: "A reply that copies a passage of its instructions word for word is replaced by a sentence.",
                            fr: "Une réplique qui reprend mot pour mot un passage de ses consignes est remplacée par une phrase.",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch id="securite-recitation" checked={brouillon.jamais.recitation} onCheckedChange={(v) => poser("jamais", { recitation: v })} />
                </ChampReglage>
                {brouillon.jamais.recitation && (
                    <>
                        <ChampReglage
                            cle="securite_consigne_recitee_mots"
                            idControle="securite-mots"
                            libelle={{ en: "Passage recited from", fr: "Passage récité à partir de" }}
                            aides={[
                                {
                                    en: "Number of consecutive words identical to the instructions. Do not count: injected variables (address, hours), the greeting and the sentences the prompt asks to say as they are.",
                                    fr: "Nombre de mots consécutifs identiques aux consignes. Ne comptent pas : les variables (adresse, horaires), l'accueil et les phrases que le prompt demande de dire telles quelles.",
                                },
                            ]}
                            bornes={{ en: `≥ ${MOTS_MIN} · ≤ ${MOTS_MAX}`, fr: `≥ ${MOTS_MIN} · ≤ ${MOTS_MAX}` }}
                            erreur={errMots}
                            disposition="ligne"
                            sous={
                                <div className="pt-1">
                                    <Curseur
                                        aria-label={t({ en: "Passage recited from", fr: "Passage récité à partir de" })}
                                        min={MOTS_MIN}
                                        max={MOTS_MAX}
                                        step={1}
                                        value={Math.min(Math.max(brouillon.jamais.mots, MOTS_MIN), MOTS_MAX)}
                                        onChange={(e) => poser("jamais", { mots: Number(e.target.value) })}
                                        className="w-full"
                                    />
                                    <div className="flex justify-between text-[10px] text-muted-foreground">
                                        <span>{MOTS_MIN}</span>
                                        <span>{MOTS_MAX}</span>
                                    </div>
                                </div>
                            }
                        >
                            <Input
                                id="securite-mots"
                                type="number"
                                min={MOTS_MIN}
                                max={MOTS_MAX}
                                step={1}
                                aria-invalid={errMots ? true : undefined}
                                value={brouillon.jamais.mots}
                                onChange={(e) => poser("jamais", { mots: Number(e.target.value) })}
                                className="h-8 w-20 border-transparent bg-transparent px-1 text-right text-lg font-semibold tabular-nums shadow-none md:text-lg"
                            />
                        </ChampReglage>
                        <ChampReglage
                            cle="securite_consigne_recitee_phrase"
                            idControle="securite-recitation-phrase"
                            libelle={{ en: "Sentence", fr: "Phrase" }}
                            aides={[
                                {
                                    en: "What is said instead of a reply that recites the instructions.",
                                    fr: "Ce qui est dit à la place d'une réplique qui récite les consignes.",
                                },
                            ]}
                        >
                            <Input
                                id="securite-recitation-phrase"
                                maxLength={LONGUEUR_PHRASE_MAX}
                                placeholder={t(VIDE_CODE)}
                                value={brouillon.jamais.phrase}
                                onChange={(e) => poser("jamais", { phrase: e.target.value })}
                            />
                        </ChampReglage>
                    </>
                )}
            </Intertitre>

            <Intertitre
                id="securite-groupe-ecoute"
                titre={{ en: "Listening to the caller", fr: "Écoute de l'appelant" }}
                description={{
                    en: "A classifier reads each sentence of the caller in parallel with the reply: no wait added. Off until measured on the bench.",
                    fr: "Un classifieur lit chaque phrase de l'appelant en parallèle de la réponse : aucune attente ajoutée. Éteint tant qu'il n'est pas mesuré au banc.",
                }}
            >
                <ChampReglage
                    cle="securite_classifieur"
                    idControle="securite-ecoute"
                    libelle={{ en: "Caller classifier", fr: "Classifieur de l'appelant" }}
                    aides={[
                        {
                            en: "Turns on the classifier that reads each sentence of the caller in parallel with the reply, without making it wait.",
                            fr: "Allume le classifieur qui lit chaque phrase de l'appelant en parallèle de la réponse, sans la faire attendre.",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch id="securite-ecoute" checked={brouillon.ecoute.actif} onCheckedChange={(v) => poser("ecoute", { actif: v })} />
                </ChampReglage>
                {brouillon.ecoute.actif && (
                    <>
                        <ChampReglage
                            cle="securite_classifieur_sensibilite"
                            idControle="securite-sensibilite"
                            libelle={{ en: "Sensitivity", fr: "Sensibilité" }}
                            aides={[
                                {
                                    en: "Cautious: triggers at the slightest doubt. Wide: only when it is clear.",
                                    fr: "Prudente : se déclenche au moindre doute. Large : seulement quand c'est net.",
                                },
                            ]}
                        >
                            <Segments
                                cle="securite-sensibilite"
                                valeur={brouillon.ecoute.sensibilite}
                                options={options<SecuriteComplete["ecoute"]["sensibilite"]>([
                                    ["prudente", { en: "Cautious", fr: "Prudente" }],
                                    ["normale", { en: "Normal", fr: "Normale" }],
                                    ["large", { en: "Wide", fr: "Large" }],
                                ])}
                                onChange={(v) => poser("ecoute", { sensibilite: v as SecuriteComplete["ecoute"]["sensibilite"] })}
                                desactive={false}
                            />
                        </ChampReglage>
                        <ChampReglage
                            cle="securite_classifieur_manipulation"
                            idControle="securite-sur-manipulation"
                            libelle={{ en: "Manipulation spotted", fr: "Manipulation repérée" }}
                            aides={[
                                {
                                    en: "What the code does on the next turn when the classifier spots a manipulation.",
                                    fr: "Ce que fait le code au tour suivant quand le classifieur repère une manipulation.",
                                },
                            ]}
                        >
                            <Segments
                                cle="securite-sur-manipulation"
                                valeur={brouillon.ecoute.sur_manipulation}
                                options={options<SecuriteComplete["ecoute"]["sur_manipulation"]>([
                                    ["noter", { en: "Only note it", fr: "Noter seulement" }],
                                    ["rappel", { en: "Remind the model of its instructions", fr: "Rappeler la consigne au modèle" }],
                                ])}
                                onChange={(v) => poser("ecoute", { sur_manipulation: v as SecuriteComplete["ecoute"]["sur_manipulation"] })}
                                desactive={false}
                            />
                        </ChampReglage>
                        <ChampReglage
                            cle="securite_classifieur_detresse"
                            idControle="securite-sur-detresse"
                            libelle={{ en: "Distress spotted", fr: "Détresse repérée" }}
                            aides={[
                                {
                                    en: "What the code does on the next turn when the classifier spots a distress.",
                                    fr: "Ce que fait le code au tour suivant quand le classifieur repère une détresse.",
                                },
                            ]}
                        >
                            <Segments
                                cle="securite-sur-detresse"
                                valeur={brouillon.ecoute.sur_detresse}
                                options={options<SecuriteComplete["ecoute"]["sur_detresse"]>([
                                    ["noter", { en: "Only note it", fr: "Noter seulement" }],
                                    ["urgence", { en: "Emergency instruction", fr: "Consigne d'urgence" }],
                                ])}
                                onChange={(v) => poser("ecoute", { sur_detresse: v as SecuriteComplete["ecoute"]["sur_detresse"] })}
                                desactive={false}
                            />
                        </ChampReglage>
                        <ChampReglage
                            cle="securite_classifieur_consigne"
                            idControle="securite-consigne"
                            libelle={{ en: "Classifier instruction", fr: "Consigne du classifieur" }}
                            aides={[
                                {
                                    en: "The classifier's system instruction: the two questions it asks itself (manipulation, distress). Empty: the code's own text.",
                                    fr: "La consigne système du classifieur : les deux questions qu'il se pose (manipulation, détresse). Vide : le texte du code.",
                                },
                            ]}
                        >
                            <Textarea
                                id="securite-consigne"
                                rows={4}
                                maxLength={LONGUEUR_CONSIGNE_MAX}
                                placeholder={t(VIDE_CODE)}
                                value={brouillon.ecoute.consigne}
                                onChange={(e) => poser("ecoute", { consigne: e.target.value })}
                            />
                        </ChampReglage>
                    </>
                )}
            </Intertitre>

            <Intertitre id="securite-suivi" titre={{ en: "Follow-up", fr: "Suivi" }}>
                <ChampReglage
                    cle="securite_marquer"
                    idControle="securite-marquer"
                    libelle={{ en: "Mark every trigger", fr: "Marquer chaque déclenchement" }}
                    aides={[
                        {
                            en: "The reply concerned is marked in the call (Calls tab) and the call arrives in « To improve ».",
                            fr: "La réplique concernée est marquée dans l'appel (onglet Appels) et l'appel arrive dans « À améliorer ».",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch id="securite-marquer" checked={brouillon.marquer} onCheckedChange={(v) => setBrouillon((a) => ({ ...a, marquer: v }))} />
                </ChampReglage>
            </Intertitre>

            <Intertitre
                id="securite-blocs"
                titre={{ en: "Reusable blocks", fr: "Blocs réutilisables" }}
                description={{
                    en: "How the library's blocks reach a call: live, or frozen at publication.",
                    fr: "Comment les blocs de la bibliothèque arrivent dans un appel : en direct, ou figés à la publication.",
                }}
            >
                <Reglage cle="blocs_mode" valeur={blocs.brouillon.blocs_mode} onChange={(v) => blocs.setBrouillon((a) => ({ ...a, blocs_mode: v as "direct" | "fige" | null }))} />
            </Intertitre>
        </Theme>
    );
};
