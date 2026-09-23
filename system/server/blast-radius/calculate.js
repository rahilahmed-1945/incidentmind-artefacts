// Blast Radius Calculator
// Purely deterministic graph traversal engine. No LLMs.

function calculateBlastRadius(incidentData) {
  const rootNode = incidentData.rootService;
  const edges = incidentData.failurePropagation || [];
  
  // 1. Build Adjacency List
  const graph = {};
  edges.forEach(edge => {
    if (!graph[edge.from]) graph[edge.from] = [];
    if (!graph[edge.to]) graph[edge.to] = [];
    graph[edge.from].push({ node: edge.to, reason: edge.reason });
  });

  // 2. BFS Traversal for Depth & Impact categorization
  const depths = {};
  const queue = [{ node: rootNode, depth: 0, path: [rootNode] }];
  const visited = new Set();
  const traversalPaths = [];

  depths[rootNode] = 0;
  visited.add(rootNode);

  let maxDepth = 0;
  
  while (queue.length > 0) {
    const current = queue.shift();
    
    if (graph[current.node]) {
      graph[current.node].forEach(neighbor => {
        if (!visited.has(neighbor.node)) {
          visited.add(neighbor.node);
          const newDepth = current.depth + 1;
          depths[neighbor.node] = newDepth;
          if (newDepth > maxDepth) maxDepth = newDepth;
          
          const newPath = [...current.path, neighbor.node];
          traversalPaths.push({
            path: newPath.join(' -> '),
            reason: neighbor.reason
          });
          
          queue.push({ node: neighbor.node, depth: newDepth, path: newPath });
        }
      });
    }
  }

  // 3. Categorize Impacts
  const directlyImpacted = [];
  const indirectlyImpacted = [];
  
  Object.keys(depths).forEach(service => {
    if (depths[service] === 1) {
      directlyImpacted.push(service);
    } else if (depths[service] > 1) {
      indirectlyImpacted.push(service);
    }
  });

  // 4. Calculate Risk Score based on service criticality
  const serviceWeights = {
    'checkout-service': 40,
    'payments-service': 35,
    'gateway-service': 30,
    'primary-db': 25,
    'auth-service': 20,
    'redis-cache': 15,
    'inventory-service': 10,
    'user-profile-service': 5
  };

  let riskScore = 0;
  Object.keys(depths).forEach(service => {
    // Add base weight
    let weight = serviceWeights[service] || 5;
    
    // Multiplier based on proximity to root
    if (depths[service] === 1) weight *= 1.2; // Direct impact multiplier
    if (depths[service] >= 2) weight *= 0.8;  // Indirect impact dampener

    riskScore += weight;
  });

  // Cap risk score at 100
  riskScore = Math.min(Math.round(riskScore), 100);

  // 5. Calculate Severity
  let calculatedSeverity = "SEV-3";
  if (riskScore > 80 || visited.has('checkout-service') || visited.has('payments-service')) {
    calculatedSeverity = "SEV-1";
  } else if (riskScore > 50 || visited.has('primary-db')) {
    calculatedSeverity = "SEV-2";
  }

  // 6. Calculate Affected Users
  let affectedUsers = "Unknown";
  if (visited.has('gateway-service')) {
    affectedUsers = "100% of active sessions (Global Gateway failure)";
  } else if (visited.has('checkout-service') || visited.has('payments-service')) {
    affectedUsers = "15-20% (Users actively in checkout funnel)";
  } else if (visited.has('inventory-service') || visited.has('user-profile-service')) {
    affectedUsers = "5-10% (Users attempting to modify carts or profiles)";
  } else {
    affectedUsers = "< 1% (Isolated internal subsystem)";
  }

  return {
    rootService: rootNode,
    traversalPaths,
    directlyImpacted,
    indirectlyImpacted,
    propagationDepth: maxDepth,
    severity: calculatedSeverity,
    riskScore,
    affectedUsers
  };
}

module.exports = { calculateBlastRadius };
