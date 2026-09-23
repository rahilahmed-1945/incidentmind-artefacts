const fs = require('fs');
const path = require('path');
const { runLiveIncidentEngine } = require('./calculate');

const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

const predefinedRcaOutput = {
  rootCause: "A deployment to the auth-service introduced a CPU-intensive regex operation, causing latency spikes and a gateway retry storm.",
  confidence: 95,
  evidence: ["alert_22", "alert_25", "commit_89"]
};

// Configuration for test
const config = {
  mode: "LIVE", // or "INSTANT"
  stageDelayMs: 300 // slightly accelerated for demo purposes
};

console.log("=== IncidentMind Live Runtime Engine ===\n");
console.log(`Simulation Start: ${new Date().toISOString()}`);
console.log(`Mode: ${config.mode}`);
console.log("Awaiting Socket Stream...\n");

const eventStreamLog = [];

function handleEvent(evt) {
  eventStreamLog.push(evt);
  
  const timeInfo = `[Actual: ${evt.actualTimestamp}] [Display: ${evt.displayTimestamp}]`;
  console.log(`${timeInfo} [${evt.eventType}]`);
  console.log(`  State: ${evt.currentState} -> ${evt.nextState} | Trigger: ${evt.trigger}`);
  
  if (evt.eventType === "RAW_TELEMETRY_EVENT") {
    console.log(`  > ${evt.payload.message}\n`);
  } 
  else if (evt.eventType === "SERVICE_STATE_CHANGE") {
    console.log(`  > [${evt.payload.service}] Transited from ${evt.payload.oldState} to ${evt.payload.newState}\n`);
  }
  else if (evt.eventType.endsWith("_STARTED")) {
    console.log(`  > ⏳ ${evt.payload.message}\n`);
  }
  else if (evt.eventType === "RCA_AVAILABLE") {
    console.log(`  > ✅ Identified Root Cause: ${evt.payload.rootCause}\n`);
  }
  else if (evt.eventType === "BLAST_RADIUS_AVAILABLE") {
    console.log(`  > ✅ Calculated Blast Radius: ${evt.payload.directlyImpacted.length + evt.payload.indirectlyImpacted.length} downstream dependencies breached.\n`);
  }
  else if (evt.eventType === "BUSINESS_IMPACT_AVAILABLE") {
    console.log(`  > ✅ Calculated Business Impact: ${evt.payload.formatted.revenueRiskPerHour}/hr Risk.\n`);
  }
  else if (evt.eventType === "PREDICTION_AVAILABLE") {
    console.log(`  > ✅ Prediction Complete: ${evt.payload.predictions.length} additional services at risk.\n`);
  }
  else if (evt.eventType === "RECOVERY_AVAILABLE") {
    console.log(`  > ✅ Recovery Strategy Generated: ${evt.payload.recommendedAction}\n`);
  }
  else if (evt.eventType === "PARALLEL_UNIVERSE_AVAILABLE") {
    console.log(`  > ✅ Parallel Universe Scenarios Ready: Best Action = ${evt.payload.bestScenario.scenarioName}\n`);
  }
  else if (evt.eventType === "INCIDENT_RESOLVED") {
    console.log(`  > 🏁 ${evt.payload.message}\n`);
  }
}

async function run() {
  await runLiveIncidentEngine(incidentData, predefinedRcaOutput, handleEvent, config);
  console.log("==================================================");
  console.log(`End of Simulation. Processed ${eventStreamLog.length} events asynchronously.`);
}

run();
