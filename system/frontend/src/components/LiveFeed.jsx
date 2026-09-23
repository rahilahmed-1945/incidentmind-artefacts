import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, GitBranch, Activity, Box, AlertOctagon, Brain, Database } from 'lucide-react';

const sourceConfig = {
  GITHUB: { icon: GitBranch, color: 'text-zinc-200', bg: 'bg-zinc-800' },
  DATADOG: { icon: Activity, color: 'text-purple-400', bg: 'bg-purple-950' },
  KUBERNETES: { icon: Box, color: 'text-blue-400', bg: 'bg-blue-950' },
  PAGERDUTY: { icon: AlertOctagon, color: 'text-green-400', bg: 'bg-green-950' },
  CORAL: { icon: Brain, color: 'text-cyan-400', bg: 'bg-cyan-950' },
  SENTRY: { icon: Database, color: 'text-red-400', bg: 'bg-red-950' },
  SLACK: { icon: Terminal, color: 'text-blue-400', bg: 'bg-blue-950' },
  DEFAULT: { icon: Terminal, color: 'text-zinc-400', bg: 'bg-zinc-900' }
};

export default function LiveFeed({ events = [] }) {
  
  const getLevelStyles = (level) => {
    switch(level) {
      case 'CRITICAL': return 'border-red-500/30';
      case 'WARNING': return 'border-yellow-500/30';
      case 'AI INFERENCE': return 'border-cyan-500/30';
      case 'INFO': default: return 'border-zinc-500/30';
    }
  };

  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-3xl p-5 shadow-xl h-full flex flex-col relative overflow-hidden">
      <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />
      
      {/* Active Connectors Row */}
      <div className="flex items-center justify-between mb-4 border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-2">
          <Terminal size={16} className="text-cyan-500" />
          <h3 className="text-cyan-500 font-mono text-[10px] tracking-widest uppercase">Multi-Source Fabric</h3>
        </div>
        <div className="flex gap-1">
          {Object.entries(sourceConfig).filter(([k]) => k !== 'DEFAULT').map(([key, config]) => {
            const Icon = config.icon;
            return (
              <div key={key} className={`${config.bg} ${config.color} p-1 rounded-md border border-zinc-700 relative group cursor-help`} title={`${key} Connected`}>
                <Icon size={12} />
                <div className="absolute -top-1 -right-1 w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              </div>
            )
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col-reverse gap-3 pr-2">
        <AnimatePresence initial={false}>
          {Array.isArray(events) ? events.map((event) => {
            const source = event.source || 'DEFAULT';
            const config = sourceConfig[source] || sourceConfig.DEFAULT;
            const Icon = config.icon;
            
            return (
              <motion.div
                key={event.id}
                initial={{ opacity: 0, x: -20, height: 0 }}
                animate={{ opacity: 1, x: 0, height: 'auto' }}
                exit={{ opacity: 0, scale: 0.9, height: 0 }}
                transition={{ type: "spring", bounce: 0, duration: 0.5 }}
                className={`border-l-2 pl-3 py-2 bg-zinc-900/50 ${getLevelStyles(event.level)} flex flex-col gap-1.5 rounded-r-xl`}
              >
                <div className="flex justify-between items-center opacity-80">
                  <div className="flex items-center gap-2">
                    <span className={`flex items-center gap-1 ${config.bg} ${config.color} px-1.5 py-0.5 rounded text-[8px] font-mono tracking-widest uppercase border border-zinc-700`}>
                      <Icon size={10} />
                      {source}
                    </span>
                    <span className="font-mono text-[9px] uppercase tracking-wider text-zinc-400">{event.level}</span>
                  </div>
                  <span className="font-mono text-[9px] text-zinc-500">
                    {new Date(event.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit' })}
                  </span>
                </div>
                <p className={`font-mono text-xs leading-relaxed ${event.level === 'CRITICAL' ? 'text-red-300' : event.level === 'WARNING' ? 'text-yellow-300' : event.level === 'AI INFERENCE' ? 'text-cyan-300' : 'text-zinc-300'}`}>
                  {event.message}
                </p>
              </motion.div>
            );
          }) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}
