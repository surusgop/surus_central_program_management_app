// Mock data for the Surus Central Program Management UI kit.
// Mirrors the real dataset columns from data/queries.py (state/nation/group/week
// + total/unique contacts, contact-type breakdown, frequency, events).

const STATES  = ["Arizona", "New Mexico", "Oklahoma", "Montana", "South Dakota"];
const NATIONS = ["Navajo Nation", "Cherokee Nation", "Pueblo", "Crow Nation", "Oglala Lakota"];
const GROUPS  = ["BP", "CLP"];

const CONTACT_TYPES = [
  ["Door Knock",   "contact_door_knock"],
  ["Email",        "contact_email"],
  ["Phone",        "contact_phone"],
  ["Text",         "contact_text"],
  ["Snail Mail",   "contact_snail_mail"],
  ["Face to Face", "contact_face_to_face"],
  ["Other",        "contact_other"],
];

const CONTACT_FREQUENCY = [
  ["1 Time",   "contacted_1_time"],
  ["2 Times",  "contacted_2_times"],
  ["3 Times",  "contacted_3_times"],
  ["4+ Times", "contacted_4plus_times"],
];

// Surus Illinois marketing palette — used by the dashboard charts.
const IL_CAT_COLORS = ["#C1272D","#2A313C","#75859E","#E07A2F","#A11F24","#5B7FB0","#C9A24B"];

// Deterministic pseudo-random so the grid is stable across renders.
function _seed(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return () => { h += 0x6D2B79F5; let t = Math.imul(h ^ (h >>> 15), 1 | h);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

const WEEKS = ["2025-01-06","2025-01-13","2025-01-20","2025-01-27","2025-02-03","2025-02-10"];

// Build the full row set once.
const ALL_ROWS = (() => {
  const rows = [];
  STATES.forEach((state, si) => {
    const nation = NATIONS[si % NATIONS.length];
    const group  = GROUPS[si % GROUPS.length];
    WEEKS.forEach((week) => {
      const rnd = _seed(state + nation + group + week);
      const dk = Math.floor(rnd()*1400)+200;
      const em = Math.floor(rnd()*900)+100;
      const ph = Math.floor(rnd()*1200)+300;
      const tx = Math.floor(rnd()*1600)+400;
      const sm = Math.floor(rnd()*300)+20;
      const f2f= Math.floor(rnd()*500)+50;
      const ot = Math.floor(rnd()*150)+5;
      const total = dk+em+ph+tx+sm+f2f+ot;
      rows.push({
        state, nation, group, week_start: week,
        total_contacts: total,
        unique_contacts: Math.floor(total*0.62),
        contact_door_knock: dk, contact_email: em, contact_phone: ph,
        contact_text: tx, contact_snail_mail: sm, contact_face_to_face: f2f,
        contact_other: ot,
        total_events: Math.floor(rnd()*60)+10,
        contacted_1_time: Math.floor(total*0.55),
        contacted_2_times: Math.floor(total*0.25),
        contacted_3_times: Math.floor(total*0.13),
        contacted_4plus_times: Math.floor(total*0.07),
      });
    });
  });
  return rows;
})();

function filterRows({states, nations, groups, start, end}) {
  return ALL_ROWS.filter(r =>
    (!states  || !states.length  || states.includes(r.state)) &&
    (!nations || !nations.length || nations.includes(r.nation)) &&
    (!groups  || !groups.length  || groups.includes(r.group)) &&
    (!start || r.week_start >= start) &&
    (!end   || r.week_start <= end)
  );
}

const fmt = (n) => n == null ? "—" : n.toLocaleString();

Object.assign(window, {
  STATES, NATIONS, GROUPS, CONTACT_TYPES, CONTACT_FREQUENCY, IL_CAT_COLORS,
  WEEKS, ALL_ROWS, filterRows, fmt,
});
