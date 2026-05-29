import zmq
import uuid
import random
import time

context = zmq.Context()

sender = context.socket(zmq.PUSH)

# Docker service name
sender.connect("tcp://controller:5555")

print("Provider started")

while True:

    job = {
        "job_id": str(uuid.uuid4()),
        "job_type": random.choice([
            "cpu",
            "file_write",
            "memory_access"
        ]),
        "duration": random.randint(5, 15)
    }

    sender.send_json(job)

    print(f"Generated {job['job_id']}")

    time.sleep(3)