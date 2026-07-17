const express = require('express');
const WebSocket = require('ws');
const { Pool } = require('pg');

// ─────────────────────────────────────────────────────────
// CONFIGURATION
// ─────────────────────────────────────────────────────────

const HTTP_PORT = 3000;
const WS_PORT = 8080;
const DB_CONFIG = {
    host: 'localhost',
    port: 5432,
    user: 'postgres',
    password: 'password',
    database: 'ev_charging'
};

// ─────────────────────────────────────────────────────────
// DATABASE SETUP
// ─────────────────────────────────────────────────────────

let db;
let useInMemory = false;
const memoryStore = {
    stations: new Map(),
    telemetry: [],
    transactions: []
};

async function initDatabase() {
    try {
        db = new Pool(DB_CONFIG);
        await db.query(`
            CREATE TABLE IF NOT EXISTS stations (
                station_id VARCHAR(50) PRIMARY KEY,
                vendor VARCHAR(100),
                model VARCHAR(100),
                status VARCHAR(20) DEFAULT 'Available',
                last_seen TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        `);
        await db.query(`
            CREATE TABLE IF NOT EXISTS telemetry (
                id SERIAL PRIMARY KEY,
                station_id VARCHAR(50),
                timestamp TIMESTAMP,
                status VARCHAR(20),
                voltage FLOAT,
                current FLOAT,
                power_kw FLOAT,
                energy_kwh FLOAT,
                temperature FLOAT,
                fault BOOLEAN,
                fault_type VARCHAR(50)
            )
        `);
        await db.query(`
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                station_id VARCHAR(50),
                transaction_id INTEGER,
                connector_id INTEGER,
                id_tag VARCHAR(50),
                meter_start FLOAT,
                meter_stop FLOAT,
                start_time TIMESTAMP,
                stop_time TIMESTAMP,
                reason VARCHAR(50)
            )
        `);
        console.log('[DB] PostgreSQL connected');
    } catch (err) {
        console.log('[DB] PostgreSQL not available, using in-memory store');
        useInMemory = true;
    }
}

// ─────────────────────────────────────────────────────────
// OCPP MESSAGE HANDLERS
// ─────────────────────────────────────────────────────────

const connections = new Map(); // stationId -> ws

function sendOCPPResponse(ws, messageId, payload) {
    const response = [3, messageId, payload];
    ws.send(JSON.stringify(response));
    console.log(`[→] CallResult to ${ws.stationId}: ${JSON.stringify(response).substring(0, 80)}`);
}

function sendOCPPError(ws, messageId, errorCode, description) {
    const error = [4, messageId, errorCode, description, {}];
    ws.send(JSON.stringify(error));
    console.log(`[!] CallError: ${errorCode} - ${description}`);
}

async function handleBootNotification(ws, messageId, payload) {
    const { chargePointVendor, chargePointModel, chargePointSerialNumber } = payload;
    const stationId = chargePointSerialNumber || ws.stationId || 'unknown';
    ws.stationId = stationId;
    
    console.log(`[*] BootNotification from ${stationId}`);
    console.log(`    Vendor: ${chargePointVendor}, Model: ${chargePointModel}`);
    
    // Store connection
    connections.set(stationId, ws);
    
    // Store station
    if (useInMemory) {
        memoryStore.stations.set(stationId, {
            station_id: stationId,
            vendor: chargePointVendor,
            model: chargePointModel,
            status: 'Available',
            last_seen: new Date()
        });
    } else {
        await db.query(`
            INSERT INTO stations (station_id, vendor, model, last_seen)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (station_id) DO UPDATE SET
                vendor = EXCLUDED.vendor,
                model = EXCLUDED.model,
                last_seen = NOW()
        `, [stationId, chargePointVendor, chargePointModel]);
    }
    
    sendOCPPResponse(ws, messageId, {
        status: 'Accepted',
        currentTime: new Date().toISOString(),
        interval: 300
    });
}

async function handleStatusNotification(ws, messageId, payload) {
    const { connectorId, status, errorCode, timestamp } = payload;
    const stationId = ws.stationId || 'unknown';
    console.log(`[*] StatusNotification from ${stationId}: Connector ${connectorId} = ${status}`);
    
    // Update station status
    if (useInMemory) {
        const station = memoryStore.stations.get(stationId);
        if (station) {
            station.status = status;
            station.last_seen = new Date();
        }
    } else {
        await db.query(`
            UPDATE stations SET status = $1, last_seen = NOW()
            WHERE station_id = $2
        `, [status, stationId]);
    }
}

async function handleStartTransaction(ws, messageId, payload) {
    const { connectorId, idTag, meterStart, timestamp } = payload;
    const stationId = ws.stationId || 'unknown';
    const transactionId = Date.now() % 1000000;
    
    console.log(`[*] StartTransaction from ${stationId}`);
    console.log(`    Connector: ${connectorId}, ID Tag: ${idTag}`);
    
    if (useInMemory) {
        memoryStore.transactions.push({
            station_id: stationId,
            transaction_id: transactionId,
            connector_id: connectorId,
            id_tag: idTag,
            meter_start: meterStart / 1000,
            start_time: timestamp
        });
    } else {
        await db.query(`
            INSERT INTO transactions (station_id, transaction_id, connector_id, id_tag, meter_start, start_time)
            VALUES ($1, $2, $3, $4, $5, $6)
        `, [stationId, transactionId, connectorId, idTag, meterStart / 1000, timestamp]);
    }
    
    sendOCPPResponse(ws, messageId, {
        transactionId: transactionId,
        idTagInfo: {
            status: 'Accepted',
            expiryDate: new Date(Date.now() + 3600000).toISOString()
        }
    });
}

async function handleStopTransaction(ws, messageId, payload) {
    const { transactionId, meterStop, timestamp, reason } = payload;
    const stationId = ws.stationId || 'unknown';
    
    console.log(`[*] StopTransaction from ${stationId}`);
    console.log(`    Transaction: ${transactionId}, Meter Stop: ${meterStop} Wh`);
    
    if (useInMemory) {
        const tx = memoryStore.transactions.find(t => t.transaction_id === transactionId);
        if (tx) {
            tx.meter_stop = meterStop / 1000;
            tx.stop_time = timestamp;
            tx.reason = reason;
        }
    } else {
        await db.query(`
            UPDATE transactions 
            SET meter_stop = $1, stop_time = $2, reason = $3
            WHERE transaction_id = $4
        `, [meterStop / 1000, timestamp, reason, transactionId]);
    }
    
    sendOCPPResponse(ws, messageId, {
        idTagInfo: { status: 'Accepted' }
    });
}

async function handleMeterValues(ws, messageId, payload) {
    const { connectorId, transactionId, meterValue } = payload;
    const stationId = ws.stationId || 'unknown';
    
    if (!meterValue || meterValue.length === 0) return;
    
    const reading = meterValue[0];
    const sampled = reading.sampledValue || [];
    
    let voltage, current, power, energy, temperature;
    for (const sample of sampled) {
        const measurand = sample.measurand || '';
        const value = parseFloat(sample.value);
        
        if (measurand === 'Voltage') voltage = value;
        else if (measurand === 'Current.Import') current = value;
        else if (measurand === 'Power.Active.Import') power = value;
        else if (measurand === 'Energy.Active.Import.Register') energy = value;
        else if (measurand === 'Temperature') temperature = value;
    }
    
    console.log(`[*] MeterValues from ${stationId}: ${power?.toFixed(2)}kW, ${temperature?.toFixed(1)}°C`);
    
    // Store telemetry
    if (useInMemory) {
        memoryStore.telemetry.push({
            station_id: stationId,
            timestamp: reading.timestamp,
            status: 'Charging',
            voltage,
            current,
            power_kw: power,
            energy_kwh: energy,
            temperature,
            fault: false
        });
    } else {
        await db.query(`
            INSERT INTO telemetry (station_id, timestamp, status, voltage, current, power_kw, energy_kwh, temperature, fault)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        `, [stationId, reading.timestamp, 'Charging', voltage, current, power, energy, temperature, false]);
    }
}

// ─────────────────────────────────────────────────────────
// WEBSOCKET SERVER
// ─────────────────────────────────────────────────────────

const wss = new WebSocket.Server({ port: WS_PORT });

wss.on('connection', (ws, req) => {
    const path = req.url;
    const stationId = path.split('/').pop() || 'unknown';
    ws.stationId = stationId;
    
    console.log(`\n[*] OCPP connection from ${stationId} at ${path}`);
    
    ws.on('message', async (data) => {
        try {
            const message = JSON.parse(data);
            console.log(`[←] Received from ${ws.stationId}: ${message[2] || '?'}`);
            
            if (!Array.isArray(message) || message.length < 4) {
                console.log('[!] Invalid OCPP message format');
                return;
            }
            
            const [msgType, messageId, action, payload] = message;
            
            if (msgType === 2) {
                switch (action) {
                    case 'BootNotification':
                        await handleBootNotification(ws, messageId, payload);
                        break;
                    case 'StatusNotification':
                        await handleStatusNotification(ws, messageId, payload);
                        break;
                    case 'StartTransaction':
                        await handleStartTransaction(ws, messageId, payload);
                        break;
                    case 'StopTransaction':
                        await handleStopTransaction(ws, messageId, payload);
                        break;
                    case 'MeterValues':
                        await handleMeterValues(ws, messageId, payload);
                        break;
                    default:
                        console.log(`[!] Unknown action: ${action}`);
                        sendOCPPError(ws, messageId, 'NotImplemented', `Action ${action} not supported`);
                }
            }
        } catch (err) {
            console.log(`[!] Error handling message: ${err.message}`);
        }
    });
    
    ws.on('close', () => {
        console.log(`[*] Connection closed: ${ws.stationId}`);
        connections.delete(ws.stationId);
    });
});

console.log(`[*] OCPP WebSocket server listening on ws://localhost:${WS_PORT}`);

// ─────────────────────────────────────────────────────────
// REST API
// ─────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    next();
});

app.get('/api/stations', async (req, res) => {
    try {
        let stations;
        if (useInMemory) {
            stations = Array.from(memoryStore.stations.values());
        } else {
            const result = await db.query('SELECT * FROM stations');
            stations = result.rows;
        }
        res.json(stations);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/telemetry/:stationId', async (req, res) => {
    try {
        const { stationId } = req.params;
        let data;
        if (useInMemory) {
            data = memoryStore.telemetry
                .filter(t => t.station_id === stationId)
                .slice(-100);
        } else {
            const result = await db.query(`
                SELECT * FROM telemetry 
                WHERE station_id = $1 
                ORDER BY timestamp DESC 
                LIMIT 100
            `, [stationId]);
            data = result.rows;
        }
        res.json(data);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/transactions', async (req, res) => {
    try {
        let data;
        if (useInMemory) {
            data = memoryStore.transactions;
        } else {
            const result = await db.query('SELECT * FROM transactions ORDER BY id DESC');
            data = result.rows;
        }
        res.json(data);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.listen(HTTP_PORT, () => {
    console.log(`[*] REST API listening on http://localhost:${HTTP_PORT}`);
});

// ─────────────────────────────────────────────────────────
// STARTUP
// ─────────────────────────────────────────────────────────

initDatabase().then(() => {
    console.log('\n[*] Backend server ready');
    console.log(`    WebSocket: ws://localhost:${WS_PORT}`);
    console.log(`    REST API:  http://localhost:${HTTP_PORT}`);
    console.log(`    Database:  ${useInMemory ? 'In-Memory' : 'PostgreSQL'}`);
    console.log('');
});