const { calculateBlastRadius } = require('../blast-radius/calculate');
const { calculateBusinessImpact } = require('../business-impact/calculate');
const { calculatePredictions } = require('../prediction/calculate');
const { calculateRecovery } = require('../recovery/calculate');
const { calculateParallelUniverse } = require('../parallel-universe/calculate');
const { generateRCA } = require('../rca/generate-rca');

let globalSnapshots = [];

function getSnapshots() {
  return globalSnapshots;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Service State Machine Transition Logic
function determineServiceState(eventText, currentServiceState) {
  const text = eventText.toLowerCase();
  if (text.includes("healthy") || text.includes("baseline") || text.includes("false alarm")) {
    return "HEALTHY";
  }
  if (text.includes("rollback") || text.includes("mitigation") || text.includes("revert")) {
    return "RECOVERING";
  }
  if (text.includes("recovery") || text.includes("stabilize") || text.includes("stabilization") || text.includes("operational") || text.includes("resolved")) {
    return "RECOVERED";
  }
  if (text.includes("timeout") || text.includes("error") || text.includes("exhaustion") || text.includes("failing") || text.includes("saturation") || text.includes("catastrophic") || text.includes("critical") || text.includes("pegs at 100%")) {
    return "CRITICAL";
  }
  if (text.includes("latency") || text.includes("warning") || text.includes("degradation") || text.includes("spike") || text.includes("weak signal")) {
    return (currentServiceState === "CRITICAL") ? "CRITICAL" : "WARNING"; // Don't downgrade CRITICAL to WARNING
  }
  return currentServiceState;
}

// Extractor helper to map services mentioned in an event
const allKnownServices = ["auth-service", "gateway-service", "redis-cache", "checkout-service", "primary-db", "payments-service", "inventory-service", "user-profile-service"];

async function runLiveIncidentEngine(incidentData, eventEmitterCallback, socket, config = {}) {
  const orchestrationConfig = {
    mode: config.mode || "LIVE",
    stageDelayMs: config.stageDelayMs || 1000
  };

  const simulationStart = new Date();
  globalSnapshots = [];
  
  let operatorResolution = null;
  if (socket) {
    socket.on('operator_action', (data) => {
      operatorResolution = data.action;
    });
  }
  
  let activeState = {
    metrics: { deploymentRisk: null, fragilityScore: null, businessSeverity: null },
    nodes: [
      { id: 'gateway-service', type: 'custom', position: { x: 300, y: 50 }, data: { label: 'gateway service', state: 'healthy', subLabel: 'Healthy', iconName: 'CloudRain', influenceScore: 10 } },
      { id: 'auth-service', type: 'custom', position: { x: 100, y: 200 }, data: { label: 'auth service', state: 'healthy', subLabel: 'Healthy', iconName: 'ShieldAlert', influenceScore: 20 } },
      { id: 'user-profile-service', type: 'custom', position: { x: -100, y: 350 }, data: { label: 'user profile service', state: 'healthy', subLabel: 'Healthy', iconName: 'Cpu', influenceScore: 5 } },
      { id: 'checkout-service', type: 'custom', position: { x: 500, y: 200 }, data: { label: 'checkout service', state: 'healthy', subLabel: 'Healthy', iconName: 'Cpu', influenceScore: 30 } },
      { id: 'payments-service', type: 'custom', position: { x: 700, y: 350 }, data: { label: 'payments service', state: 'healthy', subLabel: 'Healthy', iconName: 'Cpu', influenceScore: 25 } },
      { id: 'inventory-service', type: 'custom', position: { x: 500, y: 350 }, data: { label: 'inventory service', state: 'healthy', subLabel: 'Healthy', iconName: 'Database', influenceScore: 15 } },
      { id: 'redis-cache', type: 'custom', position: { x: 300, y: 350 }, data: { label: 'redis cache', state: 'healthy', subLabel: 'Healthy', iconName: 'Database', influenceScore: 40 } },
      { id: 'primary-db', type: 'custom', position: { x: 300, y: 500 }, data: { label: 'primary db', state: 'healthy', subLabel: 'Healthy', iconName: 'Database', influenceScore: 50 } }
    ],
    edges: [
      { id: 'e-gate-auth', source: 'gateway-service', target: 'auth-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-gate-check', source: 'gateway-service', target: 'checkout-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-auth-user', source: 'auth-service', target: 'user-profile-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-check-pay', source: 'checkout-service', target: 'payments-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-check-inv', source: 'checkout-service', target: 'inventory-service', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-check-redis', source: 'checkout-service', target: 'redis-cache', animated: true, style: { stroke: '#06b6d4' } },
      { id: 'e-redis-db', source: 'redis-cache', target: 'primary-db', animated: true, style: { stroke: '#06b6d4' } }
    ],
    narrative: { rootCause: null, propagation: null, remediation: null, confidence: null, blastRadius: null, projection: null, rankedCauses: null },
    events: [],
    forecast: { predictions: [] },
    simulator: null
  };

  const reduceState = (evt) => {
    let next = JSON.parse(JSON.stringify(activeState));

    if (evt.eventType === "RAW_TELEMETRY_EVENT") {
      next.events = [{ id: evt.eventId, source: 'CORAL', timestamp: evt.displayTimestamp, level: 'INFO', message: evt.payload.message }, ...next.events].slice(0, 50);
    } else if (evt.eventType === "SERVICE_STATE_CHANGE") {
      const isCritical = evt.payload.newState === 'CRITICAL';
      next.events = [{ id: evt.eventId, source: 'DATADOG', timestamp: evt.displayTimestamp, level: isCritical ? 'CRITICAL' : 'WARNING', message: `[${evt.payload.service}] State changed: ${evt.payload.oldState} -> ${evt.payload.newState}` }, ...next.events].slice(0, 50);
      next.nodes = next.nodes.map(n => {
        if (n.id === evt.payload.service) {
          return { ...n, data: { ...n.data, state: evt.payload.newState.toLowerCase(), subLabel: evt.payload.newState === 'CRITICAL' ? 'Offline' : evt.payload.newState === 'DEGRADED' || evt.payload.newState === 'WARNING' ? 'Degraded' : 'Healthy' } };
        }
        return n;
      });
      if (evt.payload.newState === 'HEALTHY' || evt.payload.newState === 'RECOVERED') {
        next.edges = next.edges.map(e => {
          if (e.source === evt.payload.service || e.target === evt.payload.service) {
            return { ...e, style: { stroke: '#06b6d4' } };
          }
          return e;
        });
      }

      // Calculate dynamic fragilityScore based on active graph state severity
      const nodeFragilityWeights = { 'healthy': 0, 'warning': 10, 'critical': 25, 'recovering': 5, 'recovered': 0 };
      const dynamicFragility = next.nodes.reduce((acc, node) => acc + (nodeFragilityWeights[node.data.state] || 0), 0);
      const normalizedFragility = Math.min(100, Math.floor(dynamicFragility / 2));
      next.metrics = { ...next.metrics, fragilityScore: normalizedFragility };

    } else if (evt.eventType === "RCA_AVAILABLE") {
      if (!evt.payload || !evt.payload.rootCause) {
        console.warn("RCA_AVAILABLE reducer received null or invalid payload. Skipping narrative updates.");
      } else {
        next.narrative = { ...next.narrative, rootCause: evt.payload.rootCause, confidence: evt.payload.confidence };
        next.events = [{ id: evt.eventId, source: 'CORAL', timestamp: evt.displayTimestamp, level: 'AI INFERENCE', message: `Identified Root Cause: ${evt.payload.rootCause}` }, ...next.events].slice(0, 50);
      }
    } else if (evt.eventType === "BLAST_RADIUS_AVAILABLE") {
      const propagationStr = evt.payload.failurePath ? evt.payload.failurePath.join(" -> ") : (evt.payload.traversalPaths && evt.payload.traversalPaths.length > 0 ? evt.payload.traversalPaths[evt.payload.traversalPaths.length - 1].path : "Unknown");
      next.narrative = { ...next.narrative, blastRadius: evt.payload.directlyImpacted.length + evt.payload.indirectlyImpacted.length, propagation: propagationStr, directlyImpacted: evt.payload.directlyImpacted, indirectlyImpacted: evt.payload.indirectlyImpacted };
      next.edges = next.edges.map(e => {
        if (evt.payload.directlyImpacted.includes(e.target) || evt.payload.indirectlyImpacted.includes(e.target)) {
          return { ...e, style: { stroke: '#ef4444' } };
        }
        return e;
      });
    } else if (evt.eventType === "BUSINESS_IMPACT_AVAILABLE") {
      next.metrics = { ...next.metrics, deploymentRisk: evt.payload.revenueRiskPerHour > 50000 ? 95 : Math.floor(evt.payload.revenueRiskPerHour / 1000), businessSeverity: evt.payload.businessSeverity, revenueRiskPerHour: evt.payload.revenueRiskPerHour, affectedUsers: evt.payload.affectedUsers };
      next.narrative = { ...next.narrative, rankedCauses: [ { service: evt.payload.rootService || "unknown", influence: 95 }, ...(evt.payload.impactedTeams || []).map((team, idx) => ({ service: team, influence: 60 - (idx * 10) })) ] };
    } else if (evt.eventType === "PREDICTION_AVAILABLE") {
      next.forecast = { ...next.forecast, predictions: evt.payload.predictions, escalationMomentum: evt.payload.escalationMomentum };
      if (evt.payload.predictions.length > 0) {
        next.narrative = { ...next.narrative, projection: `AI model predicts ${evt.payload.predictions[0].service} will experience failure within ${evt.payload.predictions[0].estimatedTimeToImpactMinutes} minutes.` };
      }
    } else if (evt.eventType === "RECOVERY_AVAILABLE") {
      next.narrative = { ...next.narrative, remediation: evt.payload.recommendedAction, recoverySuccessProbability: evt.payload.recoverySuccessProbability, expectedRecoveryTimeMinutes: evt.payload.expectedRecoveryTimeMinutes, estimatedRevenueSaved: evt.payload.estimatedRevenueSaved };
    } else if (evt.eventType === "ACTION_REQUIRED") {
      next.narrative = { ...next.narrative, recoveryState: 'ACTION_REQUIRED' };
    } else if (evt.eventType === "ACTION_APPROVED") {
      next.narrative = { ...next.narrative, recoveryState: 'ACTION_APPROVED', executedAction: evt.payload.action };
    } else if (evt.eventType === "ACTION_EXECUTING") {
      next.narrative = { ...next.narrative, recoveryState: 'ACTION_EXECUTING' };
    } else if (evt.eventType === "PARALLEL_UNIVERSE_AVAILABLE") {
      next.simulator = evt.payload;
    } else if (evt.eventType === "INCIDENT_RESOLVED") {
      next.narrative = { ...next.narrative, recoveryState: 'RESOLVED' };
      next.edges = next.edges.map(e => ({ ...e, style: { stroke: '#06b6d4' } }));
    }
    
    activeState = next;
    activeState.timelineStage = currentTimelineStage;
    globalSnapshots.push(JSON.parse(JSON.stringify(activeState)));
  };

  const generateId = () => "evt_" + Math.random().toString(36).substr(2, 9);
  
  const emit = (eventType, payload, actualTimestamp, currentState = "INCIDENT_ACTIVE", nextState = "INCIDENT_ACTIVE", trigger = "system") => {
    const evt = {
      eventId: generateId(),
      eventType,
      actualTimestamp,
      displayTimestamp: new Date().toISOString(),
      currentState,
      nextState,
      trigger,
      payload
    };
    reduceState(evt);
    if (eventEmitterCallback) eventEmitterCallback(evt);
    return evt;
  };

  const asyncSleep = async (multiplier = 1) => {
    if (orchestrationConfig.mode === "LIVE") {
      await sleep(orchestrationConfig.stageDelayMs * multiplier);
    }
  };

  const timeline = incidentData.timeline || [];
  let cascadeTriggered = false;
  let serviceStates = {};
  allKnownServices.forEach(s => serviceStates[s] = "HEALTHY");

  let currentTimelineStage = 'HEALTHY';
  let previousPredictions = [];
  let isRecovering = false;

  // Replay timeline
  for (let i = 0; i < timeline.length; i++) {
    const tEvent = timeline[i];
    const eventText = tEvent.event.toLowerCase();
    
    // Update Timeline Stage based on eventText
    if (eventText.includes("weak signal")) currentTimelineStage = "WEAK_SIGNAL";
    else if (eventText.includes("first warning") || eventText.includes("threshold")) {
      if (currentTimelineStage === "WEAK_SIGNAL" || currentTimelineStage === "HEALTHY") {
        currentTimelineStage = "FIRST_WARNING";
      }
    }
    else if (eventText.includes("stabilization") || eventText.includes("resolv") || eventText.includes("false alarm")) {
      currentTimelineStage = "TEMPORARY_STABILIZATION";
    }
    else if (eventText.includes("repeated warning") || eventText.includes("warning returns")) {
      currentTimelineStage = "REPEATED_WARNING";
    }
    else if (eventText.includes("escalation") || eventText.includes("degradation") || eventText.includes("spike")) {
      currentTimelineStage = "ESCALATION";
    }
    else if (eventText.includes("failing") || eventText.includes("timeout") || eventText.includes("exhaustion")) {
      currentTimelineStage = "DEPENDENCY_FAILURE";
    }
    else if (eventText.includes("sev-1") || eventText.includes("incident declaration")) {
      currentTimelineStage = "SEV-1";
    }

    // Emit RAW TELEMETRY
    emit("RAW_TELEMETRY_EVENT", { message: tEvent.event }, tEvent.timestamp, "MONITORING", "MONITORING", "telemetry_ingest");
    await asyncSleep(0.5);

    // Detect Service State Changes
    const mentionedServices = allKnownServices.filter(s => eventText.includes(s));
    let stateChanged = false;
    for (const service of mentionedServices) {
      const oldState = serviceStates[service];
      const newState = determineServiceState(eventText, oldState);
      
      if (oldState !== newState) {
        serviceStates[service] = newState;
        emit("SERVICE_STATE_CHANGE", { service, oldState, newState }, tEvent.timestamp, oldState, newState, "telemetry_analysis");
        stateChanged = true;
        await asyncSleep(0.5);
      }
    }

    if (stateChanged || currentTimelineStage !== 'HEALTHY') {
        const predResult = calculatePredictions(serviceStates, incidentData.failurePropagation, incidentData.rootService, currentTimelineStage, previousPredictions, isRecovering);
        previousPredictions = predResult.predictions;
        emit("PREDICTION_AVAILABLE", predResult, tEvent.timestamp, "MONITORING", "MONITORING", "continuous_prediction");
    }

    // Intelligence Cascade Trigger
    if (!cascadeTriggered && currentTimelineStage === 'ESCALATION') {
      cascadeTriggered = true;
      const cascadeStartTimestamp = tEvent.timestamp;

      // RCA
      emit("RCA_STARTED", { message: "Root Cause Engine analyzing telemetry..." }, cascadeStartTimestamp, "INCIDENT_DETECTED", "ANALYZING_RCA", "sev1_declaration");
      await asyncSleep(1);
      const rcaResult = await generateRCA("Determine the root cause of the incident cascade based on the provided telemetry, alerts, and deployment logs.");
      emit("RCA_AVAILABLE", rcaResult.rca, cascadeStartTimestamp, "ANALYZING_RCA", "RCA_READY", "rca_analysis_complete");
      await asyncSleep(0.5);

      // Blast Radius
      emit("BLAST_RADIUS_STARTED", { message: "Traversing dependency graph..." }, cascadeStartTimestamp, "RCA_READY", "ANALYZING_BLAST_RADIUS", "rca_available");
      await asyncSleep(1);
      const blastRadius = calculateBlastRadius(incidentData);
      emit("BLAST_RADIUS_AVAILABLE", blastRadius, cascadeStartTimestamp, "ANALYZING_BLAST_RADIUS", "BLAST_RADIUS_READY", "blast_radius_analysis_complete");
      await asyncSleep(0.5);

      // Business Impact
      emit("BUSINESS_IMPACT_STARTED", { message: "Calculating revenue and user risk..." }, cascadeStartTimestamp, "BLAST_RADIUS_READY", "ANALYZING_BUSINESS_IMPACT", "blast_radius_available");
      await asyncSleep(1);
      const businessImpact = calculateBusinessImpact(blastRadius, timeline);
      emit("BUSINESS_IMPACT_AVAILABLE", businessImpact, cascadeStartTimestamp, "ANALYZING_BUSINESS_IMPACT", "BUSINESS_IMPACT_READY", "business_impact_analysis_complete");
      await asyncSleep(0.5);

      // Prediction
      emit("PREDICTION_STARTED", { message: "Simulating downstream degradation pathways..." }, cascadeStartTimestamp, "BUSINESS_IMPACT_READY", "ANALYZING_PREDICTION", "business_impact_available");
      await asyncSleep(1);
      const predictions = calculatePredictions(serviceStates, incidentData.failurePropagation, incidentData.rootService, currentTimelineStage, previousPredictions, false);
      previousPredictions = predictions.predictions;
      emit("PREDICTION_AVAILABLE", predictions, cascadeStartTimestamp, "ANALYZING_PREDICTION", "PREDICTION_READY", "prediction_analysis_complete");
      await asyncSleep(0.5);

      // Recovery
      emit("RECOVERY_STARTED", { message: "Querying historical mitigation sequences..." }, cascadeStartTimestamp, "PREDICTION_READY", "ANALYZING_RECOVERY", "prediction_available");
      await asyncSleep(1);
      const recovery = calculateRecovery(incidentData, blastRadius, businessImpact);
      emit("RECOVERY_AVAILABLE", recovery, cascadeStartTimestamp, "ANALYZING_RECOVERY", "RECOVERY_READY", "recovery_analysis_complete");
      await asyncSleep(0.5);

      // Parallel Universe
      emit("PARALLEL_UNIVERSE_STARTED", { message: "Simulating alternative chronological topologies..." }, cascadeStartTimestamp, "RECOVERY_READY", "ANALYZING_PARALLEL_UNIVERSE", "recovery_available");
      await asyncSleep(1);
      const parallelUniverse = calculateParallelUniverse(incidentData, blastRadius, businessImpact, recovery);
      emit("PARALLEL_UNIVERSE_AVAILABLE", parallelUniverse, cascadeStartTimestamp, "ANALYZING_PARALLEL_UNIVERSE", "PARALLEL_UNIVERSE_READY", "parallel_universe_analysis_complete");
      await asyncSleep(0.5);

      // --- OPERATOR DRIVEN RECOVERY WORKFLOW ---
      if (rcaResult.rca.confidence > 70) {
        emit("ACTION_REQUIRED", { status: "WAITING_FOR_OPERATOR", recommendedAction: recovery.recommendedAction }, cascadeStartTimestamp, "PARALLEL_UNIVERSE_READY", "WAITING_FOR_OPERATOR", "operator_decision_needed");
        
        // Pause timeline playback until operator clicks a button
        while (!operatorResolution) {
          if (orchestrationConfig.mode !== "LIVE") {
            operatorResolution = recovery.recommendedAction; // auto-approve in instant mode
            break;
          }
          await asyncSleep(0.5); // wait 500ms and check again
        }

        const actionTimestamp = new Date().toISOString(); // Simulated time advances
        emit("ACTION_APPROVED", { action: operatorResolution }, actionTimestamp, "WAITING_FOR_OPERATOR", "ACTION_APPROVED", "operator_approved");
        await asyncSleep(1);

        emit("RAW_TELEMETRY_EVENT", { message: `Operator Action: Executed ${operatorResolution}` }, actionTimestamp, "WAITING_FOR_OPERATOR", "ACTION_APPROVED", "telemetry_ingested");
        await asyncSleep(1);

        emit("ACTION_EXECUTING", { action: operatorResolution }, actionTimestamp, "ACTION_APPROVED", "ACTION_EXECUTING", "platform_executing");
        await asyncSleep(2);

        if (operatorResolution === 'Rollback Deployment') {
          // Simulate state recovery visually
          for (const service of blastRadius.directlyImpacted.concat(blastRadius.indirectlyImpacted)) {
            if (serviceStates[service] !== "HEALTHY") {
              const oldState = serviceStates[service];
              serviceStates[service] = "RECOVERING";
              emit("SERVICE_STATE_CHANGE", { service, oldState, newState: "RECOVERING" }, actionTimestamp, oldState, "RECOVERING", "operator_action_effect");
            }
          }
          await asyncSleep(1);

          // Drastically lower risk metrics progressively
          isRecovering = true;
          for (let collapseTick = 0; collapseTick < 3; collapseTick++) {
            const collapsedPreds = calculatePredictions(serviceStates, incidentData.failurePropagation, incidentData.rootService, currentTimelineStage, previousPredictions, isRecovering);
            previousPredictions = collapsedPreds.predictions;
            emit("PREDICTION_AVAILABLE", collapsedPreds, actionTimestamp, "ACTION_EXECUTING", "ACTION_EXECUTING", "risk_recalculation");
            await asyncSleep(1);
          }
          
          const recoveredBusinessImpact = {
            ...businessImpact,
            revenueRiskPerHour: Math.floor(businessImpact.revenueRiskPerHour * 0.05),
            businessSeverity: "LOW"
          };
          emit("BUSINESS_IMPACT_AVAILABLE", recoveredBusinessImpact, actionTimestamp, "ACTION_EXECUTING", "ACTION_EXECUTING", "impact_recalculation");
          await asyncSleep(2);

          // Fully recover nodes
          for (const service of blastRadius.directlyImpacted.concat(blastRadius.indirectlyImpacted).concat([incidentData.rootService])) {
             const oldState = serviceStates[service];
             if (oldState !== "HEALTHY" && oldState !== "RECOVERED") {
                serviceStates[service] = "RECOVERED";
                emit("SERVICE_STATE_CHANGE", { service, oldState, newState: "RECOVERED" }, actionTimestamp, oldState, "RECOVERED", "operator_action_success");
             }
          }
          await asyncSleep(1);

          // Exit generic timeline
          break; 

        } else if (operatorResolution === 'Ignore Warning') {
          // The generic timeline contains a historical rollback. We must break to avoid emitting contradictory events.
          break;
          
        } else if (operatorResolution === 'Enable Fallback') {
          // Recover auth-service, but checkout stays degraded
          serviceStates['auth-service'] = "RECOVERING";
          emit("SERVICE_STATE_CHANGE", { service: "auth-service", oldState: "CRITICAL", newState: "RECOVERING" }, actionTimestamp, "CRITICAL", "RECOVERING", "fallback_engaged");
          await asyncSleep(1);
          serviceStates['auth-service'] = "RECOVERED";
          emit("SERVICE_STATE_CHANGE", { service: "auth-service", oldState: "RECOVERING", newState: "RECOVERED" }, actionTimestamp, "RECOVERING", "RECOVERED", "fallback_active");
          
          // Recalculate impact/risk
          isRecovering = true;
          const collapsedPreds = calculatePredictions(serviceStates, incidentData.failurePropagation, incidentData.rootService, currentTimelineStage, previousPredictions, isRecovering);
          previousPredictions = collapsedPreds.predictions;
          emit("PREDICTION_AVAILABLE", collapsedPreds, actionTimestamp, "ACTION_EXECUTING", "ACTION_EXECUTING", "risk_recalculation");
          
          const recoveredBusinessImpact = { ...businessImpact, revenueRiskPerHour: Math.floor(businessImpact.revenueRiskPerHour * 0.4), businessSeverity: "MEDIUM" };
          emit("BUSINESS_IMPACT_AVAILABLE", recoveredBusinessImpact, actionTimestamp, "ACTION_EXECUTING", "ACTION_EXECUTING", "impact_recalculation");
          await asyncSleep(2);
          
          break;

        } else if (operatorResolution === 'Restart Service') {
          // Temporary improvement
          serviceStates['auth-service'] = "HEALTHY";
          emit("SERVICE_STATE_CHANGE", { service: "auth-service", oldState: "CRITICAL", newState: "HEALTHY" }, actionTimestamp, "CRITICAL", "HEALTHY", "service_restarted");
          await asyncSleep(1);
          
          // Residual risk
          const restartPreds = calculatePredictions(serviceStates, incidentData.failurePropagation, incidentData.rootService, currentTimelineStage, previousPredictions, false);
          previousPredictions = restartPreds.predictions;
          if (restartPreds.predictions.length > 0) restartPreds.predictions[0].riskProbability = 65; // Force residual risk
          emit("PREDICTION_AVAILABLE", restartPreds, actionTimestamp, "ACTION_EXECUTING", "ACTION_EXECUTING", "risk_recalculation");
          
          const partialImpact = { ...businessImpact, revenueRiskPerHour: Math.floor(businessImpact.revenueRiskPerHour * 0.8), businessSeverity: "HIGH" };
          emit("BUSINESS_IMPACT_AVAILABLE", partialImpact, actionTimestamp, "ACTION_EXECUTING", "ACTION_EXECUTING", "impact_recalculation");
          await asyncSleep(2);
          
          break;
        }
      } else {
         emit("SYSTEM_MESSAGE", { message: "Decision Intelligence skipped: RCA confidence below threshold." }, cascadeStartTimestamp, "PARALLEL_UNIVERSE_READY", "MONITORING", "low_confidence_skip");
      }
    }
    
    // Simulate real-time gap between raw timeline events
    await asyncSleep(1.5);
  }

  // Final State
  emit("INCIDENT_RESOLVED", { message: "All services recovered. Incident timeline complete." }, timeline[timeline.length - 1].timestamp, "RECOVERED", "CLOSED", "timeline_exhausted");
}

module.exports = { runLiveIncidentEngine, getSnapshots };
