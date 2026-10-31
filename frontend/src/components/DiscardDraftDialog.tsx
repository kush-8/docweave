import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

type Props = { open: boolean; onCancel: () => void; onDiscard: () => void };

export function DiscardDraftDialog({ open, onCancel, onDiscard }: Props) {
  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (!next) onCancel(); }}>
      <AlertDialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain">
        <AlertDialogHeader><AlertDialogTitle>Discard your message?</AlertDialogTitle><AlertDialogDescription>Your message hasn’t been sent. Starting or switching chats will discard it.</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep writing</AlertDialogCancel>
          <AlertDialogAction onClick={onDiscard}>Discard draft</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
