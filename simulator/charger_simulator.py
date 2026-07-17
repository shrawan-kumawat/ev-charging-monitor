import json
import random
import time
import signal
import argparse
from datetime import datetime, timezone
from enum import Enum


class ChargerStatus(Enum):
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    FAULTED = "Faulted"
    FINISHING = "Finishing"


class ChargerSimulator:
    def __init__(self, station_id="CS-001", max_current=32.0):
        self.station_id = station_id
        self.max_current = max_current
        self.rated_voltage = 230.0
        self.status = ChargerStatus.AVAILABLE
        self.voltage = self.rated_voltage
        self.current = 0.0
        self.power_kw = 0.0
        self.energy_kwh = 0.0
        self.temperature = 25.0
        self.session_active = False
        self.target_current = 0.0
        self.fault_injected = False
        self.fault_type = None
        self.ambient_temp = 25.0

    def plug_in(self):
        if self.status == ChargerStatus.AVAILABLE:
            self.status = ChargerStatus.PREPARING
            print(f"[{self.station_id}] EV plugged in")
            return True
        return False

    def start_charging(self, requested_current=None):
        if self.status != ChargerStatus.PREPARING:
            return False
        if self.fault_injected:
            return False
        self.target_current = min(requested_current or self.max_current, self.max_current)
        self.status = ChargerStatus.CHARGING
        self.session_active = True
        print(f"[{self.station_id}] Charging started at {self.target_current}A")
        return True

    def stop_charging(self):
        if not self.session_active:
            return False
        self.status = ChargerStatus.FINISHING
        self.target_current = 0.0
        self.session_active = False
        print(f"[{self.station_id}] Charging stopped. Energy: {self.energy_kwh:.3f} kWh")
        return True

    def unplug(self):
        if self.status == ChargerStatus.CHARGING:
            self.stop_charging()
        self.status = ChargerStatus.AVAILABLE
        self.energy_kwh = 0.0
        self.current = 0.0
        self.power_kw = 0.0
        print(f"[{self.station_id}] EV unplugged")

    def inject_fault(self, fault_type="overheat"):
        self.fault_injected = True
        self.fault_type = fault_type
        self.status = ChargerStatus.FAULTED
        self.target_current = 0.0
        if fault_type == "overheat":
            self.temperature = random.uniform(85, 105)
        elif fault_type == "overcurrent":
            self.current = random.uniform(40, 55)
        print(f"[{self.station_id}] FAULT: {fault_type.upper()}")

    def clear_fault(self):
        self.fault_injected = False
        self.fault_type = None
        self.temperature = self.ambient_temp
        self.current = 0.0
        self.voltage = self.rated_voltage
        self.status = ChargerStatus.AVAILABLE
        print(f"[{self.station_id}] Fault cleared")

    def tick(self, dt=1.0):
        if self.status == ChargerStatus.FAULTED:
            self._cool(dt)
            return self._get_reading()

        if not self.session_active:
            self._cool(dt)
            self.current = 0.0
            self.power_kw = 0.0
            return self._get_reading()

        ramp_speed = 5.0
        delta = self.target_current - self.current
        if abs(delta) > 0.1:
            step = min(abs(delta), ramp_speed * dt) * (1 if delta > 0 else -1)
            self.current += step
        else:
            self.current = self.target_current

        self.current += random.gauss(0, 0.15)
        self.current = max(0, self.current)

        voltage_drop = self.current * 0.05
        self.voltage = self.rated_voltage - voltage_drop + random.gauss(0, 0.3)

        self.power_kw = (self.voltage * self.current) / 1000.0
        self.energy_kwh += self.power_kw * (dt / 3600.0)

        heat_input = (self.current ** 2) * 0.001 + self.power_kw * 0.5
        temp_rise = heat_input * 2.5 * dt
        temp_diff = self.temperature - self.ambient_temp
        cooling = 0.8 * temp_diff * dt
        self.temperature += temp_rise - cooling + random.gauss(0, 0.1)

        if self.temperature > 80 and not self.fault_injected:
            self.inject_fault("overheat")
        elif self.current > self.max_current * 1.2 and not self.fault_injected:
            self.inject_fault("overcurrent")

        return self._get_reading()

    def _cool(self, dt):
        temp_diff = self.temperature - self.ambient_temp
        self.temperature -= 0.8 * temp_diff * dt * 0.5
        self.temperature += random.gauss(0, 0.05)

    def _get_reading(self):
        return {
            "station_id": self.station_id,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": self.status.value,
            "voltage_l1": round(self.voltage, 2),
            "current_l1": round(self.current, 2),
            "power_kw": round(self.power_kw, 3),
            "energy_kwh": round(self.energy_kwh, 4),
            "temperature": round(self.temperature, 2),
            "max_current": self.max_current,
            "fault": self.fault_injected,
            "fault_type": self.fault_type
        }


class MQTTPublisher:
    def __init__(self, broker_host="localhost", broker_port=1883):
        self.client = None
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.connected = False

    def connect(self):
        import paho.mqtt.client as mqtt
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sim-{random.randint(1000, 9999)}"
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        try:
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"MQTT connection failed: {e}")
            return False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = True
        print(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        print("Disconnected from MQTT broker")

    def publish(self, station_id, payload):
        if not self.connected:
            return False
        topic = f"chargers/{station_id}/telemetry"
        try:
            self.client.publish(topic, json.dumps(payload), qos=1)
            return True
        except Exception as e:
            print(f"Publish error: {e}")
            return False

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()


def run_simulation(station_id, broker, port, scenario="normal"):
    charger = ChargerSimulator(station_id, max_current=32.0)
    mqtt = MQTTPublisher(broker, port)

    if not mqtt.connect():
        print("Failed to connect to MQTT. Exiting.")
        return

    running = True

    def shutdown(sig, frame):
        nonlocal running
        running = False
        print("\nShutting down...")

    signal.signal(signal.SIGINT, shutdown)

    print(f"\n{'='*50}")
    print(f"  EV Charger Simulator: {station_id}")
    print(f"  Scenario: {scenario}")
    print(f"  MQTT: {broker}:{port}")
    print(f"{'='*50}\n")

    tick_count = 0

    while running:
        if scenario == "normal":
            if tick_count == 3:
                charger.plug_in()
            if tick_count == 5 and charger.status == ChargerStatus.PREPARING:
                charger.start_charging(requested_current=32.0)
            if tick_count == 65 and charger.status == ChargerStatus.CHARGING:
                charger.stop_charging()
            if tick_count == 68 and charger.status == ChargerStatus.FINISHING:
                charger.unplug()
            if tick_count >= 75:
                running = False

        elif scenario == "fault_heat":
            if tick_count == 3:
                charger.plug_in()
            if tick_count == 5:
                charger.start_charging(32.0)
            if tick_count == 50 and charger.status == ChargerStatus.FAULTED:
                charger.clear_fault()
            if tick_count == 55:
                charger.start_charging(16.0)
            if tick_count == 100:
                charger.stop_charging()
                charger.unplug()
                running = False

        elif scenario == "fault_current":
            if tick_count == 3:
                charger.plug_in()
            if tick_count == 5:
                charger.start_charging(32.0)
            if tick_count == 20:
                charger.inject_fault("overcurrent")
            if tick_count == 40:
                charger.clear_fault()
                charger.start_charging(16.0)
            if tick_count == 80:
                charger.stop_charging()
                charger.unplug()
                running = False

        elif scenario == "idle":
            pass

        reading = charger.tick(dt=1.0)
        mqtt.publish(station_id, reading)

        status_icon = {
            "Available": "OK", "Preparing": "--", "Charging": ">>",
            "Faulted": "!!", "Finishing": "XX"
        }.get(reading["status"], "??")

        print(f"[{tick_count:3d}s] {status_icon} {reading['status']:12s} | "
              f"{reading['power_kw']:6.3f} kW | "
              f"{reading['current_l1']:5.1f}A | "
              f"{reading['voltage_l1']:6.1f}V | "
              f"{reading['temperature']:5.1f}C | "
              f"{reading['energy_kwh']:7.4f} kWh"
              + (f" | ALERT: {reading['fault_type']}" if reading['fault'] else ""))

        tick_count += 1
        time.sleep(1.0)

    mqtt.disconnect()
    print(f"\nSimulation complete. Total ticks: {tick_count}")


def main():
    parser = argparse.ArgumentParser(description="EV Charging Station Simulator")
    parser.add_argument("--id", default="CS-001", help="Station ID")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--scenario", default="normal",
                       choices=["normal", "fault_heat", "fault_current", "idle"],
                       help="Simulation scenario")
    args = parser.parse_args()
    run_simulation(args.id, args.broker, args.port, args.scenario)


if __name__ == "__main__":
    main()