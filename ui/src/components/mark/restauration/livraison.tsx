"use client";

/**
 * [.mark] Module Restauration, lot 12 (F3) : l'onglet « Livraison » d'Entreprise.
 *
 * Reprend la maquette (`livraison.tsx`, `zones-visuel.tsx`) sur les vraies données (``GET …/livraison``) : le curseur de kilomètres (le composant
 * `Curseur` de production), les communes trouvées avec leur distance rangées en zones d'un clic, les zones par communes ou par rayons, le tableau des
 * zones (frais, minimum, délai de livraison, seuil de gratuité) et le schéma des cercles, aux couleurs `--zone-1` à `--zone-5`, INDÉPENDANT du curseur,
 * sans point ni nom de commune.
 *
 * Une zone « par rayons » accepte tout ce qui est dans son cercle ; « par communes », les communes rangées dedans (le cercle sert alors au schéma et
 * au rangement). Une commune refusée n'est jamais livrée, même dans un cercle. Les frais particuliers d'une commune ne sont pas faits (rien ne les
 * porte dans le classeur). Chaque geste écrit tout de suite (`PUT …/livraison/zones`) et relit le résultat.
 */
import { ListChecks, MapPin, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Curseur } from "@/components/ui/curseur";
import { Switch } from "@/components/ui/switch";

import { notifier } from "../notifications";
import { echecAffiche } from "../notifications/echec-affiche";
import { ECHECS } from "../notifications/phrases-echec";
import { Champs, FenetreOnglets, LigneChamp as Ligne, Section } from "../studio/fenetre-onglets";
import { Info, Marque } from "../studio/marques";
import { Cellule, Ligne as LigneT, Tableau, TitreTableau } from "../studio/tableau";
import { centimes, Confirmer, EcranDonnees, euros, Nombre, Segment3, SelecteurEtab, useTexte } from "./commun";
import { useCharge, useModuleRestauration } from "./contexte";
import { type CommuneTrouvee, ecrireLesZones, lireLaLivraison, type LivraisonRendue, type Zone } from "./donnees";
import { BadgeZone, couleurZone, SchemaZones, texteZone } from "./zones-visuel";

const RAYON_LU_KM = 30; // les communes se lisent une fois jusqu'à 30 km ; le curseur filtre sans relire
const MAX_ZONES = 5;
type ZoneL = Zone & { id: number };

const dite = (z: Zone) => ({ frais_centimes: z.frais, minimum_centimes: z.minimum });

export function OngletLivraison() {
    const t = useTexte();
    const { etab } = useModuleRestauration();
    const { donnee: liv, etat, relire, poser } = useCharge(etab === null ? null : () => lireLaLivraison(etab, RAYON_LU_KM), `livraison-${etab}`, ECHECS.restaurationLivraison);
    const [rayon, setRayon] = useState(12);
    const [zone, setZone] = useState<number | null>(null);
    const [exception, setException] = useState<string | null>(null);
    const [retrait, setRetrait] = useState<ZoneL | null>(null);

    const zones: ZoneL[] = [...(liv?.zones ?? [])].sort((a, b) => (a.cercle_km ?? 0) - (b.cercle_km ?? 0));
    const mode: "communes" | "rayons" = zones.length > 0 && zones.every((z) => z.forme === "rayon") ? "rayons" : "communes";
    const trouvees = (liv?.communes ?? []).filter((c) => c.km <= rayon);
    const rang = (id: number | null) => (id === null ? null : zones.findIndex((z) => z.id === id));

    /** Écrit l'ensemble des zones (triées par cercle : la couleur est le rang) et remplace l'état par le résultat. */
    const ecrire = async (nouvelles: Zone[], message?: { fr: string; en: string }) => {
        if (etab === null) return false;
        const triees = [...nouvelles].sort((a, b) => (a.cercle_km ?? 0) - (b.cercle_km ?? 0));
        const r = await ecrireLesZones(etab, triees, RAYON_LU_KM);
        if (r.error || !r.data) {
            echecAffiche(r.error, ECHECS.restaurationLivraisonEnregistrer);
            return false;
        }
        poser(r.data as LivraisonRendue);
        if (message) notifier.succes(message);
        return true;
    };
    /** Range les communes trouvées dans la première zone dont le cercle les contient ; les refusées n'entrent nulle part. */
    const rangees = (cibles: ZoneL[]): ZoneL[] =>
        cibles.map((z) => ({ ...z, forme: "communes" as const, communes: [] })).map((z, _i, tout) => {
            const mienne = (liv?.communes ?? []).filter((c) => !c.refusee && tout.find((x) => (x.cercle_km ?? 0) >= c.km)?.id === z.id).map((c) => c.insee);
            return { ...z, communes: mienne };
        });
    const ranger = () => void ecrire(rangees(zones), { fr: "Communes rangées dans les zones d'après leur distance.", en: "Towns sorted into zones by distance." });
    const changerMode = (v: "communes" | "rayons") => {
        if (v === mode || zones.length === 0) return;
        if (v === "rayons") void ecrire(zones.map((z) => ({ ...z, forme: "rayon" as const, communes: [] })), { fr: "Zones par rayons : tout ce qui est dans un cercle est livré.", en: "Zones by radii: anything inside a circle is delivered." });
        else void ecrire(rangees(zones), { fr: "Zones par communes : les communes rangées dans une zone sont livrées.", en: "Zones by towns: towns sorted into a zone are delivered." });
    };
    const ajouter = async () => {
        const km = Math.min(RAYON_LU_KM, Math.round(((zones.at(-1)?.cercle_km ?? 0) + 4) * 10) / 10);
        const neuve: Zone = { id: null, nom: `${t("Zone", "Zone")} ${zones.length + 1}`, forme: mode === "rayons" ? "rayon" : "communes", cercle_km: km, communes: [], exclues: [...new Set(zones.flatMap((z) => z.exclues))], frais: 500, minimum: 3000, gratuite_des: null, delai: 60 };
        if (await ecrire([...zones, neuve], { fr: `Cercle de ${km} km ajouté.`, en: `${km} km circle added.` })) setZone(-1);
    };

    const exceptionChoisie = exception ? (liv?.communes ?? []).find((c) => c.insee === exception) : undefined;
    const zoneChoisie = zone !== null && zone > 0 ? zones.find((z) => z.id === zone) : zone === -1 ? zones.at(-1) : undefined;
    return (
        <EcranDonnees etat={etab === null ? "pret" : etat} relire={() => void relire()} vide={etab === null} iconeVide={MapPin} titreVide={t("Aucun établissement dans la base du client", "No site in the client's database")}>
            <div className="flex flex-wrap items-center gap-3 pt-2">
                <SelecteurEtab />
                <span className="flex-1" />
                <Segment3 valeur={mode} changer={changerMode} options={[{ v: "communes", l: t("Par communes", "By towns") }, { v: "rayons", l: t("Par rayons", "By radii") }]} />
                <Info>
                    {t(
                        "Aucune carte dessinée : un schéma de cercles, et les communes trouvées avec leur distance. Par communes : l'agent accepte les communes rangées dans une zone. Par rayons : il accepte tout ce qui est dans un cercle.",
                        "No map: a circle diagram and the towns found with their distance. By towns: the agent accepts towns sorted into a zone. By radii: anything inside a circle.",
                    )}
                </Info>
            </div>
            {liv && !liv.centre_connu && (
                <p className="text-sm text-muted-foreground" role="status">
                    {t("La commune de cet établissement n'est pas connue : renseignez son adresse dans sa fiche pour chercher les communes autour.", "This site's town is not known: fill in its address in its sheet to look for towns around it.")}
                </p>
            )}
            <div className="@container">
                <div className="grid items-start gap-8 @4xl:grid-cols-[360px_1fr]">
                    <div className="space-y-4">
                        {zones.length > 0 && (
                            <SchemaZones
                                choisi={zoneChoisie ? String(zoneChoisie.id) : null}
                                libelle={t("Schéma des zones de livraison autour du restaurant", "Delivery zones around the restaurant")}
                                cercles={zones.map((z, i) => ({ cle: String(z.id), km: z.cercle_km ?? 1, rang: i, texte: texteZone(dite(z), t) }))}
                            />
                        )}
                        <div className="space-y-1.5">
                            <label className="flex items-center justify-between text-sm">
                                <span className="font-medium">{t("Chercher les communes jusqu'à", "Look for towns up to")}</span>
                                <b className="tabular-nums">{rayon} km</b>
                            </label>
                            <Curseur min={1} max={RAYON_LU_KM} step={1} value={rayon} onChange={(e) => setRayon(Number(e.target.value))} aria-label={t("Distance en kilomètres", "Distance in kilometres")} className="w-full" />
                            <p className="text-xs text-muted-foreground">
                                {trouvees.length} {t(`communes trouvées à moins de ${rayon} km de`, `towns found within ${rayon} km of`)} {liv?.commune ?? t("l'établissement", "the site")}
                            </p>
                        </div>
                    </div>
                    <div className="min-w-0 space-y-1">
                        <TitreTableau
                            titre={t("Communes trouvées", "Towns found")}
                            info={<Info>{t("Rangées en zones d'un clic d'après leur distance au restaurant ; une commune refusée prend le dessus sur la zone.", "Sorted into zones in one click by distance; a refused town takes precedence over the zone.")}</Info>}
                            action={mode === "communes" ? <Button variant="outline" size="sm" className="cursor-pointer" disabled={zones.length === 0} onClick={ranger}><ListChecks className="size-3.5" /> {t("Ranger en zones", "Sort into zones")}</Button> : undefined}
                        />
                        <Tableau colonnes={[{ titre: t("Commune", "Town") }, { titre: t("Distance", "Distance"), droite: true }, { titre: t("Zone", "Zone") }, { titre: t("Exception", "Exception"), secondaire: 1 }]}>
                            {trouvees.map((c) => {
                                const r = rang(c.zone_id);
                                const livree = !c.refusee && r !== null;
                                return (
                                    <LigneT key={c.insee} onClick={() => setException(c.insee)}>
                                        <Cellule principale>{c.nom}</Cellule>
                                        <Cellule droite>{String(c.km).replace(".", ",")} km</Cellule>
                                        <Cellule>
                                            {livree && c.zone_id !== null ? <BadgeZone rang={r} texte={texteZone(dite(zones[r!]), t)} onClick={() => setException(c.insee)} titre={zones[r!].nom} /> : <BadgeZone rang={null} texte={t("Pas livrée", "Not delivered")} onClick={() => setException(c.insee)} />}
                                        </Cellule>
                                        <Cellule>{c.refusee ? <Marque ton="danger">{t("refusée", "refused")}</Marque> : "–"}</Cellule>
                                    </LigneT>
                                );
                            })}
                        </Tableau>
                    </div>
                </div>
            </div>
            <TitreTableau
                titre={t("Cercles et règles", "Circles and rules")}
                info={<Info>{t("Chaque cercle a ses frais, son minimum de commande, son délai de livraison et le seuil à partir duquel la livraison est offerte.", "Each circle has its fee, order minimum, delivery time and the threshold above which delivery is free.")}</Info>}
                action={<Button variant="outline" size="sm" className="cursor-pointer" disabled={zones.length >= MAX_ZONES} onClick={() => void ajouter()}><Plus className="size-3.5" /> {t("Cercle", "Circle")}</Button>}
            />
            <Tableau colonnes={[{ titre: t("Cercle", "Circle") }, { titre: t("Rayon", "Radius"), droite: true }, { titre: t("Frais", "Fee"), droite: true }, { titre: t("Minimum", "Minimum"), droite: true, secondaire: 2 }, { titre: t("Délai de livraison", "Delivery time"), droite: true, secondaire: 3 }, { titre: t("Offerte dès", "Free from"), droite: true, secondaire: 1 }]}>
                {zones.map((z, i) => (
                    <LigneT key={z.id} onClick={() => setZone(z.id)}>
                        <Cellule principale><span className="inline-flex items-center gap-2"><span className="size-2.5 rounded-full" style={{ background: couleurZone(i) }} />{z.nom}</span></Cellule>
                        <Cellule droite>{z.cercle_km} km</Cellule>
                        <Cellule droite>{z.frais ? euros(z.frais) : t("Gratuit", "Free")}</Cellule>
                        <Cellule droite>{euros(z.minimum)}</Cellule>
                        <Cellule droite>{z.delai} min</Cellule>
                        <Cellule droite>{z.gratuite_des ? euros(z.gratuite_des) : "–"}</Cellule>
                    </LigneT>
                ))}
            </Tableau>
            {etat === "pret" && zones.length === 0 && <p className="text-sm text-muted-foreground">{t("Aucune zone : l'agent ne livre nulle part. Ajoutez un cercle.", "No zone: the agent delivers nowhere. Add a circle.")}</p>}

            {zoneChoisie && (
                <PanneauZone
                    key={zoneChoisie.id}
                    z={zoneChoisie}
                    fermer={() => setZone(null)}
                    enregistrer={async (z) => {
                        if (await ecrire(zones.map((x) => (x.id === z.id ? z : x)), { fr: "Zone enregistrée.", en: "Zone saved." })) setZone(null);
                    }}
                    retirer={() => setRetrait(zoneChoisie)}
                />
            )}
            {exceptionChoisie && (
                <PanneauCommune
                    key={exceptionChoisie.insee}
                    c={exceptionChoisie}
                    zones={zones}
                    mode={mode}
                    fermer={() => setException(null)}
                    enregistrer={async (zoneId, refusee) => {
                        const insee = exceptionChoisie.insee;
                        const nouvelles = zones.map((z) => ({
                            ...z,
                            exclues: refusee ? [...new Set([...z.exclues, insee])] : z.exclues.filter((x) => x !== insee),
                            communes: mode === "communes" ? (z.id === zoneId ? [...new Set([...z.communes, insee])] : z.communes.filter((x) => x !== insee)) : z.communes,
                        }));
                        if (await ecrire(nouvelles, { fr: `${exceptionChoisie.nom} : enregistré.`, en: `${exceptionChoisie.nom}: saved.` })) setException(null);
                    }}
                />
            )}
            {retrait && (
                <Confirmer
                    titre={t(`Retirer « ${retrait.nom} » ?`, `Remove “${retrait.nom}”?`)}
                    texte={t("Les communes de ce cercle ne seront plus livrées tant qu'elles ne sont pas rangées dans une autre zone. Les commandes passées gardent leur historique.", "Towns in this circle will no longer be delivered until they are sorted into another zone. Past orders keep their history.")}
                    bouton={t("Retirer le cercle", "Remove circle")}
                    fermer={() => setRetrait(null)}
                    valider={() => {
                        const id = retrait.id;
                        void ecrire(zones.filter((x) => x.id !== id), { fr: "Cercle retiré.", en: "Circle removed." }).then((ok) => ok && setZone(null));
                    }}
                />
            )}
        </EcranDonnees>
    );
}

function PanneauZone({ z, fermer, enregistrer, retirer }: { z: ZoneL; fermer: () => void; enregistrer: (z: ZoneL) => void; retirer: () => void }) {
    const t = useTexte();
    const [initial] = useState(() => ({ nom: z.nom, km: String(z.cercle_km ?? ""), frais: String(z.frais / 100), min: String(z.minimum / 100), delai: String(z.delai), offre: z.gratuite_des !== null, seuil: z.gratuite_des !== null ? String(z.gratuite_des / 100) : "" }));
    const [v, setV] = useState(initial);
    const champ = (k: keyof typeof v) => (x: string) => setV({ ...v, [k]: x });
    const km = Number(v.km);
    const valide = v.nom.trim().length > 0 && km > 0 && km <= RAYON_LU_KM && Number(v.delai) >= 0;
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={z.nom}
            sous={`${z.cercle_km} km`}
            valider={t("Enregistrer", "Save")}
            desactiver={!valide}
            modifie={JSON.stringify(v) !== JSON.stringify(initial)}
            pied={<Button variant="ghost" size="sm" className="cursor-pointer text-destructive" onClick={retirer}><Trash2 className="size-3.5" /> {t("Retirer le cercle", "Remove circle")}</Button>}
            onValider={() =>
                enregistrer({ ...z, nom: v.nom.trim(), cercle_km: km, frais: centimes(v.frais), minimum: centimes(v.min), delai: Math.round(Number(v.delai)) || 0, gratuite_des: v.offre ? centimes(v.seuil || "0") : null })
            }
        >
            <Section titre={t("Règles du cercle", "Circle rules")}>
                <Champs>
                    <Ligne libelle={t("Nom", "Name")}>
                        <input value={v.nom} onChange={(e) => champ("nom")(e.target.value)} aria-label={t("Nom", "Name")} maxLength={80} className="h-8 w-44 rounded-md border bg-background px-2 text-sm" />
                    </Ligne>
                    <Ligne libelle={t("Rayon", "Radius")} info={t(`Jusqu'à ${RAYON_LU_KM} km.`, `Up to ${RAYON_LU_KM} km.`)}><Nombre valeur={v.km} changer={champ("km")} unite="km" min={1} max={RAYON_LU_KM} libelle={t("Rayon", "Radius")} /></Ligne>
                    <Ligne libelle={t("Frais de livraison", "Delivery fee")}><Nombre valeur={v.frais} changer={champ("frais")} unite="€" min={0} libelle={t("Frais de livraison", "Delivery fee")} /></Ligne>
                    <Ligne libelle={t("Minimum de commande", "Order minimum")}><Nombre valeur={v.min} changer={champ("min")} unite="€" min={0} libelle={t("Minimum de commande", "Order minimum")} /></Ligne>
                    <Ligne libelle={t("Délai de livraison", "Delivery time")} info={t("Ce que l'agent annonce pour cette zone : « livrée dans 40 minutes ». Le temps ajouté pendant le service vient par-dessus.", "What the agent says for this zone: “delivered in 40 minutes”. Time added during service comes on top.")}>
                        <Nombre valeur={v.delai} changer={champ("delai")} unite="min" min={0} libelle={t("Délai de livraison", "Delivery time")} />
                    </Ligne>
                    <Ligne libelle={t("Livraison offerte au-dessus d'un seuil", "Free delivery above a threshold")}>
                        <Switch checked={v.offre} onCheckedChange={(x) => setV({ ...v, offre: x, seuil: v.seuil || "35" })} aria-label={t("Livraison offerte au-dessus d'un seuil", "Free delivery above a threshold")} />
                    </Ligne>
                    {v.offre && <Ligne libelle={t("Seuil de livraison offerte", "Free delivery threshold")}><Nombre valeur={v.seuil} changer={champ("seuil")} unite="€" min={0} libelle={t("Seuil de livraison offerte", "Free delivery threshold")} /></Ligne>}
                </Champs>
            </Section>
        </FenetreOnglets>
    );
}

function PanneauCommune({ c, zones, mode, fermer, enregistrer }: { c: CommuneTrouvee; zones: ZoneL[]; mode: "communes" | "rayons"; fermer: () => void; enregistrer: (zoneId: number | null, refusee: boolean) => void }) {
    const t = useTexte();
    const [zoneId, setZoneId] = useState<number | null>(c.zone_id);
    const [refusee, setRefusee] = useState(c.refusee);
    const bouton = "cursor-pointer rounded-md border px-2.5 py-1 text-sm";
    return (
        <FenetreOnglets fermer={fermer} titre={c.nom} sous={`${String(c.km).replace(".", ",")} km${c.code_postal ? ` · ${c.code_postal}` : ""}`} valider={t("Enregistrer", "Save")} modifie={zoneId !== c.zone_id || refusee !== c.refusee} onValider={() => enregistrer(zoneId, refusee)}>
            <Section titre={t("Zone et exception", "Zone and exception")} info={t("Une commune refusée n'est jamais livrée, même dans un cercle.", "A refused town is never delivered, even inside a circle.")}>
                <Champs>
                    {mode === "communes" ? (
                        <Ligne libelle={t("Zone", "Zone")}>
                            <span className="inline-flex gap-1">
                                {[null, ...zones.map((z) => z.id)].map((id, i) => (
                                    <button key={id ?? "hors"} type="button" aria-pressed={zoneId === id} onClick={() => setZoneId(id)} className={`${bouton} ${zoneId === id ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted hover:font-medium"}`}>
                                        {id === null ? t("Hors zone", "Outside") : i}
                                    </button>
                                ))}
                            </span>
                        </Ligne>
                    ) : (
                        <Ligne libelle={t("Zone", "Zone")} info={t("Par rayons, la zone suit la distance : seule la commune refusée se règle ici.", "By radii the zone follows the distance: only a refusal is set here.")}>
                            <span className="text-sm text-muted-foreground">{zones.find((z) => z.id === c.zone_id)?.nom ?? t("Hors zone", "Outside")}</span>
                        </Ligne>
                    )}
                    <Ligne libelle={t("Refusée", "Refused")}>
                        <Switch checked={refusee} onCheckedChange={setRefusee} aria-label={t("Refusée", "Refused")} />
                    </Ligne>
                </Champs>
            </Section>
        </FenetreOnglets>
    );
}
