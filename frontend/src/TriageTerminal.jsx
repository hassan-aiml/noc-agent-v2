import React, { useEffect, useRef, useState } from 'react';

const CURSOR_CHAR = '█';

export default function TriageTerminal({ brief, loading, incident }) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);
  const timerRef = useRef(null);
  const idxRef = useRef(0);

  useEffect(() => {
    clearInterval(timerRef.current);
    setDisplayed('');
    setDone(false);
    idxRef.current = 0;
    if (!brief) return;

    timerRef.current = setInterval(() => {
      idxRef.current += 1;
      setDisplayed(brief.slice(0, idxRef.current));
      if (idxRef.current >= brief.length) {
        clearInterval(timerRef.current);
        setDone(true);
      }
    }, 18);

    return () => clearInterval(timerRef.current);
  }, [brief]);

  // P1–P5 bar mapping — visual only, backend always uses P1–P5
  const severityMap  = { 'P1': 5, 'P2': 4, 'P3': 3, 'P4': 2, 'P5': 1 };
  const severityColor = (s) => {
    if (s === 'P1') return '#ff3a3a';
    if (s === 'P2') return '#ff6a00';
    if (s === 'P3') return '#ff9500';
    if (s === 'P4') return '#ffd700';
    if (s === 'P5') return '#4d9eff';
    return '#888';
  };
  const severityBar = (s) => {
    const filled = severityMap[s] || 0;
    const color = severityColor(s);
    return (
      <span>
        {'■'.repeat(filled)}
        <span style={{ opacity: 0.2 }}>{'■'.repeat(5 - filled)}</span>
        {' '}{s}
      </span>
    );
  };

  return (
    <div style={{
      background: '#06090f',
      border: '1px solid #1e3050',
      borderTop: '2px solid #1e3a5f',
      fontFamily: "'JetBrains Mono', 'Courier New', monospace",
      fontSize: 12,
      color: '#b0c4de',
      padding: '12px 18px',
      height: '100%',
      overflowY: 'auto',
      boxSizing: 'border-box',
    }}>
      {/* Terminal header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, borderBottom: '1px solid #1e3050', paddingBottom: 8 }}>
        <span style={{ color: '#ff5f57', fontSize: 10 }}>●</span>
        <span style={{ color: '#febc2e', fontSize: 10 }}>●</span>
        <span style={{ color: '#28c840', fontSize: 10 }}>●</span>
        <span style={{ color: '#4d9eff', marginLeft: 8, letterSpacing: 2, fontSize: 11 }}>NOC TRIAGE TERMINAL</span>
      </div>

      {/* Incident metadata */}
      {incident && (
        <div style={{ marginBottom: 12, lineHeight: 1.8 }}>
          <div><span style={{ color: '#4d9eff' }}>INCIDENT   </span><span style={{ color: '#e0e0e0' }}>{incident.incident_id}</span></div>
          <div><span style={{ color: '#4d9eff' }}>TITLE      </span><span style={{ color: '#e0e0e0' }}>{incident.title}</span></div>
          <div>
            <span style={{ color: '#4d9eff' }}>SEVERITY   </span>
            <span style={{ color: severityColor(incident.severity), fontWeight: 700 }}>
              {severityBar(incident.severity)}
            </span>
          </div>
          <div><span style={{ color: '#4d9eff' }}>SCOPE      </span><span style={{ color: '#e0e0e0' }}>{incident.scope_label}</span></div>
          <div><span style={{ color: '#4d9eff' }}>ROOT CAUSE </span><span style={{ color: '#ffd700' }}>{incident.root_cause_node} ({incident.root_cause_type})</span></div>
          <div><span style={{ color: '#4d9eff' }}>ZONE       </span>
            <span style={{ color: incident.is_critical_zone ? '#ff3a3a' : '#00ffa3' }}>
              {incident.is_critical_zone ? '⚠ CRITICAL' : 'Standard'}
            </span>
          </div>
          <div style={{ marginTop: 4, color: '#888', fontSize: 11 }}>
            AFFECTED: {incident.affected_nodes?.join(', ')}
          </div>
          <div style={{ borderBottom: '1px solid #1e3050', marginTop: 8, marginBottom: 8 }} />
        </div>
      )}

      {/* AI Brief */}
      <div style={{ marginBottom: 4 }}>
        <span style={{ color: '#4d9eff' }}>AI BRIEF   </span>
        {loading && <span style={{ color: '#ff9500' }}>⟳ Generating triage brief...</span>}
      </div>
      {!loading && brief && (
        <div style={{ color: '#d4e8c2', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
          {displayed}{!done ? <span style={{ opacity: 0.7 }}>{CURSOR_CHAR}</span> : ''}
        </div>
      )}
      {!loading && !brief && (
        <div style={{ color: '#3a4a5a', fontStyle: 'italic' }}>
          — Select a scenario to run triage —
        </div>
      )}

      {/* Sparing advice */}
      {incident?.sparing_advice && done && (
        <div style={{
          marginTop: 12,
          padding: '8px 10px',
          background: '#0d1a10',
          border: '1px solid #1e5030',
          borderRadius: 4,
          color: '#6ddc8b',
          fontSize: 11,
          lineHeight: 1.6,
        }}>
          <span style={{ color: '#00ffa3', fontWeight: 700 }}>SPARING NOTE  </span>
          {incident.sparing_advice}
        </div>
      )}
    </div>
  );
}
