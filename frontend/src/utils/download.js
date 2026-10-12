import client from "../api/client";

/**
 * Downloads a file from an authenticated API endpoint. A plain <a href>
 * can't carry the Authorization header (the JWT lives in localStorage, not
 * a cookie), so every protected download must go through axios like a
 * normal request and be saved via a blob URL instead.
 *
 * `params` (optional) are sent as the query string. On failure the server's
 * JSON error message is extracted from the blob so the caller can show it.
 */
export async function downloadFile(url, filename, params) {
  let response;
  try {
    response = await client.get(url, { responseType: "blob", params });
  } catch (err) {
    throw new Error(await errorMessage(err));
  }
  saveBlob(response.data, filename);
}

/** POSTs JSON and saves the file the server returns (used by the generic table exporter). */
export async function downloadFilePost(url, body, filename) {
  let response;
  try {
    response = await client.post(url, body, { responseType: "blob" });
  } catch (err) {
    throw new Error(await errorMessage(err));
  }
  saveBlob(response.data, filename);
}

function saveBlob(data, filename) {
  const blobUrl = window.URL.createObjectURL(new Blob([data]));
  const link = document.createElement("a");
  link.href = blobUrl;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}

async function errorMessage(err) {
  const blob = err?.response?.data;
  if (blob instanceof Blob) {
    try {
      const parsed = JSON.parse(await blob.text());
      if (parsed?.message) return parsed.message;
    } catch (_) { /* not JSON */ }
  }
  return "The download failed. Please try again.";
}
