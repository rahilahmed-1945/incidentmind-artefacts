const { ChromaClient } = require('chromadb');
const { pipeline, env } = require('@xenova/transformers');

// Prevent downloading models every time if possible
env.allowLocalModels = false;

let extractor = null;
const client = new ChromaClient();

async function retrieveSemantic(question) {
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

  const results = await collection.query({
    queryEmbeddings: [queryEmbedding],
    nResults: 10
  });

  const evidence = [];
  if (results.ids[0]) {
    for (let i = 0; i < results.ids[0].length; i++) {
      evidence.push({
        type: results.metadatas[0][i].type,
        score: results.distances[0][i].toString(), // smaller distance usually means more similar in Chroma
        timestamp: results.metadatas[0][i].timestamp,
        content: results.documents[0][i],
        details: JSON.parse(results.metadatas[0][i].data)
      });
    }
  }

  return {
    question,
    evidence
  };
}

module.exports = { retrieveSemantic };
