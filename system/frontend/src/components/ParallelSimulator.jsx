import React from 'react';
import { motion } from 'framer-motion';
import { GitBranch, AlertTriangle, PlayCircle, Trophy, TrendingDown, Clock, Users, ShieldCheck } from 'lucide-react';

export default function ParallelSimulator({ simulatorState, setSimulatorState, simulator, recoveryState }) {
  const isHealed = recoveryState && recoveryState !== 'ACTION_REQUIRED';

  if (!simulator) {
    return (
      <motion.div 
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 shadow-xl flex flex-col gap-6"
      >
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2 opacity-50">
            <GitBranch size={20} className="text-purple-400" />
            Parallel Universe Simulator
          </h2>
          <p className="text-zinc-500 text-sm mt-2 font-mono flex items-center gap-2">
            <PlayCircle size={14} className="animate-spin" />
            Awaiting Decision Intelligence Data...
          </p>
        </div>
      </motion.div>
    );
  }

  const { currentReality, alternativeScenarios } = simulator;

  return (
    <motion.div 
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="bg-zinc-900 border border-purple-500/30 rounded-3xl p-6 shadow-[0_0_40px_rgba(168,85,247,0.15)] flex flex-col gap-6 relative overflow-hidden"
    >
      <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-purple-500/20 blur-3xl rounded-full" />
      
      <div>
        <h2 className="text-xl font-semibold text-white flex items-center gap-2 relative z-10">
          <GitBranch size={20} className="text-purple-400 drop-shadow-[0_0_8px_rgba(168,85,247,0.8)]" />
          Decision Intelligence Simulator
        </h2>
        <p className="text-zinc-400 text-sm mt-2 relative z-10">
          Evaluating outcome vectors against the current operational trajectory.
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 relative z-10">
        
        {/* Current Reality Pane */}
        <div className="lg:w-1/3 bg-zinc-950/80 border border-red-900/50 rounded-2xl p-4 flex flex-col gap-3">
          <h3 className="text-red-400 font-semibold border-b border-red-900/50 pb-2">Reality (SEV-1)</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="text-zinc-500">Revenue Lost</div>
            <div className="text-red-300 font-mono text-right">{currentReality.formatted.revenueLoss}</div>
            
            <div className="text-zinc-500">MTTR</div>
            <div className="text-red-300 font-mono text-right">{currentReality.downtimeMinutes}m</div>
            
            <div className="text-zinc-500">Users Impacted</div>
            <div className="text-red-300 font-mono text-right">{currentReality.usersImpacted.toLocaleString()}</div>
            
            <div className="text-zinc-500">Peak Risk</div>
            <div className="text-red-300 font-mono text-right">{currentReality.peakRisk}%</div>
          </div>
        </div>

        {/* Alternatives Ranked Table */}
        <div className="lg:w-2/3 flex flex-col gap-4">
          <h3 className="text-zinc-300 font-medium text-sm">Ranked Intervention Paths</h3>
          
          <div className="flex flex-col gap-3 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
            {Array.isArray(alternativeScenarios) ? alternativeScenarios.map((scen, idx) => (
              <div key={scen.scenarioName} className="bg-zinc-950/50 border border-purple-500/20 rounded-xl p-4 hover:bg-zinc-900 transition-colors group">
                
                {/* Header */}
                <div className="flex items-center justify-between mb-3 border-b border-zinc-800 pb-3">
                  <div className="flex items-center gap-3">
                    <div className="bg-purple-900/30 text-purple-400 font-bold w-6 h-6 rounded-full flex items-center justify-center text-xs border border-purple-500/30">
                      {idx + 1}
                    </div>
                    <span className="text-zinc-200 font-medium">{scen.scenarioName}</span>
                    {scen.recommended && (
                      <span className="bg-yellow-500/10 text-yellow-500 border border-yellow-500/30 text-[10px] uppercase font-bold px-2 py-0.5 rounded-full flex items-center gap-1 ml-2">
                        ⭐ AI Recommended
                      </span>
                    )}
                  </div>
                  <div className="text-xs bg-zinc-800 text-zinc-400 px-2 py-1 rounded font-mono border border-zinc-700 flex items-center gap-1">
                    <Trophy size={12} className="text-yellow-500" /> Score: {scen.scenarioScore}
                  </div>
                </div>

                {/* Metrics Row */}
                <div className="grid grid-cols-4 gap-2 mb-4">
                  <div className="bg-black/20 p-2 rounded flex flex-col items-center justify-center text-center">
                    <TrendingDown size={14} className="text-green-400 mb-1" />
                    <span className="text-green-300 font-mono text-xs">{scen.formatted.revenueSaved}</span>
                    <span className="text-[9px] text-zinc-500 uppercase mt-1">Saved</span>
                  </div>
                  <div className="bg-black/20 p-2 rounded flex flex-col items-center justify-center text-center">
                    <Clock size={14} className="text-cyan-400 mb-1" />
                    <span className="text-cyan-300 font-mono text-xs">-{scen.mttrReduction}m</span>
                    <span className="text-[9px] text-zinc-500 uppercase mt-1">MTTR</span>
                  </div>
                  <div className="bg-black/20 p-2 rounded flex flex-col items-center justify-center text-center">
                    <Users size={14} className="text-blue-400 mb-1" />
                    <span className="text-blue-300 font-mono text-xs">{(scen.usersImpacted).toLocaleString()}</span>
                    <span className="text-[9px] text-zinc-500 uppercase mt-1">Impacted</span>
                  </div>
                  <div className="bg-black/20 p-2 rounded flex flex-col items-center justify-center text-center">
                    <ShieldCheck size={14} className="text-purple-400 mb-1" />
                    <span className="text-purple-300 font-mono text-xs">{scen.peakRisk}%</span>
                    <span className="text-[9px] text-zinc-500 uppercase mt-1">Peak Risk</span>
                  </div>
                </div>

                {/* Explanations */}
                <div className="bg-zinc-900/50 rounded p-3 text-xs text-zinc-400 space-y-1">
                  {Array.isArray(scen.explanations) ? scen.explanations.map((exp, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <div className="text-purple-500 mt-0.5">•</div>
                      <div>{exp}</div>
                    </div>
                  )) : null}
                </div>

              </div>
            )) : null}
          </div>
        </div>

      </div>
    </motion.div>
  );
}
