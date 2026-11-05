"use client";

/**
 * [.mark] Partie 3, L5b : la colonne principale de la page de pilotage d'un client (maquette `accueil-client.tsx`, décision 16) :
 * « À faire maintenant », les chiffres de la période, les motifs d'appel, les agents, et la liste d'installation d'un client pas
 * encore en service. Chaque bloc ne fait qu'AFFICHER ce que le serveur a calculé (`api/services/pilotage_client`).
 */
import { AudioLines, Check, Circle, Gauge, PhoneIncoming, Repeat2, Star, Timer, Wallet, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { BandeChiffres } from "@/components/mark/qualite/BandeChiffres";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";

import type { ItemAFaire } from "./a-faire";
import { SENS, valeurAffichee } from "./format";
import { T, texte } from "./textes";
import { type AgentPilotage, type ChiffrePilotage, LIBELLE_PERIODE, type MotifPilotage, type Periode, PERIODES, type PilotageClient } from "./types";

const ICONES: Record<ChiffrePilotage["id"], LucideIcon> = { appels: PhoneIncoming, resolus: Check, transferes: Repeat2, note: Star, cout: Wallet, duree: Timer };
const LIBELLES: Record<ChiffrePilotage["id"], Texte> = { appels: T.appels, resolus: T.resolus, transferes: T.transferes, note: T.note, cout: T.cout, duree: T.duree };

export function SelecteurPeriode({ valeur, changer }: { valeur: Periode; changer: (p: Periode) => void }) {
    const { t } = useLangue();
    return (
        <div role="group" aria-label={t(T.periode)} className="inline-flex rounded-md border p-0.5 text-xs">
            {PERIODES.map((p) => (
                <button
                    key={p}
                    type="button"
                    aria-pressed={valeur === p}
                    onClick={() => changer(p)}
                    className={`cursor-pointer rounded px-2.5 py-1 hover:font-semibold ${valeur === p ? "bg-foreground font-medium text-background" : "text-muted-foreground"}`}
                >
                    {LIBELLE_PERIODE[p]}
                </button>
            ))}
        </div>
    );
}

function Section({ titre, info, children }: { titre: string; info?: React.ReactNode; children: React.ReactNode }) {
    return (
        <section>
            <div className="flex items-center gap-2 pb-2">
                <h2 className="flex flex-1 items-center gap-1.5 text-base font-semibold">
                    {titre}
                    {info && <Info>{info}</Info>}
                </h2>
            </div>
            {children}
        </section>
    );
}

/** « À faire maintenant » : alertes, intégrations, problèmes graves, installation ; « Rien à faire » quand tout est lu et vide. */
export function ALaFaire({
    items,
    illisibles,
    chargement,
    base,
    reprendre,
    reessayer,
}: {
    items: ItemAFaire[];
    illisibles: string[];
    chargement: boolean;
    base: string;
    reprendre: () => void;
    reessayer: () => void;
}) {
    const { t } = useLangue();
    const mots: Record<ItemAFaire["bouton"], Texte> = { regler: T.regler, ouvrir: T.ouvrir, reprendre: T.reprendre };
    return (
        <Section titre={t(T.aFaire)} info={t(T.aFaireInfo)}>
            {chargement ? (
                <p className="py-3 text-sm text-muted-foreground">{t(T.chargement)}</p>
            ) : (
                <>
                    {items.length === 0 && illisibles.length === 0 && (
                        <p data-pilotage="rien-a-faire" className="flex items-center gap-2 py-3 text-sm">
                            <Check className="size-4 text-(--etat-fait)" strokeWidth={2.5} /> {t(T.rienAFaire)}
                        </p>
                    )}
                    {items.length > 0 && (
                        <ul className="divide-y">
                            {items.map((f) => (
                                <li key={f.id} data-a-faire={f.id} className="flex items-center gap-3 py-2.5 text-sm">
                                    <span
                                        className={`size-2 shrink-0 rounded-full ${f.gravite === "grave" ? "bg-destructive" : "bg-muted-foreground"}`}
                                        role="img"
                                        aria-label={t(f.gravite === "grave" ? T.grave : T.normal)}
                                    />
                                    <span className="flex-1">{t(f.texte)}</span>
                                    {f.vers ? (
                                        <Button variant={f.gravite === "grave" ? "default" : "outline"} size="sm" className="h-7 shrink-0" asChild>
                                            <Link href={`${base}/${f.vers}`}>{t(mots[f.bouton])}</Link>
                                        </Button>
                                    ) : (
                                        <Button variant="outline" size="sm" className="h-7 shrink-0" onClick={reprendre}>
                                            {t(mots[f.bouton])}
                                        </Button>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}
                    {illisibles.length > 0 && (
                        <p data-pilotage="illisible" className="flex items-center gap-2 py-2.5 text-sm text-muted-foreground">
                            <span className="flex-1">
                                {t(T.lectureImpossible)} {illisibles.map((b) => t(T.sujets[b as keyof typeof T.sujets] ?? { en: b, fr: b })).join(", ")}
                            </span>
                            <Button variant="outline" size="sm" className="h-7" onClick={reessayer}>
                                {t(T.reessayer)}
                            </Button>
                        </p>
                    )}
                </>
            )}
        </Section>
    );
}

function Tendance({ c, periode }: { c: ChiffrePilotage; periode: Periode }) {
    const { t } = useLangue();
    if (c.tendance === null) return <span className="text-muted-foreground">{t(T.pasDAvant)}</span>;
    if (c.tendance === 0) return <span className="text-muted-foreground">{t(T.stable)}</span>;
    const sens = SENS[c.id];
    const bon = sens === "neutre" ? null : c.tendance > 0 === (sens === "haut");
    const couleur = bon === null ? "text-muted-foreground" : bon ? "text-(--etat-fait)" : "text-destructive";
    return (
        <span>
            <span className={`font-semibold ${couleur}`}>
                {c.tendance > 0 ? "▲ +" : "▼ "}
                {Math.abs(c.tendance)} %
            </span>{" "}
            <span className="text-muted-foreground">{t(texte(T.contre, LIBELLE_PERIODE[periode]))}</span>
        </span>
    );
}

/** Les six chiffres de la période (deux rangées de trois), avec tendance ; un chiffre indisponible dit comment l'activer. */
export function ChiffresDeLaPeriode({ pilotage, periode, base }: { pilotage: PilotageClient; periode: Periode; base: string }) {
    const { t, langue } = useLangue();
    const chiffres = pilotage.chiffres;
    if (chiffres === null) {
        return (
            <Section titre={t(T.surLaPeriode)} info={t(T.surLaPeriodeInfo)}>
                <p data-pilotage="chiffres-illisibles" className="py-3 text-sm text-muted-foreground">
                    {t(T.lectureImpossible)} {t(T.sujets.chiffres)}
                </p>
            </Section>
        );
    }
    const tuile = (c: ChiffrePilotage) => {
        const raison = c.raison && c.raison !== "aucun_appel" ? T.raisons[c.raison] : null;
        return {
            icone: ICONES[c.id] ?? Gauge,
            libelle: t(LIBELLES[c.id]),
            valeur: valeurAffichee(c, langue),
            phrase: !c.disponible ? (
                c.raison === "aucun_appel" || !raison ? (
                    t(T.aucunAppel)
                ) : (
                    <span className="flex flex-col items-start gap-2">
                        {t(raison.phrase)}
                        {raison.bouton && raison.vers && (
                            <Button variant="outline" size="sm" className="h-7" asChild>
                                <Link href={`${base}/${raison.vers}`}>{t(raison.bouton)}</Link>
                            </Button>
                        )}
                    </span>
                )
            ) : (
                <Tendance c={c} periode={periode} />
            ),
        };
    };
    return (
        <Section titre={t(T.surLaPeriode)} info={t(T.surLaPeriodeInfo)}>
            <div className="space-y-4" data-pilotage="chiffres">
                <BandeChiffres colonnes={3} chiffres={chiffres.slice(0, 3).map(tuile)} />
                <BandeChiffres colonnes={3} chiffres={chiffres.slice(3).map(tuile)} />
            </div>
            {pilotage.tronque && <p className="pt-2 text-xs text-muted-foreground">{t(T.tronque)}</p>}
        </Section>
    );
}

/**
 * Le lien qui ouvre les appels d'un motif : le filtre « motif » de la liste des appels (`callReason`) et, quand la période tient
 * dans la plage maximale du filtre de date (30 jours), la période. Au-delà, le motif seul.
 */
export function lienDesAppelsDuMotif(base: string, motif: string, jours: number, maintenant: Date = new Date()): string {
    const filtres: { id: string; value: unknown }[] = [{ id: "callReason", value: { value: motif } }];
    if (jours <= 30) {
        const debut = new Date(maintenant.getTime() - jours * 24 * 3600 * 1000);
        filtres.push({ id: "dateRange", value: { from: debut.toISOString(), to: maintenant.toISOString() } });
    }
    return `${base}/conversations?filters=${encodeURIComponent(JSON.stringify(filtres))}`;
}

const pct = (v: number | null, langue: string) => (v === null ? "–" : `${Math.round(v * 100)}${langue === "fr" ? " %" : "%"}`);

export function Motifs({ motifs, jours, base }: { motifs: MotifPilotage[] | null; jours: number; base: string }) {
    const { t, langue } = useLangue();
    return (
        <section data-pilotage="motifs">
            <TitreTableau titre={t(T.motifs)} info={<Info>{t(T.motifsInfo)}</Info>} />
            {motifs === null ? (
                <p className="py-6 text-sm text-muted-foreground">
                    {t(T.lectureImpossible)} {t(T.sujets.chiffres)}
                </p>
            ) : motifs.length === 0 ? (
                <p className="py-6 text-sm text-muted-foreground">{t(T.aucunAppelPeriode)}</p>
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t(T.motif) },
                        { titre: t(T.appelsCol), droite: true },
                        { titre: t(T.resolusCol), droite: true },
                        { titre: t(T.transferesCol), droite: true },
                        { titre: t(T.noteCol), droite: true },
                    ]}
                >
                    {motifs.map((m) => (
                        <Ligne key={m.motif} href={lienDesAppelsDuMotif(base, m.motif, jours)}>
                            <Cellule principale>{m.motif}</Cellule>
                            <Cellule droite>{m.appels}</Cellule>
                            <Cellule droite>{pct(m.part_resolu, langue)}</Cellule>
                            <Cellule droite>{pct(m.part_transferts, langue)}</Cellule>
                            <Cellule droite>{m.note === null ? "–" : String(m.note).replace(".", langue === "fr" ? "," : ".")}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}
        </section>
    );
}

function Pret({ pret }: { pret: AgentPilotage["pret"] }) {
    const { t } = useLangue();
    if (!pret) return <>–</>;
    if (pret.etat === "pret") return <PointEtat etat="publie">{t(T.pret)}</PointEtat>;
    if (pret.etat === "bloque") return <PointEtat etat="panne">{t(texte(T.bloquants, pret.n))}</PointEtat>;
    return <PointEtat etat="attente">{t(texte(T.aFairePret, pret.n))}</PointEtat>;
}

export function Agents({ agents, base }: { agents: AgentPilotage[] | null; base: string }) {
    const { t, langue } = useLangue();
    return (
        <section data-pilotage="agents">
            <TitreTableau
                titre={t(T.agents)}
                action={
                    <Link href={`${base}/agents`} className="text-sm text-(--acc) hover:font-semibold">
                        {t(T.tous)}
                    </Link>
                }
            />
            {agents === null ? (
                <p className="py-6 text-sm text-muted-foreground">
                    {t(T.lectureImpossible)} {t(T.sujets.agents)}
                </p>
            ) : agents.length === 0 ? (
                <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                    <AudioLines className="size-4" /> {t(T.aucunAgent)}
                </p>
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t(T.agent) },
                        { titre: t(T.enLigne) },
                        { titre: t(T.partDuTrafic), droite: true },
                        { titre: t(T.appelsCol), droite: true },
                        { titre: t(T.noteCol), droite: true },
                        { titre: t(T.pretAPublier) },
                    ]}
                >
                    {agents.map((a) => (
                        <Ligne key={a.id} href={`/agents/${a.id}`}>
                            <Cellule principale sous={a.autres.length > 0 ? a.autres.map((b) => `${b.nom} ${b.part} %`).join(" · ") : undefined}>
                                {a.nom}
                            </Cellule>
                            <Cellule>
                                <PointEtat etat={a.publie ? "publie" : "brouillon"}>
                                    {a.publie ? `${t(T.principale)} · v${a.version ?? "?"}` : t(T.brouillon)}
                                </PointEtat>
                            </Cellule>
                            <Cellule droite>{a.publie ? `${a.part} %` : "–"}</Cellule>
                            <Cellule droite>{a.appels}</Cellule>
                            <Cellule droite>{a.note === null ? "–" : String(a.note).replace(".", langue === "fr" ? "," : ".")}</Cellule>
                            <Cellule>
                                <Pret pret={a.pret} />
                            </Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}
        </section>
    );
}

/** La liste d'installation, à la place des chiffres tant que le client n'est pas en service. */
export function ListeInstallation({ pilotage, reprendre }: { pilotage: PilotageClient; reprendre: () => void }) {
    const { t, langue } = useLangue();
    const installation = pilotage.installation;
    return (
        <Section titre={t(T.installation)} info={t(T.installationInfo)}>
            {!installation ? (
                <p data-pilotage="aucune-installation" className="py-3 text-sm text-muted-foreground">
                    {t(T.aucuneInstallation)}
                </p>
            ) : (
                <>
                    <p className="pb-2 text-sm text-muted-foreground">{t(texte(T.etapesSur, installation.faites, installation.total))}</p>
                    <ul className="divide-y">
                        {installation.etapes.map((e) => {
                            const close = e.etat === "faite" || e.etat === "passee";
                            return (
                                <li key={e.numero} data-etape={e.numero} className="flex items-center gap-2.5 py-2.5 text-sm">
                                    {close ? <Check className="size-4 text-(--etat-fait)" /> : <Circle className="size-4 text-muted-foreground/40" />}
                                    <span className={close ? "" : "text-muted-foreground"}>{langue === "fr" ? e.titre.fr : (e.titre.en ?? e.titre.fr)}</span>
                                    {e.numero === installation.prochaine && (
                                        <Button variant="outline" size="sm" className="ml-auto h-7" onClick={reprendre}>
                                            {t(T.reprendre)}
                                        </Button>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                </>
            )}
        </Section>
    );
}
