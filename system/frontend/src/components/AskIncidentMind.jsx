import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, X, Loader2, Database, BrainCircuit, Activity } from 'lucide-react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000";

const TypewriterText = ({ text }) => {
  const [displayedText, setDisplayedText] = useState('');

  useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      setDisplayedText(text.slice(0, i));
      i++;
      if (i > text.length) clearInterval(timer);
    }, 15);
    return () => clearInterval(timer);
  }, [text]);

  return <span>{displayedText}</span>;
};

export default function AskIncidentMind({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([
    { role: 'system', content: 'IncidentMind Autonomous Reasoning Engine initialized.\nConnected to Coral Intelligence.' }
  ]);
  const [loading, setLoading] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState(0);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    const newMsgs = [...messages, { role: 'user', content: query }];
    setMessages(newMsgs);
    setQuery('');
    setLoading(true);
    setLoadingPhase(1);

    try {
      setTimeout(() => setLoadingPhase(2), 500);
      setTimeout(() => setLoadingPhase(3), 1000);
      setTimeout(() => setLoadingPhase(4), 1500);
      setTimeout(() => setLoadingPhase(5), 2000);
      setTimeout(() => setLoadingPhase(6), 2500);
      setTimeout(() => setLoadingPhase(7), 3000);
      
      // Delay actual response to allow animation to complete
      setTimeout(async () => {
        try {
          const response = await axios.post(API_URL + "/analyze", { query });
          const responseMsg = {
            role: 'assistant',
            evidence: response.data.evidence,
            analysis: response.data.analysis
          };
          setMessages([...newMsgs, responseMsg]);
        } catch (err) {
          setMessages([...newMsgs, { role: 'assistant', analysis: 'Failed to connect to organizational reasoning layer.' }]);
        }
        setLoading(false);
        setLoadingPhase(0);
      }, 4000);

    } catch (err) {
      setMessages([...newMsgs, { role: 'assistant', analysis: 'Failed to connect to organizational reasoning layer.' }]);
      setLoading(false);
      setLoadingPhase(0);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
            onClick={onClose}
          />
          <motion.div 
            initial={{ opacity: 0, y: 50, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ type: 'spring', damping: 20, stiffness: 100 }}
            className="fixed bottom-8 right-8 w-[600px] h-[700px] bg-zinc-950/95 backdrop-blur-xl border border-zinc-800 rounded-3xl z-50 flex flex-col shadow-[0_0_50px_rgba(0,0,0,0.8)] overflow-hidden"
          >
            <div className="p-4 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/50">
              <div className="flex items-center gap-3">
                <Terminal size={18} className="text-cyan-400" />
                <h3 className="font-mono text-cyan-400 text-sm font-semibold tracking-wide flex items-center gap-2">
                  Retrieval-Augmented Operations
                  <span className="flex items-center gap-1 text-[8px] bg-cyan-500/20 px-1.5 py-0.5 rounded text-cyan-300">
                    <Activity size={10} className="animate-pulse" /> ONLINE
                  </span>
                </h3>
              </div>
              <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6 custom-scrollbar">
              {messages.map((msg, i) => (
                <motion.div 
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  key={i} 
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[95%] rounded-2xl px-5 py-4 text-sm leading-relaxed ${
                    msg.role === 'user' 
                      ? 'bg-cyan-500/10 text-cyan-100 border border-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.1)]' 
                      : msg.role === 'system'
                        ? 'bg-zinc-900 text-zinc-400 font-mono text-xs border border-zinc-800'
                        : 'bg-zinc-900/50 text-zinc-300 border border-zinc-800 w-full backdrop-blur-md shadow-xl'
                  }`}>
                    {msg.role === 'assistant' ? (
                      <div className="flex flex-col gap-4">
                        {msg.evidence && msg.evidence.length > 0 && (
                          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="bg-black/80 border border-zinc-800 rounded-lg p-3 shadow-inner">
                            <div className="flex items-center gap-2 text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-2">
                              <Database size={12} className="text-yellow-500 animate-pulse" />
                              Retrieved Operational Evidence ({msg.evidence.length} items)
                            </div>
                            <div className="flex flex-col gap-2 max-h-[150px] overflow-y-auto custom-scrollbar">
                              {msg.evidence.map((ev, eIdx) => (
                                <div key={eIdx} className="text-[10px] text-zinc-400 font-mono border-l-2 border-zinc-700 pl-2">
                                  <span className="text-cyan-500">[{ev.type.toUpperCase()}]</span> {ev.content}
                                </div>
                              ))}
                            </div>
                          </motion.div>
                        )}
                        <div>
                          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }} className="flex items-center gap-2 text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-2">
                            <BrainCircuit size={12} className="text-purple-500" />
                            Grounded Executive Response
                          </motion.div>
                          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1 }} className="whitespace-pre-wrap font-sans text-sm text-zinc-200">
                            <TypewriterText text={msg.analysis} />
                          </motion.div>
                        </div>
                      </div>
                    ) : (
                      <pre className="whitespace-pre-wrap font-sans"><TypewriterText text={msg.content} /></pre>
                    )}
                  </div>
                </motion.div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-zinc-900 border border-zinc-800 rounded-2xl px-5 py-3 text-zinc-400 flex flex-col gap-2">
                    <div className="flex items-center gap-3">
                      <Loader2 size={16} className="animate-spin text-purple-500" />
                      <span className="font-mono text-xs text-purple-400/70 animate-pulse">
                        {loadingPhase === 1 ? '[RAG] Embedding operational query...' : 
                         loadingPhase === 2 ? '[RAG] Retrieving semantic deployment logs...' : 
                         loadingPhase === 3 ? '[RAG] Fetching Slack anomalies...' : 
                         loadingPhase === 4 ? '[CONTEXT] Synchronizing Prediction Engine state...' : 
                         loadingPhase === 5 ? '[CONTEXT] Aligning Parallel Universe branches...' : 
                         loadingPhase === 6 ? '[AI] Injecting cross-engine evidence...' : 
                         '[AI] Generating grounded reasoning...'}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <form onSubmit={handleSubmit} className="p-4 border-t border-zinc-800 bg-zinc-900/80 backdrop-blur-md">
              <div className="relative">
                <input 
                  type="text" 
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="e.g., Which engineer touched the failing systems?"
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-all shadow-inner"
                />
              </div>
            </form>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
