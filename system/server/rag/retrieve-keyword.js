const fs = require('fs');
const path = require('path');

// Load datasets
const datasetsPath = path.join(__dirname, '..', '..', 'datasets');
const loadJson = (filename) => JSON.parse(fs.readFileSync(path.join(datasetsPath, filename), 'utf8'));

const commits = loadJson('commits.json');
const logs = loadJson('logs.json');
const alerts = loadJson('alerts.json');
const slack = loadJson('slack.json');
const deployments = loadJson('deployments.json');
const incident001 = loadJson('incidents/incident-001.json');

let allEvidence = [];

// Flatten into standard format for retrieval
commits.forEach(c => allEvidence.push({ type: 'commit', timestamp: c.timestamp, text: `${c.service} commit by ${c.author}: ${c.message}`, data: c }));
logs.forEach(l => allEvidence.push({ type: 'log', timestamp: l.timestamp, text: `${l.service} [${l.level}]: ${l.message}`, data: l }));
alerts.forEach(a => allEvidence.push({ type: 'alert', timestamp: a.timestamp, text: `${a.service} [${a.severity}]: ${a.alert}`, data: a }));
slack.forEach(s => allEvidence.push({ type: 'slack', timestamp: s.timestamp, text: `${s.channel} user ${s.user}: ${s.message}`, data: s }));
deployments.forEach(d => allEvidence.push({ type: 'deployment', timestamp: d.timestamp, text: `Deployment ${d.status} on ${d.service} version ${d.version}`, data: d }));

// Handle incident (if it's an array or object)
const incidents = Array.isArray(incident001) ? incident001 : [incident001];
incidents.forEach(i => {
  allEvidence.push({ type: 'incident', timestamp: i.timeline && i.timeline[0] ? i.timeline[0].timestamp : '', text: `Incident ${i.severity} on ${i.rootService}: ${i.title} - ${i.summary}`, data: i });
});

// Basic stop words to ignore during tokenization
const stopWords = new Set(['why', 'is', 'what', 'changed', 'after', 'which', 'were', 'happened', 'before', 'the', 'caused', 'a', 'to', 'of', 'in', 'and', 'for', 'on', 'by', 'it', 'this', 'that']);

// Simple tokenizer
function tokenize(text) {
  return text.toLowerCase().split(/\W+/).filter(w => w.length > 2 && !stopWords.has(w));
}

function retrieve(question) {
  const queryTokens = tokenize(question);
  
  // Score each item
  const scored = allEvidence.map(item => {
    let score = 0;
    const itemTokens = tokenize(item.text);
    const itemTextLower = item.text.toLowerCase();
    
    // Token matches
    queryTokens.forEach(qt => {
      // Direct token match
      if (itemTokens.includes(qt)) {
        score += 10;
        
        // Give extra weight to highly specific keywords in our incident domain
        if (['v2.4.1', 'sev-1', 'database', 'saturation', 'checkout', 'deploy', 'failing', 'impacted', 'declaration'].includes(qt)) {
          score += 10; 
        }
      } else {
        // Partial token match (e.g., 'deploy' matching 'deployment')
        const partialMatch = itemTokens.some(it => it.includes(qt) || qt.includes(it));
        if (partialMatch) score += 5;
      }
    });

    // Domain-specific heuristic boosts based on question intent
    if (queryTokens.includes('deploy') || queryTokens.includes('v2.4.1')) {
      if (item.type === 'deployment' || item.type === 'commit') score += 15;
    }
    if (queryTokens.includes('sev-1') || queryTokens.includes('declaration')) {
      if (item.type === 'alert' || item.type === 'slack') score += 15;
    }
    if (queryTokens.includes('failing') || queryTokens.includes('impacted')) {
      if (item.type === 'alert' || item.level === 'ERROR') score += 10;
    }

    return { ...item, score };
  });

  // Filter items with score > 0, sort by score descending, then chronologically if scores match
  let results = scored.filter(i => i.score > 0);
  results.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score; // Highest score first
    return new Date(a.timestamp) - new Date(b.timestamp); // Chronological
  });

  return {
    question,
    evidence: results.slice(0, 10).map(r => ({
      type: r.type,
      timestamp: r.timestamp,
      relevanceScore: r.score,
      details: r.data
    }))
  };
}

module.exports = { retrieve };
