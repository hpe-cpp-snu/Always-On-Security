# Always-On Security Platform

An always-on security monitoring and automated remediation system for airgapped monolithic HPC clusters.

This branch integrates a simulated HPC job-scheduling engine with an autonomous security telemetry collector, a cumulative risk-scoring engine, and an automated Docker-based node quarantine system.

---

## 5-Layer Architecture

The system operates across five distinct layers:

1. **Layer 1: Node Agents (`project/node/`)** — Collect system metrics (CPU, memory, processes), run local anomaly checks, execute incoming HPC jobs, and send health telemetry.
2. **Layer 2: ZeroMQ Transport** — The message-passing backbone connecting the components:
   * **Port 5555 (PUSH/PULL):** `job_provider` submits workloads to `controller`.
   * **Port 5556 (PUSH/PULL):** `controller` dispatches jobs to `node_agents`.
   * **Port 5557 (PUSH/PULL):** `node_agents` send completions to `controller`.
   * **Port 5558 (PUSH/PULL):** `node_agents` stream metrics/alerts to `controller`.
3. **Layer 3: Risk Engine (`project/controller/`)** — Assesses cumulative risk scores dynamically. Features context-aware threshold checks and risk decay (self-healing).
4. **Layer 4: Auto-Remediation (`project/controller/`)** — Monitors risk levels and initiates container-based node isolation/quarantine via the Docker API.
5. **Layer 5: Dashboard (`project/dashboard/`)** — A Flask-based web application showing real-time statistics, job queues, node states, and security events.

```
                    ┌──────────────┐
                    │ job_provider │  Simulates HPC workloads
                    └──────┬───────┘
                           │ ZMQ :5555
                           ▼
               ┌───────────────────────┐
               │      CONTROLLER       │
               │  Job Scheduler        │◄── ZMQ :5557 (completions)
               │  Security Monitor     │◄── ZMQ :5558 (telemetry)
               │  Risk Engine          │
               │  Heartbeat Checker    │
               │  Auto Remediator      │──► Docker API
               │  DB Writer            │──► SQLite
               └───────────┬───────────┘
                    ZMQ :5556 │
                           ▼
                ┌──────────────────┐
                │   NODE AGENTS    │  ×4 (node1 to node4)
                │  Job Worker      │
                │  Telemetry       │
                │  Anomaly Detect  │
                └──────────────────┘

               ┌───────────────────────┐
               │      DASHBOARD        │
               │  Flask + SQLite       │
               │  localhost:5000       │
               └───────────────────────┘
```

---

## Key Features

* **Job-Aware Anomaly Detection:** Node agents evaluate system usage intelligently. For instance, high CPU usage is normal during a CPU job and won't flag an alert, but will raise a security event if the node is supposed to be idle.
* **Cumulative Risk Scoring & Self-Healing:** The controller maintains a cumulative risk score for each node rather than acting on single alerts. If anomalies cease, the risk score decays slowly (`-5` points per interval) back to 0.
* **Heartbeat Monitor:** Detects silent node failures or network partitioning. If a node fails to send telemetry for 30 seconds, it is marked as unresponsive.
* **Automated Quarantine:** Once a node's cumulative risk score hits or exceeds `100`, the controller automatically communicates with the local Docker daemon to stop the compromised node's container immediately.

---

## Security Detection Rules

| Rule | Trigger condition | Risk Increment |
| :--- | :--- | :--- |
| **High CPU** | CPU > 80% (ignored if running `cpu` job) | `+20` risk points |
| **High Memory** | Memory > 85% (ignored if running `memory_access` job) | `+20` risk points |
| **Too Many Processes** | Running process count > 300 | `+25` risk points |
| **Suspicious Process** | Binary name match (e.g. `nmap`, `hydra`, `nc`, `stress`) | `+40` risk points |
| **Heartbeat Loss** | No telemetry received for 30s | Flagged as unresponsive |

---

## Simulated Attack & Demo Scenario

To demonstrate automated quarantine and observability without manual intervention, a **built-in threat simulator** runs inside the node agents:

1. **Triggering the Attack:** Every 5 seconds, each node has a small chance (8% for `node1` to speed up the demo, 3% for others) to initiate a threat simulation.
2. **Escalation Stages:** Once initiated, the simulation escalates stage-by-stage every 5 seconds:
   * **Stage 1 (High CPU):** Agent overrides CPU usage to 92.5% (`+20` risk points if idle).
   * **Stage 2 (High Memory):** Agent overrides Memory usage to 88.0% (`+20` risk points).
   * **Stage 3 (High Process Count):** Agent overrides Process Count to 310 (`+25` risk points).
   * **Stage 4 (Intrusion Process):** Agent simulates detection of the suspicious `hydra` brute-forcer process (`+40` risk points).
3. **Quarantine:** The cumulative risk score exceeds `100` (e.g., `20 + 20 + 25 + 40 = 105`). The controller intercepts this, stops the node's Docker container, and marks its status as **quarantined**.
4. **Dashboard Feedback:** Open the dashboard at `http://localhost:5000` to see the live telemetry alerts, the step-by-step risk score escalation, the quarantine event, and the node's status change.

---

## Quick Start

### 1. Launch the Cluster
Run the following inside the `project/` directory:
```bash
cd project
docker compose up --build
```
This builds and starts the controller, the dashboard, the job provider, and 4 node agents (`node1`, `node2`, `node3`, `node4`).

### 2. View the Dashboard
Go to [http://localhost:5000](http://localhost:5000) to view:
* Active and historical jobs.
* Live telemetry timeline.
* Real-time node statuses (Idle, Busy, Unresponsive, Quarantined) and current risk scores.

### 3. Manual Testing
You can also manually log into a node container and trigger anomalies:
```bash
# Log into node2
docker exec -it node2 bash

# Run a CPU intensive command to trigger a High CPU alert
yes > /dev/null
```

---

## Useful Commands

```bash
docker compose logs -f              # Stream all logs
docker compose logs -f controller   # Stream controller logs only
docker ps                           # Show status of all nodes/containers
docker compose down                 # Stop and clean up the environment
```
