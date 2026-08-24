import client from "../api/client";

/**
 * Downloads a file from an authenticated API endpoint. A plain <a href>
 * can't carry the Authorization header (the JWT lives in localStorage, not
 * a cookie), so every protected download must go through axios like a
 * normal request and be saved via a blob URL instead.
 */
export async function downloadFile(url, filename) {
  const response = await client.get(url, { responseType: "blob" });
  const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = blobUrl;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}
