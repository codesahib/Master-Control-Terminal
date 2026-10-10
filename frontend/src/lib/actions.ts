import { api } from "../api/client";

export async function downloadExport(prefix = "master-control-terminal-export") {
  const response = await api.get<Blob>("/export", { responseType: "blob" });
  const header = response.headers["content-disposition"] as string | undefined;
  const serverName = header?.match(/filename="?([^"]+)"?/i)?.[1] || `master-control-terminal-export-${new Date().toISOString()}.json`;
  const filename = serverName.replace("master-control-terminal-export", prefix);
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoking right away can cancel the download in some browsers.
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
  return filename;
}

export async function uploadBackup(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  await api.post("/import-backup", formData, { headers: { "Content-Type": "multipart/form-data" } });
}
