import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import VersionLabel from "./VersionLabel";

export default function AppLayout({ title, subtitle, children }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-column">
        <Topbar title={title} subtitle={subtitle} />
        <div className="page-content">{children}</div>
        <footer className="main-content-footer">
          <VersionLabel />
        </footer>
      </div>
    </div>
  );
}
