"use client";

/**
 * [.mark] U2 bis (E56) : « Écoute et sons » reprend l'écran `/recordings` de l'amont, sans changer sa fonction :
 * les enregistrements envoyés (à insérer avec `@` dans les consignes ou comme messages de transition d'un outil)
 * et le cache de la voix (écouter une phrase, l'invalider pour regénérer son audio). Mêmes composants, mêmes routes.
 *
 * [.mark] K4 : les titres sont ceux de la maquette (titre + « ! » à gauche, l'action à droite) ; les listes restent
 * celles de l'amont (voir `14-ecarts-maquette.md`).
 */
import { Upload } from "lucide-react";
import { useState } from "react";

import RecordingsList from "@/app/recordings/RecordingsList";
import { RecordingsUploadDialog } from "@/app/recordings/RecordingsUploadDialog";
import TtsCacheList from "@/app/recordings/TtsCacheList";
import { Button } from "@/components/ui/button";

import { useFormeMaquette } from "../ecran/forme-maquette";
import { useLangue } from "../langue/langue";
import { Info } from "../studio/marques";
import { TitreTableau } from "../studio/tableau";

export function SonsEtCacheVoix() {
    const { t } = useLangue();
    const maquette = useFormeMaquette();
    const [envoi, setEnvoi] = useState(false);
    const [relecture, setRelecture] = useState(0);
    return (
        <>
            <section id="ecoute-enregistrements">
                <TitreTableau
                    titre={t({ en: "Recordings", fr: "Enregistrements" })}
                    info={
                        <Info>
                            {t({
                                en: "Audio shared by all the agents of the company. Use @ in a prompt field to insert one, or as a transition message in a tool.",
                                fr: "Des sons partagés par tous les agents de l'entreprise. @ dans une consigne en insère un, ou comme message de transition d'un outil.",
                            })}
                        </Info>
                    }
                    action={
                        <Button variant="outline" size="sm" onClick={() => setEnvoi(true)} data-testid="envoyer-enregistrement">
                            <Upload className="size-3.5" />
                            {t({ en: "Upload", fr: "Envoyer" })}
                        </Button>
                    }
                />
                <RecordingsList refreshKey={relecture} />
            </section>
            {maquette ? (
                <TtsCacheList />
            ) : (
            <section id="ecoute-cache-voix">
                <TitreTableau
                    titre={t({ en: "Voice cache", fr: "Cache de la voix" })}
                    info={
                        <Info>
                            {t({
                                en: "Speech reused across the company's agents. Listen to a phrase and invalidate it to generate fresh audio on its next request.",
                                fr: "La parole réutilisée par les agents de l'entreprise. Écoutez une phrase et invalidez-la pour regénérer son audio à sa prochaine demande.",
                            })}
                        </Info>
                    }
                />
                <TtsCacheList />
            </section>
            )}
            <RecordingsUploadDialog open={envoi} onOpenChange={setEnvoi} onUploadComplete={() => setRelecture((k) => k + 1)} />
        </>
    );
}
