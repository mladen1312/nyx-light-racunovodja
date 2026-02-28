import { useState, useEffect, useRef, useCallback } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell } from "recharts";

// ═══════════════════════════════════════════
// NYX LIGHT — RAČUNOVOĐA  |  SOTA WEB UI
// ═══════════════════════════════════════════

// Design: Refined Professional — warm neutrals + teal accents
// Inspired by Notion + Linear + Bloomberg Terminal clarity

const THEME = {
  bg: "#FAFAF8",
  sidebar: "#1A1D23",
  sidebarHover: "#2A2D35",
  sidebarActive: "#35383F",
  card: "#FFFFFF",
  border: "#E8E6E1",
  text: "#1A1D23",
  textSecondary: "#6B7280",
  textMuted: "#9CA3AF",
  accent: "#0D9488",
  accentLight: "#CCFBF1",
  accentDark: "#065F46",
  success: "#059669",
  warning: "#D97706",
  danger: "#DC2626",
  info: "#2563EB",
  purple: "#7C3AED",
};

// ═══ ICONS (inline SVG) ═══
const Icons = {
  dashboard: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>
    </svg>
  ),
  chat: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  ),
  inbox: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>
    </svg>
  ),
  book: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
    </svg>
  ),
  users: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  ),
  chart: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
  ),
  scale: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 3L8 3"/><path d="M12 3v18"/><path d="M19 8l-3-5"/><path d="M5 8l3-5"/><circle cx="19" cy="11" r="3"/><circle cx="5" cy="11" r="3"/>
    </svg>
  ),
  settings: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06"/>
    </svg>
  ),
  send: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  x: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  edit: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  search: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
  ),
  bell: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
  spark: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  ),
  file: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
    </svg>
  ),
  clock: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
};

// ═══ MOCK DATA ═══
const mockDashboard = {
  todayProcessed: 47,
  pendingApproval: 12,
  anomalies: 3,
  aiConfidence: 92.4,
  weeklyTrend: [
    { d: "Pon", processed: 38, approved: 35 },
    { d: "Uto", processed: 45, approved: 42 },
    { d: "Sri", processed: 52, approved: 48 },
    { d: "Čet", processed: 41, approved: 39 },
    { d: "Pet", processed: 47, approved: 43 },
  ],
  byType: [
    { name: "Ulazni računi", value: 34, color: THEME.accent },
    { name: "Bankovni izvodi", value: 28, color: THEME.info },
    { name: "Blagajna", value: 18, color: THEME.purple },
    { name: "Putni nalozi", value: 12, color: THEME.warning },
    { name: "Ostalo", value: 8, color: THEME.textMuted },
  ],
  recentInvoices: [
    { id: "URA-2026-1247", supplier: "Konzum d.d.", amount: 1234.56, vat: 25, confidence: 97, status: "pending", date: "28.02.2026." },
    { id: "URA-2026-1246", supplier: "HEP Opskrba", amount: 892.30, vat: 25, confidence: 94, status: "pending", date: "28.02.2026." },
    { id: "URA-2026-1245", supplier: "A1 Hrvatska", amount: 456.78, vat: 25, confidence: 88, status: "approved", date: "27.02.2026." },
    { id: "URA-2026-1244", supplier: "Tisak d.d.", amount: 234.10, vat: 13, confidence: 91, status: "approved", date: "27.02.2026." },
    { id: "URA-2026-1243", supplier: "Hotel Esplanade", amount: 1890.00, vat: 25, confidence: 72, status: "flagged", date: "27.02.2026." },
  ],
  deadlines: [
    { title: "PDV obrazac (PPO-PDV)", date: "20.03.2026.", days: 20, urgent: false },
    { title: "JOPPD za veljaču", date: "15.03.2026.", days: 15, urgent: false },
    { title: "GFI godišnji izvještaj", date: "30.04.2026.", days: 61, urgent: false },
    { title: "Porez na dobit (PD)", date: "30.04.2026.", days: 61, urgent: false },
  ],
};

const mockEntries = [
  { id: 1, docId: "URA-2026-1247", supplier: "Konzum d.d.", debit: "4000 — Troš. materijala", credit: "2200 — Dobavljači", amount: 1234.56, vatRate: 25, vatAmount: 246.91, confidence: 97, status: "pending", date: "28.02." },
  { id: 2, docId: "URA-2026-1246", supplier: "HEP Opskrba", debit: "4010 — Troš. energije", credit: "2200 — Dobavljači", amount: 892.30, vatRate: 25, vatAmount: 178.46, confidence: 94, status: "pending", date: "28.02." },
  { id: 3, docId: "URA-2026-1245", supplier: "A1 Hrvatska", debit: "4030 — Troš. telekomunikacija", credit: "2200 — Dobavljači", amount: 456.78, vatRate: 25, vatAmount: 91.36, confidence: 88, status: "pending", date: "27.02." },
  { id: 4, docId: "URA-2026-1244", supplier: "Tisak d.d.", debit: "4090 — Uredski materijal", credit: "2200 — Dobavljači", amount: 234.10, vatRate: 13, vatAmount: 26.98, confidence: 91, status: "pending", date: "27.02." },
  { id: 5, docId: "URA-2026-1243", supplier: "Hotel Esplanade", debit: "4400 — Troš. reprezentacije", credit: "2200 — Dobavljači", amount: 1890.00, vatRate: 25, vatAmount: 378.00, confidence: 72, status: "flagged", date: "27.02." },
];

const mockClients = [
  { id: 1, name: "ACME d.o.o.", oib: "12345678901", entries: 234, lastActive: "28.02.2026.", status: "active" },
  { id: 2, name: "Plavi ured j.d.o.o.", oib: "98765432109", entries: 156, lastActive: "27.02.2026.", status: "active" },
  { id: 3, name: "Petar Petrović, obrt", oib: "55566677788", entries: 89, lastActive: "26.02.2026.", status: "active" },
  { id: 4, name: "Zelena energija d.d.", oib: "11122233344", entries: 312, lastActive: "28.02.2026.", status: "active" },
];

const chatHistory = [
  { role: "user", text: "Na koji konto ide račun za popravak služ. automobila za klijenta ACME d.o.o.?" },
  { role: "ai", text: "Za ACME d.o.o. popravak služ. automobila knjiži se na:\n\n**Duguje:** 4600 — Troškovi prijevoza (održ. vozila)\n**Potražuje:** 2200 — Dobavljači\n\nPDV 25% se pretporezom priznaje u cijelosti jer je vozilo 100% u poslovne svrhe (L2 pravilo #47 za ACME).\n\n📖 Temelj: ZPDV čl. 58. st. 4. (NN 73/13, 99/13, 148/13)", citations: ["ZPDV čl. 58. st. 4. (NN 73/13)"] },
];

// ═══ UTILITY COMPONENTS ═══

const Badge = ({ children, variant = "default", size = "sm" }) => {
  const styles = {
    default: { bg: "#F3F4F6", color: THEME.textSecondary },
    success: { bg: "#D1FAE5", color: "#065F46" },
    warning: { bg: "#FEF3C7", color: "#92400E" },
    danger: { bg: "#FEE2E2", color: "#991B1B" },
    info: { bg: "#DBEAFE", color: "#1E40AF" },
    accent: { bg: THEME.accentLight, color: THEME.accentDark },
  };
  const s = styles[variant] || styles.default;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: size === "sm" ? "2px 8px" : "4px 12px",
      borderRadius: 9999, fontSize: size === "sm" ? 11 : 12, fontWeight: 600,
      backgroundColor: s.bg, color: s.color, letterSpacing: "0.02em",
    }}>{children}</span>
  );
};

const ConfidencePill = ({ value }) => {
  const v = value >= 90 ? "success" : value >= 80 ? "info" : value >= 70 ? "warning" : "danger";
  return <Badge variant={v} size="sm">{value}%</Badge>;
};

const StatusBadge = ({ status }) => {
  const map = {
    pending: { label: "Čeka", variant: "warning" },
    approved: { label: "Odobreno", variant: "success" },
    flagged: { label: "Upozorenje", variant: "danger" },
    rejected: { label: "Odbijeno", variant: "danger" },
  };
  const m = map[status] || { label: status, variant: "default" };
  return <Badge variant={m.variant}>{m.label}</Badge>;
};

const KPICard = ({ label, value, sub, icon, color = THEME.accent }) => (
  <div style={{
    background: THEME.card, borderRadius: 12, padding: "20px 24px",
    border: `1px solid ${THEME.border}`, flex: 1, minWidth: 200,
    transition: "box-shadow 0.2s", cursor: "default",
  }}
  onMouseEnter={e => e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.06)"}
  onMouseLeave={e => e.currentTarget.style.boxShadow = "none"}
  >
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div>
        <div style={{ fontSize: 13, color: THEME.textSecondary, fontWeight: 500, marginBottom: 6 }}>{label}</div>
        <div style={{ fontSize: 32, fontWeight: 700, color: THEME.text, letterSpacing: "-0.02em", lineHeight: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: 12, color: THEME.textMuted, marginTop: 6 }}>{sub}</div>}
      </div>
      <div style={{ width: 40, height: 40, borderRadius: 10, background: `${color}12`, display: "flex", alignItems: "center", justifyContent: "center", color }}>
        {icon}
      </div>
    </div>
  </div>
);

// ═══ SIDEBAR ═══
const Sidebar = ({ active, onNavigate, user }) => {
  const items = [
    { id: "dashboard", icon: Icons.dashboard, label: "Dashboard" },
    { id: "chat", icon: Icons.chat, label: "AI Chat" },
    { id: "inbox", icon: Icons.inbox, label: "Inbox", badge: 12 },
    { id: "entries", icon: Icons.book, label: "Knjiženja", badge: 5 },
    { id: "clients", icon: Icons.users, label: "Klijenti" },
    { id: "reports", icon: Icons.chart, label: "Izvještaji" },
    { id: "laws", icon: Icons.scale, label: "Zakoni" },
    { id: "settings", icon: Icons.settings, label: "Postavke" },
  ];

  return (
    <div style={{
      width: 240, background: THEME.sidebar, display: "flex", flexDirection: "column",
      height: "100vh", position: "fixed", left: 0, top: 0, zIndex: 100,
      fontFamily: "'DM Sans', sans-serif",
    }}>
      {/* Logo */}
      <div style={{ padding: "24px 20px 20px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: `linear-gradient(135deg, ${THEME.accent}, #06B6D4)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, fontWeight: 800, color: "#fff",
          }}>N</div>
          <div>
            <div style={{ color: "#fff", fontSize: 15, fontWeight: 700, letterSpacing: "-0.01em" }}>Nyx Light</div>
            <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 11, fontWeight: 500 }}>Računovođa</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: "12px 10px", overflowY: "auto" }}>
        {items.map(item => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            style={{
              width: "100%", display: "flex", alignItems: "center", gap: 12,
              padding: "10px 12px", borderRadius: 8, border: "none", cursor: "pointer",
              background: active === item.id ? THEME.sidebarActive : "transparent",
              color: active === item.id ? "#fff" : "rgba(255,255,255,0.55)",
              fontSize: 14, fontWeight: active === item.id ? 600 : 400,
              transition: "all 0.15s", marginBottom: 2, textAlign: "left",
              fontFamily: "inherit",
            }}
            onMouseEnter={e => {
              if (active !== item.id) {
                e.currentTarget.style.background = THEME.sidebarHover;
                e.currentTarget.style.color = "rgba(255,255,255,0.85)";
              }
            }}
            onMouseLeave={e => {
              if (active !== item.id) {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "rgba(255,255,255,0.55)";
              }
            }}
          >
            {item.icon}
            <span style={{ flex: 1 }}>{item.label}</span>
            {item.badge && (
              <span style={{
                minWidth: 20, height: 20, borderRadius: 10, background: THEME.accent,
                color: "#fff", fontSize: 11, fontWeight: 700, display: "flex",
                alignItems: "center", justifyContent: "center", padding: "0 6px",
              }}>{item.badge}</span>
            )}
          </button>
        ))}
      </nav>

      {/* User */}
      <div style={{
        padding: "16px 16px", borderTop: "1px solid rgba(255,255,255,0.08)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8, background: "linear-gradient(135deg, #6366F1, #8B5CF6)",
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "#fff", fontSize: 13, fontWeight: 700,
        }}>{user?.initials || "VB"}</div>
        <div style={{ flex: 1 }}>
          <div style={{ color: "#fff", fontSize: 13, fontWeight: 500 }}>{user?.name || "Vladimir Budija"}</div>
          <div style={{ color: "rgba(255,255,255,0.35)", fontSize: 11 }}>Admin</div>
        </div>
        <div style={{ width: 8, height: 8, borderRadius: 4, background: THEME.success }} />
      </div>
    </div>
  );
};

// ═══ HEADER ═══
const Header = ({ title, subtitle }) => (
  <div style={{
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "20px 0", marginBottom: 4,
  }}>
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, color: THEME.text, margin: 0, letterSpacing: "-0.02em" }}>{title}</h1>
      {subtitle && <p style={{ fontSize: 14, color: THEME.textSecondary, margin: "4px 0 0" }}>{subtitle}</p>}
    </div>
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      {/* Search */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 14px",
        background: THEME.card, border: `1px solid ${THEME.border}`, borderRadius: 8,
        color: THEME.textMuted, fontSize: 13, minWidth: 200, cursor: "text",
      }}>
        {Icons.search}
        <span>Pretraži...</span>
        <span style={{
          marginLeft: "auto", fontSize: 11, padding: "2px 6px", borderRadius: 4,
          background: "#F3F4F6", color: THEME.textMuted, fontWeight: 500,
        }}>⌘K</span>
      </div>
      {/* Notifications */}
      <button style={{
        width: 38, height: 38, borderRadius: 8, border: `1px solid ${THEME.border}`,
        background: THEME.card, display: "flex", alignItems: "center", justifyContent: "center",
        cursor: "pointer", color: THEME.textSecondary, position: "relative",
      }}>
        {Icons.bell}
        <span style={{
          position: "absolute", top: 6, right: 6, width: 8, height: 8,
          borderRadius: 4, background: THEME.danger, border: "2px solid #fff",
        }} />
      </button>
    </div>
  </div>
);

// ═══ DASHBOARD PAGE ═══
const DashboardPage = () => {
  const d = mockDashboard;
  return (
    <div>
      <Header title="Dashboard" subtitle="Pregled dnevnih aktivnosti i statusa obrade" />

      {/* KPI Cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <KPICard label="Danas obrađeno" value={d.todayProcessed} sub="+12% od jučer" icon={Icons.file} color={THEME.accent} />
        <KPICard label="Čeka odobrenje" value={d.pendingApproval} sub="5 hitnih" icon={Icons.clock} color={THEME.warning} />
        <KPICard label="Anomalije" value={d.anomalies} sub="1 nova od jutros" icon={Icons.bell} color={THEME.danger} />
        <KPICard label="AI pouzdanost" value={`${d.aiConfidence}%`} sub="Prosjek ovaj tjedan" icon={Icons.spark} color={THEME.info} />
      </div>

      {/* Charts Row */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 24 }}>
        {/* Weekly Trend */}
        <div style={{ background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`, padding: 24 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: THEME.text, marginBottom: 20 }}>Tjedni pregled obrade</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={d.weeklyTrend} barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
              <XAxis dataKey="d" tick={{ fontSize: 12, fill: THEME.textMuted }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: THEME.textMuted }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8, border: `1px solid ${THEME.border}`, fontSize: 13 }} />
              <Bar dataKey="processed" name="Obrađeno" fill={THEME.accent} radius={[4,4,0,0]} />
              <Bar dataKey="approved" name="Odobreno" fill="#6EE7B7" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* By Type */}
        <div style={{ background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`, padding: 24 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: THEME.text, marginBottom: 12 }}>Po vrsti dokumenta</div>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={d.byType} cx="50%" cy="50%" innerRadius={45} outerRadius={70} paddingAngle={3} dataKey="value">
                {d.byType.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
              <Tooltip contentStyle={{ borderRadius: 8, border: `1px solid ${THEME.border}`, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            {d.byType.map((t, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: THEME.textSecondary }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: t.color, display: "inline-block" }} />
                {t.name}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tables Row */}
      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: 16 }}>
        {/* Recent Invoices */}
        <div style={{ background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`, padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: THEME.text }}>Zadnji računi</span>
            <button style={{
              padding: "5px 12px", borderRadius: 6, border: `1px solid ${THEME.border}`,
              background: "transparent", fontSize: 12, color: THEME.textSecondary,
              cursor: "pointer", fontWeight: 500,
            }}>Vidi sve →</button>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${THEME.border}` }}>
                {["Br. dokumenta", "Dobavljač", "Iznos (EUR)", "AI", "Status"].map(h => (
                  <th key={h} style={{ padding: "8px 10px", textAlign: "left", fontWeight: 600, color: THEME.textSecondary, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.recentInvoices.map(inv => (
                <tr key={inv.id} style={{ borderBottom: `1px solid ${THEME.border}`, cursor: "pointer" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#FAFAF8"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  <td style={{ padding: "10px", fontWeight: 500, color: THEME.accent }}>{inv.id}</td>
                  <td style={{ padding: "10px", color: THEME.text }}>{inv.supplier}</td>
                  <td style={{ padding: "10px", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{inv.amount.toLocaleString("hr-HR", { minimumFractionDigits: 2 })}</td>
                  <td style={{ padding: "10px" }}><ConfidencePill value={inv.confidence} /></td>
                  <td style={{ padding: "10px" }}><StatusBadge status={inv.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Deadlines */}
        <div style={{ background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`, padding: 24 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: THEME.text, marginBottom: 16 }}>Nadolazeći rokovi</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {d.deadlines.map((dl, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
                borderRadius: 8, background: "#FAFAF8", border: `1px solid ${THEME.border}`,
              }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 8, display: "flex", alignItems: "center",
                  justifyContent: "center", fontWeight: 700, fontSize: 14,
                  background: dl.days <= 10 ? "#FEE2E2" : dl.days <= 30 ? "#FEF3C7" : "#D1FAE5",
                  color: dl.days <= 10 ? THEME.danger : dl.days <= 30 ? "#92400E" : THEME.success,
                }}>{dl.days}d</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: THEME.text }}>{dl.title}</div>
                  <div style={{ fontSize: 12, color: THEME.textMuted }}>{dl.date}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ═══ AI CHAT PAGE ═══
const ChatPage = () => {
  const [messages, setMessages] = useState(chatHistory);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleSend = useCallback(() => {
    if (!input.trim()) return;
    const userMsg = { role: "user", text: input };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // Simulate AI response
    setTimeout(() => {
      const aiMsg = {
        role: "ai",
        text: "Analiziram vaš upit...\n\nNa temelju L2 semantičke memorije i važećih propisa, evo odgovora:\n\nPrema **ZPDV čl. 40. st. 1.** oslobođeni su PDV-a financijske usluge uključujući odobravanje i upravljanje kreditima.\n\nMeđutim, naknade za obradu kredita se **oporezuju** po stopi od 25% (ZPDV čl. 40. st. 2.).\n\n📖 Izvor: ZPDV (NN 73/13, 99/13, 148/13, 143/14) — čl. 40.",
        citations: ["ZPDV čl. 40. (NN 73/13)"],
      };
      setMessages(prev => [...prev, aiMsg]);
      setLoading(false);
    }, 2000);
  }, [input]);

  const quickActions = [
    "Na koji konto ide uredski materijal?",
    "Koliko iznosi km-naknada u 2026?",
    "Je li PDV priznat za reprezentaciju?",
    "Limit gotovine za blagajnu?",
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 40px)" }}>
      <Header title="AI Chat" subtitle="Postavite pitanje o kontiranju, PDV-u ili zakonima" />

      {/* Chat Area */}
      <div style={{
        flex: 1, overflowY: "auto", padding: "0 0 16px",
        display: "flex", flexDirection: "column", gap: 16,
      }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            display: "flex", gap: 12, maxWidth: msg.role === "user" ? "70%" : "85%",
            alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
            flexDirection: msg.role === "user" ? "row-reverse" : "row",
          }}>
            {msg.role === "ai" && (
              <div style={{
                width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                background: `linear-gradient(135deg, ${THEME.accent}, #06B6D4)`,
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#fff", fontSize: 14, fontWeight: 800,
              }}>N</div>
            )}
            <div style={{
              padding: "12px 16px", borderRadius: 12, fontSize: 14, lineHeight: 1.65,
              background: msg.role === "user" ? THEME.accent : THEME.card,
              color: msg.role === "user" ? "#fff" : THEME.text,
              border: msg.role === "ai" ? `1px solid ${THEME.border}` : "none",
              whiteSpace: "pre-wrap",
            }}>
              {msg.text}
              {msg.citations && (
                <div style={{
                  marginTop: 10, paddingTop: 10, borderTop: `1px solid ${msg.role === "user" ? "rgba(255,255,255,0.2)" : THEME.border}`,
                  fontSize: 12, color: msg.role === "user" ? "rgba(255,255,255,0.7)" : THEME.textMuted,
                  display: "flex", alignItems: "center", gap: 4,
                }}>
                  {Icons.file} {msg.citations.join(", ")}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: "flex", gap: 12, alignSelf: "flex-start" }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8, flexShrink: 0,
              background: `linear-gradient(135deg, ${THEME.accent}, #06B6D4)`,
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontSize: 14, fontWeight: 800,
            }}>N</div>
            <div style={{
              padding: "14px 20px", borderRadius: 12, background: THEME.card,
              border: `1px solid ${THEME.border}`, display: "flex", gap: 6,
            }}>
              {[0, 1, 2].map(j => (
                <div key={j} style={{
                  width: 8, height: 8, borderRadius: 4, background: THEME.textMuted,
                  animation: `pulse 1.2s infinite ${j * 0.2}s`,
                  opacity: 0.4,
                }} />
              ))}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Quick Actions */}
      {messages.length <= 2 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
          {quickActions.map((q, i) => (
            <button key={i} onClick={() => setInput(q)} style={{
              padding: "7px 14px", borderRadius: 20, border: `1px solid ${THEME.border}`,
              background: THEME.card, fontSize: 12, color: THEME.textSecondary,
              cursor: "pointer", fontFamily: "inherit", transition: "all 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = THEME.accent; e.currentTarget.style.color = THEME.accent; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = THEME.border; e.currentTarget.style.color = THEME.textSecondary; }}
            >{q}</button>
          ))}
        </div>
      )}

      {/* Input */}
      <div style={{
        display: "flex", gap: 10, alignItems: "flex-end",
        padding: "12px 16px", background: THEME.card, borderRadius: 12,
        border: `1px solid ${THEME.border}`, marginBottom: 8,
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder="Postavite pitanje o kontiranju, PDV-u, zakonima..."
          rows={1}
          style={{
            flex: 1, border: "none", outline: "none", resize: "none",
            fontSize: 14, fontFamily: "inherit", background: "transparent",
            color: THEME.text, lineHeight: 1.5,
          }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          style={{
            width: 38, height: 38, borderRadius: 8, border: "none",
            background: input.trim() ? THEME.accent : "#E5E7EB",
            color: "#fff", cursor: input.trim() ? "pointer" : "default",
            display: "flex", alignItems: "center", justifyContent: "center",
            transition: "background 0.15s", flexShrink: 0,
          }}
        >{Icons.send}</button>
      </div>
    </div>
  );
};

// ═══ ENTRIES PAGE (Knjiženja) ═══
const EntriesPage = () => {
  const [entries, setEntries] = useState(mockEntries);

  const approve = (id) => setEntries(prev => prev.map(e => e.id === id ? { ...e, status: "approved" } : e));
  const reject = (id) => setEntries(prev => prev.map(e => e.id === id ? { ...e, status: "rejected" } : e));

  return (
    <div>
      <Header title="Knjiženja" subtitle={`${entries.filter(e => e.status === "pending").length} knjiženja čeka odobrenje`} />

      <div style={{ background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#FAFAF8", borderBottom: `2px solid ${THEME.border}` }}>
              {["Dokument", "Dobavljač", "Duguje", "Potražuje", "Iznos", "PDV", "AI", "Status", "Akcije"].map(h => (
                <th key={h} style={{
                  padding: "12px 14px", textAlign: "left", fontWeight: 600,
                  color: THEME.textSecondary, fontSize: 11, textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map(e => (
              <tr key={e.id} style={{
                borderBottom: `1px solid ${THEME.border}`,
                background: e.status === "flagged" ? "#FFF7ED" : "transparent",
              }}>
                <td style={{ padding: "12px 14px" }}>
                  <div style={{ fontWeight: 600, color: THEME.accent }}>{e.docId}</div>
                  <div style={{ fontSize: 11, color: THEME.textMuted }}>{e.date}</div>
                </td>
                <td style={{ padding: "12px 14px", fontWeight: 500 }}>{e.supplier}</td>
                <td style={{ padding: "12px 14px", fontSize: 12 }}>
                  <code style={{ background: "#F3F4F6", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>{e.debit}</code>
                </td>
                <td style={{ padding: "12px 14px", fontSize: 12 }}>
                  <code style={{ background: "#F3F4F6", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>{e.credit}</code>
                </td>
                <td style={{ padding: "12px 14px", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                  {e.amount.toLocaleString("hr-HR", { minimumFractionDigits: 2 })}
                </td>
                <td style={{ padding: "12px 14px", fontSize: 12, color: THEME.textSecondary }}>
                  {e.vatRate}% ({e.vatAmount.toLocaleString("hr-HR", { minimumFractionDigits: 2 })})
                </td>
                <td style={{ padding: "12px 14px" }}><ConfidencePill value={e.confidence} /></td>
                <td style={{ padding: "12px 14px" }}><StatusBadge status={e.status} /></td>
                <td style={{ padding: "12px 14px" }}>
                  {e.status === "pending" || e.status === "flagged" ? (
                    <div style={{ display: "flex", gap: 6 }}>
                      <button onClick={() => approve(e.id)} title="Odobri" style={{
                        width: 30, height: 30, borderRadius: 6, border: `1px solid ${THEME.border}`,
                        background: "#D1FAE5", color: THEME.success, cursor: "pointer",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>{Icons.check}</button>
                      <button title="Ispravi" style={{
                        width: 30, height: 30, borderRadius: 6, border: `1px solid ${THEME.border}`,
                        background: "#DBEAFE", color: THEME.info, cursor: "pointer",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>{Icons.edit}</button>
                      <button onClick={() => reject(e.id)} title="Odbij" style={{
                        width: 30, height: 30, borderRadius: 6, border: `1px solid ${THEME.border}`,
                        background: "#FEE2E2", color: THEME.danger, cursor: "pointer",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>{Icons.x}</button>
                    </div>
                  ) : (
                    <span style={{ fontSize: 12, color: THEME.textMuted }}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ═══ LAWS PAGE (RAG) ═══
const LawsPage = () => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);

  const doSearch = () => {
    if (!query.trim()) return;
    setSearching(true);
    setTimeout(() => {
      setResults([
        {
          law: "ZPDV", article: "čl. 40. st. 1.", title: "Oslobođenja za financijske usluge",
          text: "Od plaćanja PDV-a oslobođene su financijske transakcije uključujući odobravanje i upravljanje kreditima te upravljanje kreditnim garancijama.",
          validFrom: "01.01.2017.", validTo: "", nn: "NN 73/13, 115/16", current: true,
        },
        {
          law: "ZPDV", article: "čl. 58. st. 4.", title: "Pretporez za osobna vozila",
          text: "Porezni obveznik može odbiti 50% pretporeza za nabavu i održavanje osobnih automobila, osim ako se koriste isključivo za obavljanje djelatnosti.",
          validFrom: "01.01.2018.", validTo: "", nn: "NN 106/18", current: true,
        },
        {
          law: "ZPD", article: "čl. 7. st. 1.", title: "Porezna osnovica",
          text: "Osnovica poreza na dobit je dobit koja se utvrđuje prema računovodstvenim propisima kao razlika prihoda i rashoda prije obračuna poreza na dobit.",
          validFrom: "01.01.2024.", validTo: "", nn: "NN 177/04, 65/24", current: true,
        },
      ]);
      setSearching(false);
    }, 1200);
  };

  return (
    <div>
      <Header title="Zakoni i propisi" subtitle="Time-Aware RAG pretraga — rezultati prema datumu poslovnog događaja" />

      {/* Search */}
      <div style={{
        display: "flex", gap: 10, marginBottom: 24, background: THEME.card,
        padding: 16, borderRadius: 12, border: `1px solid ${THEME.border}`,
      }}>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 10, padding: "0 12px", background: "#FAFAF8", borderRadius: 8, border: `1px solid ${THEME.border}` }}>
          {Icons.search}
          <input
            value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && doSearch()}
            placeholder="Npr: PDV na financijske usluge, km-naknada 2025, reprezentacija..."
            style={{ flex: 1, border: "none", outline: "none", background: "transparent", fontSize: 14, fontFamily: "inherit", padding: "12px 0", color: THEME.text }}
          />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", background: "#FAFAF8", borderRadius: 8, border: `1px solid ${THEME.border}` }}>
          {Icons.clock}
          <input type="date" defaultValue="2026-02-28" style={{ border: "none", outline: "none", background: "transparent", fontSize: 13, fontFamily: "inherit", color: THEME.text }} />
        </div>
        <button onClick={doSearch} style={{
          padding: "0 24px", borderRadius: 8, border: "none",
          background: THEME.accent, color: "#fff", fontSize: 14,
          fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
        }}>Pretraži</button>
      </div>

      {/* Results */}
      {searching && (
        <div style={{ textAlign: "center", padding: 40, color: THEME.textMuted }}>
          <div style={{ fontSize: 14 }}>Pretražujem zakonsku bazu...</div>
        </div>
      )}
      {results && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: 13, color: THEME.textSecondary, marginBottom: 4 }}>
            {results.length} rezultata za „{query}"
          </div>
          {results.map((r, i) => (
            <div key={i} style={{
              background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`,
              padding: 20, transition: "box-shadow 0.2s",
            }}
            onMouseEnter={e => e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.05)"}
            onMouseLeave={e => e.currentTarget.style.boxShadow = "none"}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <Badge variant="accent" size="md">{r.law}</Badge>
                    <span style={{ fontWeight: 700, fontSize: 15, color: THEME.text }}>{r.article}</span>
                    {r.current && <Badge variant="success" size="sm">Važeći</Badge>}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: THEME.textSecondary }}>{r.title}</div>
                </div>
                <div style={{ fontSize: 11, color: THEME.textMuted, textAlign: "right" }}>
                  <div>{r.nn}</div>
                  <div>Od: {r.validFrom}</div>
                </div>
              </div>
              <div style={{
                fontSize: 14, lineHeight: 1.7, color: THEME.text, padding: "12px 16px",
                background: "#FAFAF8", borderRadius: 8, borderLeft: `3px solid ${THEME.accent}`,
              }}>{r.text}</div>
            </div>
          ))}
        </div>
      )}

      {!results && !searching && (
        <div style={{
          textAlign: "center", padding: "60px 20px", color: THEME.textMuted,
        }}>
          <div style={{ fontSize: 40, marginBottom: 16, opacity: 0.3 }}>{Icons.scale}</div>
          <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>Pretražite zakonsku bazu</div>
          <div style={{ fontSize: 13, maxWidth: 400, margin: "0 auto" }}>
            ZPDV, ZPD, ZDOH, ZOR, Zakon o fiskalizaciji, Pravilnici — s vremenskim kontekstom
          </div>
        </div>
      )}
    </div>
  );
};

// ═══ CLIENTS PAGE ═══
const ClientsPage = () => (
  <div>
    <Header title="Klijenti" subtitle={`${mockClients.length} aktivnih klijenata`} />
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
      {mockClients.map(c => (
        <div key={c.id} style={{
          background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`,
          padding: 20, cursor: "pointer", transition: "all 0.2s",
        }}
        onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.06)"; e.currentTarget.style.borderColor = THEME.accent; }}
        onMouseLeave={e => { e.currentTarget.style.boxShadow = "none"; e.currentTarget.style.borderColor = THEME.border; }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div style={{
              width: 42, height: 42, borderRadius: 10,
              background: `linear-gradient(135deg, ${["#6366F1","#EC4899","#F59E0B","#10B981"][c.id % 4]}, ${["#8B5CF6","#F472B6","#FBBF24","#34D399"][c.id % 4]})`,
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontSize: 16, fontWeight: 700,
            }}>{c.name[0]}</div>
            <Badge variant="success">Aktivan</Badge>
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: THEME.text, marginBottom: 4 }}>{c.name}</div>
          <div style={{ fontSize: 12, color: THEME.textMuted, fontVariantNumeric: "tabular-nums", marginBottom: 12 }}>OIB: {c.oib}</div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: THEME.textSecondary }}>
            <span>{c.entries} knjiženja</span>
            <span>Zadnje: {c.lastActive}</span>
          </div>
        </div>
      ))}
    </div>
  </div>
);

// ═══ REPORTS PAGE ═══
const ReportsPage = () => {
  const reports = [
    { name: "GFI — Godišnji financijski izvještaj", format: "XML", target: "FINA", status: "ready", icon: "📊" },
    { name: "PPO-PDV — Prijava PDV-a", format: "XML", target: "Porezna uprava", status: "draft", icon: "🧾" },
    { name: "JOPPD — Obračun plaća", format: "XML", target: "Porezna uprava", status: "ready", icon: "💰" },
    { name: "PD — Porez na dobit", format: "PDF", target: "Porezna uprava", status: "draft", icon: "📋" },
    { name: "Bilanca", format: "XLSX", target: "Interno", status: "ready", icon: "📈" },
    { name: "RDG — Račun dobiti i gubitka", format: "XLSX", target: "Interno", status: "ready", icon: "📉" },
  ];

  return (
    <div>
      <Header title="Izvještaji" subtitle="Generiranje financijskih izvještaja i poreznih obrazaca" />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {reports.map((r, i) => (
          <div key={i} style={{
            background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`,
            padding: 20, display: "flex", gap: 16, alignItems: "flex-start",
            cursor: "pointer", transition: "box-shadow 0.2s",
          }}
          onMouseEnter={e => e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.06)"}
          onMouseLeave={e => e.currentTarget.style.boxShadow = "none"}
          >
            <div style={{ fontSize: 28 }}>{r.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: THEME.text, marginBottom: 4 }}>{r.name}</div>
              <div style={{ fontSize: 12, color: THEME.textSecondary, marginBottom: 10 }}>{r.target} • {r.format}</div>
              <div style={{ display: "flex", gap: 8 }}>
                <StatusBadge status={r.status === "ready" ? "approved" : "pending"} />
                <button style={{
                  padding: "4px 12px", borderRadius: 6, border: `1px solid ${THEME.border}`,
                  background: "transparent", fontSize: 12, color: THEME.accent,
                  cursor: "pointer", fontWeight: 500, fontFamily: "inherit",
                }}>Generiraj</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ═══ INBOX PAGE ═══
const InboxPage = () => {
  const tiers = [
    { tier: "Tier 1", label: "Peppol XML", count: 8, confidence: "~100%", color: THEME.success },
    { tier: "Tier 2", label: "Poznati PDF", count: 15, confidence: "~95%", color: THEME.info },
    { tier: "Tier 3", label: "Nepoznati PDF", count: 6, confidence: "~85%", color: THEME.warning },
    { tier: "Tier 4", label: "Skenovi/Slike", count: 3, confidence: "~75%", color: THEME.danger },
  ];

  return (
    <div>
      <Header title="Inbox" subtitle="Primljeni računi — automatska klasifikacija i ekstrakcija" />
      {/* Tier summary */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
        {tiers.map(t => (
          <div key={t.tier} style={{
            flex: 1, background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`,
            padding: 16, borderLeft: `4px solid ${t.color}`,
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: THEME.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t.tier}</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: THEME.text, marginTop: 4 }}>{t.label}</div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 8 }}>
              <span style={{ fontSize: 24, fontWeight: 700, color: THEME.text }}>{t.count}</span>
              <Badge variant={t.color === THEME.success ? "success" : t.color === THEME.info ? "info" : t.color === THEME.warning ? "warning" : "danger"}>
                {t.confidence}
              </Badge>
            </div>
          </div>
        ))}
      </div>
      {/* Invoice table */}
      <div style={{ background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#FAFAF8", borderBottom: `2px solid ${THEME.border}` }}>
              {["Izvor", "Dokument", "Dobavljač", "Iznos", "PDV", "AI", "Datum", "Status"].map(h => (
                <th key={h} style={{ padding: "12px 14px", textAlign: "left", fontWeight: 600, color: THEME.textSecondary, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {mockDashboard.recentInvoices.map((inv, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${THEME.border}`, cursor: "pointer" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#FAFAF8"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <td style={{ padding: "10px 14px" }}><Badge variant={i < 2 ? "success" : i < 4 ? "info" : "warning"}>{i < 2 ? "Peppol" : i < 4 ? "PDF" : "Sken"}</Badge></td>
                <td style={{ padding: "10px 14px", fontWeight: 600, color: THEME.accent }}>{inv.id}</td>
                <td style={{ padding: "10px 14px" }}>{inv.supplier}</td>
                <td style={{ padding: "10px 14px", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{inv.amount.toLocaleString("hr-HR", { minimumFractionDigits: 2 })} EUR</td>
                <td style={{ padding: "10px 14px", color: THEME.textSecondary }}>{inv.vat}%</td>
                <td style={{ padding: "10px 14px" }}><ConfidencePill value={inv.confidence} /></td>
                <td style={{ padding: "10px 14px", color: THEME.textSecondary }}>{inv.date}</td>
                <td style={{ padding: "10px 14px" }}><StatusBadge status={inv.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ═══ SETTINGS PAGE ═══
const SettingsPage = () => (
  <div>
    <Header title="Postavke" subtitle="Konfiguracija sustava i upravljanje korisnicima" />
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      {[
        { title: "Korisnici", desc: "Upravljanje korisničkim računima i ulogama", icon: Icons.users, count: "6 aktivnih" },
        { title: "AI Model", desc: "Qwen3-235B-A22B — status i konfiguracija", icon: Icons.spark, count: "130 GB RAM" },
        { title: "Backup", desc: "Automatski backup baze podataka", icon: Icons.file, count: "Zadnji: danas 03:00" },
        { title: "Mreža", desc: "LAN, Tailscale i firewall postavke", icon: Icons.settings, count: "2 VPN korisnika" },
      ].map((s, i) => (
        <div key={i} style={{
          background: THEME.card, borderRadius: 12, border: `1px solid ${THEME.border}`,
          padding: 20, cursor: "pointer", display: "flex", gap: 16, alignItems: "center",
          transition: "box-shadow 0.2s",
        }}
        onMouseEnter={e => e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.06)"}
        onMouseLeave={e => e.currentTarget.style.boxShadow = "none"}
        >
          <div style={{
            width: 44, height: 44, borderRadius: 10, background: `${THEME.accent}12`,
            display: "flex", alignItems: "center", justifyContent: "center", color: THEME.accent,
          }}>{s.icon}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: THEME.text }}>{s.title}</div>
            <div style={{ fontSize: 12, color: THEME.textSecondary, marginTop: 2 }}>{s.desc}</div>
          </div>
          <div style={{ fontSize: 12, color: THEME.textMuted, fontWeight: 500 }}>{s.count}</div>
        </div>
      ))}
    </div>
  </div>
);

// ═══ MAIN APP ═══
export default function NyxLightApp() {
  const [page, setPage] = useState("dashboard");

  const pages = {
    dashboard: DashboardPage,
    chat: ChatPage,
    inbox: InboxPage,
    entries: EntriesPage,
    clients: ClientsPage,
    reports: ReportsPage,
    laws: LawsPage,
    settings: SettingsPage,
  };

  const PageComponent = pages[page] || DashboardPage;

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: THEME.bg, fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;0,9..40,800;1,9..40,400&display=swap');
        @keyframes pulse { 0%, 100% { opacity: 0.3; transform: scale(1); } 50% { opacity: 1; transform: scale(1.15); } }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
        ::selection { background: ${THEME.accentLight}; color: ${THEME.accentDark}; }
        code { font-family: 'SF Mono', 'Fira Code', monospace; }
      `}</style>

      <Sidebar active={page} onNavigate={setPage} user={{ name: "Vladimir Budija", initials: "VB" }} />

      <main style={{ flex: 1, marginLeft: 240, padding: "16px 32px 32px" }}>
        <PageComponent />
      </main>
    </div>
  );
}
