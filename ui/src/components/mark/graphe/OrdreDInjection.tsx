"use client";

/**
 * [.mark] RA-B (R4d, audit 02 B2) : l'ordre dans lequel les données entrent dans l'appel, affiché dans la fiche de
 * l'étape de départ. Même liste, même ordre que `api/services/workflow/ordre_d_injection.py` (`ORDRE_D_INJECTION`),
 * du plus bas au plus haut : une couche plus haute passe par-dessus une plus basse. Lecture seule.
 */
import { type Texte, useLangue } from "../langue/langue";

export const ORDRE_D_INJECTION: { id: string; texte: Texte }[] = [
    { id: "defaut", texte: { en: "Code defaults", fr: "Valeurs par défaut du code" } },
    { id: "organisation", texte: { en: "Organization (announcement, team, phrases)", fr: "Organisation (annonce, équipe, phrases)" } },
    { id: "etablissement", texte: { en: "Establishment served", fr: "Établissement servi" } },
    { id: "objets", texte: { en: "Agent objects", fr: "Objets de l'agent" } },
    { id: "lecture", texte: { en: "Pre-call lookup", fr: "Lecture avant l'appel" } },
    { id: "appel", texte: { en: "Call context (number, date, direction)", fr: "Contexte de l'appel (numéro, date, direction)" } },
];

const TEXTES = {
    titre: { en: "Order in which data enters the call", fr: "Ordre dans lequel les données entrent dans l'appel" },
    regle: {
        en: "The pre-call lookup replaces an object only if the start step asks for it, by name. Each replacement is traced in the run.",
        fr: "La lecture avant l'appel ne remplace un objet que si l'étape de départ le demande, par son nom. Chaque remplacement est tracé dans l'appel.",
    },
};

export function OrdreDInjection() {
    const { t } = useLangue();
    return (
        <div className="space-y-1 text-xs text-muted-foreground" data-testid="ordre-d-injection">
            <p className="font-medium text-foreground">{t(TEXTES.titre)}</p>
            <ol className="list-decimal space-y-0.5 pl-5">
                {ORDRE_D_INJECTION.map((c) => (
                    <li key={c.id} data-couche={c.id}>
                        {t(c.texte)}
                    </li>
                ))}
            </ol>
            <p>{t(TEXTES.regle)}</p>
        </div>
    );
}
