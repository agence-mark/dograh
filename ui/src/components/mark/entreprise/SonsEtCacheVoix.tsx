"use client";

/**
 * [.mark] U2 bis (E56) : « Écoute et sons » reprend l'écran `/recordings` de l'amont, sans changer sa fonction :
 * les enregistrements envoyés (à insérer avec `@` dans les consignes ou comme messages de transition d'un outil)
 * et le cache de la voix (écouter une phrase, l'invalider pour regénérer son audio). Mêmes composants, mêmes routes.
 */
import { Upload } from "lucide-react";
import { useState } from "react";

import RecordingsList from "@/app/recordings/RecordingsList";
import { RecordingsUploadDialog } from "@/app/recordings/RecordingsUploadDialog";
import TtsCacheList from "@/app/recordings/TtsCacheList";
import { Button } from "@/components/ui/button";

import { Intertitre } from "../ecran/Intertitre";
import { useLangue } from "../langue/langue";

export function SonsEtCacheVoix() {
    const { t } = useLangue();
    const [envoi, setEnvoi] = useState(false);
    const [relecture, setRelecture] = useState(0);
    return (
        <>
            <Intertitre
                id="ecoute-enregistrements"
                titre={{ en: "Recordings", fr: "Enregistrements" }}
                description={{
                    en: "Audio shared by all the agents of the company. Use @ in a prompt field to insert one, or as a transition message in a tool.",
                    fr: "Des sons partagés par tous les agents de l'entreprise. @ dans une consigne en insère un, ou comme message de transition d'un outil.",
                }}
            >
                <div className="flex justify-end">
                    <Button variant="outline" size="sm" onClick={() => setEnvoi(true)} data-testid="envoyer-enregistrement">
                        <Upload className="mr-1 h-4 w-4" />
                        {t({ en: "Upload a recording", fr: "Envoyer un enregistrement" })}
                    </Button>
                </div>
                <RecordingsList refreshKey={relecture} />
            </Intertitre>
            <Intertitre
                id="ecoute-cache-voix"
                titre={{ en: "Voice cache", fr: "Cache de la voix" }}
                description={{
                    en: "Speech reused across the company's agents. Listen to a phrase and invalidate it to generate fresh audio on its next request.",
                    fr: "La parole réutilisée par les agents de l'entreprise. Écoutez une phrase et invalidez-la pour regénérer son audio à sa prochaine demande.",
                }}
            >
                <TtsCacheList />
            </Intertitre>
            <RecordingsUploadDialog open={envoi} onOpenChange={setEnvoi} onUploadComplete={() => setRelecture((k) => k + 1)} />
        </>
    );
}
