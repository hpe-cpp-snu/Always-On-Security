"""
Always-On Security — Controller (Layer 2: Event Bus & Durability)

Lightweight message forwarder that sits between node agents and the risk engine.
- Receives telemetry from nodes on ZMQ PULL :5555
- Stamps each event with a sequential offset and UTC timestamp
- Forwards to risk-engine on ZMQ PUSH :5556
- Persists offset to disk with atomic writes for crash recovery
"""

import os
import logging
import zmq
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("controller")

OFFSET_PATH = "/data/controller.offset"


def load_offset():
    """Load the last committed offset from disk."""
    try:
        with open(OFFSET_PATH) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def save_offset(offset):
    """Atomically persist offset to disk (fsync + rename)."""
    tmp = OFFSET_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(offset))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, OFFSET_PATH)


def main():
    offset = load_offset()
    log.info(f"Controller starting at offset {offset}")

    ctx = zmq.Context()

    # Receive telemetry from node agents
    recv = ctx.socket(zmq.PULL)
    recv.bind("tcp://*:5555")

    # Forward to risk engine
    fwd = ctx.socket(zmq.PUSH)
    fwd.connect("tcp://risk-engine:5556")

    log.info("Listening on :5555 -> forwarding to risk-engine:5556")

    while True:
        try:
            msg = recv.recv_json()
            offset += 1
            save_offset(offset)
            msg["_offset"] = offset
            msg["_received_at"] = datetime.now(timezone.utc).isoformat()
            fwd.send_json(msg)
            log.info(
                f"Forwarded offset={offset} "
                f"node={msg.get('node')} "
                f"event={msg.get('event_type')}"
            )
        except Exception as e:
            log.error(f"Forward error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
