const fs = require('fs');
const path = require('path');
const { calculateBlastRadius } = require('../blast-radius/calculate');
const { calculateBusinessImpact, formatINR } = require('../business-impact/calculate');
const { calculateRecovery } = require('../recovery/calculate');
const { calculateParallelUniverse } = require('./calculate');

// Load Data
const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

// Run Frozen Core Engines
const blastRadius = calculateBlastRadius(incidentData);
const businessImpact = calculateBusinessImpact(blastRadius, incidentData.timeline);
const recoveryRecommendation = calculateRecovery(incidentData, blastRadius, businessImpact);

// Run Parallel Universe Simulator
const puResult = calculateParallelUniverse(incidentData, blastRadius, businessImpact, recoveryRecommendation);

console.log("=== IncidentMind Parallel Universe Simulator ===\n");

console.log("Current Reality");
console.log(`Downtime:\n${puResult.currentReality.downtimeMinutes} minutes\n`);
console.log(`Services Impacted:\n${puResult.currentReality.servicesImpactedCount}\n`);
console.log(`Revenue Loss:\n${formatINR(puResult.currentReality.revenueLoss)}\n`);
console.log(`Users Impacted:\n${puResult.currentReality.usersImpacted.toLocaleString('en-IN')}\n`);
console.log("---\n");

puResult.alternativeScenarios.forEach(scen => {
  console.log(`Alternative Reality`);
  console.log(`${scen.scenarioName}\n`);
  
  console.log(`Downtime:\n${scen.downtimeMinutes} minutes\n`);
  console.log(`Services Impacted:\n${scen.servicesImpactedCount}\n`);
  console.log(`Revenue Loss:\n${scen.formatted.revenueLoss}\n`);
  
  if (scen.revenueSaved >= 0) {
    console.log(`Revenue Saved:\n${scen.formatted.revenueSaved}\n`);
    console.log(`Users Impacted:\n${scen.usersImpacted.toLocaleString('en-IN')}\n`);
    console.log(`Users Protected:\n${scen.usersProtected.toLocaleString('en-IN')}\n`);
    console.log(`Transactions Preserved:\n${scen.transactionsPreserved.toLocaleString('en-IN')}\n`);
    console.log(`Services Prevented from Failing:\n${scen.servicesPrevented}\n`);
    console.log(`MTTR Reduction:\n${scen.mttrReduction} minutes\n`);
  }
  
  console.log(`Scenario Score:\n${scen.scenarioScore}/100\n`);
  console.log(`Executive Summary:\n${scen.executiveSummary}\n`);
  console.log("---\n");
});

console.log(`BEST SCENARIO RANKING`);
console.log(`Winner: ${puResult.bestScenario.scenarioName}`);
console.log(`Score: ${puResult.bestScenario.scenarioScore}/100`);
console.log(`Total Value Protected: ${puResult.bestScenario.formatted.revenueSaved}`);

console.log("\n=========================================");
console.log("FULL JSON PAYLOAD:");
console.log(JSON.stringify(puResult, null, 2));
