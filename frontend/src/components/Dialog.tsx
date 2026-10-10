import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { errorMessage } from "../lib/format";
import { Icon } from "./Icon";

interface DialogProps {
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  aside?: ReactNode;
  size?: "sm" | "md" | "lg";
}

// Native <dialog>: Escape, focus trap and backdrop come from the browser.
export function Dialog({ title, subtitle, onClose, children, footer, aside, size = "md" }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement as HTMLElement | null;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      opener?.focus?.();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className={`dlg dlg-${size}${aside ? " has-aside" : ""}`}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header className="dlg-h">
        <div className="dlg-title">
          <h2 id={titleId}>{title}</h2>
          {subtitle && <p className="sub">{subtitle}</p>}
        </div>
        <kbd className="hide-touch">Esc</kbd>
        <button className="btn btn-g icon-btn" type="button" onClick={onClose} aria-label="Close">
          <Icon name="close" />
        </button>
      </header>
      <div className="dlg-b">
        <div className="dlg-main">{children}</div>
        {aside && <aside className="dlg-aside" aria-label="Summary">{aside}</aside>}
      </div>
      {footer && <footer className="dlg-f">{footer}</footer>}
    </dialog>
  );
}

interface ConfirmProps {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}

export function ConfirmDialog({ title, message, confirmLabel, danger, onConfirm, onClose }: ConfirmProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await onConfirm();
      onClose();
    } catch (exc) {
      setError(errorMessage(exc));
      setBusy(false);
    }
  }

  return (
    <Dialog
      title={title}
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-s" type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className={`btn ${danger ? "btn-danger" : "btn-p"}`} type="button" onClick={confirm} disabled={busy} autoFocus>
            {busy ? "Working…" : confirmLabel}
          </button>
        </>
      }
    >
      <p className="confirm-msg">{message}</p>
      {error && <p className="form-error" role="alert">{error}</p>}
    </Dialog>
  );
}
