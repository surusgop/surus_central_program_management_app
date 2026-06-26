// Page-level views for the Surus Central Program Management kit.
const { useState: useStateP, useMemo } = React;

// ── Login (Google OAuth gate, restricted to workspace domain) ─────────────────
function LoginPage({ onLogin }) {
  return (
    <div className="d-flex align-items-center justify-content-center"
         style={{minHeight:"100vh",background:"#F4F6F8"}}>
      <div className="card text-center" style={{width:"380px",borderRadius:"4px",borderTop:"4px solid var(--il-red)"}}>
        <div className="card-body p-5">
          <h4 className="mb-1 brand-title" style={{fontSize:"1.6rem"}}>
            Surus Central Program Management
          </h4>
          <p className="text-muted small mb-4">Voter contact data by state and nation.</p>
          <button className="btn btn-primary w-100 d-flex align-items-center justify-content-center"
                  style={{gap:"8px",whiteSpace:"nowrap",fontSize:"13px"}} onClick={onLogin}>
            <i className="bi bi-google"></i> Sign in with Google
          </button>
          <p className="text-muted mt-3 mb-0" style={{fontSize:"12px"}}>
            Restricted to @surusenterprises.com accounts.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Home (centered hero) ────────────────────────────────────────────────────
function HomePage({ onNav }) {
  return (
    <div className="container-fluid">
      <div className="row">
        <div className="col-6 offset-3 text-center">
          <div style={{height:"3px",background:"var(--il-red)",width:"120px",margin:"48px auto 22px"}}></div>
          <h3 className="brand-title" style={{fontSize:"2rem"}}>Surus Central Program Management</h3>
          <p className="text-muted">
            Voter contact data by state and nation. Use the navigation above to explore.
          </p>
          <button className="btn btn-primary mt-2" onClick={()=>onNav("/analytics")}>
            View Contacts
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Shared filter bar ─────────────────────────────────────────────────────────
function FilterBar({ f, set, showDate }) {
  return (
    <div className="row mb-2 align-items-end">
      <div className={showDate ? "col-12 col-sm-6 col-lg-3 mb-3" : "col-12 col-sm-6 col-lg-4 mb-3"}>
        <MultiSelect label="State" options={STATES} value={f.states}
          placeholder="All states…" onChange={(v)=>set({...f,states:v})} />
      </div>
      <div className={showDate ? "col-12 col-sm-6 col-lg-3 mb-3" : "col-12 col-sm-6 col-lg-4 mb-3"}>
        <MultiSelect label="Nation" options={NATIONS} value={f.nations}
          placeholder="All nations…" onChange={(v)=>set({...f,nations:v})} />
      </div>
      <div className={showDate ? "col-12 col-sm-6 col-lg-3 mb-3" : "col-12 col-sm-6 col-lg-4 mb-3"}>
        <MultiSelect label="Group" options={GROUPS} value={f.groups}
          placeholder="All groups…" onChange={(v)=>set({...f,groups:v})} />
      </div>
      {showDate && (
        <div className="col-12 col-sm-6 col-lg-3 mb-3">
          <label className="fw-semibold small mb-1 d-block">Date Range</label>
          <select className="form-select" value={f.range || ""}
                  onChange={(e)=>{
                    const v=e.target.value;
                    if(!v){set({...f,range:"",start:null,end:null});}
                    else if(v==="jan"){set({...f,range:v,start:"2025-01-01",end:"2025-01-31"});}
                    else if(v==="q1"){set({...f,range:v,start:"2025-01-01",end:"2025-03-31"});}
                  }}>
            <option value="">All dates…</option>
            <option value="jan">Jan 2025</option>
            <option value="q1">Q1 2025</option>
          </select>
        </div>
      )}
    </div>
  );
}

function statusLine(f) {
  const parts = [
    f.states.length  ? [...f.states].sort().join(", ")  : "All states",
    f.nations.length ? [...f.nations].sort().join(", ") : "All nations",
    f.groups.length  ? [...f.groups].sort().join(", ")  : "All groups",
  ];
  if (f.start || f.end) parts.push(`${f.start||"…"} → ${f.end||"…"}`);
  return parts.join(" · ");
}

// ── Contacts (KPIs + donuts) ───────────────────────────────────────────────────
function ContactsPage({ f, set }) {
  const rows = useMemo(()=>filterRows(f), [JSON.stringify(f)]);
  const sum = (k)=>rows.reduce((a,r)=>a+(r[k]||0),0);

  const typeLabels=[], typeValues=[];
  CONTACT_TYPES.forEach(([label,field])=>{ const v=sum(field); if(v>0){typeLabels.push(label);typeValues.push(v);} });

  // Frequency uses only the latest week in range
  const latest = rows.length ? rows.reduce((m,r)=>r.week_start>m?r.week_start:m, rows[0].week_start) : null;
  const latestRows = rows.filter(r=>r.week_start===latest);
  const freqLabels=[], freqValues=[];
  CONTACT_FREQUENCY.forEach(([label,field])=>{ const v=latestRows.reduce((a,r)=>a+(r[field]||0),0); if(v>0){freqLabels.push(label);freqValues.push(v);} });

  return (
    <div className="container-fluid px-4">
      <div className="row"><div className="col-12">
        <h4 className="my-3 brand-title">Contact Summary</h4>
      </div></div>
      <FilterBar f={f} set={set} showDate={true} />
      <div className="row mb-4">
        <div className="col-12 col-md-4 mb-3">
          <KpiCard icon="bi-telephone-fill" color="#C1272D" value={fmt(sum("total_contacts"))} label="Total Contacts" />
        </div>
        <div className="col-12 col-md-4 mb-3">
          <KpiCard icon="bi-people-fill" color="#C1272D" value={fmt(sum("unique_contacts"))} label="Unique Contacts" />
        </div>
        <div className="col-12 col-md-4 mb-3">
          <KpiCard icon="bi-calendar-event-fill" color="#C1272D" value={fmt(sum("total_events"))} label="Total Events" />
        </div>
      </div>
      <div className="row align-items-stretch">
        <div className="col-12 col-lg-6 mb-4">
          <DonutCard title="Contact Type Breakdown" labels={typeLabels} values={typeValues}
                     emptyMsg="No contact data for this selection." />
        </div>
        <div className="col-12 col-lg-6 mb-4">
          <DonutCard title="Contacts by Frequency" labels={freqLabels} values={freqValues}
                     emptyMsg="No frequency data for this selection." />
        </div>
      </div>
      <div className="row"><div className="col-12">
        <div className="text-muted small mb-3">{statusLine(f)}</div>
      </div></div>
    </div>
  );
}

// ── Contacts Detail (grid) ──────────────────────────────────────────────────
function ContactsDetailPage({ f, set }) {
  const rows = useMemo(()=>filterRows(f), [JSON.stringify(f)]);
  const cols = [
    ["State","state"],["Group","group"],["Nation","nation"],["Week","week_start"],
    ["Total Contacts","total_contacts"],["Unique Contacts","unique_contacts"],
    ["Door Knock","contact_door_knock"],["Email","contact_email"],["Phone","contact_phone"],
    ["Text","contact_text"],["Snail Mail","contact_snail_mail"],["Face to Face","contact_face_to_face"],
    ["Other","contact_other"],["Total Events","total_events"],
  ];
  const numeric = (field)=>!["state","group","nation","week_start"].includes(field);
  return (
    <div className="container-fluid px-4">
      <div className="row"><div className="col-12">
        <h4 className="my-3 brand-title">Contacts Detail</h4>
      </div></div>
      <FilterBar f={f} set={set} showDate={false} />
      <div className="row"><div className="col-12 mb-4">
        <div className="card shadow-sm">
          <div className="card-header">Contacts by State, Nation &amp; Group</div>
          <div className="card-body p-0">
            <div style={{overflowX:"auto"}}>
              <table className="ag-mock" style={{width:"100%",borderCollapse:"collapse",fontSize:"13px",color:"var(--il-navy)"}}>
                <thead>
                  <tr style={{background:"var(--il-red)"}}>
                    {cols.map(([h,field])=>(
                      <th key={field} style={{padding:"9px 12px",fontWeight:700,color:"#fff",
                          textAlign:numeric(field)?"right":"left",whiteSpace:"nowrap",
                          textTransform:"uppercase",letterSpacing:".03em",fontSize:"11px",
                          position:field==="state"?"sticky":"static",left:0,
                          background:"var(--il-red)"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r,i)=>(
                    <tr key={i} style={{background:i%2 ? "var(--il-gray-band)" : "#fff",
                        borderBottom:"1px solid var(--il-border)"}}>
                      {cols.map(([h,field])=>(
                        <td key={field} style={{padding:"8px 12px",
                            textAlign:numeric(field)?"right":"left",whiteSpace:"nowrap",
                            fontWeight:field==="state"?800:400,
                            color:"var(--il-navy)",
                            fontVariantNumeric:numeric(field)?"tabular-nums":"normal",
                            position:field==="state"?"sticky":"static",left:0,
                            background:i%2 ? "var(--il-gray-band)" : "#fff"}}>
                          {field==="week_start" ? new Date(r[field]).toLocaleDateString()
                            : numeric(field) ? fmt(r[field]) : r[field]}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {rows.length===0 && (
                    <tr><td colSpan={cols.length} className="text-center text-muted py-4">
                      No rows for this selection.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div></div>
      <div className="row"><div className="col-12">
        <div className="text-muted small mb-3">{statusLine(f)}</div>
      </div></div>
    </div>
  );
}

Object.assign(window, { LoginPage, HomePage, ContactsPage, ContactsDetailPage, FilterBar, statusLine });
