"use client";

/**
 * [.mark] Clôture, SA-3 (D18) : les limites que le moteur du planificateur tenait du code (adresses placées, délais, mémoire,
 * durée d'une prise de rendez-vous), réglables au niveau « avancé » de l'organisation. Valeurs d'avant par défaut, mêmes
 * bornes que le serveur. Propres à l'organisation : elles ne dépendent ni d'un établissement ni de la base du client.
 * Même forme que les autres sections de l'onglet : lignes en lecture, « Modifier » ouvre le panneau, notification du résultat.
 */
import { useEffect, useState } from "react";

import { getPlanificateurMoteurApiV1OrganizationsPlanificateurMoteurGet, putPlanificateurMoteurApiV1OrganizationsPlanificateurMoteurPut } from "@/client/sdk.gen";
import type { ReglagesMoteurPlanificateur } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

import { type ChampNumerique, SECONDES, texteBornesNumerique } from "../ecran/ChampsNumeriques";
import { type Texte, useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import type { Valeurs } from "../studio/fenetre-champs";
import { SectionLue } from "./section-lue";

type Cle = keyof ReglagesMoteurPlanificateur;
type Champ = Omit<ChampNumerique, "cle" | "id"> & { cle: Cle };

export const CHAMPS_MOTEUR_PLANIFICATEUR: Champ[] = [
    { cle: "max_lieux", libelle: { en: "Addresses placed per call", fr: "Adresses placées par appel" }, aide: { en: "Most distinct addresses of the agendas placed on the map for one call; the others are left out.", fr: "Nombre maximal d'adresses distinctes des agendas placées sur la carte pour un appel ; les autres sont laissées de côté." }, min: 1, max: 200, pas: 1, defaut: 40, unite: SECONDES },
    { cle: "parallele_lieux", libelle: { en: "Addresses placed at once", fr: "Adresses placées en même temps" }, aide: { en: "How many addresses are sent to the address service at the same time.", fr: "Combien d'adresses partent en même temps vers le service d'adresses." }, min: 1, max: 20, pas: 1, defaut: 8, unite: SECONDES },
    { cle: "temps_max_lieux_s", libelle: { en: "Time to place the addresses", fr: "Temps pour placer les adresses" }, aide: { en: "Seconds at most spent placing the addresses of the agendas; what is not placed in time is said, never invented.", fr: "Secondes au plus passées à placer les adresses des agendas ; ce qui n'est pas placé à temps est dit, jamais inventé." }, min: 0.5, max: 10, pas: 0.5, defaut: 2.5, unite: SECONDES },
    { cle: "geocodage_delai_s", libelle: { en: "Address service: time to answer", fr: "Service d'adresses : délai de réponse" }, aide: { en: "Seconds the address service has to answer for one address.", fr: "Secondes laissées au service d'adresses pour répondre à une adresse." }, min: 0.5, max: 10, pas: 0.5, defaut: 1.5, unite: SECONDES },
    { cle: "geocodage_score_min", libelle: { en: "Address service: lowest confidence", fr: "Service d'adresses : confiance minimale" }, aide: { en: "Below this score (0 to 1) a placed address is not believed.", fr: "En dessous de ce score (de 0 à 1), une adresse placée n'est pas crue." }, min: 0.1, max: 1, pas: 0.05, defaut: 0.6, unite: { en: "", fr: "" } },
    { cle: "geocodage_memoire_s", libelle: { en: "Address service: memory", fr: "Service d'adresses : mémoire" }, aide: { en: "Seconds an address already placed is remembered, to avoid asking again.", fr: "Secondes pendant lesquelles une adresse déjà placée est retenue, pour ne pas la redemander." }, min: 60, max: 86400, pas: 60, defaut: 3600, unite: SECONDES },
    { cle: "pose_duree_s", libelle: { en: "Booking in progress: how long it is kept", fr: "Prise de rendez-vous en cours : durée gardée" }, aide: { en: "Seconds the state of a booking in progress is kept, so a repeated request never books twice.", fr: "Secondes pendant lesquelles l'état d'une prise de rendez-vous en cours est gardé, pour qu'une demande répétée ne réserve jamais deux fois." }, min: 600, max: 86400, pas: 600, defaut: 14400, unite: SECONDES },
];
// Les lieux ne sont pas des secondes : la bonne unité par champ.
const UNITE: Partial<Record<Cle, Texte>> = {
    max_lieux: { en: "addresses", fr: "adresses" },
    parallele_lieux: { en: "at once", fr: "à la fois" },
    geocodage_score_min: { en: "", fr: "" },
};
const unite = (c: Champ): Texte => UNITE[c.cle] ?? c.unite;

export function SectionMoteurPlanificateur() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [reglages, setReglages] = useState<ReglagesMoteurPlanificateur | null>(null);

    useEffect(() => {
        if (loading || !user) return;
        let annule = false;
        void (async () => {
            const r = await getPlanificateurMoteurApiV1OrganizationsPlanificateurMoteurGet();
            if (!annule && r?.data) setReglages(r.data);
        })();
        return () => {
            annule = true;
        };
    }, [loading, user]);

    if (!reglages) return null;
    const valeur = (c: Champ) => (reglages[c.cle] as number | undefined) ?? c.defaut;
    const texte = (c: Champ) => `${valeur(c)}${t(unite(c)) ? ` ${t(unite(c))}` : ""}`;
    const lire = (v: Valeurs, c: Champ) => (String(v[c.cle]).trim() === "" ? Number.NaN : Number(v[c.cle]));

    return (
        <SectionLue
            titre={t({ en: "Advanced: engine limits", fr: "Avancé : limites du moteur" })}
            info={t({
                en: "Limits that were fixed in the code: addresses placed, delays, memory. Current values by default; change them only for a reason. They apply to the whole organization.",
                fr: "Limites qui étaient fixées dans le code : adresses placées, délais, mémoire. Valeurs d'avant par défaut ; à changer pour une raison précise. Elles valent pour toute l'organisation.",
            })}
            lignes={CHAMPS_MOTEUR_PLANIFICATEUR.map((c): [string, string] => [t(c.libelle), texte(c)])}
            fenetre={{
                titre: t({ en: "Advanced: engine limits", fr: "Avancé : limites du moteur" }),
                sections: [
                    {
                        champs: CHAMPS_MOTEUR_PLANIFICATEUR.map((c) => ({
                            id: c.cle,
                            t: "nombre" as const,
                            l: t(c.libelle),
                            v: String(valeur(c)),
                            min: c.min,
                            max: c.max,
                            unite: t(unite(c)) || undefined,
                            info: `${t(c.aide)} (${t(texteBornesNumerique({ ...c, id: c.cle }))})`,
                        })),
                    },
                ],
            }}
            verifier={(v) => {
                const fautes: Record<string, string> = {};
                for (const c of CHAMPS_MOTEUR_PLANIFICATEUR) {
                    const n = lire(v, c);
                    if (!(Number.isFinite(n) && n >= c.min && n <= c.max)) fautes[c.cle] = t({ en: `A number from ${c.min} to ${c.max}.`, fr: `Un nombre de ${c.min} à ${c.max}.` });
                }
                return Object.keys(fautes).length ? fautes : null;
            }}
            onValider={async (v) => {
                const corps = Object.fromEntries(CHAMPS_MOTEUR_PLANIFICATEUR.map((c) => [c.cle, lire(v, c)])) as ReglagesMoteurPlanificateur;
                const r = await putPlanificateurMoteurApiV1OrganizationsPlanificateurMoteurPut({ body: corps });
                if (r.error || !r.data) {
                    notifier.echec({ fr: "Les limites du moteur n'ont pas été enregistrées.", en: "The engine limits were not saved." }, { erreur: r.error });
                    return false;
                }
                setReglages(r.data);
                notifier.succes({ fr: "Limites du moteur enregistrées.", en: "Engine limits saved." });
                return true;
            }}
        />
    );
}
