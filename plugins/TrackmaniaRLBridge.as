// TrackMania RL — J1 bridge (TMInterface AngelScript plugin).
//
// Local TCP server on 127.0.0.1:8479 (the demonstrator TelemetrieVoiture uses 8478).
// Game -> client: one JSON object per line ("hello", "state", "event").
// Client -> game: one text command per line:
//   CFG <sync 0|1> <timeout_ms> <stream_every_steps> [auto_restart 0|1] [official_finish 0|1]
//   A <episode> <action_id> <source_seq> <steer -65536..65536> <accel 0|1> <brake 0|1> <ticks>
//   R <episode>          release inputs, restart the race, new episode id
//                        (GiveUp while racing; after a finish, rewind to the countdown state
//                        saved at the start of the race, because GiveUp is ignored then;
//                        during the countdown, rewind too (0.4.1): at high speed GiveUp
//                        lands late, after the new episode has already started; while
//                        racing, rewind too (0.4.2): a car released near the line could
//                        cross it before GiveUp landed; GiveUp is now only the fallback
//                        when no start state is saved)
//   REL                  release inputs and disarm
//   MAP <file>           execute the TMInterface "map" console command
//   PING <n>             transport round trip, answered with a "pong" event
//   SPD <factor>         simulation speed through SimulationManager.SetSpeed, 0 < factor <= 100
//                        (0.3.0, D22). Answered with a "speed" event. The bridge restores
//                        speed 1 when the client is lost or replaced and when disabled.
// Safety: inputs are held for at most <ticks> run steps, then for at most <timeout_ms>
// wall time while waiting for the next action; afterwards they are released.
// Controlled finish: the finish state is sent from OnCheckpointCountChanged, then
// PreventSimulationFinish keeps the race alive (otherwise the end-of-race dialog stops
// OnRunStep and blocks every restart). auto_restart=1 then rewinds to the countdown state
// saved at the start of the race. official_finish=1 instead permits the normal game
// finish (end dialog and game record), so another attempt needs a manual restart.
// No map-specific constant lives here.

const string BRIDGE_VERSION = "0.4.2";
const uint16 BRIDGE_PORT = 8479;

Net::Socket@ g_server = null;
Net::Socket@ g_client = null;
string g_inbuf = "";

int g_episode = 0;
int g_seq = 0;
int g_actionId = 0;
int g_sourceSeq = -1;
int g_steer = 0;
bool g_accel = false;
bool g_brake = false;
int g_holdTicks = 0;
bool g_armed = false;
bool g_awaiting = false;       // boundary reached, waiting for next action
uint64 g_awaitDeadline = 0;
int g_appliedTick = 0;

bool g_sync = true;
uint g_timeoutMs = 250;
int g_streamEvery = 10;
int g_streamCounter = 0;

bool g_waitStart = false;
bool g_sawNegative = false;
int g_cpTarget = -1;
bool g_finishReported = false;
uint64 g_lastHeartbeat = 0;

// Restart after a finish: state saved on the first countdown tick of each race.
SimulationState@ g_startState = null;
string g_startUid = "";
int g_prevRaceTime = 0;
bool g_prevInRace = false;
bool g_autoRestart = false;
bool g_officialFinish = false;
bool g_rewindPending = false;   // performed in OnRunStep, never from Render()
string g_rewindCause = "";
int g_cpOverride = -1;          // checkpoint count given by OnCheckpointCountChanged
double g_speed = 1.0;           // last speed set by SPD (1 = normal)

PluginInfo@ GetPluginInfo()
{
    PluginInfo info;
    info.Author = "zen";
    info.Name = "TrackMania RL Bridge J1";
    info.Description = "J1 telemetry/control bridge for local RL experiments";
    info.Version = BRIDGE_VERSION;
    return info;
}

void Main()
{
    @g_server = Net::Socket();
    if (!g_server.Listen("127.0.0.1", BRIDGE_PORT)) {
        log("RL bridge: cannot listen on 127.0.0.1:8479", Severity::Error);
        @g_server = null;
    } else {
        log("RL bridge " + BRIDGE_VERSION + " listening on 127.0.0.1:8479");
    }
}

// Back to normal speed when the controlling client goes away (never leave the game fast).
void RestoreSpeed(const string &in why)
{
    if (g_speed == 1.0) {
        return;
    }
    auto@ sim = GetSimulationManager();
    if (sim !is null) {
        sim.SetSpeed(1.0f);
    }
    g_speed = 1.0;
    log("RL bridge: speed restored to 1 (" + why + ")");
}

void OnDisabled()
{
    Release("plugin_disabled");
    RestoreSpeed("plugin_disabled");
    @g_client = null;
    @g_server = null;
}

// ---------- formatting ----------

string F(double x) { return Text::FormatFloat(x, "", 0, 6); }
string B(bool b) { return b ? "true" : "false"; }
string V(const vec3 &in v) { return "[" + F(v.x) + "," + F(v.y) + "," + F(v.z) + "]"; }
string Q(const string &in s)
{
    string o = "\"";
    for (uint i = 0; i < s.Length; i++) {
        uint8 c = s[i];
        if (c == 34 || c == 92) { o += "\\"; }
        if (c < 32) { o += " "; continue; }
        string one = " ";
        one[0] = c;
        o += one;
    }
    return o + "\"";
}

void Send(const string &in json)
{
    if (g_client is null) {
        return;
    }
    if (!g_client.Write(json + "\n")) {
        @g_client = null;
        g_inbuf = "";
        ReleaseInputsOnly();
        g_armed = false;
        g_awaiting = false;
        RestoreSpeed("client_lost");
        log("RL bridge: client write failed, inputs released", Severity::Warning);
    }
}

string MapUid()
{
    auto@ ch = GetCurrentChallenge();
    if (ch is null) {
        return "";
    }
    return ch.Uid;
}

string MapName()
{
    auto@ ch = GetCurrentChallenge();
    if (ch is null) {
        return "";
    }
    return ch.Name;
}

void SendEvent(const string &in name, const string &in extra)
{
    auto@ sim = GetSimulationManager();
    int race = 0;
    int tick = 0;
    bool inRace = false;
    if (sim !is null) {
        inRace = sim.InRace;
        if (inRace) {
            race = sim.RaceTime;
            tick = sim.TickTime;
        }
    }
    string s = "{\"kind\":\"event\",\"event\":" + Q(name)
        + ",\"episode\":" + g_episode + ",\"seq\":" + g_seq
        + ",\"action_id\":" + g_actionId
        + ",\"in_race\":" + B(inRace) + ",\"race_ms\":" + race + ",\"tick_ms\":" + tick
        + ",\"wall_ms\":" + Time::Now + ",\"game_state\":" + int(GetCurrentGameState());
    if (extra.Length > 0) {
        s += "," + extra;
    }
    Send(s + "}");
}

// ---------- inputs ----------

void ApplyInputs(SimulationManager@ sim)
{
    if (sim is null) {
        return;
    }
    sim.SetInputState(InputType::Left, 0);
    sim.SetInputState(InputType::Right, 0);
    sim.SetInputState(InputType::Steer, g_steer);
    sim.SetInputState(InputType::Up, g_accel ? 1 : 0);
    sim.SetInputState(InputType::Down, g_brake ? 1 : 0);
}

void ReleaseInputsOnly()
{
    g_steer = 0;
    g_accel = false;
    g_brake = false;
    auto@ sim = GetSimulationManager();
    if (sim !is null && sim.InRace) {
        ApplyInputs(sim);
    }
}

void Release(const string &in reason)
{
    bool was = g_armed || g_awaiting;
    ReleaseInputsOnly();
    g_armed = false;
    g_awaiting = false;
    g_holdTicks = 0;
    SendEvent("released", "\"reason\":" + Q(reason) + ",\"was_armed\":" + B(was));
}

// ---------- state ----------

string StateJson(SimulationManager@ sim, const string &in reason)
{
    auto@ player = sim.PlayerInfo;
    auto@ car = sim.SceneVehicleCar;
    auto@ dyna = sim.Dyna;
    auto@ wheels = sim.Wheels;
    float yaw, pitch, roll;
    dyna.CurrentState.Location.Rotation.GetYawPitchRoll(yaw, pitch, roll);
    mat3 rot = dyna.CurrentState.Location.Rotation;
    vec3 pos = dyna.CurrentState.Location.Position;
    vec3 vel = dyna.CurrentState.LinearSpeed;
    vec3 ang = dyna.CurrentState.AngularSpeed;
    quat q = dyna.CurrentState.Quat;
    InputState inp = sim.GetInputState();

    string contact = "[";
    string sliding = "[";
    string offsets = "[";
    string names = "[";
    string ngc = "[";
    for (uint i = 0; i < 4; i++) {
        auto@ w = wheels[i];
        string sep = i == 0 ? "" : ",";
        contact += sep + B(w.RTState.HasGroundContact);
        sliding += sep + B(w.RTState.IsSliding);
        offsets += sep + V(w.OffsetFromVehicle);
        ngc += sep + w.RTState.NbGroundContacts;
        string n = "?";
        if (w is wheels.FrontLeft) { n = "FL"; }
        else if (w is wheels.FrontRight) { n = "FR"; }
        else if (w is wheels.BackRight) { n = "BR"; }
        else if (w is wheels.BackLeft) { n = "BL"; }
        names += sep + Q(n);
    }

    const array<int>@ cps = player.CheckpointStates;
    string cpStates = "[";
    for (uint i = 0; i < cps.Length; i++) {
        cpStates += (i == 0 ? "" : ",") + cps[i];
    }

    return "{\"kind\":\"state\",\"version\":1,\"reason\":" + Q(reason)
        + ",\"episode\":" + g_episode + ",\"seq\":" + g_seq
        + ",\"action_id\":" + g_actionId + ",\"source_seq\":" + g_sourceSeq
        + ",\"applied_tick_ms\":" + g_appliedTick
        + ",\"armed\":" + B(g_armed) + ",\"sync\":" + B(g_sync)
        + ",\"tick_ms\":" + sim.TickTime + ",\"race_ms\":" + sim.RaceTime
        + ",\"wall_ms\":" + Time::Now
        + ",\"map_uid\":" + Q(MapUid())
        + ",\"game_state\":" + int(GetCurrentGameState())
        + ",\"position\":" + V(pos)
        + ",\"velocity\":" + V(vel)
        + ",\"local_velocity\":" + V(car.CurrentLocalSpeed)
        + ",\"rotation_ypr\":[" + F(yaw) + "," + F(pitch) + "," + F(roll) + "]"
        + ",\"rotation_matrix\":[" + V(rot.x) + "," + V(rot.y) + "," + V(rot.z) + "]"
        + ",\"quat_wxyz\":[" + F(q.w) + "," + F(q.x) + "," + F(q.y) + "," + F(q.z) + "]"
        + ",\"angular_velocity\":" + V(ang)
        + ",\"gear\":" + car.CarEngine.Gear
        + ",\"rear_gear\":" + car.CarEngine.RearGear
        + ",\"rpm\":" + F(car.CarEngine.ActualRPM)
        + ",\"display_speed\":" + player.DisplaySpeed
        + ",\"turning_rate\":" + F(car.TurningRate)
        + ",\"car_inputs\":[" + F(car.InputSteer) + "," + F(car.InputGas) + "," + F(car.InputBrake) + "]"
        + ",\"inputs\":[" + inp.Steer + "," + (inp.Up ? 1 : 0) + "," + (inp.Down ? 1 : 0) + "]"
        + ",\"input_gas\":" + inp.Gas
        + ",\"input_lr\":[" + (inp.Left ? 1 : 0) + "," + (inp.Right ? 1 : 0) + "]"
        + ",\"commanded\":[" + g_steer + "," + (g_accel ? 1 : 0) + "," + (g_brake ? 1 : 0) + "]"
        + ",\"is_sliding_global\":" + B(car.IsSliding)
        + ",\"wheel_contact\":" + contact + "]"
        + ",\"wheel_sliding\":" + sliding + "]"
        + ",\"wheel_ground_contacts\":" + ngc + "]"
        + ",\"wheel_offsets\":" + offsets + "]"
        + ",\"wheel_names\":" + names + "]"
        + ",\"checkpoints\":" + (g_cpOverride >= 0 ? g_cpOverride : int(player.CurCheckpointCount))
        + ",\"checkpoints_raw\":" + player.CurCheckpointCount
        + ",\"checkpoint_target\":" + g_cpTarget
        + ",\"checkpoint_states\":" + cpStates + "]"
        + ",\"finished\":" + B(player.RaceFinished)
        + "}";
}

void SendState(SimulationManager@ sim, const string &in reason)
{
    g_seq++;
    Send(StateJson(sim, reason));
}

// ---------- command handling ----------

// Returns true when an action was applied.
bool HandleLine(const string &in line)
{
    array<string>@ p = line.Split(" ");
    if (p.Length == 0) {
        return false;
    }
    string cmd = p[0];
    if (cmd == "A" && p.Length == 8) {
        int ep = int(Text::ParseInt(p[1]));
        if (ep != g_episode) {
            SendEvent("action_rejected", "\"why\":\"episode\",\"line\":" + Q(line));
            return false;
        }
        auto@ sim = GetSimulationManager();
        if (sim is null || !sim.InRace) {
            SendEvent("action_rejected", "\"why\":\"not_in_race\",\"line\":" + Q(line));
            return false;
        }
        int steer = int(Text::ParseInt(p[4]));
        int ticks = int(Text::ParseInt(p[7]));
        if (steer < -65536 || steer > 65536 || ticks < 1 || ticks > 25) {
            SendEvent("action_rejected", "\"why\":\"range\",\"line\":" + Q(line));
            return false;
        }
        g_actionId = int(Text::ParseInt(p[2]));
        g_sourceSeq = int(Text::ParseInt(p[3]));
        g_steer = steer;
        g_accel = p[5] == "1";
        g_brake = p[6] == "1";
        g_holdTicks = ticks;
        g_armed = true;
        g_awaiting = false;
        g_appliedTick = sim.TickTime;
        ApplyInputs(sim);
        return true;
    }
    if (cmd == "R" && p.Length == 2) {
        g_episode = int(Text::ParseInt(p[1]));
        ReleaseInputsOnly();
        g_armed = false;
        g_awaiting = false;
        g_waitStart = true;
        g_sawNegative = false;
        g_cpTarget = -1;
        g_finishReported = false;
        g_actionId = 0;
        g_sourceSeq = -1;
        g_rewindPending = false;
        string method = "give_up";
        auto@ sim = GetSimulationManager();
        if (sim !is null && sim.InRace && sim.PlayerInfo.RaceFinished) {
            // GiveUp is ignored once the race is finished (J3-03): rewind instead.
            if (StartStateUsable()) {
                g_rewindPending = true;
                g_rewindCause = "reset_after_finish";
                method = "rewind_start";
            } else {
                method = "none_no_start_state";
            }
        } else if (sim !is null && sim.InRace && sim.RaceTime < 0 && StartStateUsable()) {
            // Countdown, typically right after an auto_restart rewind. GiveUp takes effect a
            // few frames later; at x10 the countdown already reached 0, the "start" state was
            // sent, and the late restart then jumped the new episode back to the countdown
            // (training errors "tick delta -4960 != 50", 0.4.0). Rewinding is immediate.
            g_rewindPending = true;
            g_rewindCause = "reset_in_countdown";
            method = "rewind_start";
        } else if (sim !is null && sim.InRace && StartStateUsable()) {
            // Racing (0.4.2). GiveUp lands a few frames late; at x10 a car released near the
            // line (time limit) could coast across it meanwhile, GiveUp was then ignored and
            // the end-of-race dialog blocked every restart (run 20260930-204802,
            // "none_not_in_race"). Rewinding is immediate.
            g_rewindPending = true;
            g_rewindCause = "reset_in_race";
            method = "rewind_start";
        } else if (sim !is null && sim.InRace) {
            sim.GiveUp();
        } else {
            // End-of-race dialog or menu: no run step, nothing safe to do from here.
            method = "none_not_in_race";
        }
        SendEvent("reset_requested", "\"method\":" + Q(method));
        return false;
    }
    if (cmd == "REL") {
        Release("client_request");
        return false;
    }
    if (cmd == "CFG" && (p.Length == 4 || p.Length == 5 || p.Length == 6)) {
        g_sync = p[1] == "1";
        g_timeoutMs = uint(Text::ParseUInt(p[2]));
        g_streamEvery = int(Text::ParseInt(p[3]));
        g_autoRestart = p.Length >= 5 && p[4] == "1";
        g_officialFinish = p.Length == 6 && p[5] == "1";
        if (g_autoRestart && g_officialFinish) {
            g_officialFinish = false;
            SendEvent("config_rejected", "\"why\":\"official_finish_conflicts_with_auto_restart\"");
        }
        SendEvent("config", "\"sync\":" + B(g_sync) + ",\"timeout_ms\":" + g_timeoutMs
            + ",\"stream_every\":" + g_streamEvery + ",\"auto_restart\":" + B(g_autoRestart)
            + ",\"official_finish\":" + B(g_officialFinish));
        return false;
    }
    if (cmd == "MAP" && p.Length >= 2) {
        string name = line.Substr(4);
        ReleaseInputsOnly();
        g_armed = false;
        g_awaiting = false;
        ExecuteCommand("map " + name);
        SendEvent("map_requested", "\"file\":" + Q(name));
        return false;
    }
    if (cmd == "SPD" && p.Length == 2) {
        double f = Text::ParseFloat(p[1]);
        auto@ sim = GetSimulationManager();
        if (!(f > 0.0) || f > 100.0) {
            SendEvent("speed", "\"ok\":false,\"why\":\"range\",\"requested\":" + F(f));
            return false;
        }
        if (sim is null) {
            SendEvent("speed", "\"ok\":false,\"why\":\"no_simulation\",\"requested\":" + F(f));
            return false;
        }
        sim.SetSpeed(float(f));
        g_speed = f;
        SendEvent("speed", "\"ok\":true,\"requested\":" + F(f)
            + ",\"speed_variable\":" + F(GetVariableDouble("speed")));
        return false;
    }
    if (cmd == "PING" && p.Length == 2) {
        SendEvent("pong", "\"n\":" + p[1]);
        return false;
    }
    SendEvent("unknown_command", "\"line\":" + Q(line));
    return false;
}

// Non-blocking: drain the socket and handle complete lines.
bool Poll()
{
    if (g_client is null) {
        return false;
    }
    uint avail = g_client.Available;
    if (avail > 0) {
        g_inbuf += g_client.ReadString(avail);
    }
    if (g_inbuf.Length > 65536) {
        g_inbuf = "";
        Release("input_overflow");
        return false;
    }
    bool applied = false;
    int nl = g_inbuf.FindFirst("\n");
    while (nl >= 0) {
        string line = g_inbuf.Substr(0, nl);
        g_inbuf = g_inbuf.Substr(nl + 1);
        if (line.Length > 0 && line[line.Length - 1] == 13) {
            line = line.Substr(0, line.Length - 1);
        }
        if (line.Length > 0 && HandleLine(line)) {
            applied = true;
        }
        nl = g_inbuf.FindFirst("\n");
    }
    return applied;
}

void AcceptClient()
{
    if (g_server is null) {
        return;
    }
    // A new connection replaces the previous one (single controller, latest wins).
    Net::Socket@ incoming = g_server.Accept(0);
    if (incoming is null) {
        return;
    }
    if (g_client !is null) {
        Release("client_replaced");
        RestoreSpeed("client_replaced");
    }
    @g_client = incoming;
    if (g_client !is null) {
        g_client.NoDelay = true;
        g_inbuf = "";
        auto@ sim = GetSimulationManager();
        bool inRace = sim !is null && sim.InRace;
        Send("{\"kind\":\"hello\",\"bridge_version\":" + Q(BRIDGE_VERSION)
            + ",\"protocol\":1,\"port\":8479,\"wall_ms\":" + Time::Now
            + ",\"map_uid\":" + Q(MapUid()) + ",\"map_name\":" + Q(MapName())
            + ",\"in_race\":" + B(inRace)
            + ",\"game_state\":" + int(GetCurrentGameState())
            + ",\"speed\":" + F(GetVariableDouble("speed")) + "}");
    }
}

// ---------- callbacks ----------

void Render()
{
    AcceptClient();
    Poll();
    // Asynchronous wall-clock watchdog (also covers a frozen client between steps).
    if (g_awaiting && Time::Now >= g_awaitDeadline) {
        Release("action_timeout");
    }
    // Heartbeat: a failed write detects a dead client and releases inputs.
    if (g_client !is null && Time::Now - g_lastHeartbeat >= 500) {
        g_lastHeartbeat = Time::Now;
        SendEvent("heartbeat", "");
    }
}

void OnGameStateChanged(TM::GameState state)
{
    SendEvent("game_state", "\"new_state\":" + int(state));
    if (state != TM::GameState::LocalRace) {
        g_prevInRace = false;
        g_rewindPending = false;
        if (g_armed || g_awaiting) {
            Release("left_race");
        }
    }
}

void OnCheckpointCountChanged(SimulationManager@ sim, int current, int target)
{
    g_cpTarget = target;
    auto@ player = sim.PlayerInfo;
    SendEvent("checkpoint", "\"current\":" + current + ",\"target\":" + target
        + ",\"finished\":" + B(player.RaceFinished)
        + ",\"cur_checkpoint_count\":" + player.CurCheckpointCount);
    bool controlled = g_armed || g_awaiting;
    if (!controlled && g_rewindPending && !g_officialFinish && current == target
            && player.RaceFinished) {
        // Finish between R and the pending rewind (0.4.2): keep the race alive so the
        // rewind on the next run step still restarts it.
        sim.PreventSimulationFinish();
        SendEvent("finish_prevented", "\"cause\":\"pending_rewind\"");
        return;
    }
    if (!controlled || current != target || !player.RaceFinished || g_finishReported) {
        return;
    }
    // Controlled finish. Report it here, then keep the race alive: without
    // PreventSimulationFinish the game opens its end-of-race dialog a few seconds later
    // (even after a rewind), which stops OnRunStep and blocks every restart (J3-03).
    g_finishReported = true;
    SendEvent("finish", "\"race_time_ms\":" + player.RaceTime + ",\"checkpoints\":" + current
        + ",\"source\":\"checkpoint_callback\"");
    g_cpOverride = current;   // the game passes the new count; the player field may lag
    SendState(sim, "finish");
    g_cpOverride = -1;
    Release("finish");
    if (g_officialFinish) {
        SendEvent("finish_unprevented", "");
        return;   // let TMNF commit its finish and open its normal race-end dialog
    }
    sim.PreventSimulationFinish();
    SendEvent("finish_prevented", "");
    if (g_autoRestart) {
        g_rewindCause = "auto_restart";
        g_rewindPending = true;   // rewind on the next run step, not inside this callback
    }
}

void WaitForAction(SimulationManager@ sim)
{
    g_awaiting = true;
    g_awaitDeadline = Time::Now + g_timeoutMs;
    if (!g_sync) {
        return;   // keep simulating; Render()/OnRunStep() watchdog releases on timeout
    }
    while (g_client !is null) {
        if (Poll()) {
            return;
        }
        if (!g_awaiting) {
            return;   // released or reset by a command
        }
        if (Time::Now >= g_awaitDeadline) {
            Release("action_timeout");
            return;
        }
    }
    Release("client_lost");
    RestoreSpeed("client_lost");
}

bool StartStateUsable()
{
    return g_startState !is null && g_startUid.Length > 0 && g_startUid == MapUid();
}

// Save the first countdown tick of every new race (normal start, GiveUp or rewind).
void CaptureStartState(SimulationManager@ sim)
{
    int rt = sim.RaceTime;
    bool newRace = !g_prevInRace || g_prevRaceTime >= 0 || rt < g_prevRaceTime;
    g_prevInRace = true;
    g_prevRaceTime = rt;
    if (rt >= 0 || !newRace) {
        return;
    }
    if (sim.PlayerInfo.CurCheckpointCount != 0 || sim.PlayerInfo.RaceFinished) {
        return;
    }
    @g_startState = sim.SaveState();
    g_startUid = MapUid();
    SendEvent("start_state_saved", "\"saved_race_ms\":" + rt);
}

void DoRewind(SimulationManager@ sim)
{
    g_rewindPending = false;
    if (!StartStateUsable()) {
        SendEvent("rewind_failed", "\"cause\":" + Q(g_rewindCause) + ",\"why\":\"no_start_state\"");
        return;
    }
    ReleaseInputsOnly();
    g_armed = false;
    g_awaiting = false;
    g_holdTicks = 0;
    sim.RewindToState(g_startState);
    ApplyInputs(sim);   // neutral inputs on the restored state
    g_sawNegative = sim.RaceTime < 0;
    g_prevRaceTime = sim.RaceTime;
    g_finishReported = sim.PlayerInfo.RaceFinished;
    SendEvent("rewound", "\"cause\":" + Q(g_rewindCause)
        + ",\"checkpoints\":" + sim.PlayerInfo.CurCheckpointCount
        + ",\"finished\":" + B(sim.PlayerInfo.RaceFinished));
}

void OnRunStep(SimulationManager@ sim)
{
    AcceptClient();
    bool newAction = Poll();

    if (g_rewindPending) {
        DoRewind(sim);
        return;
    }

    CaptureStartState(sim);

    if (g_awaiting && !newAction && Time::Now >= g_awaitDeadline) {
        Release("action_timeout");
    }

    if (sim.RaceTime < 0) {
        g_sawNegative = true;
    }

    auto@ player = sim.PlayerInfo;
    if (player.RaceFinished && !g_finishReported) {
        // Fallback only: controlled finishes are normally handled in OnCheckpointCountChanged.
        g_finishReported = true;
        bool controlled = g_armed || g_awaiting;
        SendEvent("finish", "\"race_time_ms\":" + player.RaceTime
            + ",\"checkpoints\":" + player.CurCheckpointCount + ",\"source\":\"run_step\"");
        if (controlled) {
            SendState(sim, "finish");
            Release("finish");
            if (g_officialFinish) {
                SendEvent("finish_unprevented", "");
            } else {
                sim.PreventSimulationFinish();
                SendEvent("finish_prevented", "");
                if (g_autoRestart) {
                    g_rewindCause = "auto_restart";
                    DoRewind(sim);
                    return;
                }
            }
        }
    }

    if (g_waitStart && g_sawNegative && sim.RaceTime >= 0) {
        g_waitStart = false;
        SendState(sim, "start");
        if (g_client !is null) {
            WaitForAction(sim);
        }
        return;
    }

    if (g_armed && !g_awaiting) {
        ApplyInputs(sim);   // re-assert held inputs every step
        g_holdTicks--;
        if (g_holdTicks <= 0) {
            SendState(sim, "boundary");
            WaitForAction(sim);
        }
        return;
    }

    if (g_awaiting) {
        ApplyInputs(sim);   // async mode: previous action held until watchdog
        return;
    }

    if (g_client !is null && g_streamEvery > 0) {
        g_streamCounter++;
        if (g_streamCounter >= g_streamEvery) {
            g_streamCounter = 0;
            SendState(sim, "stream");
        }
    }
}
