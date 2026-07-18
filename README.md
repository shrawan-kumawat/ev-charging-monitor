\# EV Charging Station IoT Monitor



This project is a simple IoT-based EV charging station monitoring system built to understand how Electric Vehicle (EV) chargers communicate using the OCPP 1.6 protocol.



The project simulates multiple charging stations, sends charging data over MQTT, converts it into OCPP messages, and displays the information on a real-time web dashboard.



\---



\## Features



\- Simulates multiple EV charging stations

\- Generates real-time charging data

\- Uses MQTT for communication

\- Converts MQTT messages into OCPP 1.6 messages

\- Displays live station status and telemetry on a dashboard

\- Supports fault simulation such as overheating and overcurrent

\- REST API for accessing station and transaction data

\- Designed so that a database like PostgreSQL can be added later



\---



\## System Architecture



```

Simulator (Python)

&#x20;       │

&#x20;     MQTT

&#x20;       │

&#x20;       ▼

&#x20;Eclipse Mosquitto

&#x20;       │

&#x20;       ▼

&#x20;OCPP Gateway

&#x20;       │

&#x20;  WebSocket

&#x20;       │

&#x20;       ▼

&#x20;Node.js Backend

&#x20;       │

&#x20;   REST API

&#x20;       │

&#x20;       ▼

&#x20;Dashboard

```



\---



\## Technologies Used



| Component | Technology |

|-----------|------------|

| Simulator | Python 3 |

| MQTT Broker | Eclipse Mosquitto (Docker) |

| Gateway | Python + paho-mqtt |

| Backend | Node.js, Express, WebSocket |

| Dashboard | HTML, CSS, JavaScript |



\---



\## Project Structure



```

ev-charging-project/

├── simulator/

│   └── charger\_simulator.py

├── gateway/

│   └── ocpp\_gateway.py

├── backend/

│   ├── server.js

│   └── package.json

├── dashboard/

│   └── index.html

├── .gitignore

└── README.md

```



\---



\## Prerequisites



Before running the project, make sure you have:



\- Python 3.12 or later

\- Node.js 20 or later

\- Docker Desktop



\---



\## Installation



Clone the repository:



```bash

git clone https://github.com/shrawan-kumawat/ev-charging-monitor.git

cd ev-charging-monitor

```



Install the Python packages:



```bash

pip install paho-mqtt websocket-client

```



Install the backend dependencies:



```bash

cd backend

npm install

```



Start the MQTT broker:



```bash

docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto

```



\---



\## Running the Project



\### Start the backend



```bash

cd backend

node server.js

```



\### Start the gateways



```bash

cd gateway



python ocpp\_gateway.py --station-id CS-001 --ws-url ws://localhost:8080/ocpp/CS-001



python ocpp\_gateway.py --station-id CS-002 --ws-url ws://localhost:8080/ocpp/CS-002



python ocpp\_gateway.py --station-id CS-003 --ws-url ws://localhost:8080/ocpp/CS-003

```



\### Start the dashboard



```bash

cd dashboard

npx serve . -l 3001

```



\### Start the simulators



```bash

cd simulator



python charger\_simulator.py --id CS-001 --scenario normal



python charger\_simulator.py --id CS-002 --scenario normal



python charger\_simulator.py --id CS-003 --scenario fault\_heat

```



Open the dashboard in your browser:



```

http://localhost:3001

```



\---



\## API Endpoints



| Method | Endpoint | Description |

|--------|----------|-------------|

| GET | `/api/stations` | Returns all charging stations |

| GET | `/api/telemetry/:stationId` | Returns telemetry of a station |

| GET | `/api/transactions` | Returns charging transactions |



\---



\## OCPP Messages



The gateway currently supports the following OCPP 1.6 messages:



\- BootNotification

\- StatusNotification

\- MeterValues

\- StartTransaction

\- StopTransaction



\---



\## Future Improvements



Some features that can be added later are:



\- PostgreSQL or MongoDB integration

\- User authentication

\- Remote charger control

\- Docker Compose support

\- OCPP 2.0.1 support

\- Historical data visualization



\---



\## License



This project is available under the MIT License.

