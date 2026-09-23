const fs = require('fs');
const path = require('path');
const { calculateBlastRadius } = require('../blast-radius/calculate');
const { calculateBusinessImpact } = require('../business-impact/calculate');
const { calculateRecovery } = require('./calculate');

// Load Data
const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

// Generate previous layer contexts
const blastRadius = calculateBlastRadius(incidentData);
const businessImpact = calculateBusinessImpact(blastRadius, incidentData.timeline);

console.log("=== IncidentMind Recovery Intelligence Engine ===\n");
console.log(`[Input] Root Service: ${blastRadius.rootService}`);
console.log(`[Input] Trigger Event: ${incidentData.triggerEvent}`);
console.log(`[Input] Impacted Services: ${1 + blastRadius.directlyImpacted.length + blastRadius.indirectlyImpacted.length}`);
console.log(`[Input] Business Severity: ${businessImpact.businessSeverity}\n`);

// Run Recovery Intelligence
const recoveryResult = calculateRecovery(incidentData, blastRadius, businessImpact);

console.log("Recommended Action:");
console.log(recoveryResult.recommendedAction + "\n");

console.log(`Confidence:\n${recoveryResult.confidence}%\n`);

console.log(`Expected Recovery:\n${recoveryResult.expectedRecoveryTimeMinutes} minutes\n`);

console.log(`Risk Level:\n${recoveryResult.riskLevel}\n`);

console.log("Reasoning:");
recoveryResult.reasoning.forEach(r => console.log(`- ${r}`));
console.log("");

console.log("Alternative Actions:");
recoveryResult.alternativeActions.forEach(a => console.log(`- ${a}`));
console.log("");

console.log("--- Simulation Telemetry (For Parallel Universe) ---");
console.log(`Recovery Success Probability: ${recoveryResult.recoverySuccessProbability}%`);
console.log(`Estimated Services Recovered: ${recoveryResult.estimatedServicesRecovered}`);
console.log(`Estimated Revenue Saved: ₹${recoveryResult.estimatedRevenueSaved.toLocaleString('en-IN')}\n`);

console.log("=========================================");
console.log("FULL JSON PAYLOAD:");
console.log(JSON.stringify(recoveryResult, null, 2));
