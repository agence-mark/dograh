'use client';

import { useRef, useState } from 'react';

import { getPresignedUploadUrlApiV1S3PresignedUploadUrlPost } from '@/client/sdk.gen';
import { useLangue } from '@/components/mark/langue/langue';
import { notifier } from "@/components/mark/notifications";
import { Info } from '@/components/mark/studio/marques';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import logger from '@/lib/logger';

interface CsvUploadSelectorProps {
  onFileUploaded: (fileKey: string, fileName: string) => void;
  selectedFileName?: string;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export default function CsvUploadSelector({ onFileUploaded, selectedFileName }: CsvUploadSelectorProps) {
  const { t } = useLangue();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.endsWith('.csv')) {
      notifier.echec({ fr: "Choisissez un fichier CSV.", en: "Choose a CSV file." });
      return;
    }

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      notifier.echec({ fr: "Fichier trop lourd : 10 Mo au maximum.", en: "File too large: 10 MB maximum." });
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    try {
      // Step 1: Request presigned upload URL
      logger.info('Requesting presigned upload URL for:', file.name);
      const { data: presignedData, error } = await getPresignedUploadUrlApiV1S3PresignedUploadUrlPost({
        body: {
          file_name: file.name,
          file_size: file.size,
          content_type: 'text/csv',
        },
      });

      if (error || !presignedData) {
        throw new Error('Failed to get upload URL');
      }

      logger.info('Received presigned URL, uploading file...');

      // Step 2: Upload file directly to S3/MinIO
      const uploadResponse = await fetch(presignedData.upload_url, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': 'text/csv',
        },
      });

      if (!uploadResponse.ok) {
        throw new Error('Failed to upload file to storage');
      }

      setUploadProgress(100);
      logger.info('File uploaded successfully, file_key:', presignedData.file_key);

      // Step 3: Notify parent with file_key
      onFileUploaded(presignedData.file_key, file.name);
      notifier.succes({ fr: `Fichier « ${file.name} » envoyé.`, en: `File "${file.name}" uploaded.` });
    } catch (error) {
      logger.error('Error uploading CSV:', error);
      notifier.echec({ fr: "Envoi impossible. Vérifiez le fichier et réessayez.", en: "Upload failed. Check the file and try again." }, { erreur: error, reessayer: () => fileInputRef.current?.click() });
    } finally {
      setUploading(false);
      setUploadProgress(0);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="space-y-2">
      <Label className="flex items-center gap-1.5">
        CSV File
        <Info>
          {t({
            en: 'Upload a CSV file with contact data. Must include phone_number column. The columns can be accessed as initial_context in the workflow nodes. Max 10MB.',
            fr: 'Envoyez un fichier CSV avec vos contacts. Il doit contenir une colonne phone_number. Les colonnes sont accessibles dans les nœuds du workflow sous initial_context. 10 Mo max.',
          })}
        </Info>
      </Label>
      <div className="flex items-center gap-4">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        <Button
          type="button"
          variant="outline"
          onClick={handleButtonClick}
          disabled={uploading}
        >
          {uploading ? `Uploading... ${uploadProgress}%` : 'Upload CSV File'}
        </Button>
        {selectedFileName && !uploading && (
          <div className="flex-1 text-sm">
            <span className="text-muted-foreground">Selected: </span>
            <span className="text-primary">{selectedFileName}</span>
          </div>
        )}
      </div>
    </div>
  );
}
