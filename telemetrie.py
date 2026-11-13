"""Affiche dans le terminal les mesures envoyees par TelemetrieVoiture.as.

Lancer avec : uv run python telemetrie.py
"""

import socket
import time


HOST = "127.0.0.1"
PORT = 8478


def main() -> None:
    print("En attente de TMInterface (jeu + modloader)...", flush=True)
    try:
        while True:
            try:
                with socket.create_connection((HOST, PORT), timeout=2) as conn:
                    conn.settimeout(None)
                    print("Connecté. Lance une course pour voir les données.", flush=True)
                    with conn.makefile("r", encoding="utf-8") as lines:
                        for line in lines:
                            parts = line.split()
                            if parts == ["WAIT"]:
                                print("\rEn attente d'une course...                 ", end="", flush=True)
                            elif len(parts) == 5 and parts[0] == "DATA":
                                _, speed, gear, rpm, sliding = parts
                                print(
                                    f"\rVitesse: {speed:>3} km/h | "
                                    f"Rapport: {gear:>2} | "
                                    f"Régime: {rpm:>5} tr/min | "
                                    f"Glisse: {'oui' if sliding == '1' else 'non':<3}   ",
                                    end="",
                                    flush=True,
                                )
                    print("\nConnexion perdue. Nouvelle tentative...", flush=True)
            except (ConnectionError, OSError):
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nArrêt de la télémétrie.")


if __name__ == "__main__":
    main()
