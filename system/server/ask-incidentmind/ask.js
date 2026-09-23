require('dotenv').config();
const axios = require('axios');
const { retrieveSemanticV2 } = require('../rag/index');

async function processQuestion(question, engineContext) {
  // 1. Retrieve evidence
  const retrieval = await retrieveSemanticV2(question);
  const evidenceList = retrieval.evidence || [];

  // Format evidence
  const evidenceText = evidenceList.map(e => {
    return `[Type: ${e.type}] ${e.timestamp || ''}
Content: ${e.content}
Details: ${JSON.stringify(e.details)}`;
  }).join('\n\n');

  // Format Engine Context
  let contextString = "No active engine context available.";
  if (engineContext) {
    const { metrics, forecast, simulator, narrative, timelineStage } = engineContext;
    contextString = `
Current Active State Context:
- Prediction (Peak Risk): ${forecast?.predictions?.[0]?.riskProbability || 'Unknown'}%
- RCA Root Cause: ${narrative?.rootCause || 'None'}
- RCA Recommendation: ${narrative?.remediation || 'None'}
- Business Impact (Revenue Lost): INR ${metrics?.revenueRiskPerHour || 0} per hour
- Business Impact (Users Impacted): ${metrics?.affectedUsers || 0} users
- Recovery (Expected MTTR): ${narrative?.expectedRecoveryTimeMinutes || 'Unknown'} minutes
- Recovery (Estimated Revenue Saved): INR ${narrative?.estimatedRevenueSaved || 0}
- Parallel Universe (Best Alternative Score): ${simulator?.bestScenario?.scenarioScore || 'None'}
- Parallel Universe Scenarios:
${simulator?.alternativeScenarios?.map(s => `  * ${s.scenarioName}: Saved INR ${s.revenueSaved || 0}, MTTR Reduced by ${s.mttrReduction || 0}m, Users Protected: ${s.usersProtected || 0}`).join('\n') || '  None'}
- Blast Radius (Direct): ${narrative?.directlyImpacted?.join(', ') || 'Unknown'}
- Blast Radius (Indirect): ${narrative?.indirectlyImpacted?.join(', ') || 'Unknown'}
- Dependency Propagation Path: ${narrative?.propagation || 'Unknown'}
- Timeline Stage: ${timelineStage || 'Unknown'}
- Decision Intelligence State: ${narrative?.recoveryState || 'Unknown'}
- Current Recommended Action (Best Intervention Path): ${narrative?.remediation || 'Unknown'}
    `;
  }

  const systemPrompt = `You are IncidentMind, an autonomous operational copilot.
Your task is to answer the user's question using ONLY the provided operational evidence and current engine state context.

EVIDENCE:
${evidenceText}

ENGINE CONTEXT:
${contextString}

CRITICAL INSTRUCTIONS:
1. Do not hallucinate data, users, or systems that are not in the evidence.
2. If the user asks about peak risk, business impact, or alternative scenarios, use the ENGINE CONTEXT.
3. Keep the response concise, professional, and operational.
4. If the user asks about cause, failure, bottleneck, impact, propagation, outage, regression, deployment, RCA, blast radius, or affected services, prioritize the RCA Root Cause and Engine Context over raw retrieved evidence.
5. Use retrieved evidence to support the RCA, not override it.
6. When explaining service impact, use dependency propagation and blast radius data.
7. If the user asks a question unrelated to operational intelligence (e.g. math, trivia, politics, general knowledge), respond: "This question is outside the operational data available to IncidentMind. I can answer questions about incidents, deployments, RCA, blast radius, predictions, business impact, recovery actions, and operational history."
8. If the user asks for exact counts across the company history (e.g. total commits, total alerts, total deployments), state that answers are based on the retrieved evidence window unless full-dataset aggregation is available.
`;

  console.log("=== ENGINE CONTEXT ===");
  console.log(contextString);
  console.log("======================");

  const userPrompt = `Question: ${question}`;

  if (!process.env.OPENROUTER_API_KEY) {
    console.warn("Missing OPENROUTER_API_KEY. Falling back to deterministic copilot generation.");
    return fallbackDeterministicAnswer(question, evidenceList, engineContext);
  }

  try {
    const response = await axios.post(
      'https://openrouter.ai/api/v1/chat/completions',
      {
        model: 'openai/gpt-oss-120b:free',
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

    const analysis = response.data.choices[0].message.content;

    return {
      evidence: evidenceList,
      analysis: analysis
    };
  } catch (error) {
    console.warn("OpenRouter API failed. Falling back to deterministic copilot generation.", error.response ? error.response.data : error.message);
    return fallbackDeterministicAnswer(question, evidenceList, engineContext);
  }
}

function fallbackDeterministicAnswer(question, evidenceList, engineContext) {
  const q = question.toLowerCase();
  
  // Engine Context Extracts
  const peakRisk = engineContext?.forecast?.predictions?.[0]?.riskProbability || 'Unknown';
  const rcaAction = engineContext?.narrative?.remediation || 'Unknown';
  const rcaCause = engineContext?.narrative?.rootCause || null;

  let analysis = rcaCause 
    ? `Current IncidentMind analysis indicates: ${rcaCause}\n\nReview the retrieved operational evidence for full technical details.`
    : "Based on the retrieved evidence, I cannot definitively answer this question.";

  if (q.includes("cause") || q.includes("fault") || q.includes("bottleneck") || q.includes("trigger") || q.includes("why") || q.includes("happened") || q.includes("origin") || q.includes("regression")) {
    if (rcaCause) {
      analysis = `The evidence strongly aligns with the current RCA deduction: ${rcaCause}`;
    } else {
      const deployments = evidenceList.filter(e => e.type === 'deployment');
      if (deployments.length > 0) {
        analysis = `The retrieved evidence suggests a regression introduced during the recent deployment to ${deployments[0].details?.service || 'the system'}.`;
      }
    }
  } else if (q.includes("who") || q.includes("deploy") || q.includes("engineer")) {
    const deployments = evidenceList.filter(e => e.type === 'deployment' || e.type === 'commit');
    if (deployments.length > 0) {
      const d = deployments[0];
      const author = d.details?.author || d.content.match(/author: ([a-zA-Z]+)/)?.[1] || "an unknown engineer";
      const service = d.details?.service || "the system";
      analysis = `According to the logs, ${author} deployed an update to ${service} recently.`;
    }
  } else if (q.includes("risk") || q.includes("peak") || q.includes("prediction")) {
    analysis = `The Prediction Engine currently estimates a Peak Risk of ${peakRisk}% based on downstream propagation vectors.`;
  } else if (q.includes("recover") || q.includes("fix") || q.includes("action")) {
    analysis = `The RCA Engine recommends: ${rcaAction}.`;
  } else if (q.includes("what failed") || q.includes("affected")) {
    const alerts = evidenceList.filter(e => e.type === 'alert');
    if (alerts.length > 0) {
      analysis = `Critical alerts indicate failures originating in ${alerts[0].details?.service || 'upstream services'} with message: "${alerts[0].content}".`;
    }
  }

  return {
    evidence: evidenceList,
    analysis: analysis
  };
}

module.exports = { processQuestion };
