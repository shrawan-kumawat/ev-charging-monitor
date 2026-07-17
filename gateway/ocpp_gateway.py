#!/usr/bin/env python3
"""
OCPP 1.6 Gateway
Translates MQTT telemetry from simulator into OCPP 1.6 JSON messages
"""

import json
import time
import uuid
import signal
import argparse
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from websocket import create_connection, WebSocket


class OCPPMessage:
    @staticmethod
    def call(action, payload):
        return [2, str(uuid.uuid4()), action, payload]
    
    @staticmethod
    def call_result(message_id, payload):
        return [3, message_id, payload]
    
    @staticmethod
    def call_error(message_id, error_code, error_description):
        return [4, message_id, error_code, error_description, {}]


class OCPPGateway:
    def __init__(self, station_id="CS-001", mqtt_broker="localhost", mqtt_port=1883,
                 ws_url="ws://localhost:8080/ocpp/CS-001"):
        self.station_id = station_id
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.ws_url = ws_url
        
        self.transaction_id = None
        self.meter_value_counter = 0
        
        self.mqtt_client = None
        self.ws_client = None
        self.connected = False
        self.running = False
        
        self.pending_calls = {}
        
    def start_mqtt(self):
        self.mqtt_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"ocpp-gateway-{self.station_id}-{uuid.uuid4().hex[:4]}"
        )
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            print(f"[*] MQTT connected to {self.mqtt_broker}:{self.mqtt_port}")
            return True
        except Exception as e:
            print(f"[!] MQTT connection failed: {e}")
            return False
    
    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        print(f"[*] MQTT subscribed to chargers/{self.station_id}/telemetry")
        client.subscribe(f"chargers/{self.station_id}/telemetry")
    
    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self._process_telemetry(payload)
        except Exception as e:
            print(f"[!] Error processing message: {e}")
    
    def connect_backend(self):
        try:
            self.ws_client = create_connection(self.ws_url)
            self.connected = True
            print(f"[*] WebSocket connected to {self.ws_url}")
            
            self._send_boot_notification()
            return True
        except Exception as e:
            print(f"[!] WebSocket connection failed: {e}")
            print("[*] Running in MQTT-only mode (no backend)")
            return False
    
    def _send_ws(self, message):
        if self.ws_client and self.connected:
            try:
                self.ws_client.send(json.dumps(message))
                return True
            except Exception as e:
                print(f"[!] WebSocket send failed: {e}")
                self.connected = False
        return False
    
    def _recv_ws(self, timeout=5):
        if self.ws_client and self.connected:
            try:
                self.ws_client.settimeout(timeout)
                response = self.ws_client.recv()
                return json.loads(response)
            except Exception:
                return None
        return None
    
    def _send_boot_notification(self):
        payload = {
            "chargePointVendor": "SimulatorCorp",
            "chargePointModel": "VirtualEVSE-v1",
            "chargePointSerialNumber": self.station_id,
            "firmwareVersion": "1.0.0",
            "meterType": "Virtual",
            "meterSerialNumber": f"SIM-{self.station_id}"
        }
        msg = OCPPMessage.call("BootNotification", payload)
        self._send_ws(msg)
        self.pending_calls[msg[1]] = "BootNotification"
        print(f"[→] BootNotification sent for {self.station_id}")
        
        response = self._recv_ws(timeout=3)
        if response:
            self._handle_response(response)
    
    def _send_status_notification(self, connector_id, status, error_code="NoError"):
        payload = {
            "connectorId": connector_id,
            "errorCode": error_code,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        msg = OCPPMessage.call("StatusNotification", payload)
        self._send_ws(msg)
        print(f"[→] StatusNotification: {status}")
    
    def _send_meter_values(self, connector_id, reading):
        self.meter_value_counter += 1
        
        payload = {
            "connectorId": connector_id,
            "transactionId": self.transaction_id,
            "meterValue": [{
                "timestamp": reading["timestamp"],
                "sampledValue": [
                    {"value": str(reading["voltage_l1"]), "context": "Sample.Periodic", 
                     "format": "Raw", "measurand": "Voltage", "phase": "L1", "unit": "V"},
                    {"value": str(reading["current_l1"]), "context": "Sample.Periodic",
                     "format": "Raw", "measurand": "Current.Import", "phase": "L1", "unit": "A"},
                    {"value": str(reading["power_kw"]), "context": "Sample.Periodic",
                     "format": "Raw", "measurand": "Power.Active.Import", "unit": "kW"},
                    {"value": str(reading["energy_kwh"]), "context": "Sample.Periodic",
                     "format": "Raw", "measurand": "Energy.Active.Import.Register", "unit": "kWh"},
                    {"value": str(reading["temperature"]), "context": "Sample.Periodic",
                     "format": "Raw", "measurand": "Temperature", "unit": "Celsius"}
                ]
            }]
        }
        msg = OCPPMessage.call("MeterValues", payload)
        self._send_ws(msg)
        print(f"[→] MeterValues #{self.meter_value_counter}: {reading['power_kw']}kW, {reading['temperature']}°C")
    
    def _send_start_transaction(self, connector_id, id_tag, meter_start, timestamp):
        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": int(meter_start * 1000),
            "timestamp": timestamp
        }
        msg = OCPPMessage.call("StartTransaction", payload)
        self._send_ws(msg)
        self.pending_calls[msg[1]] = "StartTransaction"
        print(f"[→] StartTransaction requested")
        
        response = self._recv_ws(timeout=3)
        if response:
            self._handle_response(response)
    
    def _send_stop_transaction(self, meter_stop, timestamp, reason="Local"):
        payload = {
            "transactionId": self.transaction_id,
            "meterStop": int(meter_stop * 1000),
            "timestamp": timestamp,
            "reason": reason
        }
        msg = OCPPMessage.call("StopTransaction", payload)
        self._send_ws(msg)
        self.pending_calls[msg[1]] = "StopTransaction"
        print(f"[→] StopTransaction requested")
        
        response = self._recv_ws(timeout=3)
        if response:
            self._handle_response(response)
    
    def _handle_response(self, response):
        if len(response) < 2:
            return
            
        msg_type = response[0]
        msg_id = response[1]
        
        if msg_type == 3:
            action = self.pending_calls.pop(msg_id, "Unknown")
            print(f"[←] {action} accepted")
            
            if action == "StartTransaction":
                self.transaction_id = response[2].get("transactionId")
                print(f"    Transaction ID: {self.transaction_id}")
                
        elif msg_type == 4:
            print(f"[!] CallError: {response[2]} - {response[3]}")
    
    def _process_telemetry(self, reading):
        status = reading.get("status", "Available")
        
        # FIX: Always send StatusNotification for EVERY status
        ocpp_status = self._map_status(status)
        self._send_status_notification(1, ocpp_status)
        
        if status == "Preparing" and not self.transaction_id:
            print(f"[*] EV connected on {self.station_id}")
            
            time.sleep(0.5)
            self._send_start_transaction(
                connector_id=1,
                id_tag=f"SIMULATED-ID-{self.station_id}",
                meter_start=reading.get("energy_kwh", 0),
                timestamp=reading["timestamp"]
            )
            
        elif status == "Charging" and self.transaction_id:
            self._send_meter_values(1, reading)
            
        elif status == "Finishing" and self.transaction_id:
            self._send_stop_transaction(
                meter_stop=reading.get("energy_kwh", 0),
                timestamp=reading["timestamp"],
                reason="EVDisconnected"
            )
            self.transaction_id = None
            
        elif status == "Faulted":
            print(f"[!] FAULT on {self.station_id}: {reading.get('fault_type', 'Unknown')}")
            
        elif status == "Available" and not self.transaction_id:
            pass  # StatusNotification already sent above
    
    def _map_status(self, sim_status):
        mapping = {
            "Available": "Available",
            "Preparing": "Preparing",
            "Charging": "Charging",
            "SuspendedEV": "SuspendedEV",
            "SuspendedEVSE": "SuspendedEVSE",
            "Finishing": "Finishing",
            "Reserved": "Reserved",
            "Unavailable": "Unavailable",
            "Faulted": "Faulted"
        }
        return mapping.get(sim_status, "Available")
    
    def start(self):
        self.running = True
        
        if not self.start_mqtt():
            return False
        
        self.connect_backend()
        
        print("\n[*] OCPP Gateway running. Press Ctrl+C to stop.\n")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        print("\n[*] Shutting down gateway...")
        
        if self.ws_client:
            try:
                self.ws_client.close()
            except:
                pass
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        print("[*] Gateway stopped")


def main():
    parser = argparse.ArgumentParser(description="OCPP 1.6 Gateway")
    parser.add_argument("--station-id", default="CS-001", help="Station ID")
    parser.add_argument("--mqtt-broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--ws-url", default="ws://localhost:8080/ocpp/CS-001",
                       help="Backend WebSocket URL")
    
    args = parser.parse_args()
    
    gateway = OCPPGateway(
        station_id=args.station_id,
        mqtt_broker=args.mqtt_broker,
        mqtt_port=args.mqtt_port,
        ws_url=args.ws_url
    )
    
    gateway.start()


if __name__ == "__main__":
    main()