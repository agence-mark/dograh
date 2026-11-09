"use client";

/**
 * [.mark] Theme « After the call » (chantier l-agent-travaille, L4, A1 to A10; rangement validé le 06/10).
 *
 * What Dograh does once a call has ended, for the agents that switch it on (« Call data » of the
 * agent): the summary (a smaller Mistral model, the client's key), the mail server (a generic
 * SMTP, its password a key of « Keys »), the recap mail, the modules (custom webhook), and the
 * night task (purge and counters). One « Save » for the theme (E6); the test mail, the recap now
 * and the purge now act at once.
 */
import { Mail } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
    getApresAppelApiV1OrganizationsApresAppelGet,
    postEssaiMailApiV1OrganizationsApresAppelEssaiMailPost,
    postNuitApiV1OrganizationsApresAppelNuitPost,
    postRecapitulatifApiV1OrganizationsApresAppelRecapitulatifPost,
    putApresAppelApiV1OrganizationsApresAppelPut,
} from "@/client/sdk.gen";
import type { EcranApresAppel, ReglagesApresAppel } from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";

import { PREFIXE_REFERENCE } from "../cles/ChampCleModele";
import { type Fournisseur, SelecteurCle } from "../cles/FenetreCles";
import { ChampReglage } from "../ecran/ChampReglage";
import { useFormeMaquette } from "../ecran/forme-maquette";
import { Intertitre } from "../ecran/Intertitre";
import { type ErreurNommee, Theme } from "../ecran/Theme";
import { allerAuReglage } from "../ecran/useThemesOuverts";
import { BlocLu } from "../entreprise/section-lue";
import { type Texte, useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { FenetreChamps } from "../studio/fenetre-champs";
import { Info } from "../studio/marques";
import { BlocInstallationMark } from "./BlocInstallationMark";
import { type ProprietesThemeOrganisation, useSignaler } from "./ThemesOrganisation";

export const TITRE_APRES_APPEL: Texte = { en: "After the call", fr: "Après l'appel" };

export const MODELE_SYNTHESE_DEFAUT = "mistral-small-latest";

const REGLAGES_VIDES: ReglagesApresAppel = {
    format: "apres-appel-mark",
    version: 1,
    synthese: { modele: MODELE_SYNTHESE_DEFAUT, cle: null, nom_assistant: null, nom_entreprise: null, consigne: null, delai_s: 30, temperature: 0.2, longueur_max: 400 },
    smtp: { hote: null, port: 587, securite: "starttls", utilisateur: null, mot_de_passe: null, expediteur: null, nom_expediteur: null, delai_s: 20 },
    recapitulatif: { actif: false, heures: [8] },
    webhook: { url: null, secret: null, delai_s: 10 },
    reprises: { tentatives_max: 3, delai_1_s: 60, delai_2_s: 300 },
    delai_sms_s: 15,
};

/** Clôture, lot C (D18) : les valeurs de l'après-appel qui étaient des constantes du code (niveau avancé). Mêmes bornes que le serveur. */
type ChampAvance = { cle: string; id: string; libelle: Texte; aide: Texte; min: number; max: number; pas: number; defaut: number; unite: Texte };
const S: Texte = { en: "s", fr: "s" };
const CHAMPS_AVANCES: ChampAvance[] = [
    { cle: "synthese_delai_s", id: "avance-synthese-delai", libelle: { en: "Summary: time to answer", fr: "Synthèse : délai de réponse" }, aide: { en: "Seconds the summary model has to answer before the step fails and is retried.", fr: "Secondes laissées au modèle de la synthèse pour répondre, avant que l'étape échoue et soit reprise." }, min: 5, max: 120, pas: 1, defaut: 30, unite: S },
    { cle: "synthese_temperature", id: "avance-synthese-temperature", libelle: { en: "Summary: temperature", fr: "Synthèse : température" }, aide: { en: "0 is the most regular wording, 1 the most varied.", fr: "0 donne la rédaction la plus régulière, 1 la plus variée." }, min: 0, max: 1, pas: 0.1, defaut: 0.2, unite: { en: "", fr: "" } },
    { cle: "synthese_longueur_max", id: "avance-synthese-longueur", libelle: { en: "Summary: longest answer", fr: "Synthèse : longueur maximale" }, aide: { en: "Tokens the summary may use at most (about three quarters of a word each).", fr: "Nombre de jetons au plus pour la synthèse (environ trois quarts de mot chacun)." }, min: 100, max: 2000, pas: 50, defaut: 400, unite: { en: "tokens", fr: "jetons" } },
    { cle: "smtp_delai_s", id: "avance-mail-delai", libelle: { en: "Mail: time to answer", fr: "Mail : délai de réponse" }, aide: { en: "Seconds the mail server has to answer.", fr: "Secondes laissées au serveur de mail pour répondre." }, min: 5, max: 120, pas: 1, defaut: 20, unite: S },
    { cle: "webhook_delai_s", id: "avance-webhook-delai", libelle: { en: "Webhook: time to answer", fr: "Webhook : délai de réponse" }, aide: { en: "Seconds the custom webhook has to answer.", fr: "Secondes laissées au webhook sur mesure pour répondre." }, min: 2, max: 60, pas: 1, defaut: 10, unite: S },
    { cle: "delai_sms_s", id: "avance-sms-delai", libelle: { en: "SMS: time to answer", fr: "SMS : délai de réponse" }, aide: { en: "Seconds the client's Twilio has to answer when an SMS leaves.", fr: "Secondes laissées au Twilio du client pour répondre quand un SMS part." }, min: 2, max: 60, pas: 1, defaut: 15, unite: S },
    { cle: "reprises_tentatives_max", id: "avance-reprises-tentatives", libelle: { en: "Steps: attempts before giving up", fr: "Étapes : tentatives avant d'abandonner" }, aide: { en: "A step that fails is played again alone, later, up to this many attempts, then reported to the notification addresses.", fr: "Une étape qui échoue est rejouée seule, plus tard, jusqu'à ce nombre de tentatives, puis signalée aux adresses de notification." }, min: 1, max: 6, pas: 1, defaut: 3, unite: { en: "attempts", fr: "tentatives" } },
    { cle: "reprises_delai_1_s", id: "avance-reprises-delai-1", libelle: { en: "Steps: wait before the 2nd attempt", fr: "Étapes : attente avant la 2e tentative" }, aide: { en: "Seconds between the first failure and the second attempt.", fr: "Secondes entre le premier échec et la deuxième tentative." }, min: 10, max: 3600, pas: 10, defaut: 60, unite: S },
    { cle: "reprises_delai_2_s", id: "avance-reprises-delai-2", libelle: { en: "Steps: wait before the next ones", fr: "Étapes : attente avant les suivantes" }, aide: { en: "Seconds between the second failure and each later attempt.", fr: "Secondes entre le deuxième échec et chaque tentative suivante." }, min: 10, max: 3600, pas: 10, defaut: 300, unite: S },
];
const decouperCle = (cle: string): [string, string] => {
    const i = cle.indexOf("_");
    return [cle.slice(0, i), cle.slice(i + 1)];
};
const lireAvance = (r: ReglagesApresAppel, cle: string): number | undefined => {
    if (cle === "delai_sms_s") return r.delai_sms_s;
    const [partie, champ] = decouperCle(cle);
    return (r as Record<string, Record<string, number> | undefined>)[partie]?.[champ];
};
const poserAvance = (r: ReglagesApresAppel, cle: string, valeur: number): ReglagesApresAppel => {
    if (cle === "delai_sms_s") return { ...r, delai_sms_s: valeur };
    const [partie, champ] = decouperCle(cle);
    const base = (REGLAGES_VIDES as Record<string, object | undefined>)[partie] ?? {};
    return { ...r, [partie]: { ...base, ...((r as Record<string, object | undefined>)[partie] ?? {}), [champ]: valeur } };
};
const horsBornes = (c: ChampAvance, v: number) => !(Number.isFinite(v) && v >= c.min && v <= c.max);

const ADRESSE = /^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/;

/** The organization's after-call settings and their screen state, read once. */
export const useApresAppel = () => {
    const { user, loading: authLoading } = useAuth();
    const [ecran, setEcran] = useState<EcranApresAppel | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const dejaLu = useRef(false);
    const relire = useCallback(async () => {
        const reponse = await getApresAppelApiV1OrganizationsApresAppelGet();
        if (reponse.error || !reponse.data) {
            setErreur(echecAffiche(reponse.error, ECHECS.apresAppelLire));
            return;
        }
        setErreur(null);
        setEcran(reponse.data);
    }, []);
    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [authLoading, user, relire]);
    return { ecran, setEcran, erreur, relire };
};

const versUuid = (reference: string | null | undefined) =>
    reference && reference.startsWith(PREFIXE_REFERENCE) ? reference.slice(PREFIXE_REFERENCE.length) : null;
const versReference = (uuid: string | null) => (uuid ? `${PREFIXE_REFERENCE}${uuid}` : null);
const vide = (v: string) => (v.trim() === "" ? null : v.trim());

/** « 8, 17 » → [8, 17]; null when a part is not an hour. */
export const lireHeures = (texte: string): number[] | null => {
    const morceaux = texte.split(/[,;\s]+/).filter(Boolean);
    const heures = morceaux.map((m) => Number(m.replace(/h$/i, "")));
    if (heures.some((h) => !Number.isInteger(h) || h < 0 || h > 23)) return null;
    return [...new Set(heures)].sort((a, b) => a - b);
};

export const ThemeApresAppel = ({
    ouvert,
    onBasculer,
    ouvrir,
    signaler,
    apresAppel,
    plat,
    sansTitre,
}: ProprietesThemeOrganisation & { apresAppel: ReturnType<typeof useApresAppel> }) => {
    const { t } = useLangue();
    const maquette = useFormeMaquette();
    const { ecran, setEcran, erreur } = apresAppel;
    const enregistre = ecran?.reglages ?? REGLAGES_VIDES;
    const [brouillon, setBrouillon] = useState<ReglagesApresAppel>(enregistre);
    const [heures, setHeures] = useState((enregistre.recapitulatif?.heures ?? [8]).join(", "));
    const [enCours, setEnCours] = useState(false);
    const [destinataireEssai, setDestinataireEssai] = useState("");
    const cle = JSON.stringify(enregistre);
    useEffect(() => {
        const relu = JSON.parse(cle) as ReglagesApresAppel;
        setBrouillon(relu);
        setHeures((relu.recapitulatif?.heures ?? [8]).join(", "));
    }, [cle]);

    const synthese = { ...REGLAGES_VIDES.synthese!, ...(brouillon.synthese ?? {}) };
    const smtp = { ...REGLAGES_VIDES.smtp!, ...(brouillon.smtp ?? {}) };
    const recap = { ...REGLAGES_VIDES.recapitulatif!, ...(brouillon.recapitulatif ?? {}) };
    const webhook = { ...REGLAGES_VIDES.webhook!, ...(brouillon.webhook ?? {}) };
    const heuresLues = lireHeures(heures);
    const envoye: ReglagesApresAppel = { ...brouillon, recapitulatif: { ...recap, heures: heuresLues ?? recap.heures } };
    const modifie = JSON.stringify(envoye) !== cle || heuresLues === null;

    const poser = <K extends "synthese" | "smtp" | "recapitulatif" | "webhook" | "reprises">(partie: K, champ: string, valeur: unknown) =>
        setBrouillon((avant) => ({ ...avant, [partie]: { ...(REGLAGES_VIDES[partie] as object), ...(avant[partie] ?? {}), [champ]: valeur } }));

    const afficher = (cleReglage: string) => {
        ouvrir();
        allerAuReglage(cleReglage);
    };
    const erreurs: ErreurNommee[] = [];
    const nommer = (cleReglage: string, libelle: Texte, message: Texte) =>
        erreurs.push({ cle: cleReglage, libelle: t(libelle), message: t(message), afficher: () => afficher(cleReglage) });
    for (const c of CHAMPS_AVANCES) {
        if (horsBornes(c, lireAvance(brouillon, c.cle) ?? c.defaut))
            nommer(c.cle, c.libelle, { en: `a number from ${c.min} to ${c.max}.`, fr: `un nombre de ${c.min} à ${c.max}.` });
    }
    if (heuresLues === null)
        nommer("recapitulatif_heures", { en: "Recap hours", fr: "Heures du récapitulatif" }, { en: "hours from 0 to 23, separated by commas.", fr: "des heures de 0 à 23, séparées par des virgules." });
    if (!(Number.isInteger(smtp.port) && (smtp.port ?? 0) >= 1 && (smtp.port ?? 0) <= 65535))
        nommer("smtp_port", { en: "Mail server port", fr: "Port du serveur de mail" }, { en: "a number from 1 to 65535.", fr: "un nombre de 1 à 65535." });
    if (smtp.expediteur && !ADRESSE.test(smtp.expediteur))
        nommer("smtp_expediteur", { en: "Sender", fr: "Expéditeur" }, { en: "not a mail address.", fr: "pas une adresse mail." });
    if (webhook.url && !/^https?:\/\/\S+$/.test(webhook.url))
        nommer("webhook_url", { en: "Webhook address", fr: "Adresse du webhook" }, { en: "starts with https://.", fr: "commence par https://." });
    useSignaler("apres-appel", modifie, erreurs.length > 0, signaler);

    const enregistrer = async () => {
        setEnCours(true);
        const reponse = await putApresAppelApiV1OrganizationsApresAppelPut({ body: envoye });
        setEnCours(false);
        if (reponse.error || !reponse.data) {
            notifier.echec({ fr: "Réglages non enregistrés. Réessayez.", en: "Settings not saved. Try again." }, { erreur: reponse.error });
            return false;
        }
        setEcran(reponse.data);
        notifier.succes({ fr: "Réglages enregistrés.", en: "Settings saved." });
        return true;
    };

    const agir = async (action: () => Promise<{ data?: unknown; error?: unknown }>, succes: Texte): Promise<boolean> => {
        setEnCours(true);
        const reponse = await action();
        setEnCours(false);
        if (reponse.error) {
            notifier.echec({ fr: "Demande refusée.", en: "Request refused." }, { erreur: reponse.error });
            return false;
        }
        notifier.succes(succes);
        await apresAppel.relire();
        return true;
    };

    const nuit = ecran?.derniere_nuit as { debut?: string; statut?: string; resultat?: { purge?: Record<string, number> } } | null | undefined;

    const resume = !ecran
        ? [t({ en: "Loading...", fr: "Chargement..." })]
        : [
              synthese.cle ? `${t({ en: "Summary", fr: "Synthèse" })} · ${synthese.modele}` : t({ en: "No summary key", fr: "Pas de clé de synthèse" }),
              smtp.hote ? `${t({ en: "Mail", fr: "Mail" })} · ${smtp.hote}` : t({ en: "No mail server", fr: "Pas de serveur de mail" }),
              recap.actif ? `${t({ en: "Recap", fr: "Récapitulatif" })} · ${(recap.heures ?? []).map((h) => `${h} h`).join(", ")}` : null,
              webhook.url ? t({ en: "Custom webhook", fr: "Webhook sur mesure" }) : null,
          ];

    const cleSelecteur = (fournisseur: Fournisseur, partie: "synthese" | "smtp" | "webhook", champ: string, valeur: string | null | undefined, libelle: Texte) => (
        <SelecteurCle
            fournisseur={fournisseur}
            valeur={versUuid(valeur)}
            libelle={libelle}
            onChange={(uuid) => poser(partie, champ, versReference(uuid))}
        />
    );

    const champsSynthese = (
        <>
                <ChampReglage
                    cle="synthese_modele"
                    idControle="apres-appel-modele"
                    libelle={{ en: "Model", fr: "Modèle" }}
                    aides={[{ en: "A smaller model than the agent's: Mistral's rate limit is per model.", fr: "Un modèle plus petit que celui de l'agent : la limite de Mistral est par modèle." }]}
                    bornes={{ en: `Default: ${MODELE_SYNTHESE_DEFAUT}`, fr: `Par défaut : ${MODELE_SYNTHESE_DEFAUT}` }}
                >
                    <Input id="apres-appel-modele" value={synthese.modele ?? ""} onChange={(e) => poser("synthese", "modele", e.target.value || MODELE_SYNTHESE_DEFAUT)} />
                </ChampReglage>
                <ChampReglage cle="synthese_cle" libelle={{ en: "Mistral key", fr: "Clé Mistral" }}>
                    {cleSelecteur("mistral", "synthese", "cle", synthese.cle, { en: "The client's key, chosen in « Keys »", fr: "La clé du client, choisie dans « Clés »" })}
                </ChampReglage>
                <ChampReglage
                    cle="synthese_nom_assistant"
                    idControle="apres-appel-assistant"
                    libelle={{ en: "Assistant's name in the summary", fr: "Nom de l'assistant dans la synthèse" }}
                    aides={[{ en: "Empty: « the voice assistant ».", fr: "Vide : « l'assistant vocal »." }]}
                >
                    <Input id="apres-appel-assistant" value={synthese.nom_assistant ?? ""} onChange={(e) => poser("synthese", "nom_assistant", vide(e.target.value))} />
                </ChampReglage>
                <ChampReglage cle="synthese_nom_entreprise" idControle="apres-appel-entreprise" libelle={{ en: "Company", fr: "Entreprise" }}>
                    <Input id="apres-appel-entreprise" value={synthese.nom_entreprise ?? ""} onChange={(e) => poser("synthese", "nom_entreprise", vide(e.target.value))} />
                </ChampReglage>
                <ChampReglage
                    cle="synthese_consigne"
                    idControle="apres-appel-consigne"
                    libelle={{ en: "Instructions", fr: "Consigne" }}
                    aides={[{ en: "Empty: the default instructions of the library (family After-call, element consigne-synthese).", fr: "Vide : la consigne par défaut de la bibliothèque (famille Après-appel, élément consigne-synthese)." }]}
                >
                    <Textarea id="apres-appel-consigne" rows={3} value={synthese.consigne ?? ""} onChange={(e) => poser("synthese", "consigne", vide(e.target.value))} />
                </ChampReglage>
        </>
    );
    const champsSmtp = (
        <>
                <ChampReglage cle="smtp_hote" idControle="smtp-hote" libelle={{ en: "Server", fr: "Serveur" }}>
                    <Input id="smtp-hote" value={smtp.hote ?? ""} placeholder={t({ en: "smtp.example.org", fr: "smtp.example.org" })} onChange={(e) => poser("smtp", "hote", vide(e.target.value))} />
                </ChampReglage>
                <ChampReglage cle="smtp_port" idControle="smtp-port" libelle={{ en: "Port", fr: "Port" }} bornes={{ en: "1 to 65535, default 587", fr: "1 à 65535, 587 par défaut" }}>
                    <div className="flex items-center gap-2">
                        <Input id="smtp-port" type="number" min={1} max={65535} value={smtp.port ?? 587} onChange={(e) => poser("smtp", "port", Number(e.target.value))} className={maquette ? "w-32" : ""} />
                        {maquette && <span className="ml-auto text-xs text-muted-foreground">{t({ en: "from 1 to 65535", fr: "de 1 à 65535" })}</span>}
                    </div>
                </ChampReglage>
                <ChampReglage cle="smtp_securite" idControle="smtp-securite" libelle={{ en: "Security", fr: "Sécurité" }}>
                    {maquette ? (
                        <span className="inline-flex rounded-lg bg-muted p-0.5 text-sm" role="group" aria-label={t({ en: "Security", fr: "Sécurité" })}>
                            {(
                                [
                                    ["starttls", "STARTTLS"],
                                    ["ssl", "SSL/TLS"],
                                    ["aucune", t({ en: "None (local network only)", fr: "Aucune (réseau local seulement)" })],
                                ] as const
                            ).map(([valeur, libelle]) => (
                                <button
                                    key={valeur}
                                    type="button"
                                    aria-pressed={(smtp.securite ?? "starttls") === valeur}
                                    onClick={() => poser("smtp", "securite", valeur)}
                                    className={`cursor-pointer rounded-md px-3 py-1 ${(smtp.securite ?? "starttls") === valeur ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                                >
                                    {libelle}
                                </button>
                            ))}
                        </span>
                    ) : (
                    <ListeDeroulante
                        id="smtp-securite"
                        className="rounded border border-border bg-background px-2 py-1 text-sm"
                        value={smtp.securite ?? "starttls"}
                        onChange={(e) => poser("smtp", "securite", e.target.value)}
                    >
                        <option value="starttls">{t({ en: "STARTTLS", fr: "STARTTLS" })}</option>
                        <option value="ssl">{t({ en: "SSL/TLS", fr: "SSL/TLS" })}</option>
                        <option value="aucune">{t({ en: "None (local network only)", fr: "Aucune (réseau local seulement)" })}</option>
                    </ListeDeroulante>
                    )}
                </ChampReglage>
                <ChampReglage cle="smtp_utilisateur" idControle="smtp-utilisateur" libelle={{ en: "User", fr: "Utilisateur" }}>
                    <Input id="smtp-utilisateur" value={smtp.utilisateur ?? ""} onChange={(e) => poser("smtp", "utilisateur", vide(e.target.value))} />
                </ChampReglage>
                <ChampReglage cle="smtp_mot_de_passe" libelle={{ en: "Password", fr: "Mot de passe" }}>
                    {cleSelecteur("smtp", "smtp", "mot_de_passe", smtp.mot_de_passe, { en: "A key of « Keys », provider SMTP", fr: "Une clé de « Clés », fournisseur SMTP" })}
                </ChampReglage>
                <ChampReglage cle="smtp_expediteur" idControle="smtp-expediteur" libelle={{ en: "Sender", fr: "Expéditeur" }}>
                    <Input id="smtp-expediteur" value={smtp.expediteur ?? ""} placeholder={t({ en: "agent@example.org", fr: "agent@example.org" })} onChange={(e) => poser("smtp", "expediteur", vide(e.target.value))} />
                </ChampReglage>
                <ChampReglage cle="smtp_nom_expediteur" idControle="smtp-nom-expediteur" libelle={{ en: "Sender name", fr: "Nom de l'expéditeur" }}>
                    <Input id="smtp-nom-expediteur" value={smtp.nom_expediteur ?? ""} onChange={(e) => poser("smtp", "nom_expediteur", vide(e.target.value))} />
                </ChampReglage>
        </>
    );
    const champsRecap = (
        <>
                <ChampReglage cle="recapitulatif_actif" idControle="recapitulatif-actif" libelle={{ en: "Send the recap", fr: "Envoyer le récapitulatif" }} bornes={{ en: "Default: off", fr: "Par défaut : éteint" }} disposition="ligne">
                    <Switch id="recapitulatif-actif" checked={Boolean(recap.actif)} onCheckedChange={(v) => poser("recapitulatif", "actif", v)} />
                </ChampReglage>
                {recap.actif && (
                    <ChampReglage cle="recapitulatif_heures" idControle="recapitulatif-heures" libelle={{ en: "Hours", fr: "Heures" }} bornes={{ en: "0 to 23, e.g. 8, 17", fr: "0 à 23, par ex. 8, 17" }}>
                        <Input id="recapitulatif-heures" value={heures} onChange={(e) => setHeures(e.target.value)} />
                    </ChampReglage>
                )}
        </>
    );
    const champsAvances = (
        <>
            {CHAMPS_AVANCES.map((c) => {
                const v = lireAvance(brouillon, c.cle) ?? c.defaut;
                return (
                    <ChampReglage
                        key={c.cle}
                        cle={c.cle}
                        idControle={c.id}
                        libelle={c.libelle}
                        aides={[c.aide]}
                        bornes={{ en: `${c.min} to ${c.max}, default ${c.defaut}`, fr: `${c.min} à ${c.max}, ${c.defaut} par défaut` }}
                        erreur={horsBornes(c, v) ? { en: `a number from ${c.min} to ${c.max}.`, fr: `un nombre de ${c.min} à ${c.max}.` } : null}
                    >
                        <span className="inline-flex items-center gap-2">
                            <Input
                                id={c.id}
                                type="number"
                                min={c.min}
                                max={c.max}
                                step={c.pas}
                                value={Number.isNaN(v) ? "" : v}
                                className="w-28"
                                onChange={(e) => setBrouillon((avant) => poserAvance(avant, c.cle, e.target.value === "" ? Number.NaN : Number(e.target.value)))}
                            />
                            {t(c.unite) && <span className="text-xs text-muted-foreground">{t(c.unite)}</span>}
                        </span>
                    </ChampReglage>
                );
            })}
        </>
    );
    const champsWebhook = (
        <>
                <ChampReglage
                    cle="webhook_url"
                    idControle="webhook-url"
                    libelle={{ en: "Custom webhook: address", fr: "Webhook sur mesure : adresse" }}
                    aides={[
                        {
                            en: "A custom n8n workflow after the call. It receives the record, the request and the summary; never the transcript. The organization travels in the secret of the X-Mark-Secret header.",
                            fr: "Un workflow n8n sur mesure après l'appel. Il reçoit la fiche, la demande et la synthèse ; jamais la transcription. L'organisation voyage dans le secret de l'en-tête X-Mark-Secret.",
                        },
                    ]}
                >
                    <Input id="webhook-url" value={webhook.url ?? ""} placeholder="https://n8n.example.org/webhook/…" onChange={(e) => poser("webhook", "url", vide(e.target.value))} />
                </ChampReglage>
                <ChampReglage cle="webhook_secret" libelle={{ en: "Custom webhook: secret", fr: "Webhook sur mesure : secret" }}>
                    {cleSelecteur("webhook", "webhook", "secret", webhook.secret, { en: "A key of « Keys », provider Webhook", fr: "Une clé de « Clés », fournisseur Webhook" })}
                </ChampReglage>
        </>
    );

    if (maquette) {
        const unite = (n: string | null | undefined) => (n && n.trim() ? n : null);
        const aucun = t({ en: "not set", fr: "non réglé" });
        const fenetre = (titre: Texte, corps: React.ReactNode) => ({
            titre: t(titre),
            corps,
            onAnnuler: () => {
                setBrouillon(JSON.parse(cle) as ReglagesApresAppel);
                setHeures((enregistre.recapitulatif?.heures ?? [8]).join(", "));
            },
            onValider: () => enregistrer(),
            verifier: () => (erreurs.length > 0 ? { [erreurs[0].cle]: erreurs[0].message } : null),
        });
        return (
            <Theme
                id="apres-appel"
                plat={plat}
                sansTitre={sansTitre}
                icone={Mail}
                titre={TITRE_APRES_APPEL}
                description={{ en: "After the call", fr: "Après l'appel" }}
                resume={resume}
                ouvert={ouvert}
                onBasculer={onBasculer}
                modifie={modifie}
                erreurs={erreurs}
            >
                {erreur && (
                    <p className="text-sm text-destructive" role="alert">
                        {erreur}
                    </p>
                )}
                {!ecran ? (
                    erreur ? null : <EtatVide cas="chargement" />
                ) : (
                    <>
                        <BlocLu
                            id="apres-appel-synthese"
                            titre={t({ en: "Summary", fr: "Synthèse" })}
                            info={t({
                                en: "A few lines on what happened on the phone, next to the record's fields and never in their place. Billed on the client's Mistral key.",
                                fr: "Quelques lignes sur ce qui s'est passé au téléphone, à côté des champs de la fiche et jamais à leur place. Facturée sur la clé Mistral du client.",
                            })}
                            lignes={[
                                [t({ en: "Model", fr: "Modèle" }), synthese.modele ?? MODELE_SYNTHESE_DEFAUT],
                                [t({ en: "Key", fr: "Clé" }), synthese.cle ? t({ en: "a key of « Keys »", fr: "une clé de « Clés »" }) : aucun],
                                [t({ en: "Instructions", fr: "Consigne" }), synthese.consigne ? t({ en: "written here", fr: "écrite ici" }) : t({ en: "generic (library)", fr: "générique (bibliothèque)" })],
                            ]}
                            fenetre={fenetre({ en: "Summary", fr: "Synthèse" }, champsSynthese)}
                        />
                        <BlocLu
                            id="apres-appel-smtp"
                            titre={t({ en: "Mail server", fr: "Serveur de mail" })}
                            info={t({
                                en: "One mail per request, to the people its subject is routed to (« Team and routing »), else to the default recipients.",
                                fr: "Un mail par demande, aux personnes de son sujet (« Équipe et routage »), sinon aux destinataires par défaut.",
                            })}
                            action={<EssaiMail enCours={enCours} bloque={modifie || !smtp.hote} envoyer={(destinataire) => agir(() => postEssaiMailApiV1OrganizationsApresAppelEssaiMailPost({ body: { destinataire } }), { en: "Test mail sent", fr: "Mail d'essai envoyé" })} />}
                            lignes={[
                                [t({ en: "Server", fr: "Serveur" }), unite(smtp.hote) ? `${smtp.hote} · ${smtp.port} · ${(smtp.securite ?? "starttls").toUpperCase()}` : aucun],
                                [t({ en: "Sender", fr: "Expéditeur" }), unite(smtp.nom_expediteur) ?? unite(smtp.expediteur) ?? aucun],
                                [t({ en: "Password", fr: "Mot de passe" }), smtp.mot_de_passe ? t({ en: "a key of « Keys »", fr: "une clé de « Clés »" }) : aucun],
                            ]}
                            fenetre={fenetre({ en: "Mail server", fr: "Serveur de mail" }, champsSmtp)}
                        />
                        <BlocLu
                            id="apres-appel-recapitulatif"
                            titre={t({ en: "Recap", fr: "Récapitulatif" })}
                            info={t({
                                en: "A mail of the requests that still wait for a call-back, to the default recipients, at the hours set (the organization's timezone).",
                                fr: "Un mail des demandes qui attendent encore un rappel, aux destinataires par défaut, aux heures réglées (fuseau de l'organisation).",
                            })}
                            action={
                                <Button variant="ghost" size="sm" disabled={enCours || modifie || !ecran.base_rattachee} data-testid="recapitulatif-maintenant" onClick={() => void agir(() => postRecapitulatifApiV1OrganizationsApresAppelRecapitulatifPost(), { en: "Recap sent", fr: "Récapitulatif envoyé" })}>
                                    {t({ en: "Send now", fr: "Envoyer maintenant" })}
                                </Button>
                            }
                            lignes={[[t({ en: "State", fr: "État" }), recap.actif ? `${t({ en: "on", fr: "allumé" })} · ${(recap.heures ?? []).map((h) => `${h} h`).join(", ")}` : t({ en: "off", fr: "éteint" })]]}
                            fenetre={fenetre({ en: "Recap", fr: "Récapitulatif" }, champsRecap)}
                        />
                        <BlocLu
                            id="apres-appel-modules"
                            titre={t({ en: "Custom webhook", fr: "Webhook sur mesure" })}
                            info={t({
                                en: "Set here, switched on agent by agent (« Call data »). Off by default.",
                                fr: "Réglé ici, allumé agent par agent (« Données de l'appel »). Éteint par défaut.",
                            })}
                            lignes={[[t({ en: "Address", fr: "Adresse" }), unite(webhook.url) ?? aucun]]}
                            fenetre={fenetre({ en: "Custom webhook", fr: "Webhook sur mesure" }, champsWebhook)}
                        />
                        <BlocLu
                            id="apres-appel-avance"
                            titre={t({ en: "Advanced", fr: "Avancé" })}
                            info={t({
                                en: "Delays, summary settings and retries that were fixed in the code. Current values by default.",
                                fr: "Délais, réglages de la synthèse et reprises qui étaient fixés dans le code. Valeurs d'avant par défaut.",
                            })}
                            lignes={[
                                [t({ en: "Summary", fr: "Synthèse" }), `${lireAvance(brouillon, "synthese_delai_s") ?? 30} s · ${lireAvance(brouillon, "synthese_longueur_max") ?? 400} ${t({ en: "tokens", fr: "jetons" })}`],
                                [t({ en: "Retries", fr: "Reprises" }), `${lireAvance(brouillon, "reprises_tentatives_max") ?? 3} ${t({ en: "attempts", fr: "tentatives" })}`],
                            ]}
                            fenetre={fenetre({ en: "Advanced", fr: "Avancé" }, champsAvances)}
                        />
                        <BlocLu
                            id="apres-appel-nuit"
                            titre={t({ en: "Night task", fr: "Tâche de nuit" })}
                            info={t({
                                en: "Every night: the purge, table by table (durations in « Client data »), and the day's counters. The result is kept as proof.",
                                fr: "Chaque nuit : la purge, table par table (durées dans « Données du client »), et les compteurs du jour. Le résultat est gardé comme preuve.",
                            })}
                            action={
                                <Button variant="ghost" size="sm" disabled={enCours || !ecran.base_rattachee} data-testid="purge-maintenant" onClick={() => void agir(() => postNuitApiV1OrganizationsApresAppelNuitPost(), { en: "Purge done", fr: "Purge faite" })}>
                                    {t({ en: "Run the purge now", fr: "Lancer la purge maintenant" })}
                                </Button>
                            }
                            lignes={[
                                [
                                    t({ en: "Last passage", fr: "Dernier passage" }),
                                    <span key="n" data-testid="derniere-nuit">
                                        {nuit?.debut
                                            ? `${new Date(nuit.debut).toLocaleString()} · ${nuit.statut} · ${Object.entries(nuit.resultat?.purge ?? {})
                                                  .map(([table, n]) => `${table} ${n}`)
                                                  .join(", ")}`
                                            : t({ en: "Not run yet.", fr: "Pas encore passée." })}
                                    </span>,
                                ],
                                ...(ecran.base_rattachee
                                    ? []
                                    : ([
                                          [
                                              t({ en: "Client database", fr: "Base du client" }),
                                              <span key="b" className="flex items-center gap-1.5" data-testid="apres-appel-sans-base">
                                                  {t({ en: "not attached", fr: "non rattachée" })}
                                                  <Info>
                                                      {t({
                                                          en: "No client database is attached (« Client data »): the calls cannot be written, nor the requests routed.",
                                                          fr: "Aucune base du client n'est rattachée (« Données du client ») : les appels ne peuvent pas s'écrire, ni les demandes être routées.",
                                                      })}
                                                  </Info>
                                              </span>,
                                          ],
                                      ] as [string, React.ReactNode][])),
                            ]}
                        />
                        <BlocInstallationMark />
                    </>
                )}
            </Theme>
        );
    }

    return (
        <Theme
            id="apres-appel"
            plat={plat}
            sansTitre={sansTitre}
            icone={Mail}
            titre={TITRE_APRES_APPEL}
            description={{
                en: "What Dograh does once a call has ended, for the agents that switch it on in « Call data »: write it in the client's database, summarise it, mail the request, run the modules.",
                fr: "Ce que fait Dograh une fois l'appel fini, pour les agents qui l'allument dans « Données de l'appel » : l'écrire dans la base du client, le résumer, envoyer la demande par mail, lancer les modules.",
            }}
            resume={resume}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={erreurs}
            enregistrement={{ onEnregistrer: () => void enregistrer(), enCours: enCours || !ecran }}
        >
            {erreur && (
                <p className="text-sm text-destructive" role="alert">
                    {erreur}
                </p>
            )}
            {ecran && !ecran.base_rattachee && (
                <p className="rounded border border-(--signal-warn) p-2 text-sm" data-testid="apres-appel-sans-base">
                    {t({
                        en: "No client database is attached (« Client data »): the calls cannot be written, nor the requests routed.",
                        fr: "Aucune base du client n'est rattachée (« Données du client ») : les appels ne peuvent pas s'écrire, ni les demandes être routées.",
                    })}
                </p>
            )}

            <Intertitre
                id="apres-appel-synthese"
                titre={{ en: "Summary", fr: "Synthèse" }}
                description={{
                    en: "A few lines on what happened on the phone, next to the record's fields and never in their place. Billed on the client's Mistral key.",
                    fr: "Quelques lignes sur ce qui s'est passé au téléphone, à côté des champs de la fiche et jamais à leur place. Facturée sur la clé Mistral du client.",
                }}
            >
                {champsSynthese}
            </Intertitre>

            <Intertitre
                id="apres-appel-smtp"
                titre={{ en: "Mail server", fr: "Serveur de mail" }}
                description={{
                    en: "One mail per request, to the people its subject is routed to (« Team and routing »), else to the default recipients.",
                    fr: "Un mail par demande, aux personnes de son sujet (« Équipe et routage »), sinon aux destinataires par défaut.",
                }}
            >
                {champsSmtp}
                <div className="flex flex-wrap items-end gap-2">
                    <Input
                        className="max-w-xs"
                        aria-label={t({ en: "Test recipient", fr: "Destinataire de l'essai" })}
                        placeholder={t({ en: "you@example.org", fr: "vous@example.org" })}
                        value={destinataireEssai}
                        onChange={(e) => setDestinataireEssai(e.target.value.trim())}
                    />
                    <Button
                        size="sm"
                        variant="outline"
                        disabled={enCours || modifie || !ADRESSE.test(destinataireEssai)}
                        data-testid="essai-mail"
                        onClick={() =>
                            void agir(
                                () => postEssaiMailApiV1OrganizationsApresAppelEssaiMailPost({ body: { destinataire: destinataireEssai } }),
                                { en: "Test mail sent", fr: "Mail d'essai envoyé" },
                            )
                        }
                    >
                        {t({ en: "Send a test mail", fr: "Envoyer un mail d'essai" })}
                    </Button>
                </div>
                {modifie && (
                    <p className="text-xs text-muted-foreground">
                        {t({ en: "Save first: the test uses the saved server.", fr: "Enregistrer d'abord : l'essai utilise le serveur enregistré." })}
                    </p>
                )}
            </Intertitre>

            <Intertitre
                id="apres-appel-recapitulatif"
                titre={{ en: "Recap", fr: "Récapitulatif" }}
                description={{
                    en: "A mail of the requests that still wait for a call-back, to the default recipients, at the hours set (the organization's timezone).",
                    fr: "Un mail des demandes qui attendent encore un rappel, aux destinataires par défaut, aux heures réglées (fuseau de l'organisation).",
                }}
            >
                {champsRecap}
                <Button
                    size="sm"
                    variant="outline"
                    disabled={enCours || modifie || !ecran?.base_rattachee}
                    data-testid="recapitulatif-maintenant"
                    onClick={() => void agir(() => postRecapitulatifApiV1OrganizationsApresAppelRecapitulatifPost(), { en: "Recap sent", fr: "Récapitulatif envoyé" })}
                >
                    {t({ en: "Send the recap now", fr: "Envoyer le récapitulatif maintenant" })}
                </Button>
            </Intertitre>

            <Intertitre
                id="apres-appel-modules"
                titre={{ en: "Modules", fr: "Modules" }}
                description={{
                    en: "Set here, switched on agent by agent (« Call data »). Off by default.",
                    fr: "Réglés ici, allumés agent par agent (« Données de l'appel »). Éteints par défaut.",
                }}
            >
                {champsWebhook}
            </Intertitre>

            <Intertitre
                id="apres-appel-avance"
                titre={{ en: "Advanced", fr: "Avancé" }}
                description={{
                    en: "Delays, summary settings and retries that were fixed in the code. Current values by default; change them only for a reason.",
                    fr: "Délais, réglages de la synthèse et reprises qui étaient fixés dans le code. Valeurs d'avant par défaut ; à changer pour une raison précise.",
                }}
            >
                {champsAvances}
            </Intertitre>

            <Intertitre
                id="apres-appel-nuit"
                titre={{ en: "Night task", fr: "Tâche de nuit" }}
                description={{
                    en: "Every night: the purge, table by table (durations in « Client data »), and the day's counters. The result is kept as proof.",
                    fr: "Chaque nuit : la purge, table par table (durées dans « Données du client »), et les compteurs du jour. Le résultat est gardé comme preuve.",
                }}
            >
                <p className="text-sm" data-testid="derniere-nuit">
                    {nuit?.debut
                        ? `${t({ en: "Last run", fr: "Dernier passage" })} : ${new Date(nuit.debut).toLocaleString()} · ${nuit.statut} · ${Object.entries(nuit.resultat?.purge ?? {})
                              .map(([table, n]) => `${table} ${n}`)
                              .join(", ")}`
                        : t({ en: "Not run yet.", fr: "Pas encore passée." })}
                </p>
                <Button
                    size="sm"
                    variant="outline"
                    disabled={enCours || !ecran?.base_rattachee}
                    data-testid="purge-maintenant"
                    onClick={() => void agir(() => postNuitApiV1OrganizationsApresAppelNuitPost(), { en: "Purge done", fr: "Purge faite" })}
                >
                    {t({ en: "Run the purge now", fr: "Lancer la purge maintenant" })}
                </Button>
            </Intertitre>

            <BlocInstallationMark />
        </Theme>
    );
};

/** Le « Mail d'essai » de la maquette : un geste direct ; l'adresse du destinataire se donne dans une petite fenêtre. */
const EssaiMail = ({ enCours, bloque, envoyer }: { enCours: boolean; bloque: boolean; envoyer: (destinataire: string) => Promise<boolean> }) => {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    return (
        <>
            <Button variant="ghost" size="sm" disabled={enCours || bloque} data-testid="essai-mail" onClick={() => setOuverte(true)}>
                <Mail className="size-3.5" />
                {t({ en: "Test mail", fr: "Mail d'essai" })}
            </Button>
            <FenetreChamps
                ouverte={ouverte}
                fermer={() => setOuverte(false)}
                titre={t({ en: "Send a test mail", fr: "Envoyer un mail d'essai" })}
                info={t({ en: "The test uses the saved mail server.", fr: "L'essai utilise le serveur de mail enregistré." })}
                sections={[{ champs: [{ id: "destinataire", t: "texte", l: t({ en: "Test recipient", fr: "Destinataire de l'essai" }) }] }]}
                valider={t({ en: "Send", fr: "Envoyer" })}
                verifier={(v) => (ADRESSE.test(String(v.destinataire ?? "").trim()) ? null : { destinataire: t({ en: "Not a mail address.", fr: "Pas une adresse mail." }) })}
                onValider={(v) => envoyer(String(v.destinataire).trim())}
            />
        </>
    );
};
