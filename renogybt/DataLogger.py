import json
import logging
import aiohttp
import asyncio
from aiomqtt import Client
from datetime import datetime

PVOUTPUT_URL = "http://pvoutput.org/service/r2/addstatus.jsp"


class DataLogger:
    def __init__(self, config):
        self.config = config

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

    async def log_mqtt(self, json_data):
        logging.info(f"mqtt logging")
        user = self.config["mqtt"]["user"]
        password = self.config["mqtt"]["password"]

        async with Client(
            self.config["mqtt"]["server"],
            port=self.config["mqtt"]["port"],
            username=user,
            password=password,
            identifier="renogy-bt",
        ) as client:
            try:
                await client.publish(
                    self.config["mqtt"]["topic"],
                    payload=json.dumps(json_data),
                    qos=0,
                    retain=False,
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
