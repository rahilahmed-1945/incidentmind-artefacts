const { retrieve } = require('./retrieve');

const questions = [
  "Why is checkout failing?",
  "What changed after deploy v2.4.1?",
  "Which services were impacted?",
  "What happened before the SEV-1 declaration?",
  "What caused database saturation?"
];

console.log("=== IncidentMind RAG Retrieval Test ===\n");

questions.forEach(q => {
  console.log('--------------------------------------------------');
  console.log(`Q: ${q}`);
  console.log('--------------------------------------------------');
  
  const result = retrieve(q);
  
  console.log(JSON.stringify(result, null, 2));
  console.log('\n');
});
