import React, { useEffect, useRef } from 'react';

import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  useNodesState,
  useEdgesState
} from '@xyflow/react';

import '@xyflow/react/dist/style.css';

import {
  Database,
  CloudRain,
  ShieldAlert,
  Cpu,
} from 'lucide-react';

import { motion } from 'framer-motion';

const iconMap = {
  CloudRain: <CloudRain size={20} />,
  ShieldAlert: <ShieldAlert size={20} />,
  Cpu: <Cpu size={20} />,
  Database: <Database size={20} />
};

const CustomNode = ({ data, isConnectable }) => {

  const isFailing = data.state === 'critical';
  const isDegraded = data.state === 'degraded' || data.state === 'warning';
  const isRecovering = data.state === 'recovering';
  const isRecovered = data.state === 'recovered';
    
  const influence = data.influenceScore || 0;
  const isHighImpact = influence > 80;
  const isMediumImpact = influence > 50 && influence <= 80;

  let bgClass = 'bg-zinc-900 border-cyan-500/30';
  let textClass = 'text-cyan-400';

  if (isRecovering) {
    bgClass = 'bg-blue-950/80 border-blue-500 shadow-[0_0_30px_rgba(59,130,246,0.6)] animate-pulse';
    textClass = 'text-blue-400';
  } else if (isRecovered) {
    bgClass = 'bg-green-950/80 border-green-500 shadow-[0_0_20px_rgba(34,197,94,0.3)]';
    textClass = 'text-green-400';
  } else if (isHighImpact) {
    bgClass = 'bg-red-950/80 border-red-500 shadow-[0_0_60px_rgba(239,68,68,0.8)]';
    textClass = 'text-red-400';
  } else if (isMediumImpact || isFailing) {
    bgClass = 'bg-yellow-950/80 border-yellow-500 shadow-[0_0_30px_rgba(234,179,8,0.5)]';
    textClass = 'text-yellow-400';
  } else if (isDegraded) {
    bgClass = 'bg-yellow-950/40 border-yellow-500/50';
    textClass = 'text-yellow-400/80';
  } else {
    // Healthy specific calming glow
    bgClass = 'bg-zinc-900/90 border-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.15)]';
  }

  return (
    <motion.div
      initial={{ scale: 0.5, opacity: 0, y: 20 }}
      animate={{ scale: 1, opacity: 1, y: 0 }}
      transition={{ type: 'spring', damping: 12, stiffness: 100, mass: 0.5 }}
      className={`
        px-6 py-5
        rounded-2xl
        border-2
        ${bgClass}
        ${isHighImpact ? 'animate-pulse' : ''}
        flex items-center gap-4
        backdrop-blur-xl
        relative
        min-w-[280px]
      `}
    >

      <Handle
        type="target"
        position={Position.Top}
        isConnectable={isConnectable}
        className="
          w-3
          h-3
          border-none
          bg-zinc-700
        "
      />

      <div className={textClass}>
        {/* Scale up the icon */}
        {React.cloneElement(iconMap[data.iconName] || data.icon, { size: 28 })}
      </div>

      <div className="flex flex-col gap-1">

        <div className="
          font-bold
          text-gray-100
          text-lg
          tracking-wide
        ">
          {data.label}
        </div>

        <div className={`
          text-sm
          font-mono
          font-semibold
          tracking-wider
          ${textClass}
        `}>
          {data.subLabel}
        </div>

      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        isConnectable={isConnectable}
        className="
          w-3
          h-3
          border-none
          bg-zinc-700
        "
      />

    </motion.div>
  );
};

const nodeTypes = {
  custom: CustomNode,
};

export default function DependencyGraph({
  simulatorState,
  nodes: initialNodes,
  edges: initialEdges
}) {

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const hasInitialized = useRef(false);

  useEffect(() => {
    console.log(`[INSTRUMENT] DependencyGraph component mounted/rendered`);
    return () => console.log(`[INSTRUMENT] DependencyGraph component unmounted`);
  }, []);

  useEffect(() => {
    if (!initialNodes) return;

    setNodes((nds) => {
      // If empty, initialize
      if (!nds || nds.length === 0) {
        return initialNodes.map(node => {
          if (simulatorState === 'healed') {
            return {
              ...node,
              data: {
                ...node.data,
                state: 'healthy',
                subLabel: node.data.subLabel.includes('Latency') ? 'Latency: 10ms' : 'Connections: OK',
              }
            };
          }
          return node;
        });
      }

      // Otherwise, only update data to preserve position and references
      return nds.map((n) => {
        const incomingNode = initialNodes.find((inNode) => inNode.id === n.id);
        if (!incomingNode) return n;

        let newData = { ...incomingNode.data };
        if (simulatorState === 'healed') {
          newData.state = 'healthy';
          newData.subLabel = newData.subLabel.includes('Latency') ? 'Latency: 10ms' : 'Connections: OK';
        }

        if (JSON.stringify(n.data) !== JSON.stringify(newData)) {
          return { ...n, data: newData };
        }
        return n;
      });
    });
  }, [initialNodes, simulatorState, setNodes]);

  useEffect(() => {
    if (!initialEdges) return;

    setEdges((eds) => {
      if (!eds || eds.length === 0) {
        return initialEdges.map(edge => {
          if (simulatorState === 'healed') {
            return {
              ...edge,
              className: 'animated-data-packet',
              style: { stroke: '#06b6d4', strokeWidth: 2 },
              markerEnd: { type: MarkerType.ArrowClosed, color: '#06b6d4' },
            };
          }
          return {
            ...edge,
            className: edge.style?.stroke === '#ef4444' ? '' : 'animated-data-packet'
          };
        });
      }

      return eds.map((e) => {
        const incomingEdge = initialEdges.find((inEdge) => inEdge.id === e.id);
        if (!incomingEdge) return e;

        let newEdge = { ...incomingEdge };
        if (simulatorState === 'healed') {
          newEdge.className = 'animated-data-packet';
          newEdge.style = { stroke: '#06b6d4', strokeWidth: 2 };
          newEdge.markerEnd = { type: MarkerType.ArrowClosed, color: '#06b6d4' };
        } else {
          newEdge.className = newEdge.style?.stroke === '#ef4444' ? '' : 'animated-data-packet';
        }

        if (JSON.stringify(e.style) !== JSON.stringify(newEdge.style) || e.className !== newEdge.className) {
          return { ...e, ...newEdge };
        }
        return e;
      });
    });
  }, [initialEdges, simulatorState, setEdges]);

  return (

    <div
      style={{
        width: '100%',
        height: '100%',
        minHeight: '600px',
      }}

      className="
        bg-black
        rounded-3xl
        border
        border-zinc-800
        overflow-hidden
        relative
        shadow-2xl
        shadow-cyan-900/10
      "
    >

      {/* LIVE BADGE */}

      <div className="
        absolute
        top-4
        left-4
        z-10
        flex
        items-center
        gap-2
        bg-zinc-900/80
        px-3
        py-1.5
        rounded-full
        border
        border-zinc-800
        backdrop-blur-md
      ">

        <div className="
          w-2
          h-2
          rounded-full
          bg-cyan-500
          animate-pulse
        " />

        <span className="
          text-cyan-400
          font-mono
          text-[10px]
          tracking-widest
          uppercase
        ">
          Coral Operational Telemetry
        </span>

      </div>

      {/* REACT FLOW */}

      <div
        style={{
          width: '100%',
          height: '100%',
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onInit={(instance) => {
            if (!hasInitialized.current) {
              console.log(`[INSTRUMENT] ReactFlow fitView triggered`);
              instance.fitView({ padding: 0.2 });
              hasInitialized.current = true;
            }
          }}
          onViewportChange={(viewport) => {
            console.log(`[INSTRUMENT] ReactFlow viewport changed: x=${viewport.x}, y=${viewport.y}, zoom=${viewport.zoom}`);
          }}
          nodesFocusable={false}
          edgesFocusable={false}
          elementsSelectable={false}
          nodesDraggable={false}
          preventScrolling={true}
          autoPanOnConnect={false}
          autoPanOnNodeDrag={false}
          proOptions={{
            hideAttribution: true,
          }}
          style={{
            width: '100%',
            height: '100%',
            background: '#09090b',
          }}
        >
          <Background
            color="#3f3f46"
            gap={16}
            size={1}
          />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}