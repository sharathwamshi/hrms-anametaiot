export const APP_VERSION = "1.0.3";

export default function VersionLabel({ className = "" }) {
  return (
    <span className={`version-label ${className}`.trim()}>
      Version {APP_VERSION}
    </span>
  );
}
