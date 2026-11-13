"""Versioned, bounded wire protocol for the J1 bridge."""
from dataclasses import dataclass
import json
import math


def validate_state(state: dict) -> None:
    """Validate the raw schema, not its still-unproven physical conventions."""
    if state.get("version") != 1:
        raise ValueError("unsupported schema")
    for field in ("episode", "seq", "tick_ms", "race_ms", "wall_ms", "action_id", "gear", "checkpoints"):
        if type(state.get(field)) is not int:
            raise ValueError(f"missing or invalid integer: {field}")
    if not isinstance(state.get("map_uid"), str) or not state["map_uid"]:
        raise ValueError("missing map identity")
    if type(state.get("finished")) is not bool:
        raise ValueError("invalid finish flag")
    for field in ("position", "velocity", "rotation_ypr", "angular_velocity", "car_inputs", "inputs"):
        values = state.get(field)
        if not isinstance(values, list) or len(values) != 3 or not all(
                type(x) in (int, float) and math.isfinite(x) for x in values):
            raise ValueError(f"missing or invalid vector: {field}")
    value = state.get("turning_rate")
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("missing turning_rate")
    for field in ("wheel_contact", "wheel_sliding"):
        values = state.get(field)
        if not isinstance(values, list) or len(values) != 4 or any(type(x) is not bool for x in values):
            raise ValueError(f"invalid per-wheel field: {field}")
    offsets = state.get("wheel_offsets")
    if not isinstance(offsets, list) or len(offsets) != 4 or any(
            not isinstance(v, list) or len(v) != 3 or any(
                type(x) not in (int, float) or not math.isfinite(x) for x in v) for v in offsets):
        raise ValueError("invalid wheel offsets")


def _reject_constant(value):
    raise ValueError(f"non-finite JSON value: {value}")


class Decoder:
    """Handle TCP fragmentation without accepting unbounded or non-JSON data."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[dict]:
        self.buffer.extend(data)
        records = []
        while b"\n" in self.buffer:
            index = self.buffer.index(10)
            if index > 16384:
                raise ValueError("oversized message")
            line = bytes(self.buffer[:index])
            del self.buffer[:index + 1]
            obj = json.loads(line.decode("utf-8"), parse_constant=_reject_constant)
            if not isinstance(obj, dict) or not isinstance(obj.get("kind"), str):
                raise ValueError("message must be a typed object")
            records.append(obj)
        if len(self.buffer) > 16384:
            raise ValueError("oversized message")
        return records


@dataclass(frozen=True)
class Action:
    steer: float
    accelerate: bool
    brake: bool
    ticks: int = 5

    def __post_init__(self):
        import math
        if (type(self.steer) not in (int, float) or not math.isfinite(self.steer)
                or not -1 <= self.steer <= 1
                or type(self.accelerate) is not bool or type(self.brake) is not bool
                or type(self.ticks) is not int or not 1 <= self.ticks <= 25):
            raise ValueError("invalid action")

    def encode(self, *, episode: int, action_id: int, source_seq: int) -> bytes:
        steer = round(self.steer * 65536)
        return f"A {episode} {action_id} {source_seq} {steer} {int(self.accelerate)} {int(self.brake)} {self.ticks}\n".encode("ascii")
