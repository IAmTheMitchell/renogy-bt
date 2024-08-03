import json
import logging
import aiohttp
import string
from datetime import datetime

PVOUTPUT_URL = "http://pvoutput.org/service/r2/addstatus.jsp"


class DataLogger:
    def __init__(self, config):
        self.config = config
        self.published_devices = set()

    def set_mqtt_client(self, mqtt_client):
        self.mqtt_client = mqtt_client

    async def log_remote(self, json_data):
        headers = {
            "Authorization": f"Bearer {self.config['remote_logging']['auth_header']}"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config["remote_logging"]["url"],
                json=json_data,
                timeout=15,
                headers=headers,
            ) as req:
                if req.status == 200:
                    logging.info("Log remote 200")
                else:
                    logging.error(f"Log remote error {req.status}")

    async def create_mqtt_device(self, device_data, device_name, device_model, topic):
        logging.info(
            f"Publishing MQTT device to Home Assistant discovery: {device_name}"
        )

        # Clean up fields before publishing
        remove_fields = ["function", "model", "device_id", "__device", "__client"]
        for field in remove_fields:
            device_data.pop(field)

        for entity in device_data:
            discovery_topic = f"homeassistant/sensor/{device_name}_{entity}/config"

            name = string.capwords(entity.replace("_", " ")).replace("Pv", "PV")

            payload = {
                "name": name,
                "state_topic": topic,
                "value_template": f"{{{{ value_json.{entity}}}}}",
                "unique_id": f"{device_name}_{entity}",
                "device": {
                    "identifiers": [device_name],
                    "name": device_name,
                    "model": device_model,
                    "manufacturer": "Renogy",
                },
            }

            # Entity specific configuration
            if "current" in entity:
                payload["device_class"] = "current"
                payload["unit_of_measurement"] = "A"
            elif "percent" in entity:
                payload["device_class"] = "battery"
                payload["unit_of_measurement"] = "%"
            elif "voltage" in entity:
                payload["device_class"] = "voltage"
                payload["unit_of_measurement"] = "V"
            elif "amp_hour" in entity:
                payload["unit_of_measurement"] = "ah"
            elif "temperature" in entity:
                payload["device_class"] = "temperature"
                payload["unit_of_measurement"] = "°F"
            elif "power" in entity:
                payload["device_class"] = "power"
                payload["unit_of_measurement"] = "W"

            try:
                await self.mqtt_client.publish(
                    discovery_topic,
                    payload=json.dumps(payload),
                    qos=0,
                    retain=True,
                )
            except Exception as e:
                logging.error(f"MQTT connection error: {e}")

        # Add device to published list
        self.published_devices.add(device_name)

    async def log_mqtt(self, json_data):
        logging.info(f"Logging {json_data['__device']} to MQTT")
        device_name = json_data["__device"]
        device_model = json_data["model"]
        topic = f"renogy/{device_model}/{device_name}"

        # Create Home Assistant device if new device
        if device_name not in self.published_devices:
            await self.create_mqtt_device(json_data, device_name, device_model, topic)
        # Publish metrics to MQTT
        try:
            await self.mqtt_client.publish(
                topic,
                payload=json.dumps(json_data),
                qos=0,
                retain=True,
            )
        except Exception as e:
            logging.error(f"MQTT connection error: {e}")

    async def log_pvoutput(self, json_data):
        date_time = datetime.now().strftime("d=%Y%m%d&t=%H:%M")
        data = f"{date_time}&v1={json_data['power_generation_today']}&v2={json_data['pv_power']}&v3={json_data['power_consumption_today']}&v4={json_data['load_power']}&v5={json_data['controller_temperature']}&v6={json_data['battery_voltage']}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Pvoutput-Apikey": self.config["pvoutput"]["api_key"],
            "X-Pvoutput-SystemId": self.config["pvoutput"]["system_id"],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                PVOUTPUT_URL, data=data, headers=headers
            ) as response:
                if response.status == 200:
                    logging.info("pvoutput 200")
                else:
                    logging.error(f"pvoutput error {response.status}")
