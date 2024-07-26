import logging
import json
import asyncio
from datetime import datetime
from os import access, R_OK
from os.path import isfile
from typing import Dict
from renogybt import (
    InverterClient,
    RoverClient,
    RoverHistoryClient,
    BatteryClient,
    DataLogger,
    Utils,
)


def is_readable(file):
    return isfile(file) and access(file, R_OK)


def load_user_config():
    try:
        with open("/data/options.json") as f:
            conf = json.load(f)
        return conf
    except Exception as e:
        print("error reading /data/options.json, trying options.json", e)
        with open("options.json") as f:
            conf = json.load(f)
        return conf


# Load config
config: Dict[str, any] = load_user_config()

# Set up logger
log_level = logging.getLevelName(config["data"]["log_level"])
logging.basicConfig(level=log_level)
logger = logging.getLogger()
logger.info(f"Starting renogybtaddon.py - {datetime.now()}")

# Disable script polling
config["data"]["enable_polling"] = False

# Set up remote logging
data_logger: DataLogger = DataLogger(config)


# The callback function when data is received
async def on_data_received(client, data):
    filtered_data = Utils.filter_fields(data, config["data"]["fields"])
    logging.info(f"{client.bleManager.device.name} => {filtered_data}")
    if config["remote_logging"]["enabled"]:
        await data_logger.log_remote(json_data=filtered_data)
    if config["mqtt"]["enabled"]:
        await data_logger.log_mqtt(json_data=filtered_data)
    if (
        config["pvoutput"]["enabled"]
        and config["device"]["type"] == "RNG_CTRL"
    ):
        await data_logger.log_pvoutput(json_data=filtered_data)
    await client.stop()


# Start client
async def start_client(device_config):
    logger.info(f"Device alias: {device_config['device']['alias']}")
    logger.info(f"Device type: {device_config['device']['type']}")
    if device_config["device"]["type"] == "RNG_CTRL":
        await RoverClient(device_config, on_data_received).start()
    elif device_config["device"]["type"] == "RNG_CTRL_HIST":
        await RoverHistoryClient(device_config, on_data_received).start()
    elif device_config["device"]["type"] == "RNG_BATT":
        await BatteryClient(device_config, on_data_received).start()
    elif device_config["device"]["type"] == "RNG_INVT":
        await InverterClient(device_config, on_data_received).start()
    else:
        logging.error("unknown device type")


async def main():
    while True:
        for device in config["devices"]:
            device_config = config
            device_config["device"] = device
            await start_client(device_config)
        await asyncio.sleep(config["data"]["poll_interval"])


if __name__ == "__main__":
    asyncio.run(main())
