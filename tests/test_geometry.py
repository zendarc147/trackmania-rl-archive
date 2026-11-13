"""Off-game tests for reference preparation, projection, progress and encoding.

EVERY FIXTURE IN THIS FILE IS SYNTHETIC (hand-built geometry and states). They test
calculations and contracts only; they do not validate the game integration. Real-data
evidence is in docs/reports/J2-observations.md.
"""
import math
import unittest

from trackmania_rl import observation as obs
from trackmania_rl import reference as ref
from trackmania_rl import vec
from trackmania_rl.geometry import ProgressTracker, ProjectionError, ReferenceLine

SYNTHETIC_UID = "SYNTHETIC-MAP"
PROFILE = {"name": "synthetic", "uid": SYNTHETIC_UID, "checkpoint_count": 3}


def synthetic_prepared(points, ups=None, cp_fractions=(1 / 3, 2 / 3)):
    """Build a prepared reference from a synthetic polyline (already densely sampled)."""
    s = ref._cumulative(points)
    ups = ups or [[0.0, 1.0, 0.0]] * len(points)
    bounds = [0.0] + [s[-1] * f for f in cp_fractions] + [s[-1]]
    return {"schema": ref.PREPARED_SCHEMA, "points": points, "ups": ups, "s": s,
            "sector_bounds_m": bounds, "sha256": "synthetic"}


def straight(length=300.0, step=1.0):
    n = int(length / step)
    return [[0.0, 0.0, i * step] for i in range(n + 1)]   # travel along +z


def quarter_left(radius=50.0, n=200):
    # Start at origin heading +z, turn LEFT (towards +x, since car x = left, see report).
    return [[radius - radius * math.cos(t), 0.0, radius * math.sin(t)]
            for t in (math.pi / 2 * i / n for i in range(n + 1))]


def figure_with_overpass():
    """Line going +z along x=0, loop around, then passing over the same (x, z) 10 m higher."""
    pts = [[0.0, 0.0, float(z)] for z in range(0, 201)]                         # 0..200 m
    c = [100.0, 0.0, 200.0]
    for i in range(1, 315):                                                      # half circle
        a = math.pi * i / 314
        pts.append([c[0] - 100 * math.cos(a), 5.0 * i / 314, c[2] + 100 * math.sin(a)])
    for x in range(199, -100, -1):                                               # back along -x ...
        pts.append([float(x), 5.0, 200.0])
    return pts


class LineMixin:
    def tracker(self, prepared, **params):
        tr = ProgressTracker(ReferenceLine(prepared), params or None)
        tr.reset()
        return tr


class ProjectionTests(LineMixin, unittest.TestCase):
    def test_straight_line_progress_and_signed_offsets(self):
        tr = self.tracker(synthetic_prepared(straight()))
        p = tr.update([2.0, 0.5, 10.0], 0, 0)
        self.assertAlmostEqual(p.s_m, 10.0, places=6)
        self.assertAlmostEqual(p.progress, 10.0 / 300.0, places=6)
        # heading +z with up +y: left = up x forward = +x
        self.assertAlmostEqual(p.lateral_m, 2.0, places=6)
        self.assertAlmostEqual(p.vertical_m, 0.5, places=6)
        p = tr.update([-3.0, -0.25, 20.0], 10, 0)
        self.assertAlmostEqual(p.lateral_m, -3.0, places=6)
        self.assertAlmostEqual(p.vertical_m, -0.25, places=6)

    def test_left_curve_inside_is_positive_lateral(self):
        pts = quarter_left()
        tr = self.tracker(synthetic_prepared(pts))
        mid = pts[100]
        center = [50.0, 0.0, 0.0]
        inward = vec.normalize(vec.sub(center, mid))
        p = tr.update(vec.add(mid, vec.scale(inward, 2.0)), 0, 0)
        self.assertGreater(p.lateral_m, 1.9)   # inside of a left turn = left
        p = tr.update(vec.add(mid, vec.scale(inward, -2.0)), 10, 0)
        self.assertLess(p.lateral_m, -1.9)
        self.assertAlmostEqual(p.s_m, 50.0 * math.pi / 4, delta=0.2)

    def test_slope_vertical_uses_local_normal(self):
        # 20 % ramp along +z; car up tilted with the ramp.
        k = 0.2
        pts = [[0.0, k * z, float(z)] for z in range(0, 201)]
        up = vec.normalize([0.0, 1.0, -k])
        tr = self.tracker(synthetic_prepared(pts, [up] * len(pts)), start_window_m=1e9)
        base = pts[50]
        p = tr.update(vec.add(base, vec.scale(up, 1.5)), 0, 0)
        self.assertAlmostEqual(p.vertical_m, 1.5, places=6)
        self.assertAlmostEqual(p.lateral_m, 0.0, places=6)
        self.assertAlmostEqual(p.s_m, math.hypot(50, 10), places=6)
        # A pure world-vertical offset is not the local normal offset on the ramp.
        p = tr.update(vec.add(base, [0.0, 1.5, 0.0]), 10, 0)
        self.assertLess(p.vertical_m, 1.5)

    def test_crossing_keeps_the_section_consistent_with_continuity(self):
        pts = figure_with_overpass()
        prep = synthetic_prepared(pts, cp_fractions=(0.3, 0.6))
        line = ReferenceLine(prep)
        tr = ProgressTracker(line)
        tr.reset()
        # Drive along the first section up to z=150 (x=0, y=0), 1 m per 10 ms.
        for z in range(0, 151):
            p = tr.update([0.0, 0.0, float(z)], z * 10, 0)
        self.assertAlmostEqual(p.s_m, 150.0, places=6)
        # Fast-forward to the upper pass above (0, 200)? Not reachable in 10 ms: stays lower.
        p_low = tr.update([0.0, 4.0, 160.0], 1510, 0)
        self.assertLess(p_low.s_m, 200.0)
        # Now a fresh episode in which the car really is on the upper pass, with the game
        # checkpoint count consistent with that part of the track.
        tr.reset()
        s_upper = line.s[len(pts) - 100]          # point at x=0, y=5, z=200 on the upper pass
        tr.last = None
        tr.p["start_window_m"] = 1e9              # allow start there only for this synthetic case
        p_up = tr.update([0.0, 5.2, 200.0], 0, 2)
        self.assertAlmostEqual(p_up.s_m, s_upper, delta=1.0)
        self.assertAlmostEqual(p_up.vertical_m, 0.2, delta=1e-6)
        # With checkpoint count 0 the same position can only project on the first section.
        tr.reset()
        tr.p["start_window_m"] = 1e9
        p_first = tr.update([0.0, 5.2, 200.0], 0, 0)
        self.assertLessEqual(p_first.s_m, prep["sector_bounds_m"][1] + tr.p["sector_margin_m"])

    def test_nearest_point_would_jump_but_tracker_does_not(self):
        pts = figure_with_overpass()
        line = ReferenceLine(synthetic_prepared(pts, cp_fractions=(0.9, 0.95)))
        tr = ProgressTracker(line)
        tr.reset()
        for z in range(0, 195):
            p = tr.update([0.0, 2.8, float(z)], z * 10, 0)
        # At z=194, y=2.8 the upper pass (y=5 at z=200) is ~6.3 m away and the lower 2.8 m:
        # both local; ensure s stays continuous (no jump of hundreds of metres).
        self.assertAlmostEqual(p.s_m, 194.0, delta=0.5)
        # Near (0, 4.9, 200): globally nearest is the upper pass; the tracker stays low.
        p = tr.update([0.0, 4.9, 200.0], 1950, 0)
        global_best = line.best_in([0.0, 4.9, 200.0], range(len(pts) - 1))
        self.assertGreater(line.s[global_best[0]], 400.0)
        self.assertLess(p.s_m, 210.0)

    def test_jump_above_the_track_keeps_progress_and_positive_vertical(self):
        tr = self.tracker(synthetic_prepared(straight()))
        prev_s = 0.0
        for k in range(0, 101):                         # 1 s airborne, parabolic arc
            z = 50.0 + k * 0.5
            y = 20.0 * (k / 100) * (1 - k / 100) * 4
            p = tr.update([0.0, y, z], k * 10, 0)
            self.assertGreaterEqual(p.s_m, prev_s - 1e-9)
            self.assertFalse(p.relocalized)
            prev_s = p.s_m
            self.assertAlmostEqual(p.vertical_m, y, places=6)

    def test_reversing_decreases_progress(self):
        tr = self.tracker(synthetic_prepared(straight()))
        values = [tr.update([0.0, 0.0, z], i * 10, 0).progress
                  for i, z in enumerate([10.0, 20.0, 30.0, 25.0, 15.0])]
        self.assertLess(values[-1], values[2])
        self.assertAlmostEqual(values[-1], 15.0 / 300.0, places=6)
        self.assertAlmostEqual(tr.max_s_m, 30.0, places=6)   # diagnostic only

    def test_reset_does_not_keep_progress(self):
        tr = self.tracker(synthetic_prepared(straight()))
        for i in range(0, 101):
            tr.update([0.0, 0.0, float(i)], i * 10, 0)
        tr.reset()
        p = tr.update([0.0, 0.0, 0.0], 0, 0)
        self.assertEqual(p.s_m, 0.0)
        self.assertEqual(tr.max_s_m, 0.0)

    def test_time_going_back_without_reset_is_an_error(self):
        tr = self.tracker(synthetic_prepared(straight()))
        tr.update([0.0, 0.0, 10.0], 100, 0)
        with self.assertRaises(ProjectionError):
            tr.update([0.0, 0.0, 0.0], 0, 0)

    def test_update_without_reset_and_bad_inputs_are_errors(self):
        tr = ProgressTracker(ReferenceLine(synthetic_prepared(straight())))
        with self.assertRaises(ProjectionError):
            tr.update([0.0, 0.0, 0.0], 0, 0)
        tr.reset()
        with self.assertRaises(ProjectionError):
            tr.update([0.0, float("nan"), 0.0], 0, 0)
        with self.assertRaises(ProjectionError):
            tr.update([0.0, 0.0, 0.0], 0, 4)

    def test_progress_never_validates_a_checkpoint(self):
        prep = synthetic_prepared(straight(), cp_fractions=(1 / 3, 2 / 3))
        tr = self.tracker(prep)
        # The car drives to the end but the game never counted checkpoint 1.
        for i in range(0, 301):
            p = tr.update([0.0, 0.0, float(i)], i * 10, 0)
        # Sector limits apply at the granularity of one reference segment (1 m here).
        limit = prep["sector_bounds_m"][1] + tr.p["sector_margin_m"] + 1.0
        self.assertLessEqual(p.s_m, limit + 1e-9)
        self.assertLess(p.progress, 0.5)
        self.assertEqual(p.sector, 0)
        # Once the game reports checkpoint 1, the next sector becomes reachable.
        p = tr.update([0.0, 0.0, 300.0], 3010, 1)
        self.assertEqual(p.sector, 1)
        self.assertGreater(p.s_m, limit)
        self.assertLessEqual(p.s_m, prep["sector_bounds_m"][2] + tr.p["sector_margin_m"] + 1.0)


# ---------------------------------------------------------------- reference preparation

def synthetic_run(n=500, speed=10.0, cp_at=(150, 300), finish_at=450, jump_at=None,
                  countdown=True, uid=SYNTHETIC_UID):
    """SYNTHETIC passive recording: states every 10 ms along +z, events for checkpoints."""
    msgs = []
    if countdown:
        for t in (-30, -20, -10):
            msgs.append(state(t, 0.0, 0))
    count = 0
    for i in range(finish_at + 3):
        race = min(i, finish_at) * 10
        z = i * speed * 0.01
        if jump_at is not None and i >= jump_at:
            z += 50.0
        if i in cp_at:
            count += 1
            msgs.append({"kind": "event", "event": "checkpoint", "current": count, "target": 3,
                         "race_ms": race, "finished": False})
        finished = i >= finish_at
        if i == finish_at:
            msgs.append({"kind": "event", "event": "checkpoint", "current": 3, "target": 3,
                         "race_ms": race, "finished": True})
        c = 3 if finished else count if i not in cp_at else count - 1
        msgs.append(state(race, z, c, finished=finished, tick=i * 10, uid=uid, speed=speed))
    return msgs


def state(race, z, checkpoints, finished=False, tick=None, uid=SYNTHETIC_UID, speed=10.0):
    return {"kind": "state", "race_ms": race, "tick_ms": race if tick is None else tick,
            "map_uid": uid, "position": [0.0, 0.0, z], "velocity": [0.0, 0.0, speed],
            "rotation_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "quat_wxyz": [1.0, 0.0, 0.0, 0.0], "checkpoints": checkpoints, "finished": finished}


class ReferenceTests(unittest.TestCase):
    def test_valid_synthetic_run_and_preparation(self):
        msgs = synthetic_run()
        rep = ref.validate_run(msgs, PROFILE)
        self.assertTrue(rep["valid"], rep["problems"])
        self.assertEqual(rep["race_time_ms"], 4500)
        raw = ref.raw_reference(msgs, PROFILE, rep, {"kind": "synthetic"})
        prep = ref.prepare_reference(raw, {"spacing_m": 2.0})
        self.assertAlmostEqual(prep["length_m"], 45.0, places=6)
        self.assertEqual(prep["sector_bounds_m"][0], 0.0)
        self.assertAlmostEqual(prep["sector_bounds_m"][1], 15.0, places=6)
        self.assertAlmostEqual(prep["sector_bounds_m"][2], 30.0, places=6)
        self.assertEqual(prep["sector_bounds_m"][-1], prep["length_m"])
        self.assertEqual(prep["map"]["uid"], SYNTHETIC_UID)
        self.assertEqual(prep["raw_sha256"], raw["sha256"])
        self.assertEqual(ref.prepare_reference(raw, {"spacing_m": 2.0})["sha256"], prep["sha256"])

    def test_invalid_runs_are_rejected(self):
        cases = {"respawn": synthetic_run(jump_at=200), "no countdown": synthetic_run(countdown=False),
                 "wrong map": synthetic_run(uid="OTHER")}
        no_finish = [m for m in synthetic_run() if not m.get("finished")]
        cases["no finish"] = no_finish
        for name, msgs in cases.items():
            with self.subTest(name=name):
                rep = ref.validate_run(msgs, PROFILE)
                self.assertFalse(rep["valid"])
                with self.assertRaises(ValueError):
                    ref.raw_reference(msgs, PROFILE, rep, {"kind": "synthetic"})

    def test_attempts_split_on_restart(self):
        msgs = synthetic_run() + synthetic_run()
        attempts = ref.split_attempts(msgs)
        self.assertEqual(len(attempts), 2)
        self.assertTrue(all(ref.validate_run(a, PROFILE)["valid"] for a in attempts))

    def test_dedup_removes_standstill_but_keeps_checkpoint_samples(self):
        msgs = synthetic_run()
        # Freeze the car for 40 ticks in the middle (standstill), including checkpoint 1 at i=150.
        states = [m for m in msgs if m.get("kind") == "state" and m["race_ms"] >= 0]
        frozen = list(states[130]["position"])
        shift = states[170]["position"][2] - frozen[2]
        for m in states[130:171]:
            m["position"] = list(frozen)
        for m in states[171:]:
            m["position"] = [0.0, 0.0, m["position"][2] - shift]
        rep = ref.validate_run(msgs, PROFILE)
        self.assertTrue(rep["valid"], rep["problems"])
        raw = ref.raw_reference(msgs, PROFILE, rep, {"kind": "synthetic"})
        prep = ref.prepare_reference(raw, {"spacing_m": 1.0})
        self.assertLess(prep["raw_points_kept"], prep["raw_points_total"] - 30)
        self.assertAlmostEqual(prep["sector_bounds_m"][1], frozen[2], delta=1e-6)
        self.assertLess(prep["max_raw_to_prepared_m"], 1e-6)


# ---------------------------------------------------------------- observation encoding

def obs_state(**changes):
    s = {"map_uid": SYNTHETIC_UID, "tick_ms": 1000,
         "rotation_matrix": [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]],   # yaw +90°
         "velocity": [10.0, 0.0, 0.0], "angular_velocity": [0.0, 0.5, 0.0], "gear": 2,
         "turning_rate": -0.25, "wheel_contact": [True, True, False, True],
         "wheel_sliding": [False, True, False, False]}
    s.update(changes)
    return s


class ObservationTests(LineMixin, unittest.TestCase):
    def setUp(self):
        self.proj = self.tracker(synthetic_prepared(straight())).update([1.0, 0.0, 30.0], 0, 0)

    def test_order_frames_and_dimension(self):
        f = obs.raw_features(obs_state(), self.proj)
        self.assertEqual(len(f), obs.DIM)
        self.assertEqual(len(obs.feature_names()), obs.DIM)
        names = obs.feature_names()
        get = dict(zip(names, f))
        # world velocity +x with car forward = +x (column 2) => local forward speed 10
        self.assertAlmostEqual(get["velocity_car.z"], 10.0)
        self.assertAlmostEqual(get["velocity_car.x"], 0.0)
        self.assertEqual([get["rotation_forward." + a] for a in "xyz"], [1.0, 0.0, 0.0])
        self.assertEqual([get["rotation_up." + a] for a in "xyz"], [0.0, 1.0, 0.0])
        self.assertAlmostEqual(get["angular_velocity_car.y"], 0.5)
        self.assertEqual(get["gear"], 2.0)
        self.assertEqual(get["turning_rate"], -0.25)
        self.assertAlmostEqual(get["centerline_lateral"], 1.0)
        self.assertAlmostEqual(get["progress"], 0.1)
        self.assertEqual([get[f"wheel_contact.{w}"] for w in ("FL", "FR", "BR", "BL")],
                         [1.0, 1.0, 0.0, 1.0])
        self.assertEqual([get[f"wheel_sliding.{w}"] for w in ("FL", "FR", "BR", "BL")],
                         [0.0, 1.0, 0.0, 0.0])

    def test_orientation_encoding_is_continuous_across_yaw_wrap(self):
        def rot(yaw):
            c, s = math.cos(yaw), math.sin(yaw)
            return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
        a = obs.raw_features(obs_state(rotation_matrix=rot(math.pi - 1e-4)), self.proj)
        b = obs.raw_features(obs_state(rotation_matrix=rot(-math.pi + 1e-4)), self.proj)
        i = obs.feature_names().index("rotation_forward.x")
        self.assertLess(max(abs(x - y) for x, y in zip(a[i:i + 6], b[i:i + 6])), 1e-3)

    def test_missing_nonfinite_stale_and_wrong_map_are_rejected(self):
        bad = obs_state()
        del bad["gear"]
        cases = [bad, obs_state(velocity=[float("nan"), 0, 0]), obs_state(turning_rate=None),
                 obs_state(wheel_sliding=[True] * 3), obs_state(gear=2.0),
                 obs_state(rotation_matrix=[[1, 0, 0], [0, 1, 0]])]
        for s in cases:
            with self.subTest(s=s), self.assertRaises(obs.ObservationError):
                obs.raw_features(s, self.proj)
        with self.assertRaises(obs.ObservationError):
            obs.raw_features(obs_state(), self.proj, expected_tick_ms=990)
        with self.assertRaises(obs.ObservationError):
            obs.raw_features(obs_state(map_uid="OTHER"), self.proj, expected_map_uid=SYNTHETIC_UID)

    def test_same_state_same_encoding_with_frozen_normalization(self):
        rows = [obs.raw_features(obs_state(velocity=[v, 0.0, 0.0], gear=g), self.proj)
                for v, g in ((5.0, 1), (10.0, 2), (20.0, 3))]
        norm = obs.fit_normalization(rows, data_kind="synthetic", sources=["synthetic"],
                                     map_uid=SYNTHETIC_UID, reference_sha256="synthetic")
        enc = obs.Encoder(norm, SYNTHETIC_UID)
        a = enc.encode(obs_state(), self.proj)
        b = obs.Encoder(dict(norm), SYNTHETIC_UID).encode(obs_state(), self.proj)
        self.assertEqual(a, b)
        self.assertEqual(len(a), obs.DIM)
        self.assertTrue(all(abs(x) <= obs.CLIP for x in a))
        tampered = dict(norm, clip=10.0)
        with self.assertRaises(obs.ObservationError):
            obs.Encoder(tampered, SYNTHETIC_UID)
        with self.assertRaises(obs.ObservationError):
            obs.Encoder(norm, "OTHER")

    def test_normalization_requires_data_kind(self):
        with self.assertRaises(ValueError):
            obs.fit_normalization([[0.0] * obs.DIM], data_kind="unknown", sources=[],
                                  map_uid=SYNTHETIC_UID, reference_sha256="x")


if __name__ == "__main__":
    unittest.main()
