"use client";

/**
 * [.mark] Clôture SA-5 (É11, Evan 09/11) : « Tout sur une page pour commencer » : sous la liste des configurations, la configuration
 * PRINCIPALE (celle des appels sortants par défaut) avec ses numéros et ses lignes sortantes (SIP), comme la maquette (`EcranTelephonie`).
 * Au plus simple : mêmes routes, mêmes fenêtres (`PhoneNumberDialog`) et même carte de lignes (`TrunkCard`) que la page de la configuration,
 * qui reste ouverte d'un clic pour tout le reste (identifiants, vérifications, numéro par défaut, suppression). Un chantier téléphonie
 * reprendra toute cette partie : rien ici n'est une abstraction nouvelle.
 */
import { Phone, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet,
    listPhoneNumbersApiV1OrganizationsTelephonyConfigsConfigIdPhoneNumbersGet,
} from "@/client/sdk.gen";
import type { PhoneNumberResponse, TelephonyConfigurationDetail, TelephonyConfigurationListItem } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { GroupePage } from "@/components/mark/studio/groupe-page";
import { Marque, PointEtat } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { PhoneNumberDialog } from "@/components/telephony/PhoneNumberDialog";
import { TrunkCard } from "@/components/telephony/TrunkCard";
import { Button } from "@/components/ui/button";

const T = {
    principale: { en: "Main configuration", fr: "Configuration principale" },
    principaleInfo: {
        en: "The one outbound calls use by default. The others are in the list above.",
        fr: "Celle que les appels sortants utilisent par défaut. Les autres sont dans la liste plus haut.",
    },
    ouvrir: { en: "Open the configuration", fr: "Ouvrir la configuration" },
    parDefaut: { en: "Default", fr: "Par défaut" },
    numeros: { en: "Numbers", fr: "Numéros" },
    numerosInfo: { en: "Click a number to open it.", fr: "Un clic sur un numéro l'ouvre." },
    numero: { en: "Number", fr: "Numéro" },
    entrants: { en: "Inbound calls go to", fr: "Appels entrants vers" },
    actif: { en: "Active", fr: "Actif" },
    inactif: { en: "Inactive", fr: "Inactif" },
    aucunAgent: { en: "no agent", fr: "aucun agent" },
    aucunNumero: { en: "No number yet", fr: "Aucun numéro encore" },
    sortants: { en: "Outbound calls", fr: "Appels sortants" },
    lignesSip: { en: "Outbound lines (SIP)", fr: "Lignes sortantes (SIP)" },
    entrantsGroupe: { en: "Inbound calls", fr: "Appels entrants" },
    illisible: { en: "Could not load the main configuration.", fr: "Impossible de lire la configuration principale." },
} satisfies Record<string, Texte>;

/** La configuration principale : celle des appels sortants par défaut, sinon la première active, sinon la première. */
export const configurationPrincipale = (items: TelephonyConfigurationListItem[]) =>
    items.find((i) => i.is_default_outbound && !i.inactive) ?? items.find((i) => !i.inactive) ?? items[0];

export function ConfigurationPrincipale({ item, apres }: { item: TelephonyConfigurationListItem; apres?: () => void | Promise<void> }) {
    const { t } = useLangue();
    const [detail, setDetail] = useState<TelephonyConfigurationDetail | null>(null);
    const [numeros, setNumeros] = useState<PhoneNumberResponse[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [dialogue, setDialogue] = useState<{ ouvert: boolean; numero: PhoneNumberResponse | null; ligne: number | null }>({ ouvert: false, numero: null, ligne: null });

    // Deux lectures en parallèle, jamais en chaîne.
    const lire = useCallback(async () => {
        const [cfg, liste] = await Promise.all([
            getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet({ path: { config_id: item.id } }),
            listPhoneNumbersApiV1OrganizationsTelephonyConfigsConfigIdPhoneNumbersGet({ path: { config_id: item.id } }),
        ]);
        if (cfg.error || liste.error) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setDetail(cfg.data ?? null);
        setNumeros(liste.data?.phone_numbers ?? []);
    }, [item.id]);
    useEffect(() => {
        void lire();
    }, [lire]);

    const apresEnregistrement = async () => {
        await lire();
        await apres?.();
    };
    const ouvrirNumero = (numero: PhoneNumberResponse | null, ligne: number | null = null) => setDialogue({ ouvert: true, numero, ligne });

    return (
        <div data-section="configuration-principale">
            <section aria-label={t(T.principale)}>
                <GroupePage titre={t(T.principale)} info={t(T.principaleInfo)} />
                <div className="mt-6 flex items-center gap-3 border-y py-3 text-sm">
                    <span className="font-medium">{item.name}</span>
                    <span className="text-muted-foreground">{item.provider}</span>
                    {item.is_default_outbound && <Marque ton="neutre">{t(T.parDefaut)}</Marque>}
                    <Link href={`/telephony-configurations/${item.id}`} className="ml-auto cursor-pointer hover:font-semibold">
                        {t(T.ouvrir)}
                    </Link>
                </div>
            </section>

            {erreur ? (
                <div className="pt-6">
                    <EtatVide cas="erreur" reessayer={() => void lire()} />
                </div>
            ) : (
                <>
                    <GroupePage titre={t(T.entrantsGroupe)} />
                    <section aria-label={t(T.numeros)}>
                        <TitreTableau
                            titre={t(T.numeros)}
                            action={
                                <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => ouvrirNumero(null)}>
                                    <Plus className="size-3.5" /> {t(T.numero)}
                                </Button>
                            }
                        />
                        {numeros === null ? (
                            <EtatVide cas="chargement" lignes={2} />
                        ) : numeros.length === 0 ? (
                            <EtatVide cas="premier" icone={Phone} titre={t(T.aucunNumero)} compact />
                        ) : (
                            <Tableau colonnes={[{ titre: t(T.numero) }, { titre: t(T.entrants) }, { titre: t(T.actif), droite: true }]}>
                                {numeros.map((n) => (
                                    <Ligne key={n.id} onClick={() => ouvrirNumero(n)}>
                                        <Cellule principale>{n.address}</Cellule>
                                        <Cellule>{n.inbound_workflow_name || t(T.aucunAgent)}</Cellule>
                                        <Cellule droite>
                                            <PointEtat etat={n.is_active ? "publie" : "attente"}>{n.is_active ? t(T.actif) : t(T.inactif)}</PointEtat>
                                        </Cellule>
                                    </Ligne>
                                ))}
                            </Tableau>
                        )}
                    </section>

                    {detail?.supports_trunks && numeros !== null && (
                        <>
                            <GroupePage titre={t(T.sortants)} />
                            <section aria-label={t(T.lignesSip)} className="pt-6">
                                <TrunkCard
                                    configuration={detail}
                                    phoneNumbers={numeros}
                                    onChanged={apresEnregistrement}
                                    onAddPhoneNumber={(ligne) => ouvrirNumero(null, ligne.id)}
                                    onEditPhoneNumber={(n) => ouvrirNumero(n)}
                                />
                            </section>
                        </>
                    )}
                </>
            )}

            <PhoneNumberDialog
                open={dialogue.ouvert}
                onOpenChange={(o) => setDialogue((d) => ({ ...d, ouvert: o }))}
                configId={item.id}
                trunks={detail?.trunks}
                defaultTrunkId={dialogue.ligne}
                existing={dialogue.numero}
                onSaved={() => void apresEnregistrement()}
            />
        </div>
    );
}
