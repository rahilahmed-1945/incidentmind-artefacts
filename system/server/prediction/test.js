const fs = require('fs');
const path = require('path');
const { calculatePredictions } = require('./calculate');

// Load Data
const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

// Simulate a partial "mid-incident" blast radius
// In this state, auth-service, gateway, redis, and primary-db have fallen.
// The downstream services haven't been impacted *yet*.
const partialBlastRadius = {
  rootService: "auth-service",
  directlyImpacted: ["redis-cache"],
  indirectlyImpacted: []
};

console.log("=== IncidentMind Prediction Engine ===\n");
console.log("Current State: auth-service and redis-cache are DEGRADED.");
console.log("Predicting future cascading failures...\n");

const predictionResult = calculatePredictions(partialBlastRadius, incidentData.failurePropagation, incidentData.timeline);

predictionResult.predictions.forEach(pred => {
  console.log(`[PREDICTED TARGET] ${pred.service}`);
  console.log(`Risk Probability: ${pred.riskProbability}%`);
  console.log(`Confidence: ${pred.confidence}%`);
  console.log(`Estimated Impact: ${pred.estimatedTimeToImpactMinutes} minutes`);
  console.log(`Reason: ${pred.reason}`);
  console.log(`Risk Path: ${pred.riskPath.join(' -> ')}`);
  
  // INR formatting for the risk
  const addRev = pred.additionalRevenueRiskPerHour;
  const formattedRev = addRev > 0 ? `₹${addRev.toLocaleString('en-IN')}` : '₹0';
  console.log(`Additional Users At Risk: ${pred.additionalUsersAtRisk.toLocaleString('en-IN')}`);
  console.log(`Additional Revenue Risk: ${formattedRev}/hr\n`);
});

console.log("==================================================");
console.log("FULL JSON PAYLOAD:");
console.log(JSON.stringify(predictionResult, null, 2));
