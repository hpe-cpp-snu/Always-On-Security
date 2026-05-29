import zmq
import time
import os

NODE_NAME = os.getenv("NODE_NAME", "unknown")

context = zmq.Context()

# -------------------------
# Receive jobs
# -------------------------

receiver = context.socket(zmq.PULL)
receiver.bind("tcp://*:5556")

# -------------------------
# Send completions
# -------------------------

completion_sender = context.socket(zmq.PUSH)
completion_sender.connect("tcp://controller:5557")

print(f"{NODE_NAME} waiting for jobs")

while True:

    job = receiver.recv_json()

    print(f"[{NODE_NAME}] Executing {job['job_id']}")
    print(job)

    # Simulate execution
    time.sleep(job["duration"])

    print(f"[{NODE_NAME}] Completed {job['job_id']}")

    completion_sender.send_json({
        "job_id": job["job_id"],
        "node": NODE_NAME
    })