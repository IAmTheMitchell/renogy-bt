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
# TODO: Convert to run with multiple devices
async def start_client():
    logger.info(f"Device type: {config['device']['type']}")
    if config["device"]["type"] == "RNG_CTRL":
        await RoverClient(config, on_data_received).start()
    elif config["device"]["type"] == "RNG_CTRL_HIST":
        await RoverHistoryClient(config, on_data_received).start()
    elif config["device"]["type"] == "RNG_BATT":
        await BatteryClient(config, on_data_received).start()
    elif config["device"]["type"] == "RNG_INVT":
        await InverterClient(config, on_data_received).start()
    else:
        logging.error("unknown device type")


async def main():
    while True:
        await start_client()
        await asyncio.sleep(config["data"]["poll_interval"])


if __name__ == "__main__":
    asyncio.run(main())
