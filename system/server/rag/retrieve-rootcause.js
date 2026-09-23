const fs = require('fs');
const path = require('path');
const { ChromaClient } = require('chromadb');
const { pipeline, env } = require('@xenova/transformers');

env.allowLocalModels = false;

let extractor = null;
const client = new ChromaClient();

const boostWords = ['latency', 'timeout', 'cpu', 'maxed out', 'regex', 'saturation', 'exhaustion', 'failing', 'spike', 'retry storm', 'contention'];
const penaltyWords = ['recovering', 'subsiding', 'stable', 'post-mortem', 'downgrading', 'recovery', 'drops', 'normalizes', 'operational', 'subsides', 'resolved'];

// Incident context loader
function loadIncidentContext() {
  const incidentPath = path.join(__dirname, '../../datasets/incidents/incident-001.json');
  try {
    const data = fs.readFileSync(incidentPath, 'utf8');
    const incident = JSON.parse(data);
    return {
      rootService: incident.rootService,
      incidentStart: new Date(incident.timeline[0].timestamp).getTime(),
      incidentDeclaration: new Date('2026-06-21T18:18:00Z').getTime() // From timeline SEV-1
    };
  } catch(e) {
    console.error("Failed to load incident context:", e);
    return null;
  }
}

async function retrieveRootCause(question) {
  if (!extractor) {
    extractor = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');
  }

  const output = await extractor(question, { pooling: 'mean', normalize: true });
  const queryEmbedding = Array.from(output.data);

  let collection;
  try {
    const dummyEmbeddingFunction = {
      generate: async (texts) => { return texts.map(() => Array(384).fill(0)); }
    };
    collection = await client.getCollection({ 
      name: "incident_evidence",
      embeddingFunction: dummyEmbeddingFunction
    });
  } catch(e) {
    console.error("ChromaDB collection not found or server not running.");
    return { question, evidence: [] };
  }

  const results = await collection.query({
    queryEmbeddings: [queryEmbedding],
    nResults: 50 // Fetch a broad net
  });

  const ctx = loadIncidentContext();
  let evidenceList = [];

  if (results.ids && results.ids[0]) {
    for (let i = 0; i < results.ids[0].length; i++) {
      let rawScore = results.distances[0][i];
      let type = results.metadatas[0][i].type;
      let timestamp = results.metadatas[0][i].timestamp;
      let content = results.documents[0][i];
      let details = JSON.parse(results.metadatas[0][i].data);
      let contentLower = content.toLowerCase();

      let multiplier = 1.0;
      let reasons = [];

      // --- TEMPORAL WEIGHTING ---
      if (ctx && timestamp) {
        let evTime = new Date(timestamp).getTime();
        let diffMins = (evTime - ctx.incidentStart) / (1000 * 60);

        if (diffMins >= -10 && diffMins <= 15) {
          multiplier *= 0.6;
          reasons.push("temporal boost (near incident start)");
        } else if (evTime > ctx.incidentDeclaration) {
          multiplier *= 1.4;
          reasons.push("temporal penalty (late stage/recovery)");
        }
      }

      // --- CAUSAL NODE WEIGHTING ---
      if (ctx && (details.service === ctx.rootService || contentLower.includes(ctx.rootService))) {
        multiplier *= 0.7;
        reasons.push("root-service boost");
      }

      if (type === 'deployment' || type === 'commit') {
        multiplier *= 0.6;
        reasons.push("structural boost (deployment/commit)");
      }

      if (type === 'alert' && details && (details.severity === 'CRITICAL' || details.severity === 'SEV-1')) {
        multiplier *= 0.8;
        reasons.push("alert boost (CRITICAL)");
      }
      
      // Text-based heuristics
      for (const bw of boostWords) {
        if (contentLower.includes(bw)) {
          multiplier *= 0.85;
          if (!reasons.includes("keyword boost (causal/symptom)")) {
            reasons.push("keyword boost (causal/symptom)");
          }
        }
      }

      for (const pw of penaltyWords) {
        if (contentLower.includes(pw)) {
          multiplier *= 1.5;
          if (!reasons.includes("keyword penalty (recovery/postmortem)")) {
            reasons.push("keyword penalty (recovery/postmortem)");
          }
        }
      }

      let finalScore = rawScore * multiplier;

      evidenceList.push({
        id: results.ids[0][i],
        type,
        rawScore,
        score: finalScore,
        reasons,
        timestamp,
        content,
        details
      });
    }
  }

  // Sort by the newly adjusted finalScore ascending (lower distance = better match)
  evidenceList.sort((a, b) => a.score - b.score);

  // Return Top 10
  return {
    question,
    evidence: evidenceList.slice(0, 10).map(e => ({
      id: e.id,
      type: e.type,
      rawScore: e.rawScore.toFixed(4),
      score: e.score.toFixed(4),
      reasons: e.reasons,
      timestamp: e.timestamp,
      content: e.content,
      details: e.details
    }))
  };
}

module.exports = { retrieveRootCause };
