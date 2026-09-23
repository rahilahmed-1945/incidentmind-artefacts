// Continuous Prediction Engine

const stageBaseRisks = {
  'HEALTHY': 0,
  'WEAK_SIGNAL': 15,
  'FIRST_WARNING': 30,
  'TEMPORARY_STABILIZATION': 40,
  'REPEATED_WARNING': 50,
  'ESCALATION': 70,
  'DEPENDENCY_FAILURE': 85,
  'SEV-1': 95
};

function calculatePredictions(serviceStates, failurePropagation, rootService, timelineStage, previousPredictions = [], isRecovering = false) {
  // 1. Build Adjacency List & Reverse List
  const graph = {};
  const reverseGraph = {};
  failurePropagation.forEach(edge => {
    if (!graph[edge.from]) graph[edge.from] = [];
    if (!reverseGraph[edge.to]) reverseGraph[edge.to] = [];
    graph[edge.from].push(edge.to);
    reverseGraph[edge.to].push(edge.from);
  });

  const predictions = [];
  const baseStageRisk = stageBaseRisks[timelineStage] || 0;

  // Identify all nodes
  const allNodes = new Set([...Object.keys(graph), ...Object.keys(reverseGraph)]);

  allNodes.forEach(targetNode => {
    // We only predict for nodes that are NOT currently completely broken
    // But since the UI expects to see them, let's keep predictions for any node not in CRITICAL
    if (serviceStates[targetNode] === 'CRITICAL' || serviceStates[targetNode] === 'RECOVERED') {
       return; 
    }

    // Find previous prediction for trend and recovery decay
    const prevPred = previousPredictions.find(p => p.service === targetNode);
    let prevRisk = prevPred ? prevPred.riskProbability : 0;
    
    let riskProbability = 0;
    let confidence = 0;
    let estimatedTimeToImpactMinutes = prevPred ? prevPred.estimatedTimeToImpactMinutes : 30;

    if (isRecovering) {
      // Gradual Risk Collapse
      riskProbability = Math.floor(prevRisk * 0.45); // Cut by ~55% each tick
      confidence = prevPred ? prevPred.confidence : 80;
      estimatedTimeToImpactMinutes += 10; // Time to impact gets pushed away
    } else {
      // Upstream dependency check
      const directUpstreams = (reverseGraph[targetNode] || []);
      let upstreamModifier = 0;
      directUpstreams.forEach(u => {
        if (serviceStates[u] === 'WARNING') upstreamModifier += 10;
        if (serviceStates[u] === 'CRITICAL') upstreamModifier += 25;
      });

      // If we are at root service or near it, its risk climbs directly with stage
      if (targetNode === rootService) {
        riskProbability = baseStageRisk + upstreamModifier;
      } else {
        // Downstream services scale with a slightly dampened base risk + heavy upstream influence
        riskProbability = Math.floor(baseStageRisk * 0.7) + upstreamModifier;
      }

      // Add a tiny bit of random jitter for realism
      riskProbability += Math.floor(Math.random() * 5);
      riskProbability = Math.min(riskProbability, 98); // Cap at 98%

      // Confidence climbs with the severity of the stage
      confidence = Math.min(40 + (baseStageRisk * 0.5) + (upstreamModifier * 0.5), 99);

      // Time to Impact decreases as stage worsens
      // Base is 30 mins. It drops as risk goes up.
      estimatedTimeToImpactMinutes = Math.max(1, 30 - Math.floor(riskProbability / 4));
    }

    // Determine Trend
    let trend = "Stable";
    if (riskProbability > prevRisk + 2) trend = "Rising";
    else if (riskProbability < prevRisk - 2) trend = "Improving";

    // Build risk path (Root -> ... -> directUpstream -> targetNode)
    let riskPath = [];
    if (rootService !== targetNode) {
       riskPath = [rootService, targetNode];
    }

    const reason = isRecovering ? "Operator intervention detected. Cascading risk is subsiding." : `Upstream instability and incident progression indicating ${trend.toLowerCase()} risk.`;

    predictions.push({
      service: targetNode,
      riskProbability: Math.round(riskProbability),
      confidence: Math.round(confidence),
      estimatedTimeToImpactMinutes: Math.round(estimatedTimeToImpactMinutes),
      reason,
      riskPath,
      trend
    });
  });

  // Sort by highest risk probability
  predictions.sort((a, b) => b.riskProbability - a.riskProbability);

  // Calculate Escalation Momentum
  const stateVals = Object.values(serviceStates);
  const criticalCount = stateVals.filter(s => s === 'CRITICAL').length;
  const warningCount = stateVals.filter(s => s === 'WARNING' || s === 'DEGRADED').length;
  const avgRisk = predictions.length > 0 ? predictions.reduce((acc, p) => acc + p.riskProbability, 0) / predictions.length : 0;
  
  // Base calculation
  let rawMomentum = (criticalCount * 20) + (warningCount * 8) + (avgRisk * 0.5);
  
  if (isRecovering) {
    rawMomentum = rawMomentum * 0.3; // Momentum collapses during recovery
  }
  
  const escalationMomentum = Math.min(100, Math.floor(rawMomentum));

  return { predictions, escalationMomentum };
}

module.exports = { calculatePredictions };
