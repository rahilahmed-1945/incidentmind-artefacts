const fs = require('fs');
const path = require('path');
const { calculateBlastRadius } = require('../blast-radius/calculate');
const { calculateBusinessImpact } = require('./calculate');

// Load Data
const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

// Generate Blast Radius
const blastRadius = calculateBlastRadius(incidentData);

// Generate Business Impact V2
const businessImpact = calculateBusinessImpact(blastRadius, incidentData.timeline);

// Display output
console.log("=== IncidentMind Business Impact Engine V2 (INR Edition) ===\n");

console.log("Root Cause:");
console.log(`${blastRadius.rootService} deployment (identified via Root Cause Engine)`);

console.log(`\nBlast Radius:`);
console.log(`${1 + blastRadius.directlyImpacted.length + blastRadius.indirectlyImpacted.length} services impacted`);

console.log("\nBusiness Impact:\n");

console.log(`Revenue Risk:\n${businessImpact.formatted.revenueRiskPerHour}/hr`);
console.log(`  └ Formula: ${businessImpact.formulaBreakdown.revenueRisk}\n`);

console.log(`Affected Users:\n${businessImpact.formatted.affectedUsers}`);
console.log(`  └ Formula: ${businessImpact.formulaBreakdown.affectedUsers}\n`);

console.log(`Transactions Impacted:\n${businessImpact.formatted.transactionsImpacted}`);
console.log(`  └ Formula: ${businessImpact.formulaBreakdown.transactionsImpacted}\n`);

console.log(`Orders Impacted:\n${businessImpact.formatted.ordersImpacted}`);
console.log(`  └ Formula: ${businessImpact.formulaBreakdown.ordersImpacted}\n`);

console.log(`Estimated Downtime Cost:\n${businessImpact.formatted.estimatedDowntimeCost}`);
console.log(`  └ Formula: ${businessImpact.formulaBreakdown.downtimeCost}\n`);

console.log(`SLA Risk:\n${businessImpact.slaRisk}\n`);
console.log(`Business Severity:\n${businessImpact.businessSeverity}\n`);
console.log(`Customer Impact:\n${businessImpact.customerImpact}\n`);

console.log("=========================================");
console.log("FULL JSON PAYLOAD:");
console.log(JSON.stringify(businessImpact, null, 2));
