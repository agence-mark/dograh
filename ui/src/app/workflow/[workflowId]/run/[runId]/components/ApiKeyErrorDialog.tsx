import { AlertCircle, Key } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// [.mark] U1: only the model configuration error remains.
interface ApiKeyErrorDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    error: string | null;
    onNavigateToModelConfig: () => void;
}

export const ApiKeyErrorDialog = ({
    open,
    onOpenChange,
    error,
    onNavigateToModelConfig,
}: ApiKeyErrorDialogProps) => {
    return (
        <Dialog centree open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Key className="h-5 w-5 text-destructive" />
                        API Configuration Error
                    </DialogTitle>
                    <DialogDescription className="pt-3" asChild>
                        <div className="flex items-start gap-2">
                            <AlertCircle className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                            <div className="text-sm space-y-1">
                                <p className="font-medium text-foreground">{error}</p>
                            </div>
                        </div>
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancel
                    </Button>
                    <Button onClick={onNavigateToModelConfig}>
                        Go to Model Configurations
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
