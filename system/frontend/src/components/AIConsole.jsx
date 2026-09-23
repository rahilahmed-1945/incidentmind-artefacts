import { motion } from "framer-motion";

function AIConsole() {

  const logs = [
    "Correlating deploy timelines...",
    "Matching Slack escalation patterns...",
    "Analyzing retry propagation...",
    "Identifying suspicious services...",
    "Mapping dependency graph...",
    "Root cause confidence: 92%"
  ];

  return (

    <motion.div
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.7 }}
      className="mt-8 bg-zinc-900 rounded-3xl p-6 border border-cyan-500/20 shadow-2xl"
    >

      <div className="flex items-center justify-between mb-6">

        <h2 className="text-2xl font-bold text-cyan-400">
          AI Reasoning Console
        </h2>

        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
          <div className="w-3 h-3 rounded-full bg-green-500"></div>
        </div>

      </div>

      <div className="space-y-4">

        {logs.map((log, index) => (

          <motion.div
            key={index}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.3 }}
            className="bg-black/40 border border-zinc-800 rounded-xl px-4 py-3"
          >

            <p className="text-green-400 font-mono text-sm">
              {">"} {log}
            </p>

          </motion.div>

        ))}

      </div>

      <div className="mt-6 bg-black/50 border border-red-500/20 rounded-2xl p-4">

        <p className="text-red-400 font-semibold text-lg">
          ⚠ AI Incident Conclusion
        </p>

        <p className="text-gray-300 mt-2 leading-7">
          Deploy #883 introduced instability in the authentication
          pipeline causing retry amplification and cascading latency
          failures across checkout infrastructure.
        </p>

      </div>

    </motion.div>

  );
}

export default AIConsole;