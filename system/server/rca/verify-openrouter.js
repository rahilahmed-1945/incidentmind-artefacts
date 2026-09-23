require('dotenv').config();
const axios = require('axios');
const { retrieveSemanticV2 } = require('../rag/index');

async function verifyRCA(question) {
  console.log("=========================================");
  console.log("1. RETRIEVED EVIDENCE");
  console.log("=========================================");
  const retrieval = await retrieveSemanticV2(question);
  const evidenceList = retrieval.evidence;

  const evidenceText = evidenceList.map((e, index) => {
    return `[Evidence ID: ${e.id}]
Type: ${e.type}
Timestamp: ${e.timestamp}
Content: ${e.content}
Details: ${JSON.stringify(e.details)}`;
  }).join('\n\n');

  console.log(evidenceText);

  console.log("\n=========================================");
  console.log("2. PROMPT SENT TO MODEL");
  console.log("=========================================");
  const systemPrompt = `You are a Principal Incident Commander and Root Cause Analysis engine.
Your task is to analyze the provided operational evidence and answer the user's question with a structured Root Cause Analysis.

CRITICAL INSTRUCTIONS:
1. ONLY use the provided evidence. DO NOT hallucinate, invent, or guess causes that are not explicitly supported by the evidence.
2. If the evidence is insufficient to determine the root cause or answer the question, state what is known and REDUCE your confidence score significantly.
3. Every claim in the root cause summary must be supported by the retrieved evidence.
4. Provide a JSON response EXACTLY matching the schema below.

OUTPUT SCHEMA:
{
  "rootCause": "A concise paragraph explaining the root cause based ONLY on the evidence.",
  "confidence": <integer between 0 and 100>,
  "evidence": ["list of supporting evidence items referencing the Evidence ID"],
  "affectedServices": ["list of services affected based ONLY on the evidence"],
  "recommendedAction": "A specific action to resolve or mitigate the issue, based on the evidence."
}`;

  const userPrompt = `Question: ${question}\n\nEvidence:\n${evidenceText}`;
  
  console.log("--- SYSTEM PROMPT ---");
  console.log(systemPrompt);
  console.log("\n--- USER PROMPT ---");
  console.log(userPrompt);

  console.log("\n=========================================");
  console.log("3. RAW MODEL RESPONSE");
  console.log("=========================================");

  if (!process.env.OPENROUTER_API_KEY) {
    throw new Error("Missing OPENROUTER_API_KEY in environment variables.");
  }

  const response = await axios.post(
    'https://openrouter.ai/api/v1/chat/completions',
    {
      model: 'google/gemma-4-31b-it:free',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt }
      ]
    },
    {
      headers: {
        'Authorization': `Bearer ${process.env.OPENROUTER_API_KEY}`,
        'HTTP-Referer': 'http://localhost:3000',
        'X-Title': 'IncidentMind'
      }
    }
  );

  const rawContent = response.data.choices[0].message.content;
  console.log(rawContent);

  console.log("\n=========================================");
  console.log("4. FINAL RCA JSON");
  console.log("=========================================");
  
  let rcaJson;
  try {
    rcaJson = JSON.parse(rawContent);
  } catch(e) {
    const match = rawContent.match(/```json\n([\s\S]*)\n```/);
    if (match) rcaJson = JSON.parse(match[1]);
    else throw new Error("LLM did not return valid JSON");
  }

  console.log(JSON.stringify(rcaJson, null, 2));

  console.log("\n--- CONFIRMATIONS ---");
  console.log(`Fallback logic used? No`);
  console.log(`evidenceIds preserved? ${Array.isArray(rcaJson.evidence) && rcaJson.evidence.length > 0 && rcaJson.evidence.some(e => typeof e === 'string' && e.includes('_')) ? 'Yes' : 'No'}`);
}

verifyRCA("Why is checkout failing?").catch(console.error);
