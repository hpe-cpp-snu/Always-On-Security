import zmq
import threading
import time
from queue import Queue

# ----------------------------------
# ZMQ SETUP
# ----------------------------------

context = zmq.Context()

# Jobs arrive here
job_receiver = context.socket(zmq.PULL)
job_receiver.bind("tcp://*:5555")

# Nodes report completion here
completion_receiver = context.socket(zmq.PULL)
completion_receiver.bind("tcp://*:5557")

# Controller -> Nodes
node_senders = {}

for node in ["node1", "node2", "node3", "node4"]:

    sender = context.socket(zmq.PUSH)

    sender.connect(f"tcp://{node}:5556")

    node_senders[node] = sender

# ----------------------------------
# STATE
# ----------------------------------

job_queue = Queue()

node_status = {
    "node1": "idle",
    "node2": "idle",
    "node3": "idle",
    "node4": "idle"
}

# ----------------------------------
# RECEIVE JOBS
# ----------------------------------

def receive_jobs():

    while True:

        job = job_receiver.recv_json()

        job_queue.put(job)

        print(
            f"[QUEUE] {job['job_id']} "
            f"(size={job_queue.qsize()})"
        )

# ----------------------------------
# RECEIVE COMPLETIONS
# ----------------------------------

def receive_completions():

    while True:

        msg = completion_receiver.recv_json()

        node = msg["node"]

        node_status[node] = "idle"

        print(
            f"[COMPLETE] "
            f"{msg['job_id']} finished on {node}"
        )

# ----------------------------------
# SCHEDULER
# ----------------------------------

def scheduler():

    while True:

        if not job_queue.empty():

            idle_node = None

            for node, status in node_status.items():

                if status == "idle":

                    idle_node = node
                    break

            if idle_node:

                job = job_queue.get()

                node_senders[idle_node].send_json(job)

                node_status[idle_node] = "busy"

                print(
                    f"[SCHEDULER] "
                    f"{job['job_id']} -> {idle_node}"
                )

        time.sleep(1)

# ----------------------------------
# THREADS
# ----------------------------------

threading.Thread(
    target=receive_jobs,
    daemon=True
).start()

threading.Thread(
    target=receive_completions,
    daemon=True
).start()

threading.Thread(
    target=scheduler,
    daemon=True
).start()

print("[CONTROLLER] Started")

while True:
    time.sleep(1)