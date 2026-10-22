/**
 * [.mark] Chantier voix-soniox, lot 7 (relecture m3, D-10/D-18) : QUEL mode d'envoi du texte la voix reçoit, et d'où il vient.
 *
 * Deux réglages existent : celui de l'AGENT (`tts_text_aggregation_mode`, toutes voix, « phrase par phrase » par
 * défaut) et celui de la VOIX Soniox (`text_aggregation_mode`, écran Modèles). La règle du serveur
 * (`mode_d_envoi_du_texte`, `service_factory.py`) : l'agent gagne quand il demande autre chose que le défaut ;
 * sinon, le réglage de la voix Soniox. Cette fonction ne fait que la DIRE à l'écran, avec la même règle.
 *
 * ⛔ Limite assumée (D-10) : un agent qui demande « phrase par phrase » ne peut pas contredire une voix réglée
 * « mot à mot » (indiscernable du défaut).
 */
export type ModeEnvoi = "sentence" | "token";
export type OrigineMode = "agent" | "voix" | "defaut";

export const modeRetenu = (
    modeDeLAgent: unknown,
    voix: Record<string, unknown> | null | undefined,
): { mode: ModeEnvoi; origine: OrigineMode } => {
    if (modeDeLAgent === "token") return { mode: "token", origine: "agent" };
    if (voix?.provider === "soniox") {
        // Une voix Soniox dont le réglage est absent vaut « phrase par phrase » (défaut du registre).
        const dit = voix.text_aggregation_mode === "token" ? "token" : "sentence";
        return { mode: dit, origine: dit === "token" ? "voix" : "defaut" };
    }
    return { mode: "sentence", origine: "defaut" };
};
