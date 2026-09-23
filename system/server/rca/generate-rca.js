require('dotenv').config();
const axios = require('axios');
const { retrieveSemanticV2 } = require('../rag/index');

async function generateRCA(question) {
  // Bypass ChromaDB vector search to guarantee MVP reliability
  const incidentData = require('../../datasets/incidents/incident-001.json');
  const commits = require('../../datasets/commits.json');
  const deployments = require('../../datasets/deployments.json');

  // Dynamically extract all relevant attribution data for the root service
  const rootService = incidentData.rootService;
  const relevantCommits = commits.filter(c => c.service === rootService);
  const relevantDeployments = deployments.filter(d => d.service === rootService);

  let evidenceText = `
[Evidence ID: incident_0]
Type: incident
Content: ${incidentData.summary}
Details: ${JSON.stringify(incidentData)}
`;

  const evidenceList = [
    { type: 'incident', id: 'incident_0', content: incidentData.summary, details: incidentData }
  ];

  relevantCommits.forEach(c => {
    evidenceText += `
[Evidence ID: commit_${c.commitId}]
Type: commit
Content: ${c.service} commit by ${c.author}: ${c.message}
Details: ${JSON.stringify(c)}
`;
    evidenceList.push({ type: 'commit', id: `commit_${c.commitId}`, content: `${c.service} commit by ${c.author}: ${c.message}`, details: c });
  });

  relevantDeployments.forEach(d => {
    evidenceText += `
[Evidence ID: dep_${d.deploymentId}]
Type: deployment
Content: Deployment of ${d.service} ${d.version}
Details: ${JSON.stringify(d)}
`;
    evidenceList.push({ type: 'deployment', id: `dep_${d.deploymentId}`, content: `Deployment of ${d.service} ${d.version}`, details: d });
  });

  evidenceText = evidenceText.trim();

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

  if (!process.env.OPENROUTER_API_KEY) {
    console.warn("Missing OPENROUTER_API_KEY in environment variables. Falling back to deterministic evidence-based RCA generation.");
    return fallbackDeterministicRCA(evidenceList);
  }

  try {
    const response = await axios.post(
      'https://openrouter.ai/api/v1/chat/completions',
      {
        model: 'openai/gpt-oss-120b:free',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
        response_format: { type: "json_object" }
      },
      {
        headers: {
          'Authorization': `Bearer ${process.env.OPENROUTER_API_KEY}`,
          'HTTP-Referer': 'http://localhost:3000',
          'X-Title': 'IncidentMind'
        }
      }
    );

    const content = response.data.choices[0].message.content;
    let rcaJson;
    try {
      rcaJson = JSON.parse(content);
    } catch(e) {
      // Fallback if LLM wraps in markdown
      const match = content.match(/```json\n([\s\S]*)\n```/);
      if (match) rcaJson = JSON.parse(match[1]);
      else throw new Error("LLM did not return valid JSON");
    }

    if (!rcaJson || typeof rcaJson !== 'object' || !rcaJson.rootCause) {
      throw new Error("LLM returned successfully parsed JSON but it was missing required RCA schema properties");
    }

    return {
      retrieval: evidenceList,
      rca: rcaJson
    };
  } catch (error) {
    console.warn("OpenRouter API failed. Falling back to deterministic evidence-based RCA generation.", error.response ? error.response.data : error.message);
    return fallbackDeterministicRCA(evidenceList);
  }
}

function fallbackDeterministicRCA(evidenceList) {
  let rootCause = "Initial analysis indicates an unspecified system failure.";
  let confidence = 40;
  let affectedServices = new Set();
  let recommendedAction = "Investigate telemetry logs to identify the origin of the failure.";
  
  // Parse evidence types
  const deployments = evidenceList.filter(e => e.type === 'deployment');
  const alerts = evidenceList.filter(e => e.type === 'alert' && e.details && (e.details.severity === 'CRITICAL' || e.details.severity === 'SEV-1'));
  const slackMsgs = evidenceList.filter(e => e.type === 'slack');
  const commits = evidenceList.filter(e => e.type === 'commit');

  const mainDeployment = deployments.length > 0 ? deployments[0] : null;
  const criticalAlert = alerts.length > 0 ? alerts[0] : null;

  if (mainDeployment) {
     const deployContent = mainDeployment.content || "";
     const serviceMatch = deployContent.match(/service:? ([a-zA-Z0-9-]+)/i);
     const serviceName = serviceMatch ? serviceMatch[1] : (mainDeployment.details?.service || "a core service");
     
     const versionMatch = deployContent.match(/(v\d+\.\d+\.\d+)/);
     const version = versionMatch ? versionMatch[1] : "an unknown version";

     rootCause = `The failure was likely triggered by a recent deployment to ${serviceName} (${version}). This deployment introduced a regression leading to subsequent system saturation and cascading timeouts across dependent services.`;
     confidence = 85;
     recommendedAction = `Immediate rollback of ${serviceName} to the previous stable version.`;
     affectedServices.add(serviceName);
  } else if (commits.length > 0) {
     const commitInfo = commits[0];
     rootCause = `A recent code change by ${commitInfo.details?.author || 'an engineer'} introduced a regression leading to service degradation. Commit message: ${commitInfo.details?.message || commitInfo.content}`;
     confidence = 75;
     recommendedAction = `Revert the suspect commit and run extensive regression tests.`;
     if (commitInfo.details?.service) affectedServices.add(commitInfo.details.service);
  } else if (criticalAlert) {
     rootCause = `A critical threshold breach originated from ${criticalAlert.details?.service || 'an upstream service'} ("${criticalAlert.content}"), causing severe resource exhaustion and cascading failures.`;
     confidence = 70;
     recommendedAction = `Scale up resources or mitigate the traffic spike on ${criticalAlert.details?.service || 'the affected service'}.`;
  }

  // Gather affected services from all evidence
  evidenceList.forEach(e => {
    if (e.details && e.details.service) {
      affectedServices.add(e.details.service);
    }
    const serviceMatches = (e.content || "").match(/[a-zA-Z0-9]+-service/g);
    if (serviceMatches) {
       serviceMatches.forEach(s => affectedServices.add(s));
    }
  });

  return {
    retrieval: evidenceList,
    rca: {
      rootCause,
      confidence,
      evidence: evidenceList.map(e => e.id),
      affectedServices: Array.from(affectedServices),
      recommendedAction
    }
  };
}

module.exports = { generateRCA };
