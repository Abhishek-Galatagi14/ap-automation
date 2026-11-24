import React, { useEffect, useState, useCallback } from "react";
const api = async (u, o = {}) => { const r = await fetch("/api" + u, o); return r.json(); };
const post = (u, b) => api(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) });
const Tag = ({ s }) => <span className={"tag " + s}>{s.replace("_", " ")}</span>;
const Table = ({ rows, cols, onRow }) => !rows?.length ? <p className="sub">No data.</p> : (
  <div style={{ overflowX: "auto" }}><table><thead><tr>{cols.map(c => <th key={c}>{c.replace("_", " ")}</th>)}</tr></thead><tbody>
    {rows.map((r, i) => <tr key={i} className={onRow ? "click" : ""} onClick={() => onRow?.(r)}>{cols.map(c => <td key={c}>{c === "status" ? <Tag s={r[c]} /> : typeof r[c] === "object" ? JSON.stringify(r[c]) : String(r[c] ?? "")}</td>)}</tr>)}</tbody></table></div>);

function Dashboard() {
  const [d, setD] = useState(null); useEffect(() => { api("/dashboard/").then(setD); }, []);
  if (!d) return <p>Loading…</p>; const mx = Math.max(1, ...Object.values(d.aging));
  return <>
    <div className="grid">
      <div className="card"><div className="sub">Pending approvals</div><div className="kpi">{d.pending_approvals}</div></div>
      <div className="card"><div className="sub">Avg turnaround (hrs)</div><div className="kpi">{d.avg_turnaround_hours}</div></div>
      <div className="card"><div className="sub">OCR accuracy</div><div className="kpi">{d.ocr_accuracy}%</div></div>
      <div className="card"><div className="sub">Invoices</div><div className="kpi">{d.by_status.reduce((a, s) => a + s.n, 0)}</div></div></div>
    <div className="card"><h3>Invoice aging (days past due)</h3>{Object.entries(d.aging).map(([k, v]) => <div key={k} style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}><span style={{ width: 70 }}>{k}</span><div className="bar" style={{ width: (v / mx) * 300 + 4 }} /> {v}</div>)}</div>
    <div className="card"><h3>By status</h3><Table rows={d.by_status} cols={["status", "n"]} /></div>
    <div className="card"><h3>Vendor-wise analytics</h3><Table rows={d.vendors} cols={["name", "count", "total"]} /></div>
    <div className="card"><h3>Payment tracking</h3><Table rows={d.payments} cols={["status", "n", "amt"]} /></div></>;
}

function Invoices() {
  const [list, setList] = useState([]), [sel, setSel] = useState(null), [hot, setHot] = useState(false), [msg, setMsg] = useState("");
  const load = useCallback(() => api("/invoices/").then(setList), []); useEffect(() => { load(); }, [load]);
  const open = async id => setSel(await api(`/invoices/${id}/`));
  const upload = async (files, source = "upload") => { const f = new FormData(); [...files].forEach(x => f.append("files", x)); f.append("source", source); setMsg("Processing…");
    await fetch("/api/invoices/", { method: "POST", body: f }); setMsg(`${files.length} file(s) captured, OCR + validation done`); load(); };
  const act = async (path, body) => { const r = await post(`/invoices/${sel.id}/${path}/`, body); setSel(r.invoice || r); if (r.errors?.length) setMsg("Submit blocked: " + r.errors.join("; ")); load(); };
  const edit = async (k, v) => setSel(await api(`/invoices/${sel.id}/`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [k]: v }) }));
  return <>
    <div className={"drop" + (hot ? " hot" : "")} onDragOver={e => { e.preventDefault(); setHot(true); }} onDragLeave={() => setHot(false)} onDrop={e => { e.preventDefault(); setHot(false); upload(e.dataTransfer.files, "dragdrop"); }}>
      Drag & drop invoices here (PDF, JPG, PNG, TIFF — bulk supported) or <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff" onChange={e => upload(e.target.files)} />
      <div><button className="b" onClick={() => { const i = document.createElement("input"); i.type = "file"; i.multiple = true; i.onchange = () => upload(i.files, "email"); i.click(); }}>Simulate email ingestion</button></div>
      <div className="sub">{msg}</div></div><br />
    <div className="card"><Table rows={list} onRow={r => open(r.id)} cols={["id", "invoice_number", "vendor_name", "total", "po_number", "ocr_confidence", "source", "status"]} /></div>
    {sel && <div className="card"><h3>Invoice #{sel.id} <Tag s={sel.status} /> {sel.match_type && <span className="sub">{sel.match_type} match</span>}</h3>
      <div>{["invoice_number", "vendor_name", "vendor_gstin", "invoice_date", "due_date", "po_number", "subtotal", "tax", "total"].map(k => <label key={k} className="sub">{k}<br /><input defaultValue={sel[k]} key={sel.id + k + sel[k]} onBlur={e => e.target.value !== String(sel[k]) && edit(k, e.target.value)} /></label>)}</div>
      {sel.validation_errors.length > 0 && <div className="err">{sel.validation_errors.map((e, i) => <div key={i}>⚠ {e}</div>)}</div>}
      <h4>Line items</h4><Table rows={sel.lines} cols={["description", "qty", "rate", "amount"]} />
      <h4>Approvals</h4>{sel.steps.map(s => <div key={s.id}>{s.role}: <Tag s={s.status} /> {s.escalated && "⏫ escalated"} {s.status === "pending" && <><button className="b g" onClick={() => act("approve", { step_id: s.id, decision: "approved" })}>Approve</button><button className="b r" onClick={() => act("approve", { step_id: s.id, decision: "rejected", comment: prompt("Reason?") || "" })}>Reject</button></>}</div>)}
      <div style={{ marginTop: 10 }}>
        {["extracted", "exception"].includes(sel.status) && <button className="b" onClick={() => act("submit")}>Match & submit for approval</button>}
        {sel.status === "approved" && <button className="b" onClick={() => act("pay_request")}>Generate payment request</button>}
        {sel.status === "payment_requested" && <button className="b g" onClick={() => act("mark_paid")}>Mark paid (bank confirmation)</button>}
        {sel.file && <a href={sel.file} target="_blank" rel="noreferrer">View file</a>}</div>
      {sel.payment && <><h4>Payment {sel.payment.reference} <Tag s={sel.payment.status} /></h4>{sel.payment.advice && <pre>{sel.payment.advice}</pre>}</>}
      <details><summary>OCR text</summary><pre>{sel.ocr_text || "(none — scanned file without Tesseract; edit fields manually)"}</pre></details></div>}</>;
}

function Vendors() {
  const [l, setL] = useState([]), [f, setF] = useState({ name: "", gstin: "", bank_name: "", account_no: "", ifsc: "" }); const load = () => api("/vendors/").then(setL); useEffect(() => { load(); }, []);
  const add = async () => { const r = await post("/vendors/", f); if (r.gstin?.[0] && !r.id) alert(JSON.stringify(r)); setF({ name: "", gstin: "", bank_name: "", account_no: "", ifsc: "" }); load(); };
  return <><div className="card"><h3>Vendor onboarding</h3>{Object.keys(f).map(k => <input key={k} placeholder={k} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="b" onClick={add}>Add vendor (pending)</button></div>
    <div className="card"><table><thead><tr><th>Name</th><th>GSTIN</th><th>Bank</th><th>A/c</th><th>Status</th><th /></tr></thead><tbody>{l.map(v => <tr key={v.id}><td>{v.name}</td><td>{v.gstin}</td><td>{v.bank_name} {v.ifsc}</td><td>{v.account_no}</td><td><Tag s={v.status === "pending" ? "pending_approval" : v.status} /></td>
      <td>{v.status === "pending" && <><button className="b g" onClick={async () => { await post(`/vendors/${v.id}/decide/`, { status: "approved" }); load(); }}>Approve</button><button className="b r" onClick={async () => { await post(`/vendors/${v.id}/decide/`, { status: "rejected" }); load(); }}>Reject</button></>}</td></tr>)}</tbody></table></div></>;
}

function POs() {
  const [pos, setPos] = useState([]), [vs, setVs] = useState([]), [f, setF] = useState({ po_number: "", vendor: "", date: "", desc: "", qty: "", rate: "", grn_qty: "" });
  const load = () => { api("/pos/").then(setPos); api("/vendors/").then(setVs); }; useEffect(() => { load(); }, []);
  const add = async () => { await post("/pos/", { po_number: f.po_number, vendor: +f.vendor, date: f.date, total: (f.qty * f.rate * 1.18).toFixed(2), lines: [{ description: f.desc, qty: f.qty, rate: f.rate }] }); load(); };
  const grn = async p => { const q = prompt("Qty received?"); if (q) { await post("/grns/", { grn_number: "GRN-" + Date.now(), po: p.id, date: new Date().toISOString().slice(0, 10), lines: [{ description: p.lines[0]?.description || "item", qty_received: q }] }); alert("GRN saved → invoices for this PO now use 3-way match"); } };
  return <><div className="card"><h3>Create purchase order (total = qty × rate + 18% GST)</h3>
    <input placeholder="PO number" value={f.po_number} onChange={e => setF({ ...f, po_number: e.target.value })} />
    <select value={f.vendor} onChange={e => setF({ ...f, vendor: e.target.value })}><option value="">vendor…</option>{vs.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select>
    <input type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} />
    {["desc", "qty", "rate"].map(k => <input key={k} placeholder={k} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="b" onClick={add}>Create PO</button></div>
    <div className="card"><table><thead><tr><th>PO</th><th>Vendor</th><th>Date</th><th>Total</th><th>Items</th><th /></tr></thead><tbody>{pos.map(p => <tr key={p.id}><td>{p.po_number}</td><td>{p.vendor_name}</td><td>{p.date}</td><td>{p.total}</td><td>{p.lines.map(l => `${l.description} ×${l.qty}`).join(", ")}</td><td><button className="b" onClick={() => grn(p)}>+ GRN</button></td></tr>)}</tbody></table></div></>;
}

function Reports() {
  const names = ["aging", "status", "exceptions", "audit", "gst"], [n, setN] = useState("aging"), [rows, setRows] = useState([]);
  useEffect(() => { api(`/reports/${n}/`).then(setRows); }, [n]);
  const cols = rows[0] ? Object.keys(rows[0]) : [];
  return <div className="card"><h3>Reports</h3>{names.map(x => <button key={x} className={"b" + (x === n ? " g" : "")} onClick={() => setN(x)}>{x}</button>)}
    <button className="b" onClick={async () => alert((await post("/escalate/", { hours: 24 })).escalated + " step(s) escalated")}>Run escalation</button><Table rows={rows} cols={cols} /></div>;
}

export default function App() {
  const tabs = { Dashboard, Invoices, Vendors, "Purchase Orders": POs, Reports }; const [t, setT] = useState("Dashboard"); const C = tabs[t];
  return <><nav><b>AP Automation</b>{Object.keys(tabs).map(k => <button key={k} className={t === k ? "on" : ""} onClick={() => setT(k)}>{k}</button>)}</nav><main><C key={t} /></main></>;
}
