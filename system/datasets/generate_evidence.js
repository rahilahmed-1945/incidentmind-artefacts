const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname);

// Services
const services = ['auth-service', 'gateway-service', 'checkout-service', 'user-profile-service', 'redis-cache', 'primary-db', 'payments-service', 'inventory-service', 'notifications-service', 'analytics-service', 'billing-service'];

const randomItem = (arr) => arr[Math.floor(Math.random() * arr.length)];
const randomInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const pad = (n) => n.toString().padStart(2, '0');

function generateDate(baseDate, offsetMinutes) {
  const d = new Date(baseDate);
  d.setMinutes(d.getMinutes() + offsetMinutes);
  d.setSeconds(randomInt(0, 59));
  return d.toISOString();
}

const baseIncidentTime = new Date('2026-06-21T09:00:00Z').getTime();

// --- COMMITS (50) ---
const commits = [];
for (let i = 0; i < 43; i++) {
  const d = new Date(baseIncidentTime - randomInt(1, 1000) * 60000);
  commits.push({
    commitId: Math.random().toString(16).slice(2, 9),
    timestamp: d.toISOString(),
    author: randomItem(['alice', 'bob', 'charlie', 'dave', 'eve', 'mallory']),
    service: randomItem(services),
    message: randomItem(['fix typo', 'update deps', 'refactor', 'add tests', 'update readme', 'fix bug', 'add feature'])
  });
}
// Auth service incident commits
commits.push({ commitId: 'a1b2c3d', timestamp: new Date(baseIncidentTime - 24*3600000).toISOString(), author: 'charlie', service: 'auth-service', message: 'feat: add strict regex validation for JWT tokens' });
commits.push({ commitId: 'e4f5g6h', timestamp: new Date(baseIncidentTime - 12*3600000).toISOString(), author: 'charlie', service: 'auth-service', message: 'fix: optimize regex token matching' });
commits.push({ commitId: 'i7j8k9l', timestamp: new Date(baseIncidentTime - 6*3600000).toISOString(), author: 'eve', service: 'auth-service', message: 'test: add unit tests for token regex' });
commits.push({ commitId: 'm0n1o2p', timestamp: new Date(baseIncidentTime - 2*3600000).toISOString(), author: 'charlie', service: 'auth-service', message: 'chore: prepare release v2.4.1' });
commits.push({ commitId: 'q3r4s5t', timestamp: new Date(baseIncidentTime - 3600000).toISOString(), author: 'eve', service: 'auth-service', message: 'docs: update token auth documentation' });
commits.push({ commitId: 'u6v7w8x', timestamp: new Date(baseIncidentTime + 33*60000).toISOString(), author: 'dave', service: 'auth-service', message: 'revert: "feat: add strict regex validation for JWT tokens"' });
commits.push({ commitId: 'y9z0a1b', timestamp: new Date(baseIncidentTime + 34*60000).toISOString(), author: 'dave', service: 'auth-service', message: 'chore: cut rollback release v2.4.0' });

commits.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

// --- DEPLOYMENTS (10) ---
const deployments = [];
for (let i = 0; i < 8; i++) {
  const d = new Date(baseIncidentTime - randomInt(10, 500) * 60000);
  deployments.push({
    deploymentId: `DEP-${randomInt(1000, 9999)}`,
    timestamp: d.toISOString(),
    service: randomItem(services.filter(s => s !== 'auth-service')),
    version: `v${randomInt(1, 5)}.${randomInt(0, 10)}.${randomInt(0, 20)}`,
    status: 'SUCCESS'
  });
}
deployments.push({ deploymentId: 'DEP-8842', timestamp: '2026-06-21T09:05:00Z', service: 'auth-service', version: 'v2.4.1', status: 'SUCCESS' });
deployments.push({ deploymentId: 'DEP-8843', timestamp: '2026-06-21T09:35:00Z', service: 'auth-service', version: 'v2.4.0', status: 'SUCCESS' });

deployments.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

// --- ALERTS (30) ---
const alerts = [];
for (let i = 0; i < 15; i++) {
  alerts.push({
    timestamp: new Date(baseIncidentTime - randomInt(100, 1000) * 60000).toISOString(),
    service: randomItem(services),
    severity: randomItem(['WARNING', 'INFO']),
    alert: randomItem(['High memory usage', 'Pod restarted', 'CPU threshold near limit', 'Cache miss rate elevated'])
  });
}
// Incident alerts matching timeline
alerts.push({ timestamp: '2026-06-21T09:12:00Z', service: 'auth-service', severity: 'WARNING', alert: 'P99 Latency > 250ms' });
alerts.push({ timestamp: '2026-06-21T09:18:00Z', service: 'auth-service', severity: 'INFO', alert: 'RESOLVED: P99 Latency returned to baseline' });
alerts.push({ timestamp: '2026-06-21T09:20:00Z', service: 'auth-service', severity: 'CRITICAL', alert: 'P99 Latency > 400ms (Traffic Spike Detected)' });
alerts.push({ timestamp: '2026-06-21T09:22:00Z', service: 'gateway-service', severity: 'CRITICAL', alert: 'Elevated 504 Gateway Timeout' });
alerts.push({ timestamp: '2026-06-21T09:24:00Z', service: 'redis-cache', severity: 'CRITICAL', alert: 'Thread pool saturated / High Eviction Rate' });
alerts.push({ timestamp: '2026-06-21T09:25:00Z', service: 'primary-db', severity: 'CRITICAL', alert: 'Connection Pool Exhausted (100%)' });
alerts.push({ timestamp: '2026-06-21T09:27:00Z', service: 'gateway-service', severity: 'SEV-1', alert: 'Global Error Rate > 20% - PagerDuty Triggered' });
alerts.push({ timestamp: '2026-06-21T09:38:00Z', service: 'auth-service', severity: 'INFO', alert: 'P99 Latency normalized' });
alerts.push({ timestamp: '2026-06-21T09:42:00Z', service: 'primary-db', severity: 'INFO', alert: 'Connection Pool < 20%' });

alerts.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

// --- SLACK (40) ---
const slack = [];
for (let i = 0; i < 15; i++) {
  slack.push({
    timestamp: new Date(baseIncidentTime - randomInt(100, 500) * 60000).toISOString(),
    channel: randomItem(['#engineering', '#general', '#random']),
    user: randomItem(['alice', 'bob', 'dave', 'eve', 'mallory']),
    message: randomItem(['Anyone reviewing PR #442?', 'Morning sync at 9:30?', 'The new analytics dashboard looks great.', 'Deployed billing-service v1.2', 'Who is on call today?'])
  });
}
slack.push({ timestamp: '2026-06-21T09:05:10Z', channel: '#deployments', user: 'github-bot', message: 'Deployed auth-service v2.4.1 to production' });
slack.push({ timestamp: '2026-06-21T09:08:00Z', channel: '#engineering', user: 'alice', message: 'Auth latency looking a bit high, checking dashboards.' });
slack.push({ timestamp: '2026-06-21T09:12:05Z', channel: '#alerts-auth', user: 'datadog-bot', message: 'WARNING: auth-service P99 Latency > 250ms' });
slack.push({ timestamp: '2026-06-21T09:15:00Z', channel: '#engineering', user: 'alice', message: 'Oh it\'s fine, just the usual 9am traffic burst. It\'s already dropping. I\'ll ignore for now.' });
slack.push({ timestamp: '2026-06-21T09:18:00Z', channel: '#alerts-auth', user: 'datadog-bot', message: 'RESOLVED: auth-service P99 Latency' });
slack.push({ timestamp: '2026-06-21T09:20:00Z', channel: '#alerts-auth', user: 'datadog-bot', message: 'CRITICAL: auth-service P99 Latency > 400ms' });
slack.push({ timestamp: '2026-06-21T09:20:30Z', channel: '#engineering', user: 'bob', message: 'Spoke too soon, auth is spiking hard right now.' });
slack.push({ timestamp: '2026-06-21T09:22:00Z', channel: '#alerts-api', user: 'datadog-bot', message: 'CRITICAL: gateway-service Elevated 504 Gateway Timeout' });
slack.push({ timestamp: '2026-06-21T09:24:00Z', channel: '#engineering', user: 'charlie', message: 'Wait, Redis CPU is pegged? I am getting checkout timeouts.' });
slack.push({ timestamp: '2026-06-21T09:25:00Z', channel: '#alerts-db', user: 'datadog-bot', message: 'CRITICAL: primary-db Connection Pool Exhausted' });
slack.push({ timestamp: '2026-06-21T09:25:30Z', channel: '#engineering', user: 'dave', message: 'DB connections just maxed out. Everything is failing.' });
slack.push({ timestamp: '2026-06-21T09:27:00Z', channel: '#incident-20260621', user: 'pagerduty', message: 'SEV-1 declared: Global Error Rate > 20%' });
slack.push({ timestamp: '2026-06-21T09:27:30Z', channel: '#incident-20260621', user: 'alice', message: 'I am Incident Commander. Bob is Tech Lead. War room link in topic.' });
slack.push({ timestamp: '2026-06-21T09:29:00Z', channel: '#incident-20260621', user: 'bob', message: 'Auth service CPU is at 100%. Pods are thrashing. Let me try scaling them up.' });
slack.push({ timestamp: '2026-06-21T09:30:00Z', channel: '#incident-20260621', user: 'charlie', message: 'Scaling didn\'t work, new pods instantly hit 100% CPU. Looking at flame graphs... the regex matcher for JWT tokens is taking 300ms per request.' });
slack.push({ timestamp: '2026-06-21T09:32:00Z', channel: '#incident-20260621', user: 'eve', message: 'Wasn\'t there an auth deployment recently?' });
slack.push({ timestamp: '2026-06-21T09:32:30Z', channel: '#incident-20260621', user: 'charlie', message: 'Yes, v2.4.1 went out at 09:05. It added a new regex validation.' });
slack.push({ timestamp: '2026-06-21T09:35:00Z', channel: '#incident-20260621', user: 'alice', message: 'Rolling back auth-service to v2.4.0 now.' });
slack.push({ timestamp: '2026-06-21T09:35:10Z', channel: '#deployments', user: 'github-bot', message: 'Rolling back auth-service to v2.4.0' });
slack.push({ timestamp: '2026-06-21T09:38:00Z', channel: '#incident-20260621', user: 'bob', message: 'Auth latency is dropping back to 25ms!' });
slack.push({ timestamp: '2026-06-21T09:42:00Z', channel: '#incident-20260621', user: 'eve', message: 'DB connections are recovering. Redis CPU is back to 20%.' });
slack.push({ timestamp: '2026-06-21T10:00:00Z', channel: '#incident-20260621', user: 'alice', message: 'Downgrading SEV-1. Will schedule a post-mortem for tomorrow. Good job everyone.' });

slack.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

// --- LOGS (200) ---
const logs = [];
const levels = ['INFO', 'INFO', 'INFO', 'WARN', 'ERROR'];
for (let i = 0; i < 150; i++) {
  logs.push({
    timestamp: new Date(baseIncidentTime - randomInt(1, 1000) * 60000).toISOString(),
    service: randomItem(services),
    level: randomItem(levels),
    message: randomItem(['Processing request', 'Connection established', 'Cache miss', 'Rate limit near threshold', 'Job completed'])
  });
}
// Incident logs
const addLog = (time, srv, lvl, msg) => logs.push({ timestamp: time, service: srv, level: lvl, message: msg });

addLog('2026-06-21T09:05:05Z', 'auth-service', 'INFO', 'Starting auth-service v2.4.1');
addLog('2026-06-21T09:08:00Z', 'auth-service', 'WARN', 'Token validation took 100ms (threshold 50ms)');
addLog('2026-06-21T09:12:00Z', 'auth-service', 'WARN', 'Token validation took 250ms (threshold 50ms)');
addLog('2026-06-21T09:18:00Z', 'auth-service', 'INFO', 'Token validation took 45ms (threshold 50ms) - stabilized');
addLog('2026-06-21T09:20:00Z', 'auth-service', 'ERROR', 'Token validation took 400ms (threshold 50ms)');
for(let i=0; i<5; i++) addLog(`2026-06-21T09:22:${pad(i*10)}Z`, 'gateway-service', 'ERROR', 'Request to auth-service timed out after 500ms');
for(let i=0; i<10; i++) addLog(`2026-06-21T09:23:${pad(i*5)}Z`, 'gateway-service', 'INFO', 'Retrying request to auth-service...');
for(let i=0; i<5; i++) addLog(`2026-06-21T09:24:${pad(i*10)}Z`, 'redis-cache', 'WARN', 'Thread pool saturated, delaying commands');
for(let i=0; i<5; i++) addLog(`2026-06-21T09:24:${pad(i*10 + 5)}Z`, 'checkout-service', 'ERROR', 'Failed to retrieve cart state from redis-cache: Timeout');
for(let i=0; i<5; i++) addLog(`2026-06-21T09:25:${pad(i*10)}Z`, 'auth-service', 'WARN', 'Redis connection failed, falling back to primary-db');
for(let i=0; i<5; i++) addLog(`2026-06-21T09:25:${pad(i*10 + 5)}Z`, 'primary-db', 'ERROR', 'Connection pool exhausted. Rejected 50 connections.');
for(let i=0; i<5; i++) addLog(`2026-06-21T09:26:${pad(i*10)}Z`, 'payments-service', 'ERROR', 'Unable to acquire database connection: timeout 3000ms');
for(let i=0; i<5; i++) addLog(`2026-06-21T09:26:${pad(i*10 + 5)}Z`, 'inventory-service', 'ERROR', 'Unable to acquire database connection: timeout 3000ms');

addLog('2026-06-21T09:35:30Z', 'auth-service', 'INFO', 'Starting auth-service v2.4.0');
addLog('2026-06-21T09:37:30Z', 'auth-service', 'INFO', 'Terminating auth-service v2.4.1');
addLog('2026-06-21T09:38:10Z', 'auth-service', 'INFO', 'Token validation took 22ms');
addLog('2026-06-21T09:39:00Z', 'gateway-service', 'INFO', 'Request to auth-service succeeded');

logs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

fs.writeFileSync(path.join(DIR, 'commits.json'), JSON.stringify(commits, null, 2));
fs.writeFileSync(path.join(DIR, 'deployments.json'), JSON.stringify(deployments, null, 2));
fs.writeFileSync(path.join(DIR, 'alerts.json'), JSON.stringify(alerts, null, 2));
fs.writeFileSync(path.join(DIR, 'slack.json'), JSON.stringify(slack, null, 2));
fs.writeFileSync(path.join(DIR, 'logs.json'), JSON.stringify(logs, null, 2));

console.log("Done");
