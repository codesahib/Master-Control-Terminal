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
  busy?: boolean;
}

const FIRST_FIELD = "[data-autofocus], .dlg-main input:not([type=hidden]):not([type=checkbox]), .dlg-main select, .dlg-main textarea";

// Native <dialog>: Escape, focus trap and backdrop come from the browser. `busy` blocks closing mid-save.
export function Dialog({ title, subtitle, onClose, children, footer, aside, size = "md", busy = false }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement as HTMLElement | null;
    if (dialog && !dialog.open) {
      dialog.showModal();
      dialog.querySelector<HTMLElement>(FIRST_FIELD)?.focus();
    }
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
      aria-busy={busy}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <header className="dlg-h">
        <div className="dlg-title">
          <h2 id={titleId}>{title}</h2>
          {subtitle && <p className="sub">{subtitle}</p>}
        </div>
        <kbd className="hide-touch">Esc</kbd>
        <button className="btn btn-g icon-btn" type="button" onClick={onClose} disabled={busy} aria-label="Close">
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
  message: ReactNode;
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
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-s" type="button" onClick={onClose} disabled={busy} data-autofocus>Cancel</button>
          <button className={`btn ${danger ? "btn-danger" : "btn-p"}`} type="button" onClick={confirm} disabled={busy}>
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
