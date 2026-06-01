"""
Always-On Security — Node Agent
Dual-threaded agent:
  1. Telemetry Monitor — collects system metrics, detects anomalies, sends security events
  2. Job Worker — receives job assignments, marks node as busy/idle for context-aware detection

Includes a built-in threat simulator for automated demo & testing.
"""

import zmq
import time
import os
import socket
import threading
import random
import psutil

# ----------------------------------
# IDENTITY
# ----------------------------------

NODE_NAME = os.getenv("NODE_NAME", socket.gethostname())

# ----------------------------------
# ZMQ CONTEXT (shared)
# ----------------------------------

context = zmq.Context()

# ----------------------------------
# SUSPICIOUS PROCESS LIST
# ----------------------------------

SUSPICIOUS_PROCESSES = [
    "nmap",
    "hydra",
    "nc",
    "netcat",
    "stress",
    "stress-ng",
    "hashcat",
    "john",
    "sqlmap",
    "metasploit",
]

# ----------------------------------
# CURRENT JOB TRACKING
# (shared between threads for
#  job-aware risk scoring context)
# ----------------------------------

current_job = {
    "active": False,
    "job_type": None,
    "job_id": None,
}
job_lock = threading.Lock()

# ==================================
# THREAD 1: JOB WORKER (STUB)
# ==================================

def job_worker():
    """
    Receives jobs from the risk-engine/scheduler on port 5556,
    simulates execution, and marks the node as busy/idle.
    In the current architecture this is a stub — nodes default to idle.
    """

    receiver = context.socket(zmq.PULL)
    receiver.bind("tcp://*:5556")

    print(f"[{NODE_NAME}] Job worker ready on :5556")

    while True:
        try:
            job = receiver.recv_json()

            job_id = job.get("job_id", "unknown")
            job_type = job.get("job_type", "unknown")
            duration = job.get("duration", 5)

            print(f"[{NODE_NAME}] Executing job {job_id} "
                  f"(type={job_type}, duration={duration}s)")

            # Mark job as active (for telemetry thread)
            with job_lock:
                current_job["active"] = True
                current_job["job_type"] = job_type
                current_job["job_id"] = job_id

            # Simulate execution
            time.sleep(duration)

            # Mark job complete
            with job_lock:
                current_job["active"] = False
                current_job["job_type"] = None
                current_job["job_id"] = None

            print(f"[{NODE_NAME}] Completed job {job_id}")

        except Exception as e:
            print(f"[{NODE_NAME}] Job worker error: {e}")

# ==================================
# THREAD 2: TELEMETRY & ANOMALY
# ==================================

def telemetry_monitor():
    """
    Collects system metrics via psutil every 5 seconds,
    runs rule-based anomaly detection, and sends
    security events to the controller on port 5555.
    Includes a threat simulation capability to trigger demo alerts.
    """

    # Send security events to controller
    sender = context.socket(zmq.PUSH)
    sender.connect("tcp://controller:5555")

    print(f"[{NODE_NAME}] Telemetry monitor started -> controller:5555")

    under_attack = False
    attack_stage = 0

    while True:

        # ---- Collect telemetry ----
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        process_count = len(psutil.pids())

        # ---- THREAT SIMULATOR FOR DEMO ----
        # node1 has higher chance (8%) to speed up the first quarantine demo
        trigger_chance = 0.08 if NODE_NAME == "node1" else 0.03
        if not under_attack:
            if random.random() < trigger_chance:
                under_attack = True
                attack_stage = 1
                print(f"[{NODE_NAME}] [SIMULATOR] Threat simulation INITIATED!")
        else:
            attack_stage = min(4, attack_stage + 1)
            print(f"[{NODE_NAME}] [SIMULATOR] Escalating (Stage {attack_stage})")

        # Apply simulation overrides
        if under_attack:
            if attack_stage >= 1:
                cpu = 92.5       # Triggers HIGH_CPU rule
            if attack_stage >= 2:
                memory = 88.0    # Triggers HIGH_MEMORY rule
            if attack_stage >= 3:
                process_count = 310  # Triggers PROCESS_COUNT rule
            # Stage 4 triggers SUSPICIOUS_PROCESS below

        # ---- Default state ----
        event_type = "NORMAL"
        reasons = []

        # ---- Get current job context ----
        with job_lock:
            is_busy = current_job["active"]
            active_job_type = current_job["job_type"]

        # ---- RULE 1: High CPU ----
        if cpu > 80:
            # Job-aware: if running a CPU job, high CPU is expected
            if is_busy and active_job_type == "cpu":
                pass  # Expected behavior, don't flag
            else:
                event_type = "SUSPICIOUS_ACTIVITY"
                reasons.append(f"High CPU usage detected: {cpu}%")

        # ---- RULE 2: High Memory ----
        if memory > 85:
            if is_busy and active_job_type == "memory_access":
                pass  # Expected for memory-intensive jobs
            else:
                event_type = "SUSPICIOUS_ACTIVITY"
                reasons.append(f"High memory usage detected: {memory}%")

        # ---- RULE 3: Too many processes ----
        if process_count > 300:
            event_type = "SUSPICIOUS_ACTIVITY"
            reasons.append(f"Too many running processes: {process_count}")

        # ---- RULE 4: Suspicious process names ----
        detected_suspicious = []
        for proc in psutil.process_iter(['name']):
            try:
                pname = proc.info['name']
                if pname and pname.lower() in SUSPICIOUS_PROCESSES:
                    detected_suspicious.append(pname)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Simulate suspicious process detection at stage 4
        if under_attack and attack_stage >= 4:
            detected_suspicious.append("hydra")

        for pname in detected_suspicious:
            event_type = "SUSPICIOUS_ACTIVITY"
            reasons.append(f"Suspicious process detected: {pname}")

        # ---- Build event ----
        event = {
            "node": NODE_NAME,
            "cpu_usage": cpu,
            "memory_usage": memory,
            "process_count": process_count,
            "event_type": event_type,
            "reasons": reasons,
            "is_busy": is_busy,
            "active_job_type": active_job_type,
        }

        # Send to controller
        sender.send_json(event)

        if event_type != "NORMAL":
            print(f"[{NODE_NAME}] ALERT: {reasons}")

        # Wait before next cycle
        time.sleep(5)

# ==================================
# MAIN
# ==================================

print(f"[{NODE_NAME}] Starting agent...")

t1 = threading.Thread(target=job_worker, daemon=True)
t2 = threading.Thread(target=telemetry_monitor, daemon=True)

t1.start()
t2.start()

print(f"[{NODE_NAME}] Agent running (job worker + telemetry)")

while True:
    time.sleep(1)
