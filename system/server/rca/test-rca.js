const { generateRCA } = require('./generate-rca');

const questions = [
  "Why is checkout failing?",
  "What caused database saturation?",
  "What changed after deploy v2.4.1?",
  "Which services were impacted?",
  "What evidence points to the root cause?"
];

async function runTests() {
  console.log("=== IncidentMind RCA Engine Test ===\n");

  if (!process.env.OPENROUTER_API_KEY) {
    console.log("WARN: OPENROUTER_API_KEY not set. Falling back to Local AI Mock.");
  }

  for (const q of questions) {
    console.log('==================================================');
    console.log(`Q: ${q}`);
    console.log('==================================================');
    
    try {
      const result = await generateRCA(q);
      
      console.log("\n[RETRIEVED EVIDENCE (Top 3)]:");
      result.retrieval.slice(0, 3).forEach(e => {
        console.log(`- [${e.id}] ${e.type.toUpperCase()}: ${e.content}`);
      });

      console.log("\n[GENERATED RCA]:");
      console.log(JSON.stringify(result.rca, null, 2));
      console.log('\n');
    } catch(e) {
      console.error(`Failed to generate RCA for "${q}":`, e.message);
    }
  }
}

runTests();
