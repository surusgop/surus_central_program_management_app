// Reusable UI primitives for the Surus Central Program Management kit.
const { useState, useRef, useEffect } = React;

// ── Navbar (NavbarSimple, color=primary dark) ────────────────────────────────
function Navbar({ active, onNav, userEmail, onLogout }) {
  const links = [["Contacts","/analytics"], ["Contacts Detail","/contacts"], ["Debug","/debug"]];
  return (
    <nav className="navbar navbar-expand navbar-dark bg-primary shadow-sm px-4">
      <a className="navbar-brand" href="#" onClick={(e)=>{e.preventDefault();onNav("/");}}>
        Surus Central Program Management
      </a>
      <ul className="navbar-nav ms-auto align-items-center" style={{flexDirection:"row",gap:"4px"}}>
        {links.map(([label,href]) => (
          <li className="nav-item" key={href}>
            <a className={"nav-link px-3" + (active===href ? " active fw-semibold" : "")}
               href="#" onClick={(e)=>{e.preventDefault();onNav(href);}}>{label}</a>
          </li>
        ))}
        {userEmail && (
          <li className="nav-item dropdown ms-2 d-flex align-items-center" style={{gap:"10px"}}>
            <span className="text-white-50 small d-none d-md-inline">{userEmail}</span>
            <button className="btn btn-sm btn-outline-light" onClick={onLogout}>
              <i className="bi bi-box-arrow-right"></i>
            </button>
          </li>
        )}
      </ul>
    </nav>
  );
}

// ── Multi-select dropdown (mimics dcc.Dropdown multi) ─────────────────────────
function MultiSelect({ label, options, value, onChange, placeholder }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const toggle = (opt) =>
    onChange(value.includes(opt) ? value.filter(v=>v!==opt) : [...value, opt]);
  return (
    <div ref={ref} style={{position:"relative"}}>
      <label className="fw-semibold small mb-1 d-block">{label}</label>
      <div className="form-control d-flex align-items-center flex-wrap"
           style={{minHeight:"38px",gap:"4px",cursor:"pointer",padding:"4px 8px"}}
           onClick={()=>setOpen(o=>!o)}>
        {value.length === 0 && <span className="text-muted" style={{whiteSpace:"nowrap"}}>{placeholder}</span>}
        {value.map(v => (
          <span key={v} className="d-inline-flex align-items-center"
                style={{background:"var(--il-gray-band)",color:"var(--il-navy)",fontWeight:600,borderRadius:"3px",padding:"1px 6px",fontSize:"13px"}}>
            {v}
            <i className="bi bi-x" style={{marginLeft:"3px"}}
               onClick={(e)=>{e.stopPropagation();toggle(v);}}></i>
          </span>
        ))}
        <i className="bi bi-chevron-down ms-auto" style={{fontSize:"12px",color:"var(--il-slate)"}}></i>
      </div>
      {open && (
        <div className="shadow-sm" style={{position:"absolute",zIndex:20,top:"100%",left:0,right:0,
             background:"#fff",border:"1px solid var(--il-border)",borderRadius:"4px",marginTop:"2px",
             maxHeight:"220px",overflowY:"auto"}}>
          {options.map(opt => (
            <div key={opt} onClick={()=>toggle(opt)}
                 className="px-3 py-2 d-flex align-items-center justify-content-between"
                 style={{cursor:"pointer",fontSize:"14px",color:"var(--il-navy)",
                         background: value.includes(opt) ? "rgba(193,39,45,.08)" : "transparent"}}
                 onMouseEnter={(e)=>{if(!value.includes(opt))e.currentTarget.style.background="var(--il-gray-band)";}}
                 onMouseLeave={(e)=>{if(!value.includes(opt))e.currentTarget.style.background="transparent";}}>
              {opt}
              {value.includes(opt) && <i className="bi bi-check2" style={{color:"var(--il-red)"}}></i>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── KPI card ──────────────────────────────────────────────────────────────────
function KpiCard({ icon, color, value, label }) {
  return (
    <div className="card shadow-sm h-100 border-0">
      <div className="card-body text-center py-4">
        <i className={`bi ${icon} fs-2 mb-2`} style={{color}}></i>
        <h2 className="fw-bold mb-1" style={{fontVariantNumeric:"tabular-nums"}}>{value}</h2>
        <p className="text-muted small mb-0">{label}</p>
      </div>
    </div>
  );
}

// ── Donut chart card (real Plotly) ─────────────────────────────────────────────
function DonutCard({ title, labels, values, emptyMsg }) {
  const elRef = useRef(null);
  useEffect(() => {
    if (!elRef.current || !window.Plotly) return;
    if (!values.length) {
      Plotly.purge(elRef.current);
      Plotly.newPlot(elRef.current, [], {
        margin:{t:20,b:20,l:20,r:20}, paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)", height:300,
        annotations:[{text:emptyMsg,x:0.5,y:0.5,xref:"paper",yref:"paper",
          showarrow:false,font:{size:14,color:"#75859E"}}],
        xaxis:{visible:false}, yaxis:{visible:false},
      }, {displayModeBar:false, responsive:true});
      return;
    }
    Plotly.react(elRef.current, [{
      type:"pie", labels, values, hole:0.45,
      textinfo:"label+percent",
      textfont:{color:"#FFFFFF"},
      marker:{colors: window.IL_CAT_COLORS, line:{color:"#FFFFFF", width:2}},
      hovertemplate:"%{label}: %{value:,}<extra></extra>",
    }], {
      margin:{t:20,b:20,l:20,r:20}, paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)", height:300,
      showlegend:true, legend:{orientation:"v",x:1.02,y:0.5,font:{color:"#2A313C"}},
      font:{family:"'Open Sans', sans-serif"},
    }, {displayModeBar:false, responsive:true});
  }, [JSON.stringify(labels), JSON.stringify(values)]);
  return (
    <div className="card shadow-sm border-0 h-100">
      <div className="card-header fw-semibold">{title}</div>
      <div className="card-body"><div ref={elRef} style={{width:"100%"}}></div></div>
    </div>
  );
}

Object.assign(window, { Navbar, MultiSelect, KpiCard, DonutCard });
