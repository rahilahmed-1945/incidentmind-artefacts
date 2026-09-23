const { ChromaClient } = require('chromadb');
const { pipeline, env } = require('@xenova/transformers');

// Prevent downloading models every time if possible
env.allowLocalModels = false;

let extractor = null;
const client = new ChromaClient();

// Words that indicate root cause/failure discovery
const boostWords = ['latency', 'timeout', 'cpu', 'maxed out', 'regex', 'saturation', 'exhaustion', 'failing', 'spike'];
// Words that indicate recovery/resolution
const penaltyWords = ['recovering', 'subsiding', 'stable', 'post-mortem', 'downgrading', 'recovery', 'drops', 'normalizes'];

async function retrieveSemanticV2(question) {
  if (!extractor) {
    extractor = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');
  }

  // Embed the question
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

  // Fetch a wider net to allow reranking (e.g., top 30)
  const results = await collection.query({
    queryEmbeddings: [queryEmbedding],
    nResults: 30
  });

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

      // --- BOOSTS (Reduce distance) ---
      if (type === 'deployment' || type === 'commit') {
        multiplier *= 0.7; // Strong boost for changes
      }
      if (type === 'alert' && details && (details.severity === 'CRITICAL' || details.severity === 'SEV-1')) {
        multiplier *= 0.8; // Boost severe alerts
      }
      
      // Text-based heuristics
      for (const bw of boostWords) {
        if (contentLower.includes(bw)) multiplier *= 0.9;
      }

      // --- PENALTIES (Increase distance) ---
      for (const pw of penaltyWords) {
        if (contentLower.includes(pw)) multiplier *= 1.4;
      }

      let finalScore = rawScore * multiplier;

      evidenceList.push({
        id: results.ids[0][i],
        type,
        rawScore,
        score: finalScore,
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
      score: e.score.toFixed(4),
      timestamp: e.timestamp,
      content: e.content,
      details: e.details
    }))
  };
}

module.exports = { retrieveSemanticV2 };
