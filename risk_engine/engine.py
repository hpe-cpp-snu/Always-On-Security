"""
Always-On Security — Risk Engine (Layer 3: Central Processing)

Main entry point. Listens on ZMQ PULL :5556 for forwarded events,
validates them, and feeds them through the processing pipeline.
Also runs a heartbeat monitoring thread to detect silent node failures.
"""

import time
import logging
import threading
import zmq
from datetime import datetime, timezone

from store import Store
from enrichment import Enricher
from correlation import Correlator
from rules import RuleEngine
from scoring import WeightedScorer
from router import Router
from pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("engine")

CONFIG = "/opt/security/config"

REQUIRED_FIELDS = {
    "node", "cpu_usage", "memory_usage",
    "process_count", "event_type", "reasons", "_offset",
}

# Track when each node was last seen (for heartbeat)
node_last_seen = {}
node_last_seen_lock = threading.Lock()

NODE_LIST = ["node1", "node2", "node3", "node4"]
HEARTBEAT_TIMEOUT = 30  # seconds


def validate(event):
    """Check that all required fields are present."""
    return REQUIRED_FIELDS.issubset(event.keys())


def heartbeat_checker(store):
    """
    Detects nodes that have stopped sending telemetry.
    Runs in a background thread, checking every 10 seconds.
    From Sukhraj's branch — essential for always-on monitoring.
    """
    log.info(f"Heartbeat checker running (timeout={HEARTBEAT_TIMEOUT}s)")

    # Give nodes time to start up
    time.sleep(15)

    while True:
        now = datetime.now()

        with node_last_seen_lock:
            for node in NODE_LIST:
                last = node_last_seen.get(node)
                if last is None:
                    continue

                delta = (now - last).total_seconds()

                if delta > HEARTBEAT_TIMEOUT:
                    log.warning(
                        f"HEARTBEAT: {node} unresponsive "
                        f"({delta:.0f}s since last telemetry)"
                    )

                    # Store unresponsive event in the database
                    try:
                        store.write_heartbeat_event(
                            node=node,
                            delta_seconds=delta,
                        )
                    except Exception as e:
                        log.error(f"Heartbeat DB error: {e}")

        time.sleep(10)


def main():
    store = Store()

    correlator = Correlator(
        window_seconds=600, threshold_nodes=3, multiplier=1.5
    )
    past_events = store.warm_restart_events(window_seconds=600)
    correlator.warm_restart(past_events)

    pipeline = Pipeline(
        enricher=Enricher(store),
        correlator=correlator,
        rules=RuleEngine.from_yaml(f"{CONFIG}/rules.yaml"),
        scorer=WeightedScorer.from_yaml(
            f"{CONFIG}/thresholds.yaml",
            f"{CONFIG}/node_criticality.yaml",
        ),
        router=Router.from_yaml(f"{CONFIG}/thresholds.yaml"),
    )

    last_offset = store.last_committed_offset()
    log.info(f"Risk engine ready — resuming from offset {last_offset}")

    # Start heartbeat checker thread
    hb_thread = threading.Thread(
        target=heartbeat_checker, args=(store,),
        name="HeartbeatChecker", daemon=True
    )
    hb_thread.start()
    log.info("Started heartbeat checker thread")

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    sock.bind("tcp://*:5556")
    log.info("Listening on tcp://*:5556")

    while True:
        try:
            event = sock.recv_json()
        except Exception as e:
            log.error(f"ZMQ recv error: {e}")
            continue

        if not validate(event):
            log.warning(
                f"Dropped malformed event (missing fields): "
                f"{sorted(event.keys())}"
            )
            continue

        offset = event["_offset"]
        if offset <= last_offset:
            log.debug(
                f"Skipping replayed offset {offset} "
                f"(committed={last_offset})"
            )
            continue

        # Update heartbeat tracking
        node = event.get("node", "unknown")
        with node_last_seen_lock:
            node_last_seen[node] = datetime.now()

        try:
            decision = pipeline.process(event)
            store.write_event(event, decision)
            last_offset = offset

            # Update node status in DB
            status = "idle"
            if event.get("is_busy"):
                status = "busy"
            if decision.bucket == "quarantine":
                status = "quarantined"
            store.update_node_status(
                node=node,
                status=status,
                risk_score=decision.cumulative_score,
            )

            pipeline.router.dispatch(decision)
        except Exception as e:
            log.error(
                f"Pipeline error at offset {offset}: {e}",
                exc_info=True,
            )


if __name__ == "__main__":
    main()
