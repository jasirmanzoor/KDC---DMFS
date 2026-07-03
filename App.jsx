import { useState, useEffect, useCallback } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── helpers ──────────────────────────────────────────────────
const sar = (v) => `${Number(v || 0).toLocaleString("en-SA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SAR`;
const pct = (v) => `${Number(v || 0).toFixed(1)}%`;
const api = async (path, opts = {}) => {
  const r = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return r.json();
};

// ── Status badges ─────────────────────────────────────────────
const STATUS_COLORS = {
  active: "bg-green-100 text-green-800",    hold: "bg-red-100 text-red-800",
  suspended: "bg-gray-100 text-gray-600",   terminated: "bg-gray-100 text-gray-400 line-through",
  pending_pn: "bg-yellow-100 text-yellow-800",
  approved: "bg-green-100 text-green-800",  pending: "bg-yellow-100 text-yellow-800",
  expired: "bg-gray-100 text-gray-500",     rejected: "bg-red-100 text-red-800",
  critical: "bg-red-100 text-red-800",      high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",  low: "bg-blue-100 text-blue-800",
  Per_Packet: "bg-blue-100 text-blue-800",  Fixed_Salary: "bg-purple-100 text-purple-800",
  Salary_Owan: "bg-teal-100 text-teal-800",
};
const Badge = ({ label, type }) => (
  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_COLORS[type || label] || "bg-gray-100 text-gray-600"}`}>
    {label}
  </span>
);

// ── Layout ────────────────────────────────────────────────────
const NAV = [
  { key: "dashboard",   label: "Dashboard",      icon: "📊" },
  { key: "drivers",     label: "Drivers",         icon: "👥" },
  { key: "sby",         label: "SBY DS03 Ops",   icon: "🏭" },
  { key: "payroll",     label: "Payroll",         icon: "🧮" },
  { key: "deductions",  label: "Deductions",      icon: "📋" },
  { key: "loans",       label: "Loan Requests",   icon: "💳" },
  { key: "pn",          label: "PN Requests",     icon: "📄" },
  { key: "risk",        label: "Risk & QA",       icon: "⚠️" },
  { key: "finance",     label: "Financial",       icon: "💰" },
  { key: "reports",     label: "Reports",         icon: "📈" },
  { key: "import",      label: "Import & Sync",   icon: "🔄" },
  { key: "settings",    label: "Settings",        icon: "⚙️" },
];

function Sidebar({ page, setPage, user }) {
  return (
    <div className="w-56 bg-[#1E3A5F] min-h-screen flex flex-col text-white">
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#E8A020] rounded-full flex items-center justify-center font-bold text-sm">KDC</div>
          <div>
            <div className="font-semibold text-sm">KDC DMFS</div>
            <div className="text-xs opacity-60">Operations Platform</div>
          </div>
        </div>
      </div>
      <nav className="flex-1 py-2">
        {NAV.map(n => (
          <button key={n.key}
            onClick={() => setPage(n.key)}
            className={`w-full text-left px-4 py-2.5 text-sm flex items-center gap-2.5 transition-all
              ${page === n.key ? "bg-[#E8A020] font-semibold" : "hover:bg-white/10"}`}>
            <span>{n.icon}</span>{n.label}
          </button>
        ))}
      </nav>
      <div className="p-4 border-t border-white/10 text-xs opacity-70">
        {user?.name || "Owner"} · {user?.role || "admin"}
      </div>
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────
function Dashboard() {
  const [data, setData] = useState(null);
  useEffect(() => { api("/api/dashboard").then(setData).catch(console.error); }, []);
  if (!data) return <div className="p-8 text-gray-400">Loading dashboard...</div>;
  const s = data.stats;
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-[#1E3A5F]">Owner Dashboard</h1>
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Active Drivers", value: s.active_drivers, color: "text-green-600" },
          { label: "Drivers on HOLD", value: s.held_drivers, color: s.held_drivers > 0 ? "text-red-600" : "text-gray-600" },
          { label: "PN Expiring ≤48h", value: s.pns_expiring_48h, color: s.pns_expiring_48h > 0 ? "text-red-600" : "text-green-600" },
          { label: "Total Outstanding", value: sar(s.total_outstanding), color: "text-orange-600" },
          { label: "Pending Loans", value: s.pending_loans, color: "text-blue-600" },
          { label: "Critical Risks", value: s.critical_flags, color: s.critical_flags > 0 ? "text-red-600" : "text-green-600" },
          { label: "SBY DS03 Drivers", value: s.sby_drivers, color: "text-teal-600" },
          { label: "Pending PNS", value: s.pending_pns, color: "text-yellow-600" },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
            <div className={`text-2xl font-bold ${k.color}`}>{k.value}</div>
            <div className="text-sm text-gray-500 mt-1">{k.label}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
          <h3 className="font-semibold text-gray-700 mb-3">Active Drivers by Vendor</h3>
          {data.vendor_breakdown.map(v => (
            <div key={v.vendor_code} className="flex justify-between py-1.5 border-b last:border-0 text-sm">
              <span className="font-medium">{v.vendor_code}</span>
              <Badge label={`${v.count} drivers`} type="active" />
            </div>
          ))}
        </div>
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
          <h3 className="font-semibold text-gray-700 mb-3">Recent Transactions</h3>
          {data.recent_transactions.slice(0,8).map(t => (
            <div key={t.id} className="flex justify-between py-1.5 border-b last:border-0 text-sm">
              <span className="text-gray-600 truncate max-w-[200px]">{t.description || t.category}</span>
              <span className={t.direction === "money_in" ? "text-green-600 font-semibold" : "text-red-600 font-semibold"}>
                {t.direction === "money_in" ? "+" : "-"}{sar(t.amount)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Drivers ───────────────────────────────────────────────────
function Drivers({ vendorFilter }) {
  const [drivers, setDrivers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [vendor, setVendor] = useState(vendorFilter || "");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    const p = new URLSearchParams({ page, limit: 50 });
    if (search) p.set("search", search);
    if (vendor) p.set("vendor", vendor);
    if (status) p.set("status", status);
    const r = await api(`/api/drivers?${p}`);
    setDrivers(r.data); setTotal(r.total);
  }, [page, search, vendor, status]);

  useEffect(() => { load(); }, [load]);

  const loadDetail = async (nid) => {
    setSelected(nid);
    const r = await api(`/api/drivers/${nid}`);
    setDetail(r);
  };

  return (
    <div className="p-6 flex gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-[#1E3A5F]">
            Drivers {vendorFilter ? `— ${vendorFilter}` : ""}
            <span className="text-sm font-normal text-gray-500 ml-2">{total} total</span>
          </h1>
        </div>
        <div className="flex gap-2 mb-4">
          <input className="border rounded-lg px-3 py-2 text-sm flex-1" placeholder="Search NID, name, DA code..."
            value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
          <select className="border rounded-lg px-3 py-2 text-sm" value={vendor} onChange={e => setVendor(e.target.value)}>
            <option value="">All Vendors</option>
            {["iMile","Ajex","Keeta","Naqel","J&T","Landmark","SBY_DS03"].map(v => <option key={v}>{v}</option>)}
          </select>
          <select className="border rounded-lg px-3 py-2 text-sm" value={status} onChange={e => setStatus(e.target.value)}>
            <option value="">All Status</option>
            {["active","hold","suspended","terminated","pending_pn"].map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>{["NID","Name","Station","Vendor","DA Type","PNS","Status"].map(h =>
                <th key={h} className="px-3 py-3 text-left font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {drivers.map(d => (
                <tr key={d.id} onClick={() => loadDetail(d.national_id)}
                  className={`border-b hover:bg-gray-50 cursor-pointer ${selected === d.national_id ? "bg-blue-50" : ""}`}>
                  <td className="px-3 py-2.5 font-mono text-xs text-gray-500">{d.national_id}</td>
                  <td className="px-3 py-2.5">
                    <div className="font-medium">{d.name_en || d.name_ar}</div>
                    {d.name_en && d.name_ar && <div className="text-xs text-gray-400">{d.name_ar}</div>}
                  </td>
                  <td className="px-3 py-2.5 text-gray-600 text-xs">{d.station_name || "—"}</td>
                  <td className="px-3 py-2.5"><Badge label={d.vendor_code} /></td>
                  <td className="px-3 py-2.5"><Badge label={d.da_type} type={d.da_type} /></td>
                  <td className="px-3 py-2.5"><Badge label={d.pns_status} type={d.pns_status} /></td>
                  <td className="px-3 py-2.5"><Badge label={d.employment_status} type={d.employment_status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 border-t flex items-center justify-between text-sm text-gray-500">
            <span>Page {page}</span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => Math.max(1,p-1))} disabled={page===1}
                className="px-3 py-1 border rounded disabled:opacity-40">←</button>
              <button onClick={() => setPage(p => p+1)} disabled={drivers.length < 50}
                className="px-3 py-1 border rounded disabled:opacity-40">→</button>
            </div>
          </div>
        </div>
      </div>

      {detail && (
        <div className="w-96 bg-white rounded-xl shadow-sm border border-gray-100 p-4 h-fit sticky top-6">
          <div className="flex justify-between items-start mb-3">
            <div>
              <div className="font-bold text-lg">{detail.driver.name_en || detail.driver.name_ar}</div>
              {detail.driver.name_ar && <div className="text-gray-500 text-sm">{detail.driver.name_ar}</div>}
              <div className="text-xs text-gray-400 mt-0.5">{detail.driver.national_id}</div>
            </div>
            <button onClick={() => { setSelected(null); setDetail(null); }} className="text-gray-400 hover:text-gray-600">✕</button>
          </div>
          <div className="flex gap-2 mb-4 flex-wrap">
            <Badge label={detail.driver.employment_status} type={detail.driver.employment_status} />
            <Badge label={detail.driver.pns_status} type={detail.driver.pns_status} />
            <Badge label={detail.driver.da_type} type={detail.driver.da_type} />
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm mb-4">
            {[
              ["Mobile", detail.driver.mobile],
              ["Vendor", detail.driver.vendor_code],
              ["Station", detail.driver.station_name],
              ["DA Code", detail.driver.da_code],
              ["Bank", detail.driver.bank_name],
              ["IBAN", detail.driver.iban_number ? `${detail.driver.iban_number.slice(0,8)}...` : "—"],
            ].map(([k,v]) => (
              <div key={k}><div className="text-xs text-gray-400">{k}</div><div className="font-medium text-gray-800 truncate">{v || "—"}</div></div>
            ))}
          </div>
          <div className="bg-orange-50 rounded-lg p-3 mb-3">
            <div className="text-xs text-orange-600 font-semibold uppercase mb-1">Financial Summary</div>
            <div className="flex justify-between text-sm">
              <span>Total Outstanding</span>
              <span className="font-bold text-orange-700">{sar(detail.total_outstanding)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span>Active Deductions</span>
              <span className="font-semibold">{detail.deductions.length}</span>
            </div>
          </div>
          {detail.deductions.length > 0 && (
            <div className="mb-3">
              <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Active Deductions</div>
              {detail.deductions.map(d => (
                <div key={d.id} className="flex justify-between text-xs py-1 border-b">
                  <span>{d.deduction_type}</span>
                  <span className="font-semibold text-red-600">{sar(d.remaining_balance)}</span>
                </div>
              ))}
            </div>
          )}
          {detail.payroll_history.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Last Payrolls</div>
              {detail.payroll_history.slice(0,3).map(p => (
                <div key={p.id} className="flex justify-between text-xs py-1 border-b">
                  <span className="text-gray-600">{p.cycle_name}</span>
                  <span className="font-semibold text-green-700">{sar(p.net_payable)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── SBY DS03 Ops ─────────────────────────────────────────────
function SBYOps() {
  const [tab, setTab] = useState("drivers");
  const tabs = ["drivers","deliveries","payroll","deductions","risk","reports"];
  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 bg-teal-600 rounded-xl flex items-center justify-center text-white font-bold">S</div>
        <div>
          <h1 className="text-2xl font-bold text-[#1E3A5F]">SBY DS03 Operations</h1>
          <p className="text-sm text-gray-500">KDC Internal Dispatch Station 03</p>
        </div>
      </div>
      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all capitalize
              ${tab===t ? "bg-teal-600 text-white shadow-sm" : "text-gray-600 hover:bg-gray-200"}`}>
            {t}
          </button>
        ))}
      </div>
      {tab === "drivers" && <Drivers vendorFilter="SBY_DS03" />}
      {tab !== "drivers" && (
        <div className="bg-white rounded-xl p-8 text-center text-gray-400 border border-gray-100">
          <div className="text-4xl mb-3">🏭</div>
          <div className="font-medium">SBY DS03 {tab.charAt(0).toUpperCase() + tab.slice(1)}</div>
          <div className="text-sm mt-1">Import SBY delivery data first via Import & Sync</div>
        </div>
      )}
    </div>
  );
}

// ── Import & Sync ─────────────────────────────────────────────
function ImportSync() {
  const [log, setLog] = useState([]);
  const [running, setRunning] = useState(false);
  const [logId, setLogId] = useState(null);

  const addLog = (msg, type="info") => setLog(prev => [...prev, { msg, type, time: new Date().toLocaleTimeString() }]);

  const syncDrivers = async () => {
    setRunning(true); setLog([]);
    addLog("🚀 Starting driver sync from Google Sheets...");
    try {
      const { log_id } = await api("/api/sync/drivers", { method: "POST" });
      setLogId(log_id);
      addLog(`✅ Sync job started — Log ID: ${log_id}`);
      addLog("⏳ Processing 2,652+ drivers... Check sync status below.");

      // Poll for completion
      let done = false;
      for (let i = 0; i < 60 && !done; i++) {
        await new Promise(r => setTimeout(r, 3000));
        const status = await api(`/api/sync/status/${log_id}`);
        if (status.status === "completed") {
          addLog(`✅ COMPLETE: ${status.records_created} new · ${status.records_updated} updated · ${status.records_skipped} skipped`, "success");
          if (status.errors_count > 0) addLog(`⚠️ ${status.errors_count} row errors (non-critical)`, "warn");
          done = true;
        } else if (status.status === "failed") {
          addLog(`❌ FAILED: ${JSON.parse(status.error_log || "[]")[0]}`, "error");
          done = true;
        } else {
          addLog(`⏳ Still processing... (${status.records_created + status.records_updated} done so far)`);
        }
      }
    } catch(e) {
      addLog(`❌ Error: ${e.message}`, "error");
    }
    setRunning(false);
  };

  const logColors = { success: "text-green-400", error: "text-red-400", warn: "text-yellow-400", info: "text-gray-300" };

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-2xl font-bold text-[#1E3A5F] mb-2">Import & Sync</h1>
      <p className="text-gray-500 text-sm mb-6">KDC HIRING & FINANCE — Spreadsheet ID: 1WzWa3UtzcAlnmt76cwUeQhd7K8kfiFa8fnVWgQEatoU</p>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Sync Drivers", desc: "Hiring sheet → all 2,652+ drivers", icon: "👥", action: syncDrivers },
          { label: "Sync PN Requests", desc: "pending Naifaz sheet", icon: "📄", action: () => addLog("Coming soon — add /api/sync/pn endpoint") },
          { label: "Sync Loans & Deductions", desc: "Loans&CN sheet", icon: "💳", action: () => addLog("Coming soon") },
          { label: "Sync Delivery Data", desc: "All 6 vendor payroll sheets", icon: "📦", action: () => addLog("Coming soon") },
          { label: "Sync Pricing", desc: "Price iMile sheet", icon: "💰", action: () => addLog("Coming soon") },
          { label: "Full Sync — All Sheets", desc: "Runs all syncs in sequence", icon: "🚀", action: syncDrivers },
        ].map(s => (
          <button key={s.label} onClick={s.action} disabled={running}
            className="bg-white border border-gray-200 rounded-xl p-4 text-left hover:border-[#1E3A5F] hover:shadow-sm transition-all disabled:opacity-50">
            <div className="text-2xl mb-2">{s.icon}</div>
            <div className="font-semibold text-sm text-gray-800">{s.label}</div>
            <div className="text-xs text-gray-500 mt-1">{s.desc}</div>
          </button>
        ))}
      </div>

      {log.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-4 font-mono text-sm max-h-96 overflow-y-auto">
          {log.map((l, i) => (
            <div key={i} className={`${logColors[l.type]} py-0.5`}>
              <span className="text-gray-600 text-xs mr-2">[{l.time}]</span>{l.msg}
            </div>
          ))}
          {running && <div className="text-blue-400 animate-pulse py-0.5">▌ Processing...</div>}
        </div>
      )}
    </div>
  );
}

// ── Payroll ───────────────────────────────────────────────────
function Payroll() {
  const [cycles, setCycles] = useState([]);
  const [selected, setSelected] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [newCycle, setNewCycle] = useState({ cycle_name: "", period_start: "", period_end: "" });

  useEffect(() => {
    api("/api/payroll/cycles").then(setCycles).catch(() => setCycles([]));
  }, []);

  const calculate = async (cycleId) => {
    setLoading(true);
    try {
      const r = await api(`/api/payroll/calculate/${cycleId}`);
      setResults(r);
    } catch(e) { alert(e.message); }
    setLoading(false);
  };

  const finalize = async () => {
    if (!selected || !confirm("Finalize payroll? This will update all deduction balances and create transaction records.")) return;
    try {
      const r = await api(`/api/payroll/finalize/${selected}`, { method: "POST" });
      alert(`✅ Payroll finalized! ${r.drivers_processed} drivers processed. Net: ${sar(r.totals.net)}`);
      setResults(null);
    } catch(e) { alert(e.message); }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-[#1E3A5F]">Payroll</h1>
        <button onClick={() => setShowNew(true)}
          className="bg-[#1E3A5F] text-white px-4 py-2 rounded-lg text-sm">+ New Cycle</button>
      </div>

      {!selected ? (
        <div className="grid grid-cols-2 gap-4">
          {cycles.length === 0 && (
            <div className="col-span-2 text-center py-12 text-gray-400">
              <div className="text-4xl mb-3">🧮</div>
              <div>No payroll cycles yet. Create one to get started.</div>
            </div>
          )}
          {cycles.map(c => (
            <div key={c.id} className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-semibold">{c.cycle_name}</div>
                  <div className="text-sm text-gray-500">{c.period_start} → {c.period_end}</div>
                </div>
                <Badge label={c.status} type={c.status === "paid" ? "approved" : "pending"} />
              </div>
              {c.total_net > 0 && (
                <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                  <div><div className="text-xs text-gray-400">Drivers</div><div className="font-bold">{c.total_drivers}</div></div>
                  <div><div className="text-xs text-gray-400">Gross</div><div className="font-bold">{sar(c.total_gross)}</div></div>
                  <div><div className="text-xs text-gray-400">Net</div><div className="font-bold text-green-700">{sar(c.total_net)}</div></div>
                </div>
              )}
              <button onClick={() => { setSelected(c.id); calculate(c.id); }}
                className="mt-3 w-full bg-[#1E3A5F] text-white py-2 rounded-lg text-sm">
                {c.status === "paid" ? "View Results" : "Open & Calculate"}
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div>
          <button onClick={() => { setSelected(null); setResults(null); }} className="text-sm text-blue-600 mb-4">← Back to cycles</button>
          {loading && <div className="text-center py-12 text-gray-400">🧮 Calculating payroll for all drivers...</div>}
          {results && (
            <div>
              <div className="grid grid-cols-4 gap-4 mb-6">
                {[
                  { label: "Drivers", value: results.totals.drivers },
                  { label: "Total Gross", value: sar(results.totals.gross) },
                  { label: "Total Deductions", value: sar(results.totals.deductions) },
                  { label: "Total Net", value: sar(results.totals.net) },
                ].map(k => (
                  <div key={k.label} className="bg-white rounded-xl p-4 border border-gray-100">
                    <div className="text-xl font-bold text-[#1E3A5F]">{k.value}</div>
                    <div className="text-sm text-gray-500">{k.label}</div>
                  </div>
                ))}
              </div>
              {results.warnings.length > 0 && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-3 mb-4 text-sm text-yellow-800">
                  ⚠️ {results.warnings.length} warnings: {results.warnings.slice(0,3).join(" · ")}
                </div>
              )}
              <div className="bg-white rounded-xl border border-gray-100 overflow-hidden mb-4">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                    <tr>{["NID","Name","Vendor","Gross","Bank Fee","PN Fee","KDC Ded.","Net","Cap?","Status"].map(h =>
                      <th key={h} className="px-3 py-3 text-left">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {results.results.map(r => (
                      <tr key={r.national_id} className="border-b hover:bg-gray-50">
                        <td className="px-3 py-2 font-mono text-xs text-gray-400">{r.national_id}</td>
                        <td className="px-3 py-2 font-medium">{r.driver_name_ar || r.driver_name_en}</td>
                        <td className="px-3 py-2"><Badge label={r.vendor_code} /></td>
                        <td className="px-3 py-2 font-semibold">{sar(r.gross_salary)}</td>
                        <td className="px-3 py-2 text-gray-500">{sar(r.bank_fee)}</td>
                        <td className="px-3 py-2 text-gray-500">{r.pn_fee > 0 ? sar(r.pn_fee) : "—"}</td>
                        <td className="px-3 py-2 text-red-600">{sar(r.total_kdc)}</td>
                        <td className={`px-3 py-2 font-bold ${r.net_payable < 500 ? "text-red-600" : r.net_payable < 1500 ? "text-orange-600" : "text-green-700"}`}>
                          {sar(r.net_payable)}
                        </td>
                        <td className="px-3 py-2">{r.cap_applied ? <span className="text-orange-500 font-semibold">⚠️ {r.cap_pct}%</span> : "—"}</td>
                        <td className="px-3 py-2"><Badge label={r.payment_status} type={r.payment_status === "held" ? "hold" : "active"} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex gap-3">
                <button onClick={finalize}
                  className="bg-green-600 text-white px-6 py-2.5 rounded-lg font-semibold">
                  ✅ Finalize & Save Payroll
                </button>
                <a href={`${API}/api/export/payroll/${selected}`}
                  className="border border-gray-300 px-6 py-2.5 rounded-lg text-sm">
                  📥 Export CSV
                </a>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── PN Requests ───────────────────────────────────────────────
function PNRequests() {
  const [data, setData] = useState({ data: [], stats: {} });
  useEffect(() => { api("/api/pn-requests").then(setData).catch(console.error); }, []);
  const approve = async (id) => {
    await api(`/api/pn-requests/${id}/approve`, { method: "PUT" });
    api("/api/pn-requests").then(setData);
  };
  const s = data.stats;
  const urgencyColor = (days) => {
    if (days <= 0) return "bg-red-600 text-white";
    if (days <= 1) return "bg-red-500 text-white";
    if (days <= 2) return "bg-orange-500 text-white";
    if (days <= 3) return "bg-yellow-500 text-white";
    return "bg-green-100 text-green-800";
  };
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-[#1E3A5F] mb-4">PN Requests</h1>
      <div className="grid grid-cols-5 gap-3 mb-6">
        {[
          { label: "Active/Pending", value: s.active },
          { label: "Expiring Today", value: s.expiring_today, alert: s?.expiring_today > 0 },
          { label: "Expiring ≤3 Days", value: s.expiring_3days, alert: s?.expiring_3days > 0 },
          { label: "Approved", value: s.approved },
          { label: "Wasted Fees", value: sar(s.wasted_fees) },
        ].map(k => (
          <div key={k.label} className={`rounded-xl p-3 border ${k.alert ? "bg-red-50 border-red-200" : "bg-white border-gray-100"}`}>
            <div className={`text-xl font-bold ${k.alert ? "text-red-600" : "text-[#1E3A5F]"}`}>{k.value ?? "—"}</div>
            <div className="text-xs text-gray-500 mt-0.5">{k.label}</div>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>{["Urgency","Driver","Station","Status","Fee Status","Actions"].map(h =>
              <th key={h} className="px-3 py-3 text-left">{h}</th>)}</tr>
          </thead>
          <tbody>
            {data.data.map(pn => (
              <tr key={pn.id} className="border-b hover:bg-gray-50">
                <td className="px-3 py-2.5">
                  <span className={`px-2 py-1 rounded-full text-xs font-bold ${urgencyColor(pn.days_remaining)}`}>
                    {pn.days_remaining <= 0 ? "EXPIRED" : pn.days_remaining === 1 ? "1 DAY LEFT" : `${pn.days_remaining}d left`}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <div className="font-medium">{pn.driver_name_en || pn.driver_name_ar}</div>
                  <div className="text-xs text-gray-400">{pn.national_id}</div>
                </td>
                <td className="px-3 py-2.5 text-gray-600">{pn.station_name}</td>
                <td className="px-3 py-2.5"><Badge label={pn.naafiz_status} type={pn.naafiz_status} /></td>
                <td className="px-3 py-2.5">
                  <span className={`text-xs font-medium ${pn.fee_status === "wasted" ? "text-red-600" : pn.fee_status === "deducted" ? "text-green-600" : "text-gray-500"}`}>
                    {pn.fee_status}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {pn.naafiz_status === "pending" && (
                    <button onClick={() => approve(pn.id)}
                      className="text-xs bg-green-600 text-white px-2 py-1 rounded">✓ Approve</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Loan Requests ─────────────────────────────────────────────
function LoanRequests() {
  const [loans, setLoans] = useState([]);
  useEffect(() => { api("/api/loan-requests").then(r => setLoans(r.data)).catch(console.error); }, []);
  const riskIcon = { low: "🟢", medium: "🟡", high: "🟠", critical: "🔴" };
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-[#1E3A5F] mb-6">Loan Requests</h1>
      <div className="space-y-3">
        {loans.map(l => {
          const flags = JSON.parse(l.flag_reasons || "[]");
          return (
            <div key={l.id} className={`bg-white rounded-xl border p-4 ${l.risk_level === "critical" ? "border-red-300" : l.risk_level === "high" ? "border-orange-300" : "border-gray-100"}`}>
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-semibold">{l.driver_name} <span className="text-gray-400 font-mono text-xs">({l.national_id})</span></div>
                  <div className="text-sm text-gray-500">{l.station_name} · {l.request_category}</div>
                </div>
                <div className="text-right">
                  <div className="text-xl font-bold text-[#1E3A5F]">{sar(l.requested_amount)}</div>
                  <div className="text-sm">{riskIcon[l.risk_level]} {l.risk_level?.toUpperCase()} RISK</div>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-4 gap-3 text-sm bg-gray-50 rounded-lg p-3">
                <div><div className="text-xs text-gray-400">Cycle Earnings</div><div className="font-semibold">{sar(l.cycle_earnings_to_date)}</div></div>
                <div><div className="text-xs text-gray-400">Pending Deductions</div><div className="font-semibold text-red-600">{sar(l.pending_deductions_total)}</div></div>
                <div><div className="text-xs text-gray-400">Net Available</div><div className="font-semibold text-green-700">{sar(l.net_available)}</div></div>
                <div><div className="text-xs text-gray-400">Loan Ratio</div><div className={`font-bold ${l.loan_ratio > 100 ? "text-red-600" : l.loan_ratio > 80 ? "text-orange-600" : "text-green-600"}`}>{pct(l.loan_ratio)}</div></div>
              </div>
              {flags.length > 0 && (
                <div className="mt-2 flex gap-2 flex-wrap">
                  {flags.map(f => <span key={f} className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-medium">⚠️ {f}</span>)}
                </div>
              )}
              <div className="mt-3 flex gap-2">
                <button className="text-xs bg-green-600 text-white px-3 py-1.5 rounded-lg">✅ Approve</button>
                <button className="text-xs bg-red-600 text-white px-3 py-1.5 rounded-lg">❌ Reject</button>
                <button className="text-xs border border-gray-300 px-3 py-1.5 rounded-lg">📤 Escalate to Owner</button>
              </div>
            </div>
          );
        })}
        {loans.length === 0 && <div className="text-center py-12 text-gray-400">No loan requests yet</div>}
      </div>
    </div>
  );
}

// ── Placeholder pages ─────────────────────────────────────────
const Placeholder = ({ title, icon }) => (
  <div className="p-6 text-center py-24 text-gray-400">
    <div className="text-5xl mb-4">{icon}</div>
    <div className="text-xl font-semibold text-gray-500">{title}</div>
    <div className="text-sm mt-2">Full implementation deploying — backend API ready</div>
  </div>
);

// ── App Shell ─────────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState("dashboard");

  const pages = {
    dashboard:  <Dashboard />,
    drivers:    <Drivers />,
    sby:        <SBYOps />,
    payroll:    <Payroll />,
    deductions: <Placeholder title="Deductions Ledger" icon="📋" />,
    loans:      <LoanRequests />,
    pn:         <PNRequests />,
    risk:       <Placeholder title="Risk & QA Control Tower" icon="⚠️" />,
    finance:    <Placeholder title="Financial Center" icon="💰" />,
    reports:    <Placeholder title="Reports" icon="📈" />,
    import:     <ImportSync />,
    settings:   <Placeholder title="Settings" icon="⚙️" />,
  };

  return (
    <div className="flex min-h-screen bg-[#F4F6F9] font-sans">
      <Sidebar page={page} setPage={setPage} user={{ name: "Abdullah", role: "owner" }} />
      <main className="flex-1 min-w-0 overflow-auto">
        {pages[page]}
      </main>
    </div>
  );
}
