import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  Activity,
  Loader2
} from "lucide-react";
import { io } from "socket.io-client";
import axios from "axios";

import DependencyGraph from "./components/DependencyGraph";
import ReplayEngine from "./components/ReplayEngine";
import ParallelSimulator from "./components/ParallelSimulator";
import AskIncidentMind from "./components/AskIncidentMind";
import ExecutiveNarrative from "./components/ExecutiveNarrative";
import LiveFeed from "./components/LiveFeed";
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000";

export default function App() {

  const [simulatorState, setSimulatorState] =
    useState("incident");

  const [isChatOpen, setIsChatOpen] =
    useState(false);

  // Base Initial State required by downstream components
  const [liveState, setLiveState] = useState({
    metrics: { deploymentRisk: null, fragilityScore: null, businessSeverity: null },
    nodes: [
      { id: 'gateway-service', type: 'custom', position: { x: 400, y: 50 }, data: { label: 'gateway service', state: 'healthy', subLabel: 'Healthy', iconName: 'CloudRain', influenceScore: 10 } },
      { id: 'auth-service', type: 'custom', position: { x: 200, y: 200 }, data: { label: 'auth service', state: 'healthy', subLabel: 'Healthy', iconName: 'ShieldAlert', influenceScore: 20 } },
      { id: 'user-profile-service', type: 'custom', position: { x: 100, y: 350 }, data: { label: 'user profile service', state: 'healthy', subLabel: 'Healthy', iconName: 'Cpu', influenceScore: 5 } },
      { id: 'checkout-service', type: 'custom', position: { x: 600, y: 200 }, data: { label: 'checkout service', state: 'healthy', subLabel: 'Healthy', iconName: 'Cpu', influenceScore: 30 } },
      { id: 'payments-service', type: 'custom', position: { x: 1050, y: 350 }, data: { label: 'payments service', state: 'healthy', subLabel: 'Healthy', iconName: 'Cpu', influenceScore: 25 } },
      { id: 'inventory-service', type: 'custom', position: { x: 750, y: 350 }, data: { label: 'inventory service', state: 'healthy', subLabel: 'Healthy', iconName: 'Database', influenceScore: 15 } },
      { id: 'redis-cache', type: 'custom', position: { x: 450, y: 350 }, data: { label: 'redis cache', state: 'healthy', subLabel: 'Healthy', iconName: 'Database', influenceScore: 40 } },
      { id: 'primary-db', type: 'custom', position: { x: 450, y: 500 }, data: { label: 'primary db', state: 'healthy', subLabel: 'Healthy', iconName: 'Database', influenceScore: 50 } }
    ],
    edges: [
      { id: 'e-gate-auth', source: 'gateway-service', target: 'auth-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-gate-check', source: 'gateway-service', target: 'checkout-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-auth-user', source: 'auth-service', target: 'user-profile-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-check-pay', source: 'checkout-service', target: 'payments-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-check-inv', source: 'checkout-service', target: 'inventory-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-check-redis', source: 'checkout-service', target: 'redis-cache', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-redis-db', source: 'redis-cache', target: 'primary-db', animated: true, style: { stroke: '#06b6d4' } }
    ],
    narrative: { rootCause: null, propagation: null, remediation: null, confidence: null, blastRadius: null, projection: null, rankedCauses: null },
    events: [],
    forecast: { predictions: [] },
    simulator: null
  });

  const [isConnecting, setIsConnecting] = useState(true);

  // History State
  const [historicalSnapshots, setHistoricalSnapshots] = useState([]);
  const [isReplaying, setIsReplaying] = useState(false);
  const [replayCursor, setReplayCursor] = useState(0);

  useEffect(() => {
    const intv = setInterval(() => {
      console.log(`[INSTRUMENT] scrollY: ${window.scrollY}, body.scrollHeight: ${document.body.scrollHeight}, docElement.scrollHeight: ${document.documentElement.scrollHeight}`);
    }, 1000);
    return () => clearInterval(intv);
  }, []);

  // Fetch History when Replay starts
  useEffect(() => {
    if (isReplaying) {
      axios.get(API_URL + "/history").then(res => {
        setHistoricalSnapshots(res.data);
      }).catch(err => console.error("Failed to fetch history", err));
    }
  }, [isReplaying]);

  // Connect to WebSocket for live telemetry
  const socketRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    
    // Connect to local backend
    const socket = io(API_URL);
    socketRef.current = socket;

    socket.on("connect", () => {
      console.log("Connected to Local Incident Engine V3 Stream");
    });

    socket.on("incident_event", (evt) => {
      if (!isMounted) return;

      if (isConnecting) {
        setIsConnecting(false);
      }

      setLiveState(prev => {
        let next = { ...prev };
        console.log(`[INSTRUMENT] activeState replacing via websocket. Event: ${evt.eventType}`);

        // 1. RAW TELEMETRY
        if (evt.eventType === "RAW_TELEMETRY_EVENT") {
          next.events = [{
            id: evt.eventId,
            source: 'CORAL',
            timestamp: evt.displayTimestamp,
            level: 'INFO',
            message: evt.payload.message
          }, ...next.events].slice(0, 50);
          console.log(`[INSTRUMENT] events.length: ${next.events.length}`);
        }

        // 2. SERVICE STATE CHANGE
        else if (evt.eventType === "SERVICE_STATE_CHANGE") {
          const isCritical = evt.payload.newState === 'CRITICAL';
          next.events = [{
            id: evt.eventId,
            source: 'DATADOG',
            timestamp: evt.displayTimestamp,
            level: isCritical ? 'CRITICAL' : 'WARNING',
            message: `[${evt.payload.service}] State changed: ${evt.payload.oldState} -> ${evt.payload.newState}`
          }, ...next.events].slice(0, 50);

          // Incrementally update nodes
          next.nodes = next.nodes.map(n => {
            if (n.id === evt.payload.service) {
              return { 
                ...n, 
                data: { 
                  ...n.data, 
                  state: evt.payload.newState.toLowerCase(),
                  subLabel: evt.payload.newState === 'CRITICAL' ? 'Offline' : evt.payload.newState === 'DEGRADED' || evt.payload.newState === 'WARNING' ? 'Degraded' : 'Healthy'
                } 
              };
            }
            return n;
          });
          
          if (evt.payload.newState === 'HEALTHY' || evt.payload.newState === 'RECOVERED') {
            next.edges = next.edges.map(e => {
              if (e.source === evt.payload.service || e.target === evt.payload.service) {
                return { ...e, style: { stroke: '#06b6d4' } };
              }
              return e;
            });
          }
          
          // Calculate dynamic fragilityScore based on active graph state severity
          const nodeFragilityWeights = { 'healthy': 0, 'warning': 10, 'critical': 25, 'recovering': 5, 'recovered': 0 };
          const dynamicFragility = next.nodes.reduce((acc, node) => acc + (nodeFragilityWeights[node.data.state] || 0), 0);
          // Normalize to roughly a 0-100 scale (8 nodes max 200, so divide by 2)
          const normalizedFragility = Math.min(100, Math.floor(dynamicFragility / 2));
          next.metrics = { ...next.metrics, fragilityScore: normalizedFragility };
        }

        // 3. RCA AVAILABLE
        else if (evt.eventType === "RCA_AVAILABLE") {
          if (!evt.payload || !evt.payload.rootCause) {
            console.warn("RCA_AVAILABLE reducer received null or invalid payload. Skipping narrative updates.");
          } else {
            next.narrative = { 
              ...next.narrative, 
              rootCause: evt.payload.rootCause,
              confidence: evt.payload.confidence 
            };
            next.events = [{
              id: evt.eventId,
              source: 'CORAL',
              timestamp: evt.displayTimestamp,
              level: 'AI INFERENCE',
              message: `Identified Root Cause: ${evt.payload.rootCause}`
            }, ...next.events].slice(0, 50);
          }
        }

        else if (evt.eventType === "BLAST_RADIUS_AVAILABLE") {
          next.narrative = { ...next.narrative, blastRadius: (evt.payload.directlyImpacted?.length ?? 0) + (evt.payload.indirectlyImpacted?.length ?? 0), propagation: evt.payload.traversalPaths && evt.payload.traversalPaths.length > 0 ? evt.payload.traversalPaths[0].path : "Unknown" };
          
          // Color the edges red for impacted paths
          next.edges = next.edges.map(e => {
            if (evt.payload.directlyImpacted?.includes(e.target) || evt.payload.indirectlyImpacted?.includes(e.target)) {
              return { ...e, style: { stroke: '#ef4444' } };
            }
            return e;
          });
        }

        // 5. BUSINESS IMPACT AVAILABLE
        else if (evt.eventType === "BUSINESS_IMPACT_AVAILABLE") {
          next.metrics = {
            ...next.metrics,
            deploymentRisk: evt.payload.revenueRiskPerHour > 50000 ? 95 : Math.floor(evt.payload.revenueRiskPerHour / 1000),
            businessSeverity: evt.payload.businessSeverity,
            revenueRiskPerHour: evt.payload.revenueRiskPerHour,
            affectedUsers: evt.payload.affectedUsers
          };
          // Map metrics impact to narrative rankedCauses safely
          next.narrative = {
            ...next.narrative,
            rankedCauses: []
          };
        }

        // 6. PREDICTION AVAILABLE
        else if (evt.eventType === "PREDICTION_AVAILABLE") {
          next.forecast = {
            ...next.forecast,
            predictions: evt.payload.predictions,
            escalationMomentum: evt.payload.escalationMomentum
          };
          console.log(`[INSTRUMENT] predictions.length: ${evt.payload.predictions?.length || 0}`);
          
          // Add projection to narrative
          if (evt.payload.predictions?.length > 0) {
            next.narrative = {
              ...next.narrative,
              projection: `AI model predicts ${evt.payload.predictions[0].service} will experience failure within ${evt.payload.predictions[0].estimatedTimeToImpactMinutes} minutes.`
            };
          }
        }

        // 7. RECOVERY AVAILABLE
        else if (evt.eventType === "RECOVERY_AVAILABLE") {
          next.narrative = { 
            ...next.narrative, 
            remediation: evt.payload.recommendedAction,
            recoverySuccessProbability: evt.payload.recoverySuccessProbability,
            expectedRecoveryTimeMinutes: evt.payload.expectedRecoveryTimeMinutes,
            estimatedRevenueSaved: evt.payload.estimatedRevenueSaved
          };
        }

        // 8. PARALLEL UNIVERSE AVAILABLE
        else if (evt.eventType === "PARALLEL_UNIVERSE_AVAILABLE") {
          next.simulator = evt.payload;
        }

        // 9. ACTION LIFECYCLE
        else if (evt.eventType === "ACTION_REQUIRED") {
          next.narrative = { 
            ...next.narrative, 
            recoveryState: 'ACTION_REQUIRED' 
          };
        }
        else if (evt.eventType === "ACTION_APPROVED" || evt.eventType === "ACTION_EXECUTING") {
          next.narrative = { 
            ...next.narrative, 
            recoveryState: evt.eventType,
            executedAction: evt.payload.action 
          };
        }
        else if (evt.eventType === "INCIDENT_RESOLVED") {
          next.narrative = { 
            ...next.narrative, 
            recoveryState: 'RESOLVED' 
          };
          next.edges = next.edges.map(e => ({ ...e, style: { stroke: '#06b6d4' } }));
        }

        return next;
      });
    });

    return () => {
      isMounted = false;
      socket.disconnect();
    };
  }, [simulatorState, isConnecting]);

  // Cinematic Boot Sequence
  const [bootPhase, setBootPhase] = useState(0);
  
  useEffect(() => {
    if (isConnecting) {
      const p1 = setTimeout(() => setBootPhase(1), 800);
      const p2 = setTimeout(() => setBootPhase(2), 1600);
      const p3 = setTimeout(() => setBootPhase(3), 2600);
      const p4 = setTimeout(() => setIsConnecting(false), 3500);
      return () => { clearTimeout(p1); clearTimeout(p2); clearTimeout(p3); clearTimeout(p4); };
    }
  }, [isConnecting]);

  if (isConnecting) {
    return (
      <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center font-sans relative overflow-hidden bg-ambient-grid">
        <div className="radar-sweep-bg" />
        <div className="z-10 bg-zinc-950/80 p-8 rounded-2xl border border-zinc-800 shadow-2xl backdrop-blur-md min-w-[400px]">
          <div className="flex items-center gap-3 mb-6">
            <Loader2 className="animate-spin text-cyan-500" size={24} />
            <span className="text-cyan-400 font-mono tracking-widest uppercase text-sm">IncidentMind Core Boot</span>
          </div>
          <div className="space-y-3 font-mono text-xs tracking-wider">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-zinc-500">
              [SYSTEM] Initializing IncidentMind Core...
            </motion.div>
            {bootPhase >= 1 && (
              <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} className="text-zinc-400">
                [NETWORK] Establishing Local WebSocket... <span className="text-green-400">OK</span>
              </motion.div>
            )}
            {bootPhase >= 2 && (
              <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} className="text-cyan-400">
                [FABRIC] Syncing Incident Engine V3... <span className="text-green-400">OK</span>
              </motion.div>
            )}
            {bootPhase >= 3 && (
              <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="text-green-400 mt-4 pt-4 border-t border-zinc-800">
                [STATUS] Operational Intelligence Online
              </motion.div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Core Data Flow logic: Use history if replaying, else use live data
  const activeState = isReplaying && historicalSnapshots.length > 0 
    ? historicalSnapshots[replayCursor] 
    : liveState;

  const { metrics, nodes, edges, narrative, events, forecast, simulator } = activeState || {};

  return (

    <div className="
      min-h-screen
      bg-[#0a0a0a]
      text-zinc-100
      p-6
      font-sans
      selection:bg-cyan-500/30
      relative
    ">
      
      {/* AMBIENT INTELLIGENCE LAYER */}
      <div className="absolute inset-0 bg-ambient-grid opacity-50 z-0 pointer-events-none" />
      <div className="absolute inset-0 radar-sweep-bg opacity-30 z-0 pointer-events-none" />

      <div className="relative z-10 h-full flex flex-col">
        {/* HEADER */}

      <nav className="
        flex
        justify-between
        items-center
        mb-6
      ">

        <div>

          <motion.h1
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="
              text-3xl
              font-bold
              tracking-tight
              text-white
              flex
              items-center
              gap-2
            "
          >
            IncidentMind

            <span className={`
              ${isReplaying ? 'bg-purple-500' : 'bg-red-500'}
              text-white
              text-[10px]
              uppercase
              px-2
              py-0.5
              rounded-sm
              font-mono
              tracking-wider
              font-bold
            `}>
              {isReplaying ? 'Historical Replay' : 'Live Stream Active'}
            </span>

          </motion.h1>

          <div className="flex items-center gap-3 mt-1">
            <p className="
              text-zinc-500
              text-xs
              font-mono
              tracking-widest
            ">
              AI ORGANIZATIONAL CAUSALITY ENGINE
            </p>
            <span className="text-zinc-700">|</span>
            <span className="text-[9px] font-mono tracking-widest text-cyan-500/70 bg-cyan-950/30 px-2 py-0.5 rounded border border-cyan-900/50">ENV: PRD-US-EAST</span>
            <span className="text-[9px] font-mono tracking-widest text-green-500/70 bg-green-950/30 px-2 py-0.5 rounded border border-green-900/50">CORAL: ONLINE</span>
          </div>

        </div>

        <div className="flex gap-4">

          <button
            onClick={() => setIsChatOpen(true)}
            className="
              flex
              items-center
              gap-2
              bg-zinc-900
              border
              border-zinc-700
              hover:border-cyan-500
              hover:text-cyan-400
              px-4
              py-2
              rounded-xl
              text-sm
              font-medium
              transition-colors
            "
          >
            <MessageSquare size={16} />
            Coral Investigative Reasoning Console
          </button>

        </div>
      </nav>

      {/* MAIN LAYOUT */}

      <div className="
        grid
        grid-cols-1
        lg:grid-cols-12
        gap-8
        min-h-[calc(100vh-120px)]
      ">

        {/* LEFT PANEL */}

        <motion.div 
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
          className="
          col-span-1
          lg:col-span-8
          flex
          flex-col
          gap-8
        ">
          
          <div className="flex gap-6 flex-1 min-h-[500px]">
            {/* DEPENDENCY GRAPH */}
            <div className="
              flex-1
              rounded-3xl
              overflow-hidden
            ">
              <DependencyGraph
                simulatorState={simulatorState}
                nodes={nodes}
                edges={edges}
              />
            </div>
            
            {/* LIVE FEED */}
            <div className="w-[280px] min-h-0">
              <LiveFeed events={events} />
            </div>
          </div>

          {/* REPLAY ENGINE */}

          <div className="
            h-[160px]
            shrink-0
            rounded-3xl
            overflow-hidden
          ">
            <ReplayEngine
              isReplaying={isReplaying}
              setIsReplaying={setIsReplaying}
              replayCursor={replayCursor}
              setReplayCursor={setReplayCursor}
              maxSnapshots={historicalSnapshots.length}
            />
          </div>

        </motion.div>

        {/* RIGHT SIDEBAR */}

        <motion.div 
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.4 }}
          className="
          col-span-1 
          lg:col-span-4 
          flex 
          flex-col 
          gap-8
        ">

          {/* EXECUTIVE NARRATIVE */}
          <ExecutiveNarrative 
            narrative={narrative} 
            metrics={metrics} 
            forecast={forecast} 
            submitOperatorAction={(action) => socketRef.current?.emit("operator_action", { action })}
            isReplaying={isReplaying}
          />

          {/* PREDICTIVE RISK */}

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="
              bg-zinc-900
              border
              border-zinc-800
              rounded-3xl
              p-6
              shadow-xl
            "
          >

            <h3 className="
              text-sm
              font-semibold
              text-zinc-300
              uppercase
              tracking-widest
              mb-4
              flex
              items-center
              gap-2
            ">
              <Activity
                size={16}
                className="text-cyan-400"
              />

              Coral Predictive Intelligence Layer
            </h3>

            <div className="space-y-6 h-[380px] overflow-y-auto pr-2 custom-scrollbar">

              {forecast?.predictions && forecast.predictions.length > 0 ? (
                forecast.predictions.map((pred) => (
                  <div key={pred.service}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-zinc-400 capitalize">{pred.service.replace('-', ' ')}</span>
                      <span className="text-cyan-400 font-mono">
                        <motion.span initial={{ opacity: 0.5 }} animate={{ opacity: 1 }}>
                          {pred.riskProbability}% Risk
                        </motion.span>
                      </span>
                    </div>

                    <div className="h-1.5 bg-zinc-950 rounded-full overflow-hidden border border-zinc-800 mb-2">
                      <motion.div
                        className={`h-full ${pred.riskProbability > 70 ? 'bg-cyan-500' : 'bg-yellow-500'}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${pred.riskProbability}%` }}
                        transition={{ type: "spring", bounce: 0, duration: 1 }}
                      />
                    </div>
                    
                    <motion.div 
                      className={`text-[10px] font-mono uppercase tracking-widest ${pred.riskProbability > 70 ? 'text-cyan-300 animate-pulse drop-shadow-[0_0_5px_rgba(34,211,238,0.8)]' : 'text-zinc-500'}`}
                    >
                      {pred.reason} (ETA: {pred.estimatedTimeToImpactMinutes}m)
                    </motion.div>
                  </div>
                ))
              ) : (
                <div className="text-zinc-500 text-sm font-mono flex items-center justify-center h-20 border border-dashed border-zinc-800 rounded-xl">
                  Awaiting Telemetry...
                </div>
              )}
            </div>
          </motion.div>

          {/* PARALLEL SIMULATOR */}

          <ParallelSimulator
            simulatorState={simulatorState}
            setSimulatorState={setSimulatorState}
            simulator={simulator}
            recoveryState={narrative?.recoveryState}
          />

        </motion.div>
      </div>

      {/* CHAT OVERLAY */}

      <AskIncidentMind
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
      />
      </div>
    </div>
  );
}