const express = require("express");
const cors = require("cors");
const axios = require("axios");
const { exec } = require("child_process");
const http = require("http");
const { Server } = require("socket.io");
require("dotenv").config();

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*" }
});

app.use(cors());
app.use(express.json());

let githubContext = { sha: null, author: null, message: null };
let slackContext = [];

app.get("/history", (req, res) => {
  const { getSnapshots } = require('./server/incident-engine/calculate');
  res.json(getSnapshots());
});

app.post("/analyze", async (req, res) => {
  const userQuery = req.body.query || "What caused the checkout failure?";
  
  try {
    const { getSnapshots } = require('./server/incident-engine/calculate');
    const snapshots = getSnapshots();
    const latestState = snapshots.length > 0 ? snapshots[snapshots.length - 1] : null;

    const { processQuestion } = require('./server/ask-incidentmind/ask');
    const result = await processQuestion(userQuery, latestState);

    res.json({
      evidence: result.evidence,
      analysis: result.analysis,
    });
  } catch (err) {
    res.status(500).json({
      error: err.message,
    });
  }
});

const fs = require('fs');
const path = require('path');
const { runLiveIncidentEngine, getSnapshots } = require('./server/incident-engine/calculate');

const incidentPath = path.join(__dirname, 'datasets/incidents/incident-001.json');
const incidentData = JSON.parse(fs.readFileSync(incidentPath, 'utf8'));

// WebSocket Streaming
io.on('connection', (socket) => {
  console.log('Client connected for live telemetry');
  
  const emitToClient = (evt) => {
    socket.emit('incident_event', evt);
  };
  
  runLiveIncidentEngine(incidentData, emitToClient, socket, { mode: 'LIVE', stageDelayMs: 1000 })
    .then(() => console.log('Incident simulation complete for client'))
    .catch(err => console.error('Simulation error:', err));

  socket.on('disconnect', () => {
    console.log('Client disconnected');
  });
});

const PORT = process.env.PORT || 3000;

server.listen(PORT, () => {
  console.log(`IncidentMind server running on port ${PORT} (HTTP & WebSockets)`);
});