const fs = require('fs');
const path = require('path');
const { runIncidentEngine } = require('./calculate');

// Load Data
const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

// Mock RCA input (since LLM core is frozen/bypassed)
const predefinedRcaOutput = {
  rootCause: "A deployment to the auth-service introduced a CPU-intensive regex operation, causing latency spikes and a gateway retry storm.",
  confidence: 95,
  evidence: ["alert_22", "alert_25", "commit_89"]
};

console.log("=== IncidentMind Live Orchestration Engine ===\n");
console.log("Starting real-time incident replay...\n");

const eventStream = runIncidentEngine(incidentData, predefinedRcaOutput);

eventStream.forEach(evt => {
  console.log(`[${evt.timestamp}] [${evt.eventType}]`);
  
  if (evt.eventType === "RAW_TELEMETRY_EVENT" || evt.eventType === "SERVICE_STATE_CHANGE") {
    console.log(`> ${evt.payload.message}\n`);
  } 
  else if (evt.eventType === "RCA_AVAILABLE") {
    console.log(`> Identified Root Cause: ${evt.payload.rootCause}\n`);
  }
  else if (evt.eventType === "BLAST_RADIUS_AVAILABLE") {
    console.log(`> ${evt.payload.rootService} spreading to ${evt.payload.directlyImpacted.length + evt.payload.indirectlyImpacted.length} downstream services.\n`);
  }
  else if (evt.eventType === "BUSINESS_IMPACT_AVAILABLE") {
    console.log(`> Severe Impact: ${evt.payload.formatted.revenueRiskPerHour}/hr risk. ${evt.payload.formatted.affectedUsers} users impacted.\n`);
  }
  else if (evt.eventType === "PREDICTION_AVAILABLE") {
    const predicted = evt.payload.predictions.map(p => p.service).join(', ');
    console.log(`> Predicted Future Failures: ${predicted || "None"}\n`);
  }
  else if (evt.eventType === "RECOVERY_AVAILABLE") {
    console.log(`> Recommended Mitigation: ${evt.payload.recommendedAction} (Confidence: ${evt.payload.confidence}%)\n`);
  }
  else if (evt.eventType === "PARALLEL_UNIVERSE_AVAILABLE") {
    console.log(`> Alternative Scenario Value: ${evt.payload.bestScenario.executiveSummary} Potential Savings: ${evt.payload.bestScenario.formatted.revenueSaved}\n`);
  }
});

console.log("==================================================");
console.log("Total Stream Events Fired:", eventStream.length);
