const fs = require('fs');
const path = require('path');
const { calculateBlastRadius } = require('./calculate');

// 1. Load the dataset
const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

console.log("=== IncidentMind Blast Radius Engine Test ===\n");

// 2. Run the deterministic calculation
const blastRadius = calculateBlastRadius(incidentData);

// 3. Display Results matching requirements
console.log("1. GRAPH TRAVERSAL PATHS (Breadth-First Search):");
blastRadius.traversalPaths.forEach(tp => {
  console.log(`   [Path] ${tp.path}`);
  console.log(`   [Reason] ${tp.reason}`);
});

console.log("\n2. IMPACT CATEGORIZATION:");
console.log(`   [Root Service] ${blastRadius.rootService}`);
console.log(`   [Directly Impacted (Depth 1)] ${blastRadius.directlyImpacted.join(', ')}`);
console.log(`   [Indirectly Impacted (Depth 2+)] ${blastRadius.indirectlyImpacted.join(', ')}`);
console.log(`   [Maximum Propagation Depth] ${blastRadius.propagationDepth}`);

console.log("\n3. SEVERITY & RISK SCORE CALCULATIONS:");
console.log(`   [Calculated Severity] ${blastRadius.severity}`);
console.log(`   [Risk Score] ${blastRadius.riskScore}/100 (Based on nodal weights and proximity)`);

console.log("\n4. AFFECTED USER ESTIMATION:");
console.log(`   [Affected Users] ${blastRadius.affectedUsers}`);
console.log('\n======================================================\n');
console.log("FULL JSON PAYLOAD:");
console.log(JSON.stringify(blastRadius, null, 2));
