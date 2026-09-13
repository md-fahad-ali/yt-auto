import { useEffect, useState } from "react";
import "./index.css";

export default function App() {
  const [channels, setChannels] = useState([]);
  const [status, setStatus] = useState({ running: false, log: [], channels: [], current_channel: null, current_video: null });
  const [healthData, setHealthData] = useState(null);
  const [route, setRoute] = useState(window.location.hash || "#/");
  const [activeTab, setActiveTab] = useState("batch");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash || "#/";
      setRoute(h);
      if (h.startsWith("#/ideas")) setActiveTab("ideas");
      else if (h.startsWith("#/upload")) setActiveTab("upload");
      else if (h.startsWith("#/health")) setActiveTab("health");
      else if (h.startsWith("#/profile")) setActiveTab("profile");
      else setActiveTab("batch");
      setMobileMenuOpen(false);
    };
    window.addEventListener("hashchange", onHash);
    onHash();
    fetch("/api/avatars/refresh", { method: "POST" }).catch(() => {});
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const loadData = () => {
    Promise.all([
      fetch("/api/channels").then(r => r.json()).catch(() => []),
      fetch("/api/batch/status").then(r => r.json()).catch(() => ({ running: false, log: [], channels: [] })),
      fetch("/health").then(r => r.json()).catch(() => null),
    ]).then(([ch, st, hl]) => {
      if (Array.isArray(ch)) setChannels(ch);
      if (st) setStatus(st);
      if (hl) setHealthData(hl);
    });
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, []);

  const navigateTab = (tab, hash) => {
    setActiveTab(tab);
    window.location.hash = hash;
    setMobileMenuOpen(false);
  };

  const profileMatch = route.match(/^#\/profile\/(.+)$/);

  return (
    <div className="app-container">
      {/* Permanent Left Avatar Navigation Sidebar */}
      <Sidebar 
        channels={channels} 
        status={status} 
        onRemoved={loadData} 
      />

      {/* Main App Content Area */}
      <div className="app-main">
        {/* Global Top Header Bar */}
        <Header 
          status={status} 
          channels={channels} 
          activeTab={activeTab} 
          onTabSelect={navigateTab}
          menuOpen={mobileMenuOpen}
          setMenuOpen={setMobileMenuOpen}
        />

        {/* View Switcher */}
        <div className="view-content">
          {profileMatch ? (
            <ProfileView 
              key={profileMatch[1]}
              channelId={decodeURIComponent(profileMatch[1])} 
              channels={channels} 
              onBack={() => { window.location.hash = "#/"; }}
              onUpdate={loadData}
            />
          ) : activeTab === "ideas" ? (
            <IdeaStudioView />
          ) : activeTab === "upload" ? (
            <QuickUploadView channels={channels} onUploaded={loadData} />
          ) : activeTab === "health" ? (
            <HealthView health={healthData} channels={channels} />
          ) : (
            <BatchDashboardView 
              channels={channels} 
              status={status} 
              setStatus={setStatus}
              loadData={loadData}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   TOP HEADER COMPONENT
   ========================================================================= */
function Header({ 
  status, 
  channels, 
  activeTab, 
  onTabSelect, 
  menuOpen, 
  setMenuOpen 
}) {
  const readyChannels = channels.filter(c => !!c.folder).length;

  return (
    <header className="app-header">
      <div className="header-left">
        <a href="#/" className="header-brand" onClick={() => onTabSelect("batch", "#/")}>
          <div className="header-brand-icon">⚡</div>
          <div className="header-brand-info">
            <div className="header-brand-title">
              YT AUTO <span className="header-brand-accent">STUDIO</span>
            </div>
            <div className="header-brand-sub">
              Multi-Channel Automation Engine
            </div>
          </div>
        </a>

        {/* Real-time status pill */}
        <div className={`status-pill header-status-pill ${status.running ? "running" : "idle"}`}>
          <span className={`status-dot ${status.running ? "animate-pulse-dot" : ""}`} />
          <span className="status-pill-full">{status.running ? "Batch Running" : "Engine Idle"}</span>
          <span className="status-pill-short">{status.running ? "Running" : "Idle"}</span>
        </div>
      </div>

      {/* Center Navigation Tabs (Desktop View) */}
      <nav className="header-nav header-nav-desktop" aria-label="Main Navigation">
        <button 
          className={`header-nav-btn ${activeTab === "batch" ? "active" : ""}`}
          onClick={() => onTabSelect("batch", "#/")}
          title="Batch Uploader"
        >
          <span className="header-nav-icon">📦</span>
          <span className="header-nav-label">Batch Uploader</span>
        </button>
        <button 
          className={`header-nav-btn ${activeTab === "ideas" ? "active" : ""}`}
          onClick={() => onTabSelect("ideas", "#/ideas")}
          title="Idea & Tag Studio"
        >
          <span className="header-nav-icon">💡</span>
          <span className="header-nav-label">Idea & Tag Studio</span>
        </button>
        <button 
          className={`header-nav-btn ${activeTab === "upload" ? "active" : ""}`}
          onClick={() => onTabSelect("upload", "#/upload")}
          title="Quick Upload"
        >
          <span className="header-nav-icon">⬆️</span>
          <span className="header-nav-label">Quick Upload</span>
        </button>
        <button 
          className={`header-nav-btn ${activeTab === "health" ? "active" : ""}`}
          onClick={() => onTabSelect("health", "#/health")}
          title="System Health"
        >
          <span className="header-nav-icon">📊</span>
          <span className="header-nav-label">Health</span>
        </button>
      </nav>

      {/* Right Stats & Quick Action Controls */}
      <div className="header-right">
        <div className="header-stats">
          <div className="header-stat-item">
            <span>Channels:</span> <b>{channels.length}</b>
          </div>
          <div className="header-stat-item">
            <span>Folders:</span> <b className="stat-green">{readyChannels}</b>
          </div>
        </div>

        <a 
          onClick={(e) => { e.preventDefault(); window.open("http://localhost:8000/login", "_blank"); }} href="#" 
          className="btn-primary header-connect-btn" 
          title="Connect YouTube Channel"
          aria-label="Connect Channel"
        >
          <span className="connect-btn-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </span>
          <span className="connect-btn-text">Connect Channel</span>
        </a>

        {/* Mobile / Tablet Menu Hamburger Button */}
        <button 
          className={`header-menu-btn ${menuOpen ? "open" : ""}`}
          onClick={() => setMenuOpen(!menuOpen)}
          title="Navigation menu"
          aria-label="Toggle Navigation Menu"
          aria-expanded={menuOpen}
        >
          {menuOpen ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
          )}
        </button>
      </div>

      {/* Dropdown Mobile / Tablet Menu Drawer */}
      {menuOpen && (
        <>
          <div className="mobile-menu-backdrop" onClick={() => setMenuOpen(false)} />
          <div className="mobile-menu-drawer">
            <div className="mobile-menu-header">
              <div style={{ fontWeight: 800, fontSize: 13, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Navigation & Views
              </div>
              <button className="mobile-menu-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">✕</button>
            </div>

            <div className="mobile-menu-nav">
              <button 
                className={`mobile-menu-item ${activeTab === "batch" ? "active" : ""}`}
                onClick={() => { onTabSelect("batch", "#/"); setMenuOpen(false); }}
              >
                <div className="mobile-menu-item-icon">📦</div>
                <div className="mobile-menu-item-text">
                  <div className="mobile-menu-item-title">Batch Uploader</div>
                  <div className="mobile-menu-item-desc">Multi-channel queues & schedules</div>
                </div>
                {activeTab === "batch" && <span className="mobile-active-dot" />}
              </button>

              <button 
                className={`mobile-menu-item ${activeTab === "ideas" ? "active" : ""}`}
                onClick={() => { onTabSelect("ideas", "#/ideas"); setMenuOpen(false); }}
              >
                <div className="mobile-menu-item-icon">💡</div>
                <div className="mobile-menu-item-text">
                  <div className="mobile-menu-item-title">Idea & Tag Studio</div>
                  <div className="mobile-menu-item-desc">Keyword research & viral tag generator</div>
                </div>
                {activeTab === "ideas" && <span className="mobile-active-dot" />}
              </button>

              <button 
                className={`mobile-menu-item ${activeTab === "upload" ? "active" : ""}`}
                onClick={() => { onTabSelect("upload", "#/upload"); setMenuOpen(false); }}
              >
                <div className="mobile-menu-item-icon">⬆️</div>
                <div className="mobile-menu-item-text">
                  <div className="mobile-menu-item-title">Quick Upload</div>
                  <div className="mobile-menu-item-desc">Instant upload for single video files</div>
                </div>
                {activeTab === "upload" && <span className="mobile-active-dot" />}
              </button>

              <button 
                className={`mobile-menu-item ${activeTab === "health" ? "active" : ""}`}
                onClick={() => { onTabSelect("health", "#/health"); setMenuOpen(false); }}
              >
                <div className="mobile-menu-item-icon">📊</div>
                <div className="mobile-menu-item-text">
                  <div className="mobile-menu-item-title">System Health</div>
                  <div className="mobile-menu-item-desc">Quota metrics, token health & analytics</div>
                </div>
                {activeTab === "health" && <span className="mobile-active-dot" />}
              </button>
            </div>

            <div className="mobile-menu-footer">
              <div className="mobile-menu-stats-row">
                <div className="mobile-stat-box">
                  <div className="mobile-stat-lbl">Channels</div>
                  <div className="mobile-stat-val">{channels.length}</div>
                </div>
                <div className="mobile-stat-box">
                  <div className="mobile-stat-lbl">Folders Set</div>
                  <div className="mobile-stat-val success">{readyChannels}</div>
                </div>
              </div>

              <div style={{ marginTop: 12 }}>
                <a 
                  onClick={(e) => { e.preventDefault(); window.open("http://localhost:8000/login", "_blank"); }} href="#" 
                  className="btn-primary" 
                  style={{ width: "100%", padding: "10px", fontSize: 13, justifyContent: "center", textDecoration: "none", boxSizing: "border-box" }}
                >
                  + Connect YouTube Channel
                </a>
              </div>
            </div>
          </div>
        </>
      )}
    </header>
  );
}

/* =========================================================================
   LEFT SIDEBAR CHANNEL NAVIGATOR (ALWAYS PINNED TO LEFT SIDE)
   ========================================================================= */
function Sidebar({ channels, status, onRemoved }) {
  const byId = Object.fromEntries((status.channels || []).map(c => [c.id, c]));

  const removeChannel = async (e, id, name) => {
    e.stopPropagation();
    if (!window.confirm(`Remove "${name || id}" from the app?\n\nVideos already on YouTube are NOT touched. You can re-add anytime with the + button.`)) return;
    await fetch(`/api/channels/${id}`, { method: "DELETE" });
    if (onRemoved) onRemoved();
  };

  return (
    <aside className="app-sidebar">
      <div className="sidebar-label">
        Channels
      </div>

      <div className="sidebar-scroll">
        {channels.map(c => {
          const st = byId[c.id] || {};
          const isActive = st.state === "active" || (status.running && status.current_channel === c.id);
          const isDone = st.state === "done";
          const hasFolder = !!c.folder;

          return (
            <div 
              key={c.id} 
              className={`avatar-btn ${isActive ? "active" : ""} ${isDone ? "done" : ""}`}
              onClick={() => { window.location.hash = `#/profile/${c.id}`; }}
              title={`${c.name || c.id} — ${hasFolder ? "Folder Ready" : "Click to set folder"}`}
            >
              <div 
                className="avatar-btn-inner" 
                style={{ 
                  borderColor: isActive ? "var(--accent-green)" : hasFolder ? "rgba(99, 102, 241, 0.4)" : "var(--border-subtle)" 
                }}
              >
                {c.avatar ? (
                  <img src={c.avatar} alt={c.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  (c.name || "?")[0].toUpperCase()
                )}
              </div>

              {isDone && <span className="avatar-badge-done">✓</span>}
              <span className="avatar-del" title="Remove channel"
                    onClick={(e) => removeChannel(e, c.id, c.name)}>✕</span>
              {!hasFolder && (
                <span style={{
                  position: "absolute", top: -2, right: -2, width: 9, height: 9,
                  borderRadius: "50%", background: "var(--accent-amber)", border: "2px solid var(--bg-sidebar)"
                }} />
              )}

              <div className="sidebar-tooltip">
                <div style={{ fontWeight: 700 }}>{c.name || c.id}</div>
                <div style={{ color: hasFolder ? "#34d399" : "#fbbf24", fontSize: 11, marginTop: 2 }}>
                  {hasFolder ? "📁 Folder Ready — Click to configure" : "⚠️ Click to set folder"}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <a
        onClick={(e) => { e.preventDefault(); window.open("http://localhost:8000/login", "_blank"); }} href="#"
        className="avatar-add-btn"
        title="Connect another YouTube Channel"
        style={{ display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 6 }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"></line>
          <line x1="5" y1="12" x2="19" y2="12"></line>
        </svg>
      </a>
    </aside>
  );
}



/* =========================================================================
   VIEW 1: BATCH DASHBOARD
   ========================================================================= */
function BatchDashboardView({ channels, status, setStatus, loadData }) {
  const [schedule, setSchedule] = useState(localStorage.getItem("schedule") !== "off");
  const [actionLoading, setActionLoading] = useState(false);
  const [globalSchedule, setGlobalSchedule] = useState({ auto_schedule: false, slots: [] });
  const [scheduleSaveStatus, setScheduleSaveStatus] = useState(null);

  useEffect(() => {
    fetch("/api/schedule")
      .then(r => r.json())
      .then(d => {
        if (d && Array.isArray(d.slots)) setGlobalSchedule(d);
      })
      .catch(() => {});
  }, []);

  const addGlobalSlot = () => {
    setGlobalSchedule(prev => ({
      ...prev,
      slots: [...(prev.slots || []), { time: "12:00", count: 3, enabled: true }]
    }));
  };

  const updateGlobalSlot = (index, field, value) => {
    setGlobalSchedule(prev => ({
      ...prev,
      slots: prev.slots.map((s, i) => i === index ? { ...s, [field]: value } : s)
    }));
  };

  const removeGlobalSlot = (index) => {
    setGlobalSchedule(prev => ({
      ...prev,
      slots: prev.slots.filter((_, i) => i !== index)
    }));
  };

  const saveGlobalSchedule = async () => {
    setScheduleSaveStatus({ type: "loading", message: "Saving daily schedule..." });
    try {
      const res = await fetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(globalSchedule)
      });
      const d = await res.json();
      if (res.ok && d.ok) {
        setScheduleSaveStatus({ type: "success", message: "Daily Auto-Pilot Schedule saved and active!" });
        loadData();
      } else {
        setScheduleSaveStatus({ type: "error", message: d.detail || "Failed to save schedule." });
      }
    } catch (e) {
      setScheduleSaveStatus({ type: "error", message: "Network error occurred." });
    }
  };

  const toggleSchedule = () => {
    const v = !schedule;
    setSchedule(v);
    localStorage.setItem("schedule", v ? "on" : "off");
  };

  const startBatch = async () => {
    setActionLoading(true);
    setStatus(prev => ({ ...prev, running: true, phase: "working" }));
    try {
      await fetch(`/api/batch/start?test_mode=false&schedule=${schedule}`, { method: "POST" });
      await loadData();
    } catch (e) {
      console.error(e);
      await loadData();
    } finally {
      setActionLoading(false);
    }
  };

  const stopBatch = async () => {
    setActionLoading(true);
    setStatus(prev => ({ ...prev, running: false, phase: "idle", current_channel: null, current_video: null }));
    try {
      await fetch("/api/batch/stop", { method: "POST" });
      await loadData();
    } catch (e) {
      console.error(e);
      await loadData();
    } finally {
      setActionLoading(false);
    }
  };

  const activeChannelObj = channels.find(c => c.id === status.current_channel);
  const configuredCount = channels.filter(c => !!c.folder).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Hero Control Panel */}
      <div className="glass-card" style={{ position: "relative", overflow: "hidden" }}>
        <div style={{
          position: "absolute", top: 0, right: 0, width: "320px", height: "100%",
          background: "radial-gradient(circle at 90% 10%, rgba(255, 46, 77, 0.12), transparent 70%)",
          pointerEvents: "none"
        }} />

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 20 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: "-0.02em" }}>
                Multi-Channel Batch Engine
              </h1>
              <span className={`status-pill ${status.running ? "running" : "idle"}`}>
                {status.running ? "⚡ Processing Queue" : "Ready"}
              </span>
            </div>
            <p style={{ margin: "8px 0 0", color: "var(--text-secondary)", fontSize: 14, maxWidth: 640 }}>
              Sequential uploads across all channels with configured folders. AI titles, viral tags, randomized rest intervals, and zero subscriber notification spam.
            </p>
          </div>

          {/* Quick Settings & Actions */}
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            {/* Upload Mode Switcher: Immediate vs Scheduled */}
            <div 
              className="toggle-wrapper" 
              onClick={toggleSchedule}
              style={{
                background: schedule ? "rgba(16, 185, 129, 0.12)" : "rgba(56, 189, 248, 0.12)",
                borderColor: schedule ? "rgba(16, 185, 129, 0.35)" : "rgba(56, 189, 248, 0.35)",
                padding: "8px 16px",
                gap: 12
              }}
              title={schedule ? "Scheduled Mode: Waits for peak YouTube viewership hours (UTC) for maximum viral reach" : "Immediate Mode: Uploads all videos immediately with randomized safe rests"}
            >
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: schedule ? "#34d399" : "#38bdf8" }}>
                  {schedule ? "⏰ Scheduled (Best Hours)" : "⚡ Immediate Upload"}
                </span>
                <span style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 1 }}>
                  {schedule ? "Waits for peak viral slots" : "Uploads now sequentially"}
                </span>
              </div>
              <div className={`toggle-pill ${schedule ? "checked" : ""}`} style={{ background: schedule ? "var(--accent-green)" : "#0284c7" }}>
                <div className="toggle-thumb" />
              </div>
            </div>

            {/* Start / Stop CTA Buttons */}
            {status.running ? (
              <button 
                className="btn-danger" 
                onClick={stopBatch} 
                disabled={actionLoading}
              >
                <span>■</span> Stop Batch
              </button>
            ) : (
              <button 
                className="btn-success" 
                onClick={startBatch} 
                disabled={actionLoading || configuredCount === 0}
                title={configuredCount === 0 ? "Configure at least one channel folder from the sidebar first" : "Click to upload immediately right now without waiting for schedule"}
              >
                <span>▶</span> Start Manual Run Now
              </button>
            )}
          </div>
        </div>

        {/* Safety Badges Bar */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 10, marginTop: 22,
          paddingTop: 18, borderTop: "1px solid var(--border-subtle)"
        }}>
          <div className="tag-chip" style={{ fontSize: 11.5, background: "rgba(16, 185, 129, 0.08)", borderColor: "rgba(16, 185, 129, 0.2)" }}>
            ⚡ Fast Gap: 3s per video
          </div>
          <div className="tag-chip" style={{ fontSize: 11.5, background: "rgba(99, 102, 241, 0.08)", borderColor: "rgba(99, 102, 241, 0.2)" }}>
            ⚡ Channel Gap: 3s
          </div>
          <div className="tag-chip" style={{ fontSize: 11.5, background: "rgba(56, 189, 248, 0.08)", borderColor: "rgba(56, 189, 248, 0.2)" }}>
            ⚡ 0-Quota Index Tags
          </div>
          <div className="tag-chip" style={{ fontSize: 11.5, background: "rgba(245, 158, 11, 0.08)", borderColor: "rgba(245, 158, 11, 0.2)" }}>
            🔕 notifySubscribers=False
          </div>
          <div className="tag-chip" style={{ fontSize: 11.5 }}>
            📌 Max 5/channel/day
          </div>
        </div>
      </div>

      {/* Daily Auto-Pilot Upload Scheduler Panel */}
      <div className="glass-card" style={{
        borderColor: globalSchedule.auto_schedule ? "rgba(99, 102, 241, 0.4)" : "var(--border-subtle)",
        background: globalSchedule.auto_schedule 
          ? "linear-gradient(180deg, rgba(99, 102, 241, 0.08) 0%, rgba(18, 21, 31, 0.95) 100%)" 
          : "rgba(18, 21, 31, 0.75)"
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, display: "flex", alignItems: "center", gap: 8 }}>
                ⏰ Daily Auto-Pilot Upload Schedule
              </h2>
              {globalSchedule.auto_schedule ? (
                <span className="status-pill running" style={{ fontSize: 11.5, padding: "4px 10px" }}>
                  <span className="animate-pulse-dot" style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent-green)", display: "inline-block", marginRight: 6 }} />
                  Auto-Pilot ON
                </span>
              ) : (
                <span style={{ fontSize: 11.5, color: "var(--text-muted)", background: "rgba(255,255,255,0.06)", padding: "4px 10px", borderRadius: 12, fontWeight: 700 }}>
                  Paused / OFF
                </span>
              )}
            </div>
            <p style={{ margin: "6px 0 0", color: "var(--text-secondary)", fontSize: 13.5, maxWidth: 680 }}>
              Set recurring daily timestamps and how many videos to upload per channel at each time (e.g. 12:00 PM &rarr; 4 videos, 04:00 AM &rarr; 3 videos). The background loop checks the clock and uploads automatically every day.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div 
              className="toggle-wrapper"
              onClick={() => setGlobalSchedule(prev => ({ ...prev, auto_schedule: !prev.auto_schedule }))}
              style={{
                background: globalSchedule.auto_schedule ? "rgba(16, 185, 129, 0.12)" : "rgba(255, 255, 255, 0.05)",
                borderColor: globalSchedule.auto_schedule ? "rgba(16, 185, 129, 0.35)" : "var(--border-subtle)",
                padding: "8px 14px", cursor: "pointer"
              }}
            >
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: globalSchedule.auto_schedule ? "#34d399" : "var(--text-muted)" }}>
                  {globalSchedule.auto_schedule ? "✅ Auto-Pilot Active" : "⏸️ Auto-Pilot Disabled"}
                </span>
                <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
                  {globalSchedule.auto_schedule ? "Runs automatically daily" : "Click to enable auto loop"}
                </span>
              </div>
              <div className={`toggle-pill ${globalSchedule.auto_schedule ? "checked" : ""}`} style={{ background: globalSchedule.auto_schedule ? "var(--accent-green)" : "rgba(255,255,255,0.2)" }}>
                <div className="toggle-thumb" />
              </div>
            </div>
          </div>
        </div>

        {/* Time Slots Area */}
        <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--border-subtle)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
              📅 Configured Daily Time Slots ({(globalSchedule.slots || []).length})
            </div>
            <button
              type="button"
              className="btn-primary"
              style={{
                padding: "6px 14px", fontSize: 12.5, display: "flex", alignItems: "center", gap: 6,
                background: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)", boxShadow: "0 2px 10px rgba(99, 102, 241, 0.3)"
              }}
              onClick={addGlobalSlot}
            >
              <span style={{ fontSize: 15, fontWeight: 800 }}>➕</span> Add Scheduled Time Slot
            </button>
          </div>

          {(globalSchedule.slots || []).length === 0 ? (
            <div style={{
              padding: "24px", textAlign: "center", background: "var(--bg-input)",
              borderRadius: "var(--radius-md)", border: "1px dashed var(--border-subtle)", color: "var(--text-muted)"
            }}>
              No daily timestamps added yet. Click <strong>"➕ Add Scheduled Time Slot"</strong> above to schedule daily uploads (e.g. 12:00 PM for 4 videos, 04:00 AM for 3 videos).
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {(globalSchedule.slots || []).map((slot, index) => {
                return (
                  <div
                    key={index}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      background: "var(--bg-input)", padding: "12px 16px", borderRadius: "var(--radius-md)",
                      border: slot.enabled ? "1px solid rgba(99, 102, 241, 0.35)" : "1px solid var(--border-subtle)",
                      opacity: slot.enabled ? 1 : 0.6, flexWrap: "wrap", gap: 12
                    }}
                  >
                    {/* Left: Time Picker */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 18 }}>🕒</span>
                      <div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>SCHEDULED TIME</div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                          <input
                            type="time"
                            className="input-text"
                            style={{ padding: "5px 8px", fontSize: 14, fontWeight: 700, width: 120 }}
                            value={slot.time}
                            onChange={e => updateGlobalSlot(index, "time", e.target.value)}
                          />
                          <span style={{
                            fontSize: 12, fontWeight: 800, padding: "3px 8px", borderRadius: 4,
                            background: "rgba(99, 102, 241, 0.15)", color: "#a5b4fc", border: "1px solid rgba(99, 102, 241, 0.3)"
                          }}>
                            {formatTime12h(slot.time)}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Middle: Video Count Input */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 18 }}>🎬</span>
                      <div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>VIDEOS PER CHANNEL</div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                          <input
                            type="number"
                            min="1"
                            max="50"
                            className="input-text"
                            style={{ width: 75, textAlign: "center", fontWeight: 700, padding: "5px 8px", fontSize: 14 }}
                            value={slot.count}
                            onChange={e => updateGlobalSlot(index, "count", Math.max(1, parseInt(e.target.value) || 1))}
                          />
                          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>videos / channel</span>
                        </div>
                      </div>
                    </div>

                    {/* Right: Toggle & Delete */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{
                          padding: "5px 12px", fontSize: 12,
                          background: slot.enabled ? "rgba(16, 185, 129, 0.1)" : "rgba(255,255,255,0.05)",
                          color: slot.enabled ? "#34d399" : "var(--text-muted)",
                          borderColor: slot.enabled ? "rgba(16, 185, 129, 0.3)" : undefined
                        }}
                        onClick={() => updateGlobalSlot(index, "enabled", !slot.enabled)}
                      >
                        {slot.enabled ? "Active" : "Paused"}
                      </button>

                      <button
                        type="button"
                        className="btn-secondary"
                        style={{
                          padding: "5px 10px", fontSize: 12, color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)"
                        }}
                        title="Remove time slot"
                        onClick={() => removeGlobalSlot(index)}
                      >
                        🗑️ Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Schedule Summary Banner */}
          {(globalSchedule.slots || []).length > 0 && (
            <div style={{
              marginTop: 16, padding: "12px 16px", borderRadius: "var(--radius-md)",
              background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.25)",
              display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, fontSize: 13
            }}>
              <div>
                📊 <strong>Daily Routine:</strong> {(globalSchedule.slots || []).filter(s => s.enabled).length} active time slot(s) · <strong>{(globalSchedule.slots || []).filter(s => s.enabled).reduce((sum, s) => sum + (parseInt(s.count) || 0), 0)} videos per channel</strong> daily.
              </div>
              {(() => {
                const next = getNextScheduledSlot(globalSchedule.slots, globalSchedule.auto_schedule);
                if (!next) return null;
                const hours = Math.floor(next.diffMinutes / 60);
                const mins = next.diffMinutes % 60;
                return (
                  <div style={{ color: "#34d399", fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⏳ Next Scheduled Run:</span>
                    <span>{next.count} video(s)/channel at {formatTime12h(next.time)} ({hours > 0 ? `${hours}h ` : ""}{mins}m away)</span>
                  </div>
                );
              })()}
            </div>
          )}

          <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
            <button
              type="button"
              className="btn-primary"
              style={{ padding: "10px 24px" }}
              onClick={saveGlobalSchedule}
            >
              💾 Save Daily Schedule
            </button>
          </div>

          {scheduleSaveStatus && (
            <div style={{
              marginTop: 12, padding: "10px 16px", borderRadius: "var(--radius-md)", fontSize: 13,
              background: scheduleSaveStatus.type === "success" ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)",
              color: scheduleSaveStatus.type === "success" ? "#34d399" : "#f87171",
              border: `1px solid ${scheduleSaveStatus.type === "success" ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"}`
            }}>
              {scheduleSaveStatus.message}
            </div>
          )}
        </div>
      </div>

       {/* Active Upload Spotlight (When running) */}
      {status.running && status.phase !== "resting" && (
        <div className="glass-card" style={{
          background: "linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(18, 21, 31, 0.95) 100%)",
          borderColor: "rgba(16, 185, 129, 0.3)"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{
              width: 56, height: 56, borderRadius: "50%", overflow: "hidden",
              border: "3px solid var(--accent-green)", boxShadow: "0 0 16px var(--accent-green-glow)"
            }}>
              {activeChannelObj?.avatar ? (
                <img src={activeChannelObj.avatar} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <div style={{ width: "100%", height: "100%", background: "#1e2230", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}>
                  {(activeChannelObj?.name || "?")[0]}
                </div>
              )}
            </div>

            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: "var(--accent-green)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Currently Uploading
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, marginTop: 2 }}>
                {activeChannelObj?.name || status.current_channel || "Active Channel"}
              </div>
              {status.current_video && (
                <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4, fontFamily: "var(--font-mono)" }}>
                  📄 {status.current_video}
                </div>
              )}
            </div>

            <div style={{
              background: "rgba(16, 185, 129, 0.15)", padding: "8px 16px", borderRadius: "var(--radius-md)",
              border: "1px solid rgba(16, 185, 129, 0.3)", display: "flex", alignItems: "center", gap: 8
            }}>
              <span className="animate-pulse-dot" style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--accent-green)" }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: "#34d399" }}>Live Processing</span>
            </div>
          </div>
        </div>
      )}

      {/* Channel Queue — numbered, sidebar order */}
      <div className="glass-card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-secondary)" }}>
            📋 Channel Queue — runs top to bottom
          </div>
          {status.running && (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {status.phase === "resting" && (
                <button
                  className="btn-primary"
                  style={{ padding: "4px 10px", fontSize: 11.5, background: "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)", boxShadow: "none" }}
                  onClick={async () => {
                    await fetch("/api/batch/skip-rest", { method: "POST" });
                    loadData();
                  }}
                >
                  ⏭️ Skip Rest & Upload Now
                </button>
              )}
              <span style={{ fontSize: 12, color: status.phase === "resting" ? "#38bdf8" : "var(--accent-green)", fontWeight: 700 }}>
                {(() => {
                  const idx = status.channels.findIndex(c => c.id === status.current_channel);
                  const step = (idx === -1 ? status.channels.filter(c => c.done > 0).length + 1 : idx + 1);
                  if (status.phase === "resting" && status.rest_until) {
                    const secs = Math.max(1, Math.round(status.rest_until - Date.now() / 1000));
                    const mins = Math.round(secs / 60);
                    return secs > 60 ? `⏸️ Next channel in ~${mins} min (safety rest)` : `⏸️ Next channel in ${secs}s`;
                  }
                  return `Step ${step} of ${status.channels.filter(c => c.folder).length}`;
                })()}
              </span>
            </div>
          )}
        </div>

        <div style={{
          maxHeight: 232, overflowY: "auto", paddingRight: 4,
          scrollbarWidth: "thin", scrollbarColor: "rgba(255,255,255,0.15) transparent"
        }}
             className="queue-scroll">
          {status.channels.length > 3 && (
            <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", paddingBottom: 8 }}>
              ↓ {status.channels.length} channels — scroll for more
            </div>
          )}
        {status.channels.map((c, i) => {
          const isActive = c.state === "active";
          const isWaiting = c.state === "waiting";
          const isDone = c.state === "done";
          const isReady = c.state === "ready";

          return (
            <div key={c.id} style={{
              display: "flex", alignItems: "center", gap: 14, padding: "12px 14px",
              borderRadius: "var(--radius-md)", marginBottom: 8,
              background: isActive ? "rgba(16, 185, 129, 0.1)" : "rgba(255,255,255,0.02)",
              border: `1px solid ${isActive ? "rgba(16, 185, 129, 0.35)" : "var(--border-subtle)"}`
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 800, fontSize: 13,
                background: isActive ? "var(--accent-green)" : isDone ? "rgba(52, 211, 153, 0.2)" : isWaiting ? "rgba(245, 158, 11, 0.15)" : "rgba(255,255,255,0.06)",
                color: isActive ? "#fff" : isDone ? "#34d399" : isWaiting ? "#fbbf24" : "var(--text-muted)"
              }}>
                {isDone ? "✓" : isWaiting ? "⏳" : i + 1}
              </div>

              <div style={{ width: 36, height: 36, borderRadius: "50%", overflow: "hidden", flexShrink: 0, border: "2px solid " + (isActive ? "var(--accent-green)" : "var(--border-subtle)") }}>
                {c.avatar
                  ? <img src={c.avatar} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  : <div style={{ width: "100%", height: "100%", background: "#1e2230", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13 }}>{(c.name || "?")[0]}</div>}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {c.name || c.id}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {isActive && status.current_video ? `📄 ${status.current_video}` : (c.folder ? `📁 ${c.folder} · 📌 Cap: ${c.cap || 5} vids/run` : "no folder") }
                </div>
              </div>

              <div style={{ flexShrink: 0, textAlign: "right" }}>
                {isActive ? (
                  <span className="status-pill running" style={{ fontSize: 11 }}>
                    <span className="animate-pulse-dot" style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent-green)", display: "inline-block", marginRight: 6 }} />
                    LIVE NOW — uploading {c.done + 1} of {Math.min(c.cap || 5, c.total)}
                  </span>
                ) : isWaiting ? (
                  <span style={{ fontSize: 11, color: "#fbbf24", fontWeight: 700, padding: "4px 8px", background: "rgba(245, 158, 11, 0.1)", borderRadius: 6, border: "1px solid rgba(245, 158, 11, 0.2)" }}>
                    ⏳ QUEUED ({Math.min(c.cap || 5, c.pending || c.total)} of {c.pending || c.total} in run)
                  </span>
                ) : isDone ? (
                  <span style={{ fontSize: 11, color: "#34d399", fontWeight: 700, padding: "4px 8px", background: "rgba(16, 185, 129, 0.1)", borderRadius: 6, border: "1px solid rgba(16, 185, 129, 0.2)" }}>
                    ✓ DONE ({c.done}/{c.total})
                  </span>
                ) : isReady ? (
                  <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                    Ready ({Math.min(c.cap || 5, c.pending || c.total)} of {c.pending || c.total} to upload)
                  </span>
                ) : !c.folder ? (
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>— skipped (no folder)</span>
                ) : (
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>idle</span>
                )}
              </div>
            </div>
          );
        })}
        </div>
      </div>

      {/* Terminal Log Output */}
      <TerminalLog log={status.log || []} />
    </div>
  );
}

function formatTime12h(timeStr) {
  if (!timeStr) return "";
  const parts = timeStr.split(":");
  if (parts.length < 2) return timeStr;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  if (isNaN(h) || isNaN(m)) return timeStr;
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${m < 10 ? "0" + m : m} ${ampm}`;
}

function getNextScheduledSlot(slots, autoEnabled) {
  if (!autoEnabled || !slots || !slots.length) return null;
  const activeSlots = slots.filter(s => s.enabled);
  if (!activeSlots.length) return null;

  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes();

  let nextSlot = null;
  let minDiff = Infinity;

  for (const s of activeSlots) {
    if (!s.time) continue;
    const [h, m] = s.time.split(":").map(Number);
    if (isNaN(h) || isNaN(m)) continue;
    let slotMinutes = h * 60 + m;
    let diff = slotMinutes - currentMinutes;
    if (diff <= 0) diff += 24 * 60;
    if (diff < minDiff) {
      minDiff = diff;
      nextSlot = { ...s, diffMinutes: diff };
    }
  }

  return nextSlot;
}

/* =========================================================================
   VIEW 2: CHANNEL PROFILE & FOLDER INSPECTOR
   ========================================================================= */
function ProfileView({ channelId, channels, onBack, onUpdate }) {
  const channel = channels.find(c => c.id === channelId);
  const [folder, setFolder] = useState(channel?.folder || "");
  const [cap, setCap] = useState(channel?.cap || 5);
  const [autoSchedule, setAutoSchedule] = useState(channel?.auto_schedule || false);
  const [slots, setSlots] = useState(channel?.schedule_slots || []);
  const [previewFiles, setPreviewFiles] = useState([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);
  const [scheduleSaveStatus, setScheduleSaveStatus] = useState(null);

  useEffect(() => {
    setFolder(channel?.folder || "");
    setCap(channel?.cap || 5);
    setAutoSchedule(channel?.auto_schedule || false);
    setSlots(channel?.schedule_slots || []);
    setSaveStatus(null);
    setScheduleSaveStatus(null);
    if (channel?.folder) {
      fetchPreview(channelId);
    } else {
      setPreviewFiles([]);
    }
  }, [channelId, channel?.folder, channel?.cap, channel?.schedule_slots, channel?.auto_schedule]);

  const fetchPreview = (id) => {
    setPreviewLoading(true);
    fetch(`/api/batch/preview/${id}`)
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) setPreviewFiles(data);
        else setPreviewFiles([]);
      })
      .catch(() => setPreviewFiles([]))
      .finally(() => setPreviewLoading(false));
  };

  const handleSave = async () => {
    if (!folder.trim()) return;
    const parsedCap = Math.max(1, parseInt(cap) || 5);
    setSaveStatus({ type: "loading", message: "Saving folder and upload cap..." });
    try {
      const res = await fetch(`/api/channels/${channelId}/folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder: folder.trim(), cap: parsedCap })
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        setSaveStatus({ type: "success", message: `Settings saved successfully! Upload limit set to ${parsedCap} video(s) per run.` });
        onUpdate();
        fetchPreview(channelId);
      } else {
        setSaveStatus({ type: "error", message: data.detail || "Failed to save settings." });
      }
    } catch (e) {
      setSaveStatus({ type: "error", message: "Network error occurred." });
    }
  };

  const addSlot = () => {
    setSlots([...slots, { time: "12:00", count: 3, enabled: true }]);
  };

  const updateSlot = (index, field, value) => {
    setSlots(slots.map((s, i) => i === index ? { ...s, [field]: value } : s));
  };

  const removeSlot = (index) => {
    setSlots(slots.filter((_, i) => i !== index));
  };

  const handleSaveSchedule = async () => {
    setScheduleSaveStatus({ type: "loading", message: "Saving daily schedule..." });
    try {
      const res = await fetch(`/api/channels/${channelId}/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_schedule: autoSchedule, slots })
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        setScheduleSaveStatus({ type: "success", message: "Daily auto-schedule saved successfully!" });
        onUpdate();
      } else {
        setScheduleSaveStatus({ type: "error", message: data.detail || "Failed to save schedule." });
      }
    } catch (e) {
      setScheduleSaveStatus({ type: "error", message: "Network error occurred." });
    }
  };

  if (!channel) {
    return (
      <div className="glass-card" style={{ textAlign: "center", padding: "40px" }}>
        <h3>Channel Not Found</h3>
        <p style={{ color: "var(--text-muted)" }}>This channel ID is not linked to this project.</p>
        <button className="btn-secondary" onClick={onBack}>← Back to all channels</button>
      </div>
    );
  }

  const pendingVideos = previewFiles.filter(f => !f.is_posted);
  const currentCap = parseInt(cap) || 5;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 900, margin: "0 auto" }}>
      {/* Top Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button className="btn-secondary" onClick={onBack} style={{ padding: "6px 14px", fontSize: 13 }}>
          ← Back to Dashboard
        </button>
      </div>

      {/* Channel Header Banner */}
      <div className="glass-card" style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{
          width: 72, height: 72, borderRadius: "50%", overflow: "hidden",
          background: "#1e2230", border: "3px solid var(--border-medium)", flexShrink: 0
        }}>
          {channel.avatar ? (
            <img src={channel.avatar} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          ) : (
            <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 28 }}>
              {(channel.name || "?")[0]}
            </div>
          )}
        </div>

        <div style={{ flex: 1 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{channel.name || channel.id}</h1>
          <div style={{ color: "var(--text-muted)", fontSize: 13, fontFamily: "var(--font-mono)", marginTop: 4 }}>
            Channel ID: {channel.id}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
          <span className="status-pill running" style={{ padding: "6px 12px" }}>
            ✅ Google Account Linked
          </span>
          {autoSchedule && (
            <span style={{ fontSize: 12, color: "#34d399", fontWeight: 700, background: "rgba(16, 185, 129, 0.12)", padding: "3px 8px", borderRadius: 4, border: "1px solid rgba(16, 185, 129, 0.3)" }}>
              ⏰ Daily Auto-Pilot Active
            </span>
          )}
        </div>
      </div>

      {/* Folder Settings Card */}
      <div className="glass-card">
        <h2 style={{ margin: "0 0 8px", fontSize: 17, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
          📁 Dedicated Video Directory & Batch Cap
        </h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 13.5, margin: "0 0 18px" }}>
          Set your video directory and manual batch upload limit for this account.
        </p>

        {/* Directory Input */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, fontWeight: 700, display: "block", marginBottom: 6, color: "var(--text-primary)" }}>
            📁 Dedicated Video Directory:
          </label>
          <input 
            type="text"
            className="input-text"
            style={{ width: "100%" }}
            placeholder="/Users/yourname/Videos/my-youtube-channel"
            value={folder}
            onChange={e => setFolder(e.target.value)}
          />
        </div>

        {/* Manual Batch Upload Cap Input */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 13, fontWeight: 700, display: "block", marginBottom: 6, color: "var(--text-primary)" }}>
            🎯 Manual Batch Cap (Max videos per manual run):
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <input 
              type="number"
              min="1"
              max="50"
              className="input-text"
              style={{ width: 90, textAlign: "center", fontWeight: 700, fontSize: 15 }}
              value={cap}
              onChange={e => setCap(e.target.value)}
            />
            <span style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 600 }}>videos per manual run</span>
            <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
              {[1, 2, 3, 5, 10].map(n => (
                <button
                  key={n}
                  type="button"
                  className="btn-secondary"
                  style={{
                    padding: "4px 12px", fontSize: 12,
                    background: Number(cap) === n ? "rgba(99, 102, 241, 0.25)" : undefined,
                    borderColor: Number(cap) === n ? "var(--accent-indigo)" : undefined,
                    color: Number(cap) === n ? "#fff" : undefined,
                    fontWeight: Number(cap) === n ? 700 : 500
                  }}
                  onClick={() => setCap(n)}
                >
                  {n} {n === 1 ? "vid" : "vids"}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12 }}>
          <button className="btn-primary" onClick={handleSave} style={{ padding: "10px 24px" }}>
            💾 Save Folder & Scan
          </button>
        </div>

        {saveStatus && (
          <div style={{
            marginTop: 14, padding: "10px 16px", borderRadius: "var(--radius-md)", fontSize: 13,
            background: saveStatus.type === "success" ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)",
            color: saveStatus.type === "success" ? "#34d399" : "#f87171",
            border: `1px solid ${saveStatus.type === "success" ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"}`
          }}>
            {saveStatus.message}
          </div>
        )}
      </div>

      {/* Daily Auto-Pilot Upload Schedule Card */}
      <div className="glass-card" style={{
        borderColor: autoSchedule ? "rgba(99, 102, 241, 0.4)" : "var(--border-subtle)",
        background: autoSchedule ? "linear-gradient(180deg, rgba(99, 102, 241, 0.05) 0%, rgba(18, 21, 31, 0.95) 100%)" : undefined
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 12 }}>
          <div>
            <h2 style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              ⏰ Daily Upload Schedule (Auto-Pilot Routine)
            </h2>
            <p style={{ color: "var(--text-secondary)", fontSize: 13, margin: 0 }}>
              Add multiple timestamps throughout the day and specify how many videos to upload at each time (e.g. 12:00 PM &rarr; 4 videos, 04:00 AM &rarr; 3 videos).
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: autoSchedule ? "#34d399" : "var(--text-muted)" }}>
              {autoSchedule ? "✅ Auto-Pilot Active" : "⏸️ Auto-Pilot Off"}
            </span>
            <button
              type="button"
              className={`toggle-pill ${autoSchedule ? "checked" : ""}`}
              style={{
                width: 48, height: 26, borderRadius: 13, cursor: "pointer", border: "none",
                background: autoSchedule ? "var(--accent-green)" : "rgba(255,255,255,0.15)",
                position: "relative", transition: "all 0.2s"
              }}
              onClick={() => setAutoSchedule(!autoSchedule)}
            >
              <span style={{
                position: "absolute", top: 3, left: autoSchedule ? 25 : 3, width: 20, height: 20,
                borderRadius: "50%", background: "#fff", transition: "all 0.2s"
              }} />
            </button>
          </div>
        </div>

        {/* Schedule Slots List */}
        <div style={{ marginTop: 18 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
              📅 Daily Time Slots ({slots.length})
            </span>
            <button
              type="button"
              className="btn-primary"
              style={{
                padding: "6px 14px", fontSize: 12.5, display: "flex", alignItems: "center", gap: 6,
                background: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)", boxShadow: "0 2px 10px rgba(99, 102, 241, 0.3)"
              }}
              onClick={addSlot}
            >
              <span style={{ fontSize: 15, fontWeight: 800 }}>➕</span> Add Scheduled Time Slot
            </button>
          </div>

          {slots.length === 0 ? (
            <div style={{
              padding: "24px", textAlign: "center", background: "var(--bg-input)",
              borderRadius: "var(--radius-md)", border: "1px dashed var(--border-subtle)", color: "var(--text-muted)"
            }}>
              No daily time slots added yet. Click <strong>"➕ Add Scheduled Time Slot"</strong> above to schedule daily uploads (e.g. 12:00 PM for 4 videos, 04:00 AM for 3 videos).
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {slots.map((slot, index) => {
                return (
                  <div
                    key={index}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      background: "var(--bg-input)", padding: "12px 16px", borderRadius: "var(--radius-md)",
                      border: slot.enabled ? "1px solid rgba(99, 102, 241, 0.35)" : "1px solid var(--border-subtle)",
                      opacity: slot.enabled ? 1 : 0.6, flexWrap: "wrap", gap: 12
                    }}
                  >
                    {/* Left: Time Picker */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 18 }}>🕒</span>
                      <div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>TIME OF DAY</div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                          <input
                            type="time"
                            className="input-text"
                            style={{ padding: "5px 8px", fontSize: 14, fontWeight: 700, width: 120 }}
                            value={slot.time}
                            onChange={e => updateSlot(index, "time", e.target.value)}
                          />
                          <span style={{
                            fontSize: 12, fontWeight: 800, padding: "3px 8px", borderRadius: 4,
                            background: "rgba(99, 102, 241, 0.15)", color: "#a5b4fc", border: "1px solid rgba(99, 102, 241, 0.3)"
                          }}>
                            {formatTime12h(slot.time)}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Middle: Video Count Input */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 18 }}>🎬</span>
                      <div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>VIDEOS TO UPLOAD</div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                          <input
                            type="number"
                            min="1"
                            max="50"
                            className="input-text"
                            style={{ width: 75, textAlign: "center", fontWeight: 700, padding: "5px 8px", fontSize: 14 }}
                            value={slot.count}
                            onChange={e => updateSlot(index, "count", Math.max(1, parseInt(e.target.value) || 1))}
                          />
                          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>videos</span>
                        </div>
                      </div>
                    </div>

                    {/* Right: Toggle & Delete */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{
                          padding: "5px 12px", fontSize: 12,
                          background: slot.enabled ? "rgba(16, 185, 129, 0.1)" : "rgba(255,255,255,0.05)",
                          color: slot.enabled ? "#34d399" : "var(--text-muted)",
                          borderColor: slot.enabled ? "rgba(16, 185, 129, 0.3)" : undefined
                        }}
                        onClick={() => updateSlot(index, "enabled", !slot.enabled)}
                      >
                        {slot.enabled ? "Active" : "Paused"}
                      </button>

                      <button
                        type="button"
                        className="btn-secondary"
                        style={{
                          padding: "5px 10px", fontSize: 12, color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)"
                        }}
                        title="Remove time slot"
                        onClick={() => removeSlot(index)}
                      >
                        🗑️ Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Schedule Summary Banner */}
          {slots.length > 0 && (
            <div style={{
              marginTop: 16, padding: "12px 16px", borderRadius: "var(--radius-md)",
              background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.25)",
              display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, fontSize: 13
            }}>
              <div>
                📊 <strong>Daily Plan:</strong> {slots.filter(s => s.enabled).length} active slot(s) · <strong>{slots.filter(s => s.enabled).reduce((sum, s) => sum + (parseInt(s.count) || 0), 0)} videos total</strong> will upload daily.
              </div>
              {(() => {
                const next = getNextScheduledSlot(slots, autoSchedule);
                if (!next) return null;
                const hours = Math.floor(next.diffMinutes / 60);
                const mins = next.diffMinutes % 60;
                return (
                  <div style={{ color: "#34d399", fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⏳ Next Run:</span>
                    <span>{next.count} video(s) at {formatTime12h(next.time)} ({hours > 0 ? `${hours}h ` : ""}{mins}m away)</span>
                  </div>
                );
              })()}
            </div>
          )}

          <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
            <button
              type="button"
              className="btn-primary"
              style={{ padding: "10px 24px" }}
              onClick={handleSaveSchedule}
            >
              💾 Save Daily Schedule
            </button>
          </div>

          {scheduleSaveStatus && (
            <div style={{
              marginTop: 12, padding: "10px 16px", borderRadius: "var(--radius-md)", fontSize: 13,
              background: scheduleSaveStatus.type === "success" ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)",
              color: scheduleSaveStatus.type === "success" ? "#34d399" : "#f87171",
              border: `1px solid ${scheduleSaveStatus.type === "success" ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"}`
            }}>
              {scheduleSaveStatus.message}
            </div>
          )}
        </div>
      </div>

      {/* Folder Preview / Dry Run Inspector */}
      <div className="glass-card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
              Live Folder Video Inspector
            </h3>
            <div style={{ color: "var(--text-muted)", fontSize: 12.5, marginTop: 2 }}>
              {previewFiles.length} video files in folder · {pendingVideos.length} new ready · {previewFiles.filter(f => f.is_posted).length} uploaded
            </div>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            {previewFiles.some(f => f.is_posted) && (
              <button 
                className="btn-secondary" 
                style={{ padding: "6px 12px", fontSize: 12, borderColor: "rgba(245, 158, 11, 0.4)", color: "#fbbf24" }}
                onClick={async () => {
                  if (confirm("Reset upload history for this channel? This will allow re-uploading all files in this folder.")) {
                    await fetch(`/api/channels/${channelId}/reset-uploads`, { method: "POST" });
                    fetchPreview(channelId);
                    onUpdate();
                  }
                }}
              >
                🔄 Reset Upload History
              </button>
            )}
            <button 
              className="btn-secondary" 
              style={{ padding: "6px 12px", fontSize: 12 }}
              onClick={() => fetchPreview(channelId)}
              disabled={previewLoading || !folder}
            >
              🔄 Refresh List
            </button>
          </div>
        </div>

        {/* Upload Plan Summary Badge */}
        {pendingVideos.length > 0 && (
          <div style={{
            background: "rgba(99, 102, 241, 0.1)", border: "1px solid rgba(99, 102, 241, 0.3)",
            padding: "12px 16px", borderRadius: "var(--radius-md)", fontSize: 13, color: "#e0e7ff", marginBottom: 16,
            display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16 }}>🎯</span>
              <span>
                <strong>Upload Plan:</strong> Next manual run will upload <strong>{Math.min(currentCap, pendingVideos.length)}</strong> of <strong>{pendingVideos.length}</strong> new video(s) (Cap: {currentCap}).
              </span>
            </div>
            {pendingVideos.length > currentCap && (
              <span style={{ fontSize: 12, color: "#fbbf24", background: "rgba(245, 158, 11, 0.15)", padding: "4px 10px", borderRadius: "var(--radius-sm)", border: "1px solid rgba(245, 158, 11, 0.3)" }}>
                ⏳ {pendingVideos.length - currentCap} video(s) will wait for subsequent runs
              </span>
            )}
          </div>
        )}

        {previewFiles.length > 0 && previewFiles.every(f => f.is_posted) && (
          <div style={{
            background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.25)",
            padding: "10px 14px", borderRadius: "var(--radius-md)", fontSize: 12.5, color: "#34d399", marginBottom: 14
          }}>
            ✅ All {previewFiles.length} video(s) in this folder are already uploaded to YouTube. To upload more videos, add new video files to this folder or click "Reset Upload History" to re-upload.
          </div>
        )}

        {previewLoading ? (
          <div style={{ textAlign: "center", padding: "28px", color: "var(--text-muted)" }}>
            ⏳ Scanning folder for videos...
          </div>
        ) : previewFiles.length === 0 ? (
          <div style={{
            padding: "28px", textAlign: "center", background: "var(--bg-input)",
            borderRadius: "var(--radius-md)", border: "1px dashed var(--border-subtle)", color: "var(--text-muted)"
          }}>
            {folder ? "No supported video files (.mp4, .mov, .mkv, .webm) found in this folder." : "Set a valid folder path above to inspect files."}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {previewFiles.map((v, i) => (
              <div 
                key={i}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  background: "var(--bg-input)", padding: "12px 16px", borderRadius: "var(--radius-md)",
                  border: v.is_posted 
                    ? "1px solid rgba(16, 185, 129, 0.2)" 
                    : v.in_next_batch 
                    ? "1px solid rgba(99, 102, 241, 0.4)" 
                    : "1px solid var(--border-subtle)",
                  boxShadow: v.in_next_batch ? "0 0 12px rgba(99, 102, 241, 0.1)" : "none",
                  flexWrap: "wrap", gap: 10
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 260, flex: 1 }}>
                  <span style={{ fontSize: 18 }}>{v.is_posted ? "✅" : v.in_next_batch ? "🎯" : "⏳"}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
                      {v.title}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                      File: {v.file}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {v.is_posted ? (
                    <>
                      {v.url && (
                        <a 
                          href={v.url} 
                          target="_blank" 
                          rel="noreferrer"
                          style={{ fontSize: 12, color: "var(--accent-blue)", textDecoration: "none", fontWeight: 600 }}
                        >
                          Watch on YouTube →
                        </a>
                      )}
                      <span className="tag-chip" style={{ fontSize: 11, background: "rgba(16, 185, 129, 0.12)", color: "#34d399", borderColor: "rgba(16, 185, 129, 0.3)" }}>
                        ✓ Already Uploaded
                      </span>
                      <button 
                        className="btn-secondary"
                        style={{ padding: "4px 8px", fontSize: 11 }}
                        title="Delete from history to allow re-uploading"
                        onClick={async () => {
                          await fetch(`/api/channels/${channelId}/reset-uploads?filename=${encodeURIComponent(v.file)}`, { method: "POST" });
                          fetchPreview(channelId);
                          onUpdate();
                        }}
                      >
                        🔄 Re-upload
                      </button>
                    </>
                  ) : v.in_next_batch ? (
                    <span className="tag-chip" style={{ fontSize: 11.5, background: "rgba(99, 102, 241, 0.2)", color: "#c7d2fe", borderColor: "rgba(99, 102, 241, 0.5)", fontWeight: 700 }}>
                      🎯 IN NEXT BATCH (#{v.batch_order} of {currentCap})
                    </span>
                  ) : (
                    <span className="tag-chip" style={{ fontSize: 11, background: "rgba(245, 158, 11, 0.1)", color: "#fbbf24", borderColor: "rgba(245, 158, 11, 0.25)" }}>
                      ⏳ QUEUED (Exceeds cap of {currentCap})
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* =========================================================================
   VIEW 3: IDEA & TAG STUDIO
   ========================================================================= */
function IdeaStudioView() {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [ideasData, setIdeasData] = useState(null);
  const [compareData, setCompareData] = useState(null);
  const [copiedText, setCopiedText] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");

  const searchIdeas = async () => {
    const t = topic.trim();
    if (!t) return;
    setLoading(true);
    setErrorMsg("");
    setCompareData(null);
    try {
      const res = await fetch(`/api/ideas?topic=${encodeURIComponent(t)}`);
      const d = await res.json();
      if (res.ok && !d.detail) {
        setIdeasData(d);
      } else {
        setErrorMsg(d.detail || "No ideas found for that topic.");
      }
    } catch (e) {
      setErrorMsg("Failed to connect to idea engine.");
    } finally {
      setLoading(false);
    }
  };

  const compareSources = async () => {
    const t = topic.trim();
    if (!t) return;
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch(`/api/compare?topic=${encodeURIComponent(t)}`);
      const d = await res.json();
      if (res.ok && !d.detail) {
        setCompareData(d);
      } else {
        setErrorMsg(d.detail || "Comparison failed.");
      }
    } catch (e) {
      setErrorMsg("Failed to execute compare lookup.");
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 2000);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 960, margin: "0 auto" }}>
      <div className="glass-card">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>
            💡 Viral Idea & Tag Generator
          </h1>
          <span className="status-pill running" style={{ fontSize: 11 }}>
            ⚡ 0-Quota Fast Engine
          </span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13.5, margin: "0 0 20px" }}>
          Extract high-performing keywords, viral tags, hashtags, and optimal upload timing from YouTube's top search graph without spending API quota.
        </p>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <input 
            type="text"
            className="input-text"
            style={{ flex: 1, minWidth: 260, fontSize: 15 }}
            placeholder="e.g. sajek tour, ai coding, gaming highlights, recipe"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            onKeyDown={e => e.key === "Enter" && searchIdeas()}
          />
          <button className="btn-primary" onClick={searchIdeas} disabled={loading || !topic.trim()}>
            {loading ? "Searching..." : "🔍 Find Viral Metadata"}
          </button>
          <button className="btn-secondary" onClick={compareSources} disabled={loading || !topic.trim()}>
            📊 Free vs Live Compare
          </button>
        </div>

        {errorMsg && (
          <div style={{ marginTop: 16, color: "#f87171", fontSize: 13 }}>
            ⚠️ {errorMsg}
          </div>
        )}
      </div>

      {/* Ideas Data Output */}
      {ideasData && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Metadata Source Card */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            background: "rgba(99, 102, 241, 0.1)", border: "1px solid rgba(99, 102, 241, 0.25)",
            padding: "12px 18px", borderRadius: "var(--radius-lg)"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 20 }}>⚡</span>
              <div>
                <div style={{ fontWeight: 700, fontSize: 13.5, color: "#e0e7ff" }}>
                  Source: {ideasData.source === "index" || ideasData.source === "corpus" ? "Indexed Offline Graph (0 Quota Spent)" : "Live YouTube Intelligence"}
                </div>
                <div style={{ fontSize: 12, color: "#a5b4fc" }}>
                  Optimized for fast rank retrieval and organic metadata discovery.
                </div>
              </div>
            </div>

            {ideasData.duration && (
              <div style={{ fontSize: 12, color: "#e0e7ff", textAlign: "right" }}>
                ⏱️ Top videos avg: <b>{Math.round(ideasData.duration / 60)}m {ideasData.duration % 60}s</b>
              </div>
            )}
          </div>

          {/* Keywords & Search Phrases */}
          {ideasData.keywords?.length > 0 && (
            <div className="glass-card">
              <h3 style={{ margin: "0 0 12px", fontSize: 15, fontWeight: 700 }}>
                🔑 Trending Search Keywords (Click to copy)
              </h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {ideasData.keywords.map((k, i) => (
                  <button 
                    key={i} 
                    className="tag-chip"
                    onClick={() => copyToClipboard(k)}
                  >
                    <span>+</span> {k}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Viral Tags */}
          {ideasData.tags?.length > 0 && (
            <div className="glass-card">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>
                  🏷️ High-Rank Viral Tags
                </h3>
                <button 
                  className="btn-secondary" 
                  style={{ padding: "4px 10px", fontSize: 12 }}
                  onClick={() => copyToClipboard(ideasData.tags.join(","))}
                >
                  📋 Copy All as CSV
                </button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {ideasData.tags.map((t, i) => (
                  <span 
                    key={i} 
                    className="tag-chip" 
                    style={{ background: "rgba(16, 185, 129, 0.08)", borderColor: "rgba(16, 185, 129, 0.25)", color: "#34d399" }}
                    onClick={() => copyToClipboard(t)}
                  >
                    #{t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Hashtags */}
          {ideasData.hashtags?.length > 0 && (
            <div className="glass-card">
              <h3 style={{ margin: "0 0 12px", fontSize: 15, fontWeight: 700 }}>
                #️⃣ Winning Hashtags
              </h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {ideasData.hashtags.map((h, i) => (
                  <button 
                    key={i} 
                    className="tag-chip"
                    onClick={() => copyToClipboard(h)}
                  >
                    {h}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Compare Output */}
      {compareData && (
        <div className="glass-card">
          <h3 style={{ margin: "0 0 14px", fontSize: 16, fontWeight: 700 }}>
            📊 Free Index vs Live API Tag Verification
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div style={{ background: "var(--bg-input)", padding: 14, borderRadius: "var(--radius-md)" }}>
              <div style={{ fontWeight: 700, color: "var(--accent-green)", marginBottom: 8, fontSize: 13 }}>
                ⚡ Free Index Tags ({compareData.index_videos} index videos)
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--text-secondary)" }}>
                {compareData.index_tags.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </div>
            <div style={{ background: "var(--bg-input)", padding: 14, borderRadius: "var(--radius-md)" }}>
              <div style={{ fontWeight: 700, color: "var(--accent-blue)", marginBottom: 8, fontSize: 13 }}>
                🔎 Live API Tags (1 Search Used)
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--text-secondary)" }}>
                {compareData.live_tags.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}

      {copiedText && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, background: "var(--accent-green)",
          color: "#000", fontWeight: 700, padding: "10px 18px", borderRadius: "var(--radius-md)",
          boxShadow: "var(--shadow-glow-green)", zIndex: 100
        }}>
          ✓ Copied: "{copiedText.slice(0, 30)}"
        </div>
      )}
    </div>
  );
}

/* =========================================================================
   VIEW 4: QUICK / DIRECT UPLOAD
   ========================================================================= */
function QuickUploadView({ channels, onUploaded }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [tags, setTags] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (f) {
      setFile(f);
      if (!title) {
        const clean = f.name.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
        setTitle(clean.replace(/\b\w/g, l => l.toUpperCase()));
      }
    }
  };

  const handleUpload = () => {
    if (!file) return setErrorMsg("Please choose a video file.");
    if (!title.trim()) return setErrorMsg("Please provide a title.");

    setErrorMsg("");
    setResult(null);
    setUploading(true);
    setProgress(0);

    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title.trim());
    fd.append("description", desc);
    if (tags) fd.append("tags", tags);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        setProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      setUploading(false);
      try {
        const res = JSON.parse(xhr.responseText);
        if (xhr.status === 200 && res.ok) {
          setResult(res);
          onUploaded();
        } else {
          setErrorMsg(res.detail || "Upload failed.");
        }
      } catch (err) {
        setErrorMsg("Failed to parse upload response.");
      }
    };
    xhr.onerror = () => {
      setUploading(false);
      setErrorMsg("Network error occurred during video upload.");
    };
    xhr.send(fd);
  };

  return (
    <div style={{ maxWidth: 780, margin: "0 auto" }}>
      <div className="glass-card">
        <h1 style={{ margin: "0 0 8px", fontSize: 22, fontWeight: 800 }}>
          ⬆️ Direct Single Video Upload
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13.5, margin: "0 0 24px" }}>
          Upload a single video immediately to the primary active channel with live progress tracking.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {/* File Picker Zone */}
          <div style={{
            border: "2px dashed var(--border-medium)", borderRadius: "var(--radius-lg)",
            padding: "32px 20px", textAlign: "center", background: "var(--bg-input)", cursor: "pointer"
          }} onClick={() => document.getElementById("file-input").click()}>
            <input 
              id="file-input"
              type="file" 
              accept="video/*" 
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
            <div style={{ fontSize: 36, marginBottom: 8 }}>📁</div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>
              {file ? file.name : "Click or Drag to Select Video File"}
            </div>
            <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 4 }}>
              Supports MP4, MOV, MKV, WebM
            </div>
          </div>

          {/* Title */}
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
              Video Title
            </label>
            <input 
              type="text" 
              className="input-text" 
              placeholder="e.g. My Amazing Travel Adventure 2026"
              value={title} 
              onChange={e => setTitle(e.target.value)} 
            />
          </div>

          {/* Description */}
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
              Description (Optional)
            </label>
            <textarea 
              className="input-text" 
              rows={4}
              placeholder="Enter video description and hashtags..."
              value={desc} 
              onChange={e => setDesc(e.target.value)} 
            />
          </div>

          {/* Tags */}
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
              Tags (Comma-separated)
            </label>
            <input 
              type="text" 
              className="input-text" 
              placeholder="travel, vlog, bangladesh, tour"
              value={tags} 
              onChange={e => setTags(e.target.value)} 
            />
          </div>

          {/* Progress Bar */}
          {uploading && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 6 }}>
                <span>Uploading to YouTube...</span>
                <span style={{ fontWeight: 700 }}>{progress}%</span>
              </div>
              <div style={{ width: "100%", height: 10, background: "var(--bg-input)", borderRadius: 5, overflow: "hidden" }}>
                <div style={{ width: `${progress}%`, height: "100%", background: "var(--accent-red)", transition: "width 0.2s ease" }} />
              </div>
            </div>
          )}

          {errorMsg && (
            <div style={{ color: "#f87171", fontSize: 13 }}>
              ⚠️ {errorMsg}
            </div>
          )}

          {result && (
            <div style={{
              background: "rgba(16, 185, 129, 0.15)", border: "1px solid rgba(16, 185, 129, 0.3)",
              borderRadius: "var(--radius-md)", padding: "14px 18px", color: "#34d399"
            }}>
              🎉 Upload Complete!{" "}
              <a href={result.url} target="_blank" rel="noreferrer" style={{ color: "#fff", fontWeight: 700, textDecoration: "underline" }}>
                Watch on YouTube →
              </a>
            </div>
          )}

          <button 
            className="btn-primary" 
            onClick={handleUpload} 
            disabled={uploading || !file}
            style={{ padding: "14px 24px", fontSize: 16 }}
          >
            {uploading ? `Uploading (${progress}%)...` : "🚀 Upload Video to YouTube"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   VIEW 5: HEALTH & SAFETY METRICS
   ========================================================================= */
function HealthView({ health, channels }) {
  return (
    <div style={{ maxWidth: 860, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="glass-card">
        <h1 style={{ margin: "0 0 8px", fontSize: 22, fontWeight: 800 }}>
          📊 System Health & Quota Metrics
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13.5, margin: "0 0 24px" }}>
          Real-time diagnostics on OAuth tokens, daily rate caps, and quota efficiency.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 16 }}>
          <div style={{ background: "var(--bg-input)", padding: 18, borderRadius: "var(--radius-lg)", border: "1px solid var(--border-subtle)" }}>
            <div style={{ color: "var(--text-muted)", fontSize: 12, fontWeight: 600 }}>Active Tokens</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: "var(--accent-green)", marginTop: 4 }}>
              {health?.tokens_saved || channels.length}
            </div>
          </div>

          <div style={{ background: "var(--bg-input)", padding: 18, borderRadius: "var(--radius-lg)", border: "1px solid var(--border-subtle)" }}>
            <div style={{ color: "var(--text-muted)", fontSize: 12, fontWeight: 600 }}>Total All-Time Uploads</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: "var(--text-primary)", marginTop: 4 }}>
              {health?.uploads_total || 0}
            </div>
          </div>

          <div style={{ background: "var(--bg-input)", padding: 18, borderRadius: "var(--radius-lg)", border: "1px solid var(--border-subtle)" }}>
            <div style={{ color: "var(--text-muted)", fontSize: 12, fontWeight: 600 }}>Uploaded Today</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: "var(--accent-blue)", marginTop: 4 }}>
              {health?.uploads_today_all_channels || 0}
            </div>
          </div>

          <div style={{ background: "var(--bg-input)", padding: 18, borderRadius: "var(--radius-lg)", border: "1px solid var(--border-subtle)" }}>
            <div style={{ color: "var(--text-muted)", fontSize: 12, fontWeight: 600 }}>Per-Channel Daily Cap</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: "var(--accent-amber)", marginTop: 4 }}>
              {health?.daily_cap_per_channel || 5}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   TERMINAL CONSOLE COMPONENT
   ========================================================================= */
function TerminalLog({ log }) {
  return (
    <div className="terminal-card">
      <div className="terminal-header">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="terminal-dots">
            <span className="terminal-dot" style={{ background: "#ff5f56" }} />
            <span className="terminal-dot" style={{ background: "#ffbd2e" }} />
            <span className="terminal-dot" style={{ background: "#27c93f" }} />
          </div>
          <span style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 600 }}>
            batch-engine.log — Live Activity Output
          </span>
        </div>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Auto-polling 3s</span>
      </div>

      <div className="terminal-body">
        {log.length === 0 ? (
          <div className="terminal-line" style={{ color: "var(--text-muted)" }}>
            [System] Engine idle. Click a channel in the sidebar to set its video folder, then press "Start All Channels".
          </div>
        ) : (
          log.map((line, i) => {
            const isSuccess = line.includes("POSTED") || line.includes("uploaded") || line.includes("✓");
            const isWarn = line.includes("rest") || line.includes("waiting") || line.includes("skip");
            const isError = line.includes("error") || line.includes("failed") || line.includes("rejected");
            const lineClass = isSuccess ? "success" : isError ? "error" : isWarn ? "warn" : "info";

            return (
              <div key={i} className={`terminal-line ${lineClass}`}>
                {line}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
