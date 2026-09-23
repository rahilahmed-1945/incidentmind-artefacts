const { retrieveKeyword, retrieveSemantic, ingest } = require('./index');

const questions = [
  "Why is checkout failing?",
  "What changed after the auth deployment?",
  "What caused the database to become saturated?",
  "Which systems were affected by the auth incident?",
  "What happened before the SEV-1 declaration?",
  "What evidence points to the root cause?"
];

async function runTests() {
  console.log("=== IncidentMind RAG Comparison Test ===\n");
  
  // Note: In a real environment, you'd make sure ChromaDB is running 
  // on localhost:8000 before executing this script.
  console.log(">> Attempting to ingest and embed evidence into ChromaDB...");
  try {
    await ingest();
    const { ChromaClient } = require('chromadb');
    const client = new ChromaClient();
    const collection = await client.getCollection({ name: "incident_evidence" });
    const count = await collection.count();
    console.log(`\n=> SUCCESS: Vectors are actually stored.`);
    console.log(`=> ChromaDB Collection Size: ${count} vectors stored.\n`);
  } catch(e) {
    console.error("Failed to index data. Skipping semantic tests.", e.message);
    return;
  }

  for (const q of questions) {
    console.log('--------------------------------------------------');
    console.log(`Q: ${q}`);
    console.log('--------------------------------------------------');
    
    console.log(">>> KEYWORD RETRIEVAL (Top 3):");
    const keywordResult = retrieveKeyword(q);
    if(keywordResult.evidence.length === 0) {
      console.log("No evidence found.");
    }
    keywordResult.evidence.slice(0,3).forEach(e => {
       const summary = e.details.message || e.details.alert || e.details.summary || e.details.version || e.details.title || "";
       console.log(`[Score: ${e.relevanceScore}] [${e.type}] ${summary}`);
    });
    
    console.log("\n>>> SEMANTIC RETRIEVAL (Top 3):");
    const semanticResult = await retrieveSemantic(q);
    if(semanticResult.evidence.length === 0) {
      console.log("No evidence found.");
    }
    semanticResult.evidence.slice(0,3).forEach(e => {
       console.log(`[Distance: ${parseFloat(e.score).toFixed(4)}] [${e.type}] ${e.content}`);
    });
    console.log('\n');
  }
}

runTests();
