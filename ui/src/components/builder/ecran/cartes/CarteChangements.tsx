"use client";

/**
 * [.mark] builder-agent-vocal (lot 4, Q7): the « Changes » card. « 7 changes: 3 nodes created, 2 prompts changed,
 * 2 links ». See (the existing comparison of two versions), Before / After on the canvas (Sim's highlighting),
 * Accept (keep the draft; it is NOT published) or Refuse (put the graph from before back as the draft).
 *
 * The builder never publishes: Accept only closes the review.
 */
import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";

import { useRevueDesChangements } from "../revue";
import { useBuilderEcran } from "../store";
import { Carte } from "./Carte";

const T = {
    titre: { en: "Changes", fr: "Changements" },
    regle: { en: "Reviewed.", fr: "Relu." },
    changements: { en: "change(s)", fr: "changement(s)" },
    noeudsCrees: { en: "node(s) created", fr: "nœud(s) créé(s)" },
    noeudsModifies: { en: "node(s) modified", fr: "nœud(s) modifié(s)" },
    noeudsSupprimes: { en: "node(s) removed", fr: "nœud(s) supprimé(s)" },
    liaisons: { en: "link(s) changed", fr: "liaison(s) changée(s)" },
    voir: { en: "See", fr: "Voir" },
    avantApres: { en: "Before or after", fr: "Avant ou après" },
    avant: { en: "Before", fr: "Avant" },
    apres: { en: "After", fr: "Après" },
    accepter: { en: "Accept", fr: "Accepter" },
    refuser: { en: "Refuse", fr: "Refuser" },
    enCours: { en: "The builder is drawing the changes...", fr: "Le builder dessine les changements..." },
    nonPublie: { en: "A draft, not published.", fr: "Un brouillon, pas une publication." },
} satisfies Record<string, Texte>;

export function CarteChangements() {
    const { t } = useLangue();
    const revue = useRevueDesChangements();
    const bascule = useBuilderEcran((s) => s.bascule);
    const choisirLaBascule = useBuilderEcran((s) => s.choisirLaBascule);

    if (!revue.resume) {
        return (
            <Carte type="changements" titre={t(T.titre)}>
                <p className="text-xs text-muted-foreground">{t(T.regle)}</p>
            </Carte>
        );
    }
    const r = revue.resume;
    return (
        <Carte type="changements" titre={t(T.titre)} aide={t(T.nonPublie)}>
            <p className="text-sm" data-resume-changements>
                <b>{r.total}</b> {t(T.changements)} : {r.noeudsCrees} {t(T.noeudsCrees)}, {r.noeudsModifies} {t(T.noeudsModifies)}
                {r.noeudsSupprimes ? `, ${r.noeudsSupprimes} ${t(T.noeudsSupprimes)}` : ""}, {r.liaisonsCreees + r.liaisonsModifiees + r.liaisonsSupprimees}{" "}
                {t(T.liaisons)}
            </p>
            {revue.enAttente && <p className="mt-1 text-xs text-muted-foreground">{t(T.enCours)}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-2">
                <div className="flex overflow-hidden rounded-md border text-xs" role="group" aria-label={t(T.avantApres)}>
                    {(["avant", "apres"] as const).map((b) => (
                        <button
                            key={b}
                            type="button"
                            aria-pressed={bascule === b}
                            onClick={() => choisirLaBascule(b)}
                            className={`px-2 py-1 ${bascule === b ? "bg-primary text-primary-foreground" : "bg-background"}`}
                        >
                            {t(b === "avant" ? T.avant : T.apres)}
                        </button>
                    ))}
                </div>
                <Button type="button" size="sm" variant="outline" disabled={!revue.peutVoir} onClick={() => void revue.voir()}>
                    {t(T.voir)}
                </Button>
                <Button type="button" size="sm" disabled={revue.enAttente || revue.occupe} onClick={revue.accepter}>
                    {t(T.accepter)}
                </Button>
                <Button type="button" size="sm" variant="outline" disabled={revue.enAttente || revue.occupe} onClick={() => void revue.refuser()}>
                    {t(T.refuser)}
                </Button>
            </div>
            {revue.dialogue}
        </Carte>
    );
}
