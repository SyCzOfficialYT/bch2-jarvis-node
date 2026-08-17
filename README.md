# ◈ BCH2 JARVIS NODE

**Bitcoin Cash II Full Node + Extreme Futuristic Dashboard**

> Docker-first • Zero-manual • git pull = update • NerdQAxe++ ready

---

## Was ist das?

Ein komplett containerisiertes Stack für:

- **Bitcoin Cash II (BCH2) Full Node** (offizielles Core v27.0.2+)
- **Jarvis-like Realtime Dashboard** (neon, glass, live WebSocket, Voice-Report)
- **Lokaler Stratum-Proxy** für Solo-Mining mit NerdQAxe++ / Bitaxe / etc.
- Alles über `docker compose` – kein manuelles Binary-Gezerre

---

## Quick Start (1 Minute)

```bash
git clone https://github.com/SyCzOfficialYT/bch2-jarvis-node.git
cd bch2-jarvis-node

cp .env.example .env
# RPC-Passwort ist bereits gesetzt

docker compose up -d --build
```

Danach:

| Service              | URL / Port                          |
|----------------------|-------------------------------------|
| **Dashboard**        | http://localhost:3080               |
| BCH2 P2P             | 8339                                |
| BCH2 RPC             | 8342                                |
| Stratum (Solo)       | stratum+tcp://DEINE_IP:3333         |

---

## NerdQAxe++ konfigurieren

Im AxeOS Web-UI deines Miners:

```
Stratum Host:   <IP-deines-Servers>
Stratum Port:   3333
Username:       bitcoincashii:q...deine_adresse.worker1
Password:       x
```

> Tipp: Für maximale Chance auf Blocks empfehlen die meisten aktuell auch externe Solo-Pools (forge.bch2.org, solofury). Der eingebaute Proxy ist transparent und lokal – ideal zum Experimentieren und für komplette Self-Hosting-Setups.

---

## Update = git pull

```bash
./scripts/update.sh
# oder manuell:
git pull
docker compose up -d --build
```

Nichts manuell installieren. Configs bleiben in Volumes / gemounteten Dateien.

---

## Architektur

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  NerdQAxe++     │────▶│  Stratum Proxy   │────▶│  BCH2 Core      │
│  (SHA-256)      │     │  :3333           │     │  :8339 / :8342  │
└─────────────────┘     └──────────────────┘     └─────────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│  Browser        │◄───▶│  Dashboard       │◄──────────────┘
│  :3080          │ WS  │  Backend :3001   │   RPC polling
└─────────────────┘     └──────────────────┘
```

---

## Features Dashboard

- Live Height, Difficulty (mit Graphen)
- Confirmed / Unconfirmed / Immature Balance
- Block-Runde ~10 min mit Progress-Bar (kann überlaufen)
- Best Share dieser Runde + Best Share Ever
- Pulsierende Block-Parts-Animation
- Volles Live-Log
- Komplette Block-History
- Hashrate korrekt aus Shares berechnet
- Holding-Adresse automatisch generiert
- Voice-Report (Jarvis spricht)

---

## Sicherheit

1. RPC-Passwort ist bereits stark gesetzt.
2. Port 8342 und 3333 nur im LAN / hinter Firewall freigeben.
3. Dashboard aktuell ohne Login – bei öffentlichem Access Reverse-Proxy + Auth vorschalten.

---

## Lizenz

MIT – mach was draus.

**JARVIS online.**
