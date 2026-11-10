"use client";

/**
 * [.mark] The organization's side of the outage fallback (chantier l-agent-travaille, L7, PN5),
 * in the theme « Integrations ». Acts at once (its own buttons), nothing of the theme's « Save ».
 *
 * - the emergency address: the TwiML Bin created ONCE in the client's Twilio console, with the
 *   text to paste shown here; used when our server is down (it knows no hours: its promise has
 *   no date);
 * - the catch-up: the calls lost while the server was down, rebuilt from Twilio's call log
 *   (also every hour, on its own);
 * - writing the emergency address on a number: a production gesture on the client's real
 *   number, done by hand.
 */
import { Copy, LifeBuoy, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    getPanneApiV1OrganizationsPanneGet,
    postAdresseDeSecoursApiV1OrganizationsPanneAdresseDeSecoursPost,
    postRattrapageApiV1OrganizationsPanneRattrapagePost,
    putPanneApiV1OrganizationsPannePut,
} from "@/client/sdk.gen";
import type { EcranPanne, ResultatRattrapage } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";

import { ChampReglage } from "../ecran/ChampReglage";
import { type ChampNumerique, ChampsNumeriques, horsBornes, SECONDES } from "../ecran/ChampsNumeriques";
import { type Texte, useLangue } from "../langue/langue";

/** Clôture, SA-3 (D18) : ce qui était une constante du code, réglable (avancé), valeurs d'avant par défaut, mêmes bornes que le serveur. */
export const CHAMPS_AVANCES_PANNE: ChampNumerique[] = [
    { cle: "delai_twilio_s", id: "panne-avance-delai-twilio", libelle: { en: "Twilio: time to answer", fr: "Twilio : délai de réponse" }, aide: { en: "Seconds Twilio has to answer one of our requests (hand-over of the call, call log, emergency address).", fr: "Secondes laissées à Twilio pour répondre à une de nos demandes (renvoi de l'appel, journal d'appels, adresse de secours)." }, min: 2, max: 30, pas: 1, defaut: 6, unite: SECONDES },
    { cle: "rattrapage_fenetre_h", id: "panne-avance-fenetre", libelle: { en: "Catch-up: hours read back", fr: "Rattrapage : heures relues" }, aide: { en: "How many hours back the call log is read to catch up on lost calls.", fr: "Combien d'heures en arrière le journal d'appels est relu pour rattraper les appels perdus." }, min: 1, max: 72, pas: 1, defaut: 24, unite: { en: "h", fr: "h" } },
    { cle: "rattrapage_attente_run_min", id: "panne-avance-attente", libelle: { en: "Catch-up: wait before counting a call lost", fr: "Rattrapage : attente avant de compter un appel perdu" }, aide: { en: "A call younger than this may still be finishing: it is not counted lost.", fr: "Un appel plus récent que cela peut encore se terminer : il n'est pas compté perdu." }, min: 1, max: 120, pas: 1, defaut: 10, unite: { en: "min", fr: "min" } },
];

function TexteDuBin({ id, titre, texte }: { id: string; titre: Texte; texte: string }) {
    const { t } = useLangue();
    return (
        <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{t(titre)}</span>
                <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={t({ en: "Copy the text of the Bin", fr: "Copier le texte du Bin" })}
                    onClick={() => {
                        void navigator.clipboard?.writeText(texte);
                        notifier.succes({ fr: "Copié.", en: "Copied." });
                    }}
                >
                    <Copy className="h-3.5 w-3.5" />
                </Button>
            </div>
            <Textarea id={id} readOnly rows={texte.split("\n").length + 1} className="font-mono text-xs" value={texte} />
        </div>
    );
}

export function BlocSecoursPanne() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [ecran, setEcran] = useState<EcranPanne | null>(null);
    const [url, setUrl] = useState("");
    const [urlPromesse, setUrlPromesse] = useState("");
    const [enCours, setEnCours] = useState(false);
    const [bilan, setBilan] = useState<ResultatRattrapage | null>(null);
    const [numero, setNumero] = useState("");
    const [avance, setAvance] = useState<Record<string, number>>({});
    const dejaLu = useRef(false);

    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            try {
                const r = await getPanneApiV1OrganizationsPanneGet();
                if (r.data) {
                    setEcran(r.data);
                    setUrl(r.data.reglages.url_secours ?? "");
                    setUrlPromesse(r.data.reglages.url_secours_promesse ?? "");
                    setAvance(Object.fromEntries(CHAMPS_AVANCES_PANNE.map((c) => [c.cle, (r.data.reglages as Record<string, unknown>)[c.cle] as number])));
                }
            } catch {
                // Unreachable: the block stays hidden, the theme works without it.
            }
        })();
    }, [loading, user]);

    if (!ecran) return null;
    const modifie =
        (ecran.reglages.url_secours ?? "") !== url.trim() || (ecran.reglages.url_secours_promesse ?? "") !== urlPromesse.trim();

    const modifieAvance = CHAMPS_AVANCES_PANNE.some((c) => avance[c.cle] !== (ecran.reglages as Record<string, unknown>)[c.cle]);
    const faute = CHAMPS_AVANCES_PANNE.some((c) => horsBornes(c, avance[c.cle]));
    const enregistrerAvance = async () => {
        setEnCours(true);
        const r = await putPanneApiV1OrganizationsPannePut({ body: { ...ecran.reglages, ...avance } });
        setEnCours(false);
        if (r.error || !r.data) {
            notifier.echec({ fr: "Réglages avancés de la panne non enregistrés. Réessayez.", en: "Advanced outage settings not saved. Try again." }, { erreur: r.error });
            return;
        }
        setEcran(r.data);
        setAvance(Object.fromEntries(CHAMPS_AVANCES_PANNE.map((c) => [c.cle, (r.data as { reglages: Record<string, unknown> }).reglages[c.cle] as number])));
        notifier.succes({ fr: "Réglages avancés de la panne enregistrés.", en: "Advanced outage settings saved." });
    };

    const enregistrer = async () => {
        setEnCours(true);
        const r = await putPanneApiV1OrganizationsPannePut({ body: { ...ecran.reglages, url_secours: url.trim() || null, url_secours_promesse: urlPromesse.trim() || null } });
        setEnCours(false);
        if (r.error || !r.data) {
            notifier.echec({ fr: "Adresse de secours non enregistrée. Réessayez.", en: "Fallback address not saved. Try again." }, { erreur: r.error });
            return;
        }
        setEcran(r.data);
        notifier.succes({ fr: "Adresse de secours enregistrée.", en: "Fallback address saved." });
    };

    const rattraper = async () => {
        setEnCours(true);
        const r = await postRattrapageApiV1OrganizationsPanneRattrapagePost();
        setEnCours(false);
        if (r.error || !r.data) {
            notifier.echec({ fr: "Rattrapage impossible. Réessayez.", en: "Catch-up failed. Try again." }, { erreur: r.error });
            return;
        }
        setBilan(r.data);
    };

    const ecrireSurLeNumero = async () => {
        setEnCours(true);
        const r = await postAdresseDeSecoursApiV1OrganizationsPanneAdresseDeSecoursPost({ body: { numero: numero.trim(), effacer: false } });
        setEnCours(false);
        if (r.error || !r.data) {
            notifier.echec({ fr: "Adresse non écrite sur le numéro. Réessayez.", en: "Address not written to the number. Try again." }, { erreur: r.error });
            return;
        }
        if (r.data.ecrit) notifier.succes({ fr: "Adresse écrite sur le numéro chez Twilio.", en: "Address written on the number at Twilio." });
        else notifier.information({ fr: "Rien à écrire pour ce numéro.", en: "Nothing to write for this number." });
    };

    return (
        <div className="space-y-4" id="panne-secours">
            <ChampReglage
                cle="panne.url_secours"
                idControle="panne-url-secours"
                libelle={{ en: "Emergency address (TwiML Bin)", fr: "Adresse de secours (TwiML Bin)" }}
                aides={[
                    {
                        en: "Used when our server is down, for the agents that switched the outage fallback on: Twilio says the hand-over sentence and rings the establishment's second number, else promises a call-back (without a date: the Bin knows no hours). Create the Bin once in the client's Twilio console with the text below, then paste its address here.",
                        fr: "Utilisée quand notre serveur est tombé, pour les agents qui ont allumé le repli de panne : Twilio dit la phrase de renvoi et fait sonner le second numéro de l'établissement, sinon promet un rappel (sans date : le Bin ne connaît pas les horaires). Créez le Bin une fois dans la console Twilio du client avec le texte ci-dessous, puis collez son adresse ici.",
                    },
                ]}
            >
                <div className="flex flex-wrap gap-2">
                    <Input
                        id="panne-url-secours"
                        className="min-w-0 flex-1"
                        value={url}
                        placeholder="https://handler.twilio.com/twiml/EH…"
                        onChange={(e) => setUrl(e.target.value)}
                    />
                    <Button type="button" size="sm" disabled={!modifie || enCours} onClick={() => void enregistrer()}>
                        <LifeBuoy className="mr-2 h-3.5 w-3.5" />
                        {t({ en: "Save the address", fr: "Enregistrer l'adresse" })}
                    </Button>
                </div>
            </ChampReglage>
            <ChampReglage
                cle="panne.url_secours_promesse"
                idControle="panne-url-secours-promesse"
                libelle={{ en: "Emergency address « promise only » (second TwiML Bin)", fr: "Adresse de secours « promesse seule » (second TwiML Bin)" }}
                aides={[
                    {
                        en: "For the establishments without a second number: Twilio only promises a call-back and hangs up. Create this second Bin with the second text below. Empty: they get the first Bin (its ringing fails, then the promise).",
                        fr: "Pour les établissements sans second numéro : Twilio promet seulement un rappel et raccroche. Créez ce second Bin avec le second texte ci-dessous. Vide : ils reçoivent le premier Bin (sa sonnerie échoue, puis la promesse).",
                    },
                ]}
            >
                <Input
                    id="panne-url-secours-promesse"
                    className="min-w-0"
                    value={urlPromesse}
                    placeholder="https://handler.twilio.com/twiml/EH…"
                    onChange={(e) => setUrlPromesse(e.target.value)}
                />
            </ChampReglage>
            <TexteDuBin
                id="panne-texte-bin"
                titre={{ en: "Text of the TwiML Bin « hand-over then promise », to paste in the Twilio console:", fr: "Texte du TwiML Bin « renvoi puis promesse », à coller dans la console Twilio :" }}
                texte={ecran.texte_du_bin}
            />
            <TexteDuBin
                id="panne-texte-bin-promesse"
                titre={{ en: "Text of the TwiML Bin « promise only »:", fr: "Texte du TwiML Bin « promesse seule » :" }}
                texte={ecran.texte_du_bin_promesse}
            />
            <div className="flex flex-wrap items-center gap-3">
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-auto max-w-full whitespace-normal py-1.5 text-left"
                    disabled={enCours}
                    onClick={() => void rattraper()}
                >
                    <RefreshCw className="mr-2 h-3.5 w-3.5" />
                    {t({ en: "Catch up the calls lost during an outage", fr: "Rattraper les appels perdus pendant une panne" })}
                </Button>
                {bilan && (
                    <span className="text-xs text-muted-foreground" id="panne-bilan-rattrapage">
                        {t({
                            en: `${bilan.appels_lus} calls read · ${bilan.demandes_creees} request(s) to call back created · ${bilan.deja_connus} already known`,
                            fr: `${bilan.appels_lus} appels lus · ${bilan.demandes_creees} demande(s) à rappeler créée(s) · ${bilan.deja_connus} déjà connue(s)`,
                        })}
                        {bilan.erreurs.length > 0 && ` · ${bilan.erreurs.join(" ; ")}`}
                    </span>
                )}
            </div>
            <ChampReglage
                cle="panne.adresse_de_secours"
                idControle="panne-numero-secours"
                libelle={{ en: "Write the emergency address on a number", fr: "Écrire l'adresse de secours sur un numéro" }}
                aides={[
                    {
                        en: "⚠️ Changes the client's real number at Twilio (its fallback URL), for the calls our server cannot answer at all. One of this organization's Twilio numbers.",
                        fr: "⚠️ Modifie le vrai numéro du client chez Twilio (son adresse de repli), pour les appels que notre serveur ne peut pas décrocher du tout. Un des numéros Twilio de cette organisation.",
                    },
                ]}
            >
                <div className="flex flex-wrap gap-2">
                    <Input id="panne-numero-secours" className="min-w-0 flex-1" value={numero} placeholder="+33…" onChange={(e) => setNumero(e.target.value)} />
                    <Button type="button" variant="outline" size="sm" disabled={!numero.trim() || !(ecran.reglages.url_secours || ecran.reglages.url_secours_promesse) || enCours} onClick={() => void ecrireSurLeNumero()}>
                        {t({ en: "Write at Twilio", fr: "Écrire chez Twilio" })}
                    </Button>
                </div>
            </ChampReglage>
            <div className="space-y-2 pt-2" id="panne-avance">
                <div>
                    <p className="text-sm font-medium">{t({ en: "Advanced", fr: "Avancé" })}</p>
                    <p className="text-xs text-muted-foreground">
                        {t({
                            en: "Delays that were fixed in the code. Current values by default; change them only for a reason.",
                            fr: "Délais qui étaient fixés dans le code. Valeurs d'avant par défaut ; à changer pour une raison précise.",
                        })}
                    </p>
                </div>
                <ChampsNumeriques champs={CHAMPS_AVANCES_PANNE} valeur={(cle) => avance[cle]} poser={(cle, v) => setAvance((a) => ({ ...a, [cle]: v }))} />
                <Button type="button" size="sm" disabled={!modifieAvance || faute || enCours} onClick={() => void enregistrerAvance()} data-testid="enregistrer-panne-avance">
                    {t({ en: "Save the advanced settings", fr: "Enregistrer l'avancé" })}
                </Button>
            </div>
        </div>
    );
}
