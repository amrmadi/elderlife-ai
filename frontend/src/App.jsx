import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

const LEVELS = ["Normal", "Low", "Medium", "High", "Critical"];

export default function App() {
  const [people, setPeople] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState([]);
  const [form, setForm] = useState({ kind: "medication", title: "", time: "08:00" });

  const load = useCallback(async () => {
    try {
      setPeople(await api("/elderly"));
      setAlerts(await api("/alerts"));
      if (sel) {
        setDetail(await api(`/elderly/${sel}`));
        setPlan(await api(`/elderly/${sel}/careplan`));
      }
      setError("");
    } catch {
      setError("Can't reach the server. Start the backend on port 8000.");
    }
  }, [sel]);

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const act = async (fn) => { await fn(); load(); };
  const counts = LEVELS.map((l) => people.filter((p) => p.level === l).length);
  const openAlerts = alerts.filter((a) => a.status === "open");

  return (
    <div className="app">
      <header>
        <h1>ElderLife AI</h1>
        <p>{people.length} people monitored, {openAlerts.length} open alerts</p>
        <button onClick={() => act(() => api("/simulate/seed", "POST"))}>Load sample data</button>
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      <section aria-label="Risk distribution">
        <div className="bar">
          {LEVELS.map((l, i) => counts[i] > 0 && (
            <div key={l} data-level={l} style={{ flex: counts[i] }}>{counts[i]}</div>
          ))}
        </div>
        <ul className="legend">{LEVELS.map((l, i) => <li key={l} data-level={l}>{l}: {counts[i]}</li>)}</ul>
      </section>

      <main>
        <section>
          <h2>Who needs attention</h2>
          {people.length === 0 && <p className="empty">No people yet. Load sample data to see the dashboard.</p>}
          <ul className="people">
            {people.map((p) => (
              <li key={p.id}>
                <button className={sel === p.id ? "row on" : "row"} onClick={() => setSel(p.id)} data-level={p.level}>
                  <span className="dot" />
                  <span className="name">{p.name}<small>{p.age} years old</small></span>
                  <span className="lvl">{p.level}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section>
          {detail ? (
            <div className="detail" data-level={detail.risk.level}>
              <h2>{detail.name}</h2>
              <p className="big">{detail.risk.level} risk <small>score {detail.risk.score}</small></p>
              <h3>Why?</h3>
              {detail.risk.reasons.length ? <ul>{detail.risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : <p>Nothing unusual right now.</p>}
              {detail.risk.next_step && <p className="next">Next step: {detail.risk.next_step}</p>}
              <p>Last check-in delay: {detail.risk.signals.checkin_delay_min} min</p>
              <div className="actions">
                <button onClick={() => act(() => api(`/elderly/${detail.id}/checkin`, "POST"))}>Record check-in</button>
                <button onClick={() => act(() => api("/events", "POST", { elderly_id: detail.id, kind: "fall" }))}>Simulate fall</button>
                <button onClick={() => act(() => api("/events", "POST", { elderly_id: detail.id, kind: "ok" }))}>Person says "I'm OK"</button>
              </div>
              <h3>Care plan</h3>
              <p className="note">Reminders from the recorded plan only. This app does not diagnose or change doses.</p>
              {plan.length === 0 && <p className="empty">No items yet. Add the first reminder below.</p>}
              <ul className="plan">
                {plan.map((i) => (
                  <li key={i.id} className={i.done_today ? "done" : i.overdue ? "overdue" : ""}>
                    <label>
                      <input type="checkbox" checked={i.done_today} onChange={() => act(() => api(`/careplan/${i.id}/done`, "POST"))} />
                      <span className="t">{i.time}</span> {i.title} <small>({i.kind})</small>{i.overdue && <strong className="od"> Overdue</strong>}
                    </label>
                    <button aria-label={`Remove ${i.title}`} onClick={() => act(() => api(`/careplan/${i.id}`, "DELETE"))}>Remove</button>
                  </li>
                ))}
              </ul>
              <form className="add" onSubmit={(e) => { e.preventDefault(); if (!form.title.trim()) return;
                act(() => api(`/elderly/${detail.id}/careplan`, "POST", form)); setForm({ ...form, title: "" }); }}>
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} aria-label="Type">
                  <option value="medication">Medication</option><option value="meal">Meal</option>
                  <option value="water">Water</option><option value="activity">Activity</option>
                </select>
                <input type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} aria-label="Time" />
                <input placeholder="What should be done?" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} aria-label="Title" />
                <button type="submit">Add reminder</button>
              </form>
            </div>
          ) : <p className="empty">Select a person to see why their risk level was set.</p>}

          <h2>Alerts</h2>
          {alerts.length === 0 && <p className="empty">No alerts. Alerts appear when risk reaches High.</p>}
          <ul className="alerts">
            {alerts.map((a) => (
              <li key={a.id} data-level={a.level} className={a.status}>
                <strong>{a.name}</strong> {a.level}: {a.reasons}
                {a.status === "open"
                  ? <button onClick={() => act(() => api(`/alerts/${a.id}/ack`, "POST"))}>Acknowledge</button>
                  : <em>Acknowledged</em>}
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
