// Plugin TMInterface : affiche les donnees en jeu et les envoie au terminal.

Net::Socket@ g_server = null;
Net::Socket@ g_client = null;
uint64 g_lastSend = 0;

void Main()
{
    @g_server = Net::Socket();
    if (!g_server.Listen("127.0.0.1", 8478)) {
        log("Telemetrie : impossible d'ouvrir le port local 8478", Severity::Error);
        @g_server = null;
    }
}

void OnDisabled()
{
    @g_client = null;
    @g_server = null;
}

PluginInfo@ GetPluginInfo()
{
    PluginInfo info;
    info.Author = "zen";
    info.Name = "Telemetrie Voiture";
    info.Description = "Vitesse, rapport, regime moteur et glisse en jeu et dans le terminal";
    info.Version = "1.1.0";
    return info;
}

void Render()
{
    if (g_server !is null && g_client is null) {
        @g_client = g_server.Accept(0);
    }

    bool ready = false;
    uint speed = 0;
    int gear = 0;
    int rpm = 0;
    bool sliding = false;
    auto@ sim = GetSimulationManager();
    if (sim !is null && sim.InRace) {
        auto@ player = sim.PlayerInfo;
        auto@ car = sim.SceneVehicleCar;
        if (player !is null && car !is null) {
            ready = true;
            speed = player.DisplaySpeed;
            gear = car.CarEngine.Gear;
            rpm = int(car.CarEngine.ActualRPM);
            sliding = car.IsSliding;
        }
    }

    if (UI::Begin("Telemetrie voiture")) {
        if (!ready) {
            UI::Text("Lance une course pour voir les donnees.");
        } else {
            UI::Text("Vitesse : " + Text::FormatUInt(speed) + " km/h");
            UI::Text("Rapport : " + Text::FormatInt(gear));
            UI::Text("Regime : " + Text::FormatInt(rpm) + " tr/min");
            UI::Text("Glisse : " + (sliding ? "oui" : "non"));
        }
    }
    UI::End();

    if (g_client !is null && Time::Now - g_lastSend >= 200) {
        string line = "WAIT\n";
        if (ready) {
            line = "DATA " + Text::FormatUInt(speed) + " "
                + Text::FormatInt(gear) + " " + Text::FormatInt(rpm) + " "
                + (sliding ? "1" : "0") + "\n";
        }
        if (!g_client.Write(line)) {
            @g_client = null;
        }
        g_lastSend = Time::Now;
    }
}
