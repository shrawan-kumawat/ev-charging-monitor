# EV Charging Station IoT Monitor

An IoT-based monitoring system that demonstrates communication between electric vehicle charging stations and a central server using the OCPP 1.6 protocol.

The project simulates multiple charging stations, publishes charging data through MQTT, converts the data into OCPP messages, and displays station information on a real-time web dashboard.

---

## Features

* Simulates multiple EV charging stations
* Generates real-time charging data
* Uses MQTT for communication between simulators and gateways
* Converts MQTT data into OCPP 1.6 messages
* Displays live station status and telemetry
* Simulates faults such as overheating and overcurrent
* Provides REST API endpoints for station and transaction data
* Supports future database integration

---

## System Architecture

```text
Python Charger Simulator
          │
          │ MQTT
          ▼
  Eclipse Mosquitto
          │
          │ MQTT
          ▼
     OCPP Gateway
          │
          │ OCPP 1.6 over WebSocket
          ▼
    Node.js Backend
          │
          │ REST API
          ▼
      Web Dashboard
```

### Data Flow

1. The charger simulator generates charging and status data.
2. The data is published to the MQTT broker.
3. The OCPP gateway receives the MQTT messages.
4. The gateway converts the data into OCPP 1.6 messages.
5. The backend receives the OCPP messages through WebSocket connections.
6. The dashboard retrieves and displays the latest data using the REST API.

---

## Technologies Used

| Component         | Technology                          |
| ----------------- | ----------------------------------- |
| Charger Simulator | Python 3                            |
| MQTT Broker       | Eclipse Mosquitto                   |
| OCPP Gateway      | Python, Paho MQTT, WebSocket Client |
| Backend           | Node.js, Express, WebSocket         |
| Dashboard         | HTML, CSS, JavaScript               |
| Container Runtime | Docker                              |

---

## Project Structure

```text
ev-charging-monitor/
├── simulator/
│   └── charger_simulator.py
├── gateway/
│   └── ocpp_gateway.py
├── backend/
│   ├── server.js
│   └── package.json
├── dashboard/
│   └── index.html
├── .gitignore
└── README.md
```

---

## Prerequisites

Install the following software before running the project:

* Python 3.12 or later
* Node.js 20 or later
* Docker Desktop
* Git

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/shrawan-kumawat/ev-charging-monitor.git
cd ev-charging-monitor
```

### 2. Install the Python packages

```bash
pip install paho-mqtt websocket-client
```

### 3. Install the backend dependencies

```bash
cd backend
npm install
cd ..
```

### 4. Start the MQTT broker

```bash
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto
```

If the Mosquitto container already exists, start it with:

```bash
docker start mosquitto
```

---

## Running the Project

Run each component in a separate terminal.

### 1. Start the backend

```bash
cd backend
node server.js
```

The backend runs on:

```text
http://localhost:8080
```

### 2. Start the OCPP gateways

Open a separate terminal for each charging station.

**Station CS-001**

```bash
cd gateway
python ocpp_gateway.py --station-id CS-001 --ws-url ws://localhost:8080/ocpp/CS-001
```

**Station CS-002**

```bash
cd gateway
python ocpp_gateway.py --station-id CS-002 --ws-url ws://localhost:8080/ocpp/CS-002
```

**Station CS-003**

```bash
cd gateway
python ocpp_gateway.py --station-id CS-003 --ws-url ws://localhost:8080/ocpp/CS-003
```

### 3. Start the dashboard

```bash
cd dashboard
npx serve . -l 3001
```

Open the dashboard at:

```text
http://localhost:3001
```

### 4. Start the charger simulators

Open a separate terminal for each simulator.

**Station CS-001 — Normal operation**

```bash
cd simulator
python charger_simulator.py --id CS-001 --scenario normal
```

**Station CS-002 — Normal operation**

```bash
cd simulator
python charger_simulator.py --id CS-002 --scenario normal
```

**Station CS-003 — Overheating fault**

```bash
cd simulator
python charger_simulator.py --id CS-003 --scenario fault_heat
```

---

## API Endpoints

| Method | Endpoint                    | Description                              |
| ------ | --------------------------- | ---------------------------------------- |
| `GET`  | `/api/stations`             | Returns all charging stations            |
| `GET`  | `/api/telemetry/:stationId` | Returns telemetry for a specific station |
| `GET`  | `/api/transactions`         | Returns charging transaction data        |

### Example Requests

Get all charging stations:

```bash
curl http://localhost:8080/api/stations
```

Get telemetry for station `CS-001`:

```bash
curl http://localhost:8080/api/telemetry/CS-001
```

Get all transactions:

```bash
curl http://localhost:8080/api/transactions
```

---

## Supported OCPP 1.6 Messages

The gateway supports the following OCPP messages:

* `BootNotification`
* `StatusNotification`
* `MeterValues`
* `StartTransaction`
* `StopTransaction`

---

## Fault Simulation

The simulator can reproduce different charger operating conditions.

| Scenario            | Description                          |
| ------------------- | ------------------------------------ |
| `normal`            | Simulates normal charging operation  |
| `fault_heat`        | Simulates charger overheating        |
| `fault_overcurrent` | Simulates excessive charging current |

Example:

```bash
python charger_simulator.py --id CS-001 --scenario fault_overcurrent
```

---

## Possible Improvements

* Add PostgreSQL or MongoDB storage
* Add user authentication and authorization
* Add remote start and stop controls
* Add Docker Compose configuration
* Add historical telemetry charts
* Add alerts and notification support
* Add automated tests
* Add OCPP 2.0.1 support
* Deploy the backend and dashboard to a cloud platform

---

## License

This project is licensed under the MIT License.
