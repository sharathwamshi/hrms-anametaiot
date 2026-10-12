import { useRef, useState } from "react";
import { downloadFile, downloadFilePost } from "../utils/download";

/**
 * "Export Excel" button. Two modes:
 *   • server mode — <ExportButton url="/attendance/export/team" params={{...}} filename="Team" />
 *       downloads the dedicated, full-detail workbook from the API;
 *   • table mode  — <ExportButton filename="Employees" /> (no url) exports the first table in the
 *       surrounding card exactly as it is shown on screen, via the generic exporter.
 */
export default function ExportButton({ url, params, filename = "Export", title, label = "Export Excel", size = "sm", disabled }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef(null);

  const stamp = new Date().toISOString().slice(0, 10);
  const name = `${filename.replace(/\.xlsx$/i, "")}_${stamp}.xlsx`;

  const run = async () => {
    setError("");
    setBusy(true);
    try {
      if (url) {
        await downloadFile(url, name, params);
      } else {
        const host = ref.current?.closest(".card") || ref.current?.closest(".modal-box") || ref.current?.closest(".page-content");
        const table = host?.querySelector("table");
        if (!table) throw new Error("There is no table here to export.");
        const headers = [...table.querySelectorAll("thead th")].map((th) => th.innerText.trim());
        const keep = headers.map((h) => h !== "");               // drop blank "action" columns
        const rows = [...table.querySelectorAll("tbody tr")]
          .filter((tr) => !tr.classList.contains("empty-row") && !tr.querySelector("td[colspan]"))
          .map((tr) => [...tr.children].map((td) => td.innerText.replace(/\s*\n\s*/g, " · ").trim()).filter((_, i) => keep[i]));
        const cleanHeaders = headers.filter((_, i) => keep[i]);
        if (rows.length === 0) throw new Error("There is nothing to export yet.");
        await downloadFilePost("/export/table", { filename: name, sheet: filename.slice(0, 31), title: title || filename, headers: cleanHeaders, rows }, name);
      }
    } catch (err) {
      setError(err.message || "The download failed.");
      setTimeout(() => setError(""), 6000);
    } finally {
      setBusy(false);
    }
  };

  return (
    <span ref={ref} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <button type="button" className={`btn btn-outline ${size === "sm" ? "btn-sm" : ""}`} onClick={run} disabled={busy || disabled} title="Download as an Excel file">
        {busy ? "Preparing…" : <>⬇ {label}</>}
      </button>
      {error && <span style={{ color: "var(--color-danger)", fontSize: 12 }}>{error}</span>}
    </span>
  );
}
