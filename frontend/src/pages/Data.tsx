import { useRef, useState } from "react";
import { Icon } from "../components/Icon";
import { useApp } from "../context";
import { downloadExport, uploadBackup } from "../lib/actions";
import { errorMessage, timeAgo } from "../lib/format";

export function DataActions() {
  const { health, refreshPrices, refreshingPrices, openConfirm, notify, refresh } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [exporting, setExporting] = useState(false);

  async function exportNow() {
    setExporting(true);
    try {
      notify(`Saved ${await downloadExport()}.`);
    } catch (error) {
      notify(errorMessage(error, "Export failed. Try again."), "error");
    } finally {
      setExporting(false);
    }
  }

  // Step 1: save current data. Step 2: confirm, naming the saved file, before anything is replaced.
  async function pickedFile(file: File | undefined) {
    if (fileRef.current) fileRef.current.value = "";
    if (!file) return;
    let savedAs: string;
    try {
      savedAs = await downloadExport("pre-restore-backup");
    } catch (error) {
      notify(errorMessage(error, "Could not save a backup of current data, so nothing was restored."), "error");
      return;
    }
    openConfirm({
      title: "Replace all data with this backup?",
      message: (
        <>
          Your current data was saved as <b>{savedAs}</b>. Check that it is in your downloads. Restoring <b>{file.name}</b> replaces every account, transaction, limit and price. To undo, import the saved file.
        </>
      ),
      confirmLabel: "Replace data",
      danger: true,
      onConfirm: async () => {
        await uploadBackup(file);
        notify("Backup restored.");
        refresh();
      },
    });
  }

  return (
    <ul className="action-list">
      <li className="action-item">
        <span className="ai ai-acc"><Icon name="refresh" /></span>
        <div className="attn-b"><b>Refresh prices</b><span className="muted">Last update {timeAgo(health?.prices_updated_at)}. Also saves today's value snapshot.</span></div>
        <button className="btn btn-s" type="button" onClick={refreshPrices} disabled={refreshingPrices}>{refreshingPrices ? "Refreshing…" : "Refresh"}</button>
      </li>
      <li className="action-item">
        <span className="ai ai-info"><Icon name="download" /></span>
        <div className="attn-b"><b>Export data</b><span className="muted">Download a full JSON backup.</span></div>
        <button className="btn btn-s" type="button" onClick={exportNow} disabled={exporting}>{exporting ? "Exporting…" : "Export"}</button>
      </li>
      <li className="action-item">
        <span className="ai ai-warn"><Icon name="upload" /></span>
        <div className="attn-b"><b>Import backup</b><span className="muted">Replaces all current data. Saves a copy first.</span></div>
        <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(event) => pickedFile(event.target.files?.[0])} aria-label="Backup file" />
        <button className="btn btn-s" type="button" onClick={() => fileRef.current?.click()}>Import</button>
      </li>
    </ul>
  );
}

export function Data() {
  return (
    <div className="grid">
      <section className="card s12 narrow" aria-labelledby="data-t">
        <div className="card-h"><div><h2 className="card-t" id="data-t">Import and export</h2><span className="muted">Backups stay on your computer. Keep them somewhere safe.</span></div></div>
        <DataActions />
      </section>
    </div>
  );
}
