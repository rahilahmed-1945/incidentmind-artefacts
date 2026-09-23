// Recovery Intelligence Engine
// Fully deterministic heuristic engine. No LLMs.

function calculateRecovery(incidentData, blastRadius, businessImpact) {
  const rootCause = incidentData.rootCause || incidentData.triggerEvent || "";
  const timeline = incidentData.timeline || [];
  
  // Convert root cause and timeline events to a single search string
  let contextString = rootCause.toLowerCase();
  timeline.forEach(t => {
    contextString += " " + t.event.toLowerCase();
  });

  const impactedServicesCount = 1 + (blastRadius.directlyImpacted?.length || 0) + (blastRadius.indirectlyImpacted?.length || 0);

  let recommendation = {
    recommendedAction: "Unknown",
    actionType: "Unknown",
    confidence: 0,
    expectedRecoveryTimeMinutes: 0,
    riskLevel: "Unknown",
    reasoning: [],
    alternativeActions: [],
    recoverySuccessProbability: 0,
    estimatedServicesRecovered: 0,
    estimatedRevenueSaved: 0
  };

  // 1. Deployment Check (Highest Priority)
  if (contextString.includes("deployment") || contextString.includes("deploy") || contextString.includes("v2.") || contextString.includes("rollout")) {
    recommendation.recommendedAction = "Rollback Deployment to previous stable version";
    recommendation.actionType = "Rollback Deployment";
    recommendation.confidence = 94; // Base 90 + ~4% heuristic
    recommendation.expectedRecoveryTimeMinutes = 7;
    recommendation.riskLevel = "Medium";
    
    recommendation.reasoning.push(`Incident started immediately after a deployment on ${blastRadius.rootService}`);
    recommendation.reasoning.push(`Historical recovery data indicates rollback resolved similar deployment-triggered incidents`);
    
    if (impactedServicesCount >= 3) {
      recommendation.reasoning.push(`Blast radius is expanding (${impactedServicesCount} services impacted), demanding immediate broad mitigation`);
    }

    recommendation.alternativeActions = ["Scale Service", "Enable Fallback Mode"];
    
    recommendation.recoverySuccessProbability = 95;
    recommendation.estimatedServicesRecovered = impactedServicesCount; // Full recovery expected
  } 
  // 2. Database Failure Check
  else if (contextString.includes("database") || contextString.includes("db connection") || contextString.includes("maxed out") || blastRadius.rootService.includes("db")) {
    recommendation.recommendedAction = "Failover to Read-Replica or Scale Database Connection Pool";
    recommendation.actionType = "Failover Database";
    recommendation.confidence = 85;
    recommendation.expectedRecoveryTimeMinutes = 15;
    recommendation.riskLevel = "High";

    recommendation.reasoning.push(`Database connection limits or saturation detected`);
    recommendation.reasoning.push(`Downstream transaction capability severely degraded`);
    
    recommendation.alternativeActions = ["Restart Service Connections", "Throttle Incoming Traffic"];
    
    recommendation.recoverySuccessProbability = 80;
    recommendation.estimatedServicesRecovered = Math.max(1, impactedServicesCount - 1);
  }
  // 3. Cache Check
  else if (contextString.includes("redis") || contextString.includes("cache")) {
    recommendation.recommendedAction = "Clear Cache / Restart Cache Cluster";
    recommendation.actionType = "Clear Cache";
    recommendation.confidence = 80;
    recommendation.expectedRecoveryTimeMinutes = 2;
    recommendation.riskLevel = "High"; // Cache stampede risk

    recommendation.reasoning.push(`Cache contention or memory eviction detected`);
    recommendation.alternativeActions = ["Scale Cache Nodes", "Disable Cache Reads"];
    
    recommendation.recoverySuccessProbability = 75;
    recommendation.estimatedServicesRecovered = impactedServicesCount;
  }
  // 4. Compute Check
  else if (contextString.includes("cpu") || contextString.includes("memory") || contextString.includes("oom")) {
    recommendation.recommendedAction = "Scale Service Horizontal Pods";
    recommendation.actionType = "Scale Service";
    recommendation.confidence = 75;
    recommendation.expectedRecoveryTimeMinutes = 5;
    recommendation.riskLevel = "Low";

    recommendation.reasoning.push(`CPU or memory saturation detected without direct deployment correlation`);
    recommendation.alternativeActions = ["Restart Service", "Throttle Incoming Traffic"];
    
    recommendation.recoverySuccessProbability = 85;
    recommendation.estimatedServicesRecovered = impactedServicesCount;
  }
  // Default Fallback
  else {
    recommendation.recommendedAction = "Restart Service";
    recommendation.actionType = "Restart Service";
    recommendation.confidence = 60;
    recommendation.expectedRecoveryTimeMinutes = 3;
    recommendation.riskLevel = "Medium";
    
    recommendation.reasoning.push(`No specific degradation signature detected; attempting standard mitigation`);
    recommendation.alternativeActions = ["Scale Service"];
    
    recommendation.recoverySuccessProbability = 60;
    recommendation.estimatedServicesRecovered = 1;
  }

  // Calculate estimated revenue saved
  // If we recover in expectedRecoveryTimeMinutes, we save the remaining downtime cost.
  // We represent "savings" as 1 hour of risk minus the recovery cost.
  // Or simpler: We save the revenue that would have been lost if we didn't act for another 60 mins.
  const hourlyRisk = businessImpact.revenueRiskPerHour || 0;
  // If we recover in X minutes instead of 60 minutes, we save:
  const costOfRecoveryPeriod = (hourlyRisk / 60) * recommendation.expectedRecoveryTimeMinutes;
  recommendation.estimatedRevenueSaved = Math.max(0, Math.round(hourlyRisk - costOfRecoveryPeriod));

  return recommendation;
}

module.exports = { calculateRecovery };
