import { api } from "../api/client";

export async function downloadExport(prefix = "master-control-terminal-export") {
  const response = await api.get<Blob>("/export", { responseType: "blob" });
  const header = response.headers["content-disposition"] as string | undefined;
  const filename = header?.match(/filename="?([^"]+)"?/i)?.[1] || `${prefix}-${new Date().toISOString()}.json`;
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = prefix === "master-control-terminal-export" ? filename : filename.replace("master-control-terminal-export", prefix);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return link.download;
}

// Restore replaces every table, so always save the current data first.
export async function restoreBackup(file: File) {
  const savedAs = await downloadExport("pre-restore-backup");
  const formData = new FormData();
  formData.append("file", file);
  await api.post("/import-backup", formData, { headers: { "Content-Type": "multipart/form-data" } });
  return savedAs;
}
