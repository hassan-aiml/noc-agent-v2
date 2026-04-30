import React, { useState, useEffect, useCallback } from 'react';
import FlowContainer from './FlowContainer';
import TriageTerminal from './TriageTerminal';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const SCENARIOS = [
  {
    id: 'single_ru',
    label: '① Single RU Failure',
    description: 'RU-01 — VSWR High',
    color: '#ff9500',
  },
  {
    id: 'hub_failure',
    label: '② Food Court Hub Failure',
    description: 'EH-01: All 5 RUs Offline',
    color: '#ff3a3a',
  },
  {
    id: 'poi_signal_loss',
    label: '③ Meridian n41 Signal Loss',
    description: 'Sector-wide DL Power Low',
    color: '#4d9eff',
  },
];

export default function App() {
  const [topology, setTopology] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [primaryIncident, setPrimaryIncident] = useState(null);
  const [triageBrief, setTriageBrief] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeScenario, setActiveScenario] = useState(null);
  const [error, setError] = useState('');

  // Load topology once
  useEffect(() => {
    fetch(`${API}/topology`)
      .then(r => r.json())
      .then(setTopology)
      .catch(e => setError('Backend not reachable — start FastAPI on port 8000'));
  }, []);

  const runScenario = useCallback(async (scenarioId) => {
    setLoading(true);
    setActiveScenario(scenarioId);
    setTriageBrief('');
    setIncidents([]);
    setPrimaryIncident(null);
    setError('');

    try {
      const res = await fetch(`${API}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: scenarioId }),
      });
      const data = await res.json();
      setIncidents(data.incidents || []);
      setPrimaryIncident(data.primary_incident || null);
      setTriageBrief(data.triage_brief || '');
    } catch (e) {
      setError('Simulation failed. Is the backend running?');
    } finally {
      setLoading(false);
    }
  }, []);

  const resetAll = () => {
    setIncidents([]);
    setPrimaryIncident(null);
    setTriageBrief('');
    setActiveScenario(null);
    setError('');
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      background: '#060b14',
      color: '#b0c4de',
      fontFamily: "'JetBrains Mono', monospace",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #060b14; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0a1020; }
        ::-webkit-scrollbar-thumb { background: #1e3a5f; border-radius: 3px; }
        .scenario-btn {
          background: #0a1020;
          border: 1px solid #1e3050;
          color: #b0c4de;
          padding: 10px 14px;
          border-radius: 6px;
          cursor: pointer;
          text-align: left;
          transition: all 0.2s;
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          width: 100%;
          margin-bottom: 8px;
        }
        .scenario-btn:hover { border-color: #4d9eff; background: #0d1a2b; }
        .scenario-btn.active { border-color: #ff3a3a; background: #0d0a1a; }
        .reset-btn {
          background: transparent;
          border: 1px solid #1e3050;
          color: #4d9eff;
          padding: 8px 12px;
          border-radius: 4px;
          cursor: pointer;
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          width: 100%;
          transition: all 0.2s;
        }
        .reset-btn:hover { border-color: #4d9eff; background: #0d1a2b; }
      `}</style>

      {/* ── Top Bar ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        padding: '10px 20px',
        background: '#060b14',
        borderBottom: '1px solid #1e3050',
        gap: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>🛰️</span>
          <div>
            <div style={{ color: '#4d9eff', fontWeight: 700, fontSize: 13, letterSpacing: 3 }}>NOC TRIAGE AGENT</div>
            <div style={{ color: '#3a5a7a', fontSize: 10, letterSpacing: 2 }}>DIGITAL TWIN · PHASE 2</div>
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 20, fontSize: 10, color: '#3a5a7a' }}>
          <span>SITE: <span style={{ color: '#b0c4de' }}>NORTHPARK MALL</span></span>
          <span>NODES: <span style={{ color: '#00ffa3' }}>{topology ? Object.keys(topology.nodes || {}).length : '—'}</span></span>
          {activeScenario && (
            <span>
              SCENARIO: <span style={{ color: '#ff9500' }}>
                {SCENARIOS.find(s => s.id === activeScenario)?.id.toUpperCase()}
              </span>
            </span>
          )}
        </div>
        {error && (
          <div style={{ background: '#1a0505', border: '1px solid #ff3a3a', color: '#ff7070', padding: '4px 10px', borderRadius: 4, fontSize: 10 }}>
            ⚠ {error}
          </div>
        )}
      </div>

      {/* ── Main Layout ── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar */}
        <div style={{
          width: 220,
          background: '#08101e',
          borderRight: '1px solid #1e3050',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          overflowY: 'auto',
        }}>
          <div style={{ color: '#3a5a7a', fontSize: 10, letterSpacing: 2, marginBottom: 10 }}>SIMULATE FAULT</div>

          {SCENARIOS.map(sc => (
            <button
              key={sc.id}
              className={`scenario-btn ${activeScenario === sc.id ? 'active' : ''}`}
              onClick={() => runScenario(sc.id)}
            >
              <div style={{ color: sc.color, fontWeight: 700, marginBottom: 3 }}>{sc.label}</div>
              <div style={{ color: '#3a5a7a', fontSize: 10 }}>{sc.description}</div>
            </button>
          ))}

          <div style={{ flex: 1 }} />

          <button className="reset-btn" onClick={resetAll}>↺ Reset</button>

          {/* Legend */}
          <div style={{ marginTop: 16, borderTop: '1px solid #1e3050', paddingTop: 12 }}>
            <div style={{ color: '#3a5a7a', fontSize: 9, letterSpacing: 2, marginBottom: 8 }}>LEGEND</div>
            {[
              { color: '#00ffa3', label: 'Healthy' },
              { color: '#ff3a3a', label: 'Root Fault' },
              { color: '#ff9500', label: 'Impacted' },
              { color: '#4d9eff', label: 'POI/Source' },
            ].map(item => (
              <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5, fontSize: 10 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: item.color + '33', border: `1px solid ${item.color}` }} />
                <span style={{ color: '#6a8aaa' }}>{item.label}</span>
              </div>
            ))}
          </div>

          {/* Incident list */}
          {incidents.length > 0 && (
            <div style={{ marginTop: 12, borderTop: '1px solid #1e3050', paddingTop: 12 }}>
              <div style={{ color: '#3a5a7a', fontSize: 9, letterSpacing: 2, marginBottom: 8 }}>INCIDENTS ({incidents.length})</div>
              {incidents.map(inc => (
                <div key={inc.incident_id} style={{
                  background: '#0a1020',
                  border: `1px solid ${inc.severity === 'P1' ? '#ff3a3a44' : inc.severity === 'P2' ? '#ff6a0044' : '#1e3050'}`,
                  borderRadius: 4,
                  padding: '6px 8px',
                  marginBottom: 6,
                  fontSize: 10,
                }}>
                  <div style={{ color: inc.severity === 'P1' ? '#ff7070' : inc.severity === 'P2' ? '#ff9500' : '#00ffa3', fontWeight: 700, fontSize: 9 }}>
                    {'■'.repeat({'P1':5,'P2':4,'P3':3,'P4':2,'P5':1}[inc.severity]||0)}{'□'.repeat(5-({'P1':5,'P2':4,'P3':3,'P4':2,'P5':1}[inc.severity]||0))} {inc.severity} · {inc.scope_label}
                  </div>
                  <div style={{ color: '#8aafcc', marginTop: 2 }}>{inc.root_cause_node}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Center: React Flow diagram */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: 1, minHeight: 0 }}>
            {topology
              ? <FlowContainer topology={topology} incidents={incidents} />
              : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#3a5a7a' }}>
                  {error ? error : 'Loading topology...'}
                </div>
              )
            }
          </div>

          {/* Bottom terminal */}
          <div style={{ height: 340, borderTop: "1px solid #1e3050" }}>
            <TriageTerminal
              brief={triageBrief}
              loading={loading}
              incident={primaryIncident}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
