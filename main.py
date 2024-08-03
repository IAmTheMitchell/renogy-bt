import aiomqtt
import asyncio
import atexit
import json
import logging
import signal
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

# Event to signal shutdown
shutdown_event = asyncio.Event()


def shutdown():
    logger.warning("Exit signal received. Shutting down.")
    shutdown_event.set()


async def poll_devices(config):
    # try:
    while not shutdown_event.is_set():
        tasks = [
            start_client({**config, "device": device})
            for device in config["devices"]
        ]
        await asyncio.gather(*tasks)
        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=config["data"]["poll_interval"]
            )
        except TimeoutError:
            pass
    # except Exception as e:
    #     logging.error(f"Error in main loop: {e}")


# The callback function when data is received
async def on_data_received(client, data):
    filtered_data = Utils.filter_fields(data, config["data"]["fields"])
    logging.info(f"{client.bleManager.device.name} => {filtered_data}")
    if config["remote_logging"]["enabled"]:
        await data_logger.log_remote(json_data=filtered_data)
    if config["mqtt"]["enabled"]:
        await data_logger.log_mqtt(json_data=filtered_data)
    if config["pvoutput"]["enabled"] and config["device"]["type"] == "RNG_CTRL":
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
    if config["mqtt"]["enabled"]:
        async with aiomqtt.Client(
            config["mqtt"]["server"],
            port=config["mqtt"]["port"],
            username=config["mqtt"]["user"],
            password=config["mqtt"]["password"],
            identifier="renogy-bt",
        ) as mqtt_client:
            data_logger.set_mqtt_client(mqtt_client)
            await poll_devices(config)
    else:
        await poll_devices(config)


if __name__ == "__main__":
    # Register the shutdown function
    atexit.register(shutdown)

    # Handle termination signals
    signal.signal(signal.SIGINT, lambda sig, frame: shutdown())
    signal.signal(signal.SIGTERM, lambda sig, frame: shutdown())

    asyncio.run(main())
