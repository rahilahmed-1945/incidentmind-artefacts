const { retrieveSemanticV2, retrieveRootCause } = require('./index');

const questions = [
  "Why is checkout failing?",
  "What caused database saturation?",
  "What caused the outage?",
  "What evidence points to the root cause?"
];

async function runTests() {
  console.log("=== Root Cause Retrieval Engine Test ===\n");

  for (const q of questions) {
    console.log('==================================================');
    console.log(`Q: ${q}`);
    console.log('==================================================');
    
    const resV2 = await retrieveSemanticV2(q);
    const resRC = await retrieveRootCause(q);

    console.log("\n>>> CURRENT RETRIEVAL (Semantic V2) Top 3:");
    resV2.evidence.slice(0, 3).forEach(e => {
      console.log(`[Score: ${e.score}] [${e.type}] ${e.content}`);
    });

    console.log("\n>>> ROOT CAUSE RETRIEVAL Top 10:");
    resRC.evidence.forEach(e => {
      console.log(`[Score: ${e.score}] [${e.type}] ${e.content}`);
      console.log(`    Reasons: ${e.reasons.join(', ')}`);
    });
    console.log('\n');
  }
}

runTests();
