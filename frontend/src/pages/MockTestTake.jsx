import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import client from "../api/client";
import { parseUtc } from "../utils/datetime";

export default function MockTestTake() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [started, setStarted] = useState(false);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await client.get(`/mocktest/take/${token}`);
      setInfo(data);
      setStarted(data.status === "in_progress");
    } catch (err) {
      setError(err?.response?.data?.message || "This test link is not valid.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const start = async () => {
    await client.post(`/mocktest/take/${token}/start`);
    setStarted(true);
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const payload = {
        answers: Object.entries(answers).map(([question_id, answer_text]) => ({
          question_id: Number(question_id),
          answer_text,
        })),
      };
      const { data } = await client.post(`/mocktest/take/${token}/submit`, payload);
      setResult(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not submit your answers.");
    } finally {
      setSubmitting(false);
    }
  };

  const pageStyle = {
    minHeight: "100vh",
    background: "var(--color-bg, #f5f6fb)",
    display: "flex",
    justifyContent: "center",
    padding: "40px 16px",
  };
  const cardStyle = {
    background: "#fff",
    border: "1px solid #e4e7ec",
    borderRadius: 16,
    padding: 32,
    width: "100%",
    maxWidth: 640,
    height: "fit-content",
  };

  if (loading) {
    return (
      <div style={pageStyle}>
        <div style={cardStyle}>Loading your test…</div>
      </div>
    );
  }

  if (error && !result) {
    return (
      <div style={pageStyle}>
        <div style={cardStyle}>
          <h2 style={{ marginBottom: 10 }}>Unable to load test</h2>
          <p style={{ color: "#667085" }}>{error}</p>
        </div>
      </div>
    );
  }

  if (result) {
    return (
      <div style={pageStyle}>
        <div style={cardStyle}>
          <h2 style={{ marginBottom: 6 }}>Test submitted</h2>
          <p style={{ color: "#667085", marginBottom: 20 }}>
            Thanks — your responses have been recorded and graded automatically.
          </p>
          <div style={{ fontSize: 40, fontWeight: 800, color: result.passed ? "#128A4E" : "#E03B2F" }}>
            {result.percentage}%
          </div>
          <div style={{ color: "#667085", marginBottom: 16 }}>
            {result.score} / {result.max_score} marks &middot; {result.passed ? "Passed" : "Below passing threshold"}
          </div>
          <p style={{ fontSize: 13, color: "#98a2b3" }}>
            The recruiting team will follow up with next steps.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <h2 style={{ marginBottom: 4 }}>{info.template_title}</h2>
        <p style={{ color: "#667085", marginBottom: 20 }}>
          {info.duration_minutes} minutes &middot; {info.questions.length} question(s) &middot; closes{" "}
          {parseUtc(info.window_end).toLocaleString("en-IN")}
        </p>

        {!started ? (
          <button className="btn btn-primary" onClick={start}>
            Start Test
          </button>
        ) : (
          <>
            {info.questions.map((q, idx) => (
              <div key={q.id} style={{ marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid #eee" }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>
                  {idx + 1}. {q.question_text} <span style={{ color: "#98a2b3", fontWeight: 400 }}>({q.marks} marks)</span>
                </div>
                {q.question_type === "mcq" ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {(JSON.parse(q.options_json || "[]")).map((opt) => (
                      <label key={opt} style={{ fontSize: 14 }}>
                        <input
                          type="radio"
                          name={`q_${q.id}`}
                          value={opt}
                          checked={answers[q.id] === opt}
                          onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                          style={{ marginRight: 8 }}
                        />
                        {opt}
                      </label>
                    ))}
                  </div>
                ) : (
                  <textarea
                    rows={4}
                    style={{ width: "100%", border: "1px solid #e4e7ec", borderRadius: 8, padding: 10 }}
                    value={answers[q.id] || ""}
                    onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                  />
                )}
              </div>
            ))}
            <button className="btn btn-primary" disabled={submitting} onClick={submit}>
              {submitting ? "Submitting..." : "Submit Test"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
