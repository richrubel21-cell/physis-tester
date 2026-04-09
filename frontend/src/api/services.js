import client from "./client";

export const api = {
  // Scenarios
  generateScenarios: (count = 10, useAi = true) =>
    client.post(`/scenarios/generate?count=${count}&use_ai=${useAi}`).then(r => r.data),
  listScenarios: () =>
    client.get("/scenarios/").then(r => r.data),

  // Runs / Batches
  startBatch: (count = 10, useAi = true) =>
    client.post("/runs/batch", { count, use_ai: useAi }).then(r => r.data),
  getBatch: (batchId) =>
    client.get(`/runs/batch/${batchId}`).then(r => r.data),
  listBatches: () =>
    client.get("/runs/").then(r => r.data),

  // Single run
  runSingle: (description) =>
    client.post("/simulator/run", { description }).then(r => r.data),

  // Analytics
  getSummary: () =>
    client.get("/analytics/summary").then(r => r.data),
  getFailures: () =>
    client.get("/analytics/failures").then(r => r.data),
  getBatchAnalytics: (batchId) =>
    client.get(`/analytics/batch/${batchId}`).then(r => r.data),

  // Mary testing vertical
  startMaryBatch: (count = 10, useAi = true) =>
    client.post("/mary/batch", { count, use_ai: useAi }).then(r => r.data),
  getMaryBatch: (batchId) =>
    client.get(`/mary/batch/${batchId}`).then(r => r.data),
  listMaryBatches: () =>
    client.get("/mary/").then(r => r.data),
};
