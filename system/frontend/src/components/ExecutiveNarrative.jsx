import React from 'react';
import { motion } from 'framer-motion';
import { BrainCircuit, AlertTriangle, ShieldCheck, Activity, Target, Zap, TrendingUp } from 'lucide-react';

export default function ExecutiveNarrative({ narrative, metrics, forecast, submitOperatorAction, isReplaying }) {
  if (!narrative) return null;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-zinc-900 border border-purple-500/30 rounded-3xl p-6 shadow-xl relative overflow-hidden"
    >
      <div className="absolute -top-10 -right-10 w-48 h-48 bg-purple-500/10 rounded-full blur-3xl pointer-events-none" />
      
      <div className="flex justify-between items-start mb-6">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <BrainCircuit size={20} className="text-purple-400" />
          Coral Operational Intelligence Briefing
          <span className="ml-2 px-2 py-0.5 bg-zinc-800 text-zinc-400 text-[9px] rounded font-mono uppercase tracking-widest border border-zinc-700">Correlated via GitHub + Datadog</span>
        </h2>
        
        <motion.div 
          key={narrative.confidence}
          initial={{ scale: 1.2, opacity: 0.5 }}
          animate={{ scale: 1, opacity: 1 }}
          className="flex flex-col items-end"
        >
          <span className="text-[10px] text-zinc-500 uppercase font-mono tracking-widest mb-1">Coral Correlation Confidence</span>
          <span className={`text-lg font-bold font-mono px-2 py-0.5 rounded border ${narrative.confidence > 90 ? 'bg-purple-950/50 text-purple-400 border-purple-500/30' : 'bg-yellow-950/50 text-yellow-400 border-yellow-500/30'}`}>
            {narrative.confidence}%
          </span>
        </motion.div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-zinc-950/50 p-3 rounded-xl border border-zinc-800">
          <div className="flex items-center gap-2 text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-1">
            <Target size={14} className="text-red-400" />
            Deployment Risk
          </div>
          <div className="text-xl font-mono text-red-400">
            {metrics?.deploymentRisk || 0}% <span className="text-[10px] text-zinc-500 uppercase">Risk Level</span>
          </div>
        </div>
        <div className="bg-zinc-950/50 p-3 rounded-xl border border-zinc-800">
          <div className="flex items-center gap-2 text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-1">
            <Zap size={14} className="text-yellow-400" />
            Fragility Score
          </div>
          <div className="text-xl font-mono text-yellow-400">
            {metrics?.fragilityScore || 0} <span className="text-[10px] text-zinc-500 uppercase">Score</span>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        {/* Root Cause */}
        <div>
          <h4 className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-2">
            <AlertTriangle size={14} className="text-red-400" />
            Causality Reconstruction
          </h4>
          <p className="text-sm text-zinc-200 leading-relaxed border-l-2 border-red-500/50 pl-3">
            {narrative.rootCause}
          </p>
        </div>

        {/* Propagation Chain */}
        <div>
          <h4 className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-2">
            <Activity size={14} className="text-cyan-400" />
            Infrastructure Propagation
          </h4>
          <div className="text-sm text-cyan-300/80 font-mono bg-cyan-950/20 p-3 rounded-xl border border-cyan-500/20">
            {narrative.propagation}
          </div>
        </div>

        {/* Ranked Causes (NEW) */}
        {narrative.rankedCauses && (
          <div className="bg-red-950/20 border border-red-500/20 p-4 rounded-xl relative overflow-hidden">
            <h4 className="flex items-center gap-2 text-xs font-semibold text-red-400 uppercase tracking-widest mb-3">
              <Activity size={14} className="text-red-400" />
              Ranked Root Cause Attribution
            </h4>
            <div className="space-y-3">
              {Array.isArray(narrative?.rankedCauses) ? narrative.rankedCauses.map((cause, index) => (
                <div key={cause.service} className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs font-mono text-zinc-300">
                    <span className="flex items-center gap-2">
                      <span className="text-zinc-500">#{index + 1}</span>
                      {cause.service}
                    </span>
                    <span className={index === 0 ? 'text-red-400' : 'text-yellow-400'}>{cause.influence}% Influence</span>
                  </div>
                  <div className="h-1 bg-zinc-900 rounded-full overflow-hidden">
                    <motion.div 
                      className={`h-full ${index === 0 ? 'bg-red-500' : 'bg-yellow-500'}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${cause.influence}%` }}
                      transition={{ duration: 1 }}
                    />
                  </div>
                </div>
              )) : null}
            </div>
          </div>
        )}

        {/* Future Projections (NEW) */}
        {forecast && narrative.projection && (
          <div className="bg-purple-950/20 border border-purple-500/20 p-4 rounded-xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-16 h-16 bg-purple-500/10 blur-xl rounded-full" />
            <h4 className="flex items-center gap-2 text-xs font-semibold text-purple-400 uppercase tracking-widest mb-2">
              <TrendingUp size={14} className="animate-pulse" />
              Future Risk Projection
            </h4>
            <p className="text-sm text-zinc-200 leading-relaxed mb-3">
              {narrative.projection}
            </p>
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-500 uppercase">Escalation Momentum</span>
              <span className={`px-2 py-0.5 rounded ${forecast.escalationMomentum > 70 ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-purple-500/20 text-purple-400 border border-purple-500/30'}`}>
                {forecast.escalationMomentum}/100
              </span>
            </div>
          </div>
        )}

        {/* Remediation & Operator Control */}
        <div className={`pt-4 border-t border-zinc-800 ${narrative.recoveryState === 'ACTION_REQUIRED' && !isReplaying ? 'bg-zinc-950/50 -mx-6 px-6 pb-6 pt-6 border-b' : ''}`}>
          <div className="flex justify-between items-center mb-3">
            <h4 className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase tracking-widest">
              <ShieldCheck size={14} className={narrative.recoveryState === 'ACTION_REQUIRED' ? "text-yellow-500 animate-pulse" : "text-green-400"} />
              {narrative.recoveryState === 'ACTION_REQUIRED' && !isReplaying ? 'Decision Intelligence Required' : 'Remediation Recommendation'}
            </h4>
            {narrative.recoveryState && (
              <span className={`text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 rounded border ${
                narrative.recoveryState === 'ACTION_REQUIRED' ? 'bg-yellow-950/30 text-yellow-500 border-yellow-500/30 animate-pulse' :
                narrative.recoveryState === 'ACTION_EXECUTING' ? 'bg-cyan-950/30 text-cyan-400 border-cyan-500/30' :
                'bg-green-950/30 text-green-400 border-green-500/30'
              }`}>
                {narrative.recoveryState.replace('_', ' ')}
              </span>
            )}
          </div>
          
          <motion.p 
            key={narrative.remediation}
            initial={{ opacity: 0.5 }}
            animate={{ opacity: 1 }}
            className="text-sm text-white font-medium mb-4"
          >
            {narrative.remediation}
          </motion.p>

          {narrative.recoverySuccessProbability && (
            <div className="flex gap-4 mb-4">
              <div className="text-xs font-mono text-zinc-400">
                <span className="text-green-400">{narrative.expectedRecoveryTimeMinutes}m</span> Expected MTTR
              </div>
              <div className="text-xs font-mono text-zinc-400">
                <span className="text-green-400">${(narrative.estimatedRevenueSaved || 0).toLocaleString()}</span> {narrative.recoveryState === 'ACTION_REQUIRED' ? 'Projected Revenue Saved' : 'Revenue Preserved'}
              </div>
            </div>
          )}

          {narrative.recoveryState === 'ACTION_REQUIRED' && !isReplaying && (
            <div className="grid grid-cols-2 gap-2 mt-4">
              <button onClick={() => submitOperatorAction('Rollback Deployment')} className="bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 text-xs py-2 px-3 rounded-lg font-medium transition-colors text-left">
                Rollback Deployment
              </button>
              <button onClick={() => submitOperatorAction('Ignore Warning')} className="bg-transparent hover:bg-zinc-900 text-zinc-500 border border-dashed border-zinc-700 text-xs py-2 px-3 rounded-lg font-medium transition-colors text-left">
                Ignore Warning
              </button>
              <button onClick={() => submitOperatorAction('Enable Fallback')} className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 text-xs py-2 px-3 rounded-lg font-medium transition-colors text-left">
                Enable Fallback
              </button>
              <button onClick={() => submitOperatorAction('Restart Service')} className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 text-xs py-2 px-3 rounded-lg font-medium transition-colors text-left">
                Restart Service
              </button>
            </div>
          )}

          {narrative.recoveryState && narrative.recoveryState !== 'ACTION_REQUIRED' && (
            <div className="mt-4 p-3 bg-zinc-950/50 rounded-xl border border-zinc-800 flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full ${narrative.recoveryState === 'ACTION_EXECUTING' ? 'bg-cyan-500 animate-ping' : 'bg-green-500'}`} />
              <div className="text-xs font-mono text-zinc-300">
                {narrative.recoveryState === 'ACTION_EXECUTING' ? 'Executing: ' : 'Executed: '} 
                <span className="text-white">{narrative.executedAction || 'Operator Action'}</span>
              </div>
            </div>
          )}
        </div>

      </div>
    </motion.div>
  );
}
