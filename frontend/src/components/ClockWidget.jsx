import { useEffect, useState } from "react";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import { parseUtc } from "../utils/datetime";

export default function ClockWidget() {
  const { hasClockInOut } = useAuth();
  const [record, setRecord] = useState(null);
  const [now, setNow] = useState(new Date());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchToday = async () => {
    const { data } = await client.get("/attendance/today");
    setRecord(data.record);
  };

  useEffect(() => {
    if (hasClockInOut) fetchToday();
  }, [hasClockInOut]);

  if (!hasClockInOut) {
    return (
      <div className="card clock-widget">
        <div>
          <div className="label" style={{ marginBottom: 4 }}>Attendance</div>
          <div className="muted" style={{ fontSize: 13.5 }}>
            Contract employees track hours via timesheets — clock in/out isn't applicable to your role.
          </div>
        </div>
      </div>
    );
  }

  const clockedIn = record?.clock_in && !record?.clock_out;
  const clockedOutDone = record?.clock_in && record?.clock_out;

  const handleClock = async (action) => {
    setBusy(true);
    setError("");
    try {
      await client.post(`/attendance/${action}`);
      await fetchToday();
    } catch (err) {
      setError(err?.response?.data?.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card clock-widget">
      <div>
        <div className="label" style={{ marginBottom: 4 }}>Today's Attendance</div>
        <div className="time">
          {now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </div>
        {error && <div style={{ color: "var(--color-danger)", fontSize: 12.5, marginTop: 6 }}>{error}</div>}
        {record?.clock_in && (
          <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
            In: {parseUtc(record.clock_in).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
            {record.clock_out && (
              <> &middot; Out: {parseUtc(record.clock_out).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} &middot; {record.total_hours}h</>
            )}
          </div>
        )}
      </div>
      <div>
        {!record?.clock_in && (
          <button className="btn btn-success" disabled={busy} onClick={() => handleClock("clock-in")}>
            Clock In
          </button>
        )}
        {clockedIn && (
          <button className="btn btn-danger" disabled={busy} onClick={() => handleClock("clock-out")}>
            Clock Out
          </button>
        )}
        {clockedOutDone && <span className="badge badge-success">Day complete</span>}
      </div>
    </div>
  );
}
