/**
 * [.mark] K5 : le dépôt d'un document de connaissance (mêmes trois appels que l'écran d'amont `app/files`, qu'on ne touche
 * pas) : l'adresse d'envoi, l'envoi du fichier, le lancement de l'analyse. Rend `null` si tout a réussi, sinon la raison.
 */
import { getUploadUrlApiV1KnowledgeBaseUploadUrlPost, processDocumentApiV1KnowledgeBaseProcessDocumentPost } from "@/client/sdk.gen";

export const TAILLE_MAX = 5 * 1024 * 1024;
export const TYPES_ADMIS = [".pdf", ".docx", ".doc", ".txt", ".json", ".md"];
export type ModeDeLecture = "full_document" | "chunked";

export function verifierLeFichier(fichier: File): "type" | "taille" | null {
    const extension = "." + (fichier.name.split(".").pop() ?? "").toLowerCase();
    if (!TYPES_ADMIS.includes(extension)) return "type";
    if (fichier.size > TAILLE_MAX) return "taille";
    return null;
}

export async function deposerUnDocument(fichier: File, mode: ModeDeLecture): Promise<string | null> {
    const type = fichier.type || "application/octet-stream";
    const adresse = await getUploadUrlApiV1KnowledgeBaseUploadUrlPost({
        body: { filename: fichier.name, mime_type: type, custom_metadata: { original_filename: fichier.name, uploaded_at: new Date().toISOString() } },
    });
    if (adresse.error || !adresse.data) return "upload_url";
    const envoi = await fetch(adresse.data.upload_url, { method: "PUT", body: fichier, headers: { "Content-Type": type } });
    if (!envoi.ok) return "stockage";
    const analyse = await processDocumentApiV1KnowledgeBaseProcessDocumentPost({
        body: { document_uuid: adresse.data.document_uuid, s3_key: adresse.data.s3_key, retrieval_mode: mode },
    });
    return analyse.error ? "analyse" : null;
}
