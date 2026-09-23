const fs = require('fs');
const path = require('path');
const { ChromaClient } = require('chromadb');
const { pipeline, env } = require('@xenova/transformers');

// Prevent downloading models every time if possible (caches locally)
env.allowLocalModels = false;

const datasetsPath = path.join(__dirname, '..', '..', 'datasets');
const loadJson = (filename) => JSON.parse(fs.readFileSync(path.join(datasetsPath, filename), 'utf8'));

async function ingest() {
  console.log("Loading datasets...");
  const commits = loadJson('commits.json');
  const logs = loadJson('logs.json');
  const alerts = loadJson('alerts.json');
  const slack = loadJson('slack.json');
  const deployments = loadJson('deployments.json');
  const incident001 = loadJson('incidents/incident-001.json');

  let allEvidence = [];

  commits.forEach(c => allEvidence.push({ id: `commit_${c.commitId}`, type: 'commit', timestamp: c.timestamp, text: `${c.service} commit by ${c.author}: ${c.message}`, data: c }));
  logs.forEach((l, i) => allEvidence.push({ id: `log_${i}`, type: 'log', timestamp: l.timestamp, text: `${l.service} [${l.level}]: ${l.message}`, data: l }));
  alerts.forEach((a, i) => allEvidence.push({ id: `alert_${i}`, type: 'alert', timestamp: a.timestamp, text: `${a.service} [${a.severity}]: ${a.alert}`, data: a }));
  slack.forEach((s, i) => allEvidence.push({ id: `slack_${i}`, type: 'slack', timestamp: s.timestamp, text: `${s.channel} user ${s.user}: ${s.message}`, data: s }));
  deployments.forEach((d, i) => allEvidence.push({ id: `deploy_${i}`, type: 'deployment', timestamp: d.timestamp, text: `Deployment ${d.status} on ${d.service} version ${d.version}`, data: d }));
  
  const incidents = Array.isArray(incident001) ? incident001 : [incident001];
  incidents.forEach((inc, i) => {
    allEvidence.push({ id: `incident_${i}`, type: 'incident', timestamp: inc.timeline && inc.timeline[0] ? inc.timeline[0].timestamp : '', text: `Incident ${inc.severity} on ${inc.rootService}: ${inc.title} - ${inc.summary}`, data: inc });
  });

  console.log(`Loaded ${allEvidence.length} total evidence items.`);
  console.log("Initializing xenova/all-MiniLM-L6-v2 pipeline...");
  const extractor = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');

  console.log("Initializing ChromaDB Client...");
  const client = new ChromaClient();
  const dummyEmbeddingFunction = {
    generate: async (texts) => { return texts.map(() => Array(384).fill(0)); }
  };
  let collection;
  try {
    collection = await client.getOrCreateCollection({
      name: "incident_evidence",
      embeddingFunction: dummyEmbeddingFunction,
      metadata: { "hnsw:space": "cosine" }
    });
  } catch (err) {
    console.error("Failed to connect to ChromaDB. Ensure it is running on http://localhost:8000.");
    throw err;
  }

  // Clear existing items if any to avoid duplicates in this demo
  try {
    const existing = await collection.get();
    if (existing && existing.ids && existing.ids.length > 0) {
      await collection.delete({ ids: existing.ids });
    }
  } catch(e) {}

  console.log("Generating embeddings and indexing into ChromaDB (this may take a moment)...");
  
  // Batch processing
  const batchSize = 100;
  for (let i = 0; i < allEvidence.length; i += batchSize) {
    const batch = allEvidence.slice(i, i + batchSize);
    const ids = batch.map(e => e.id);
    const documents = batch.map(e => e.text);
    const metadatas = batch.map(e => ({ type: e.type, timestamp: e.timestamp, data: JSON.stringify(e.data) }));

    const embeddings = [];
    for (const doc of documents) {
      const output = await extractor(doc, { pooling: 'mean', normalize: true });
      embeddings.push(Array.from(output.data));
    }

    await collection.add({
      ids,
      embeddings,
      metadatas,
      documents
    });
    
    console.log(`Indexed batch ${Math.floor(i / batchSize) + 1}/${Math.ceil(allEvidence.length / batchSize)}`);
  }

  console.log("Indexing complete.");
}

module.exports = { ingest };

// If run directly
if (require.main === module) {
  ingest().catch(console.error);
}
