import logging
import json
import configparser
import asyncio
from datetime import datetime
from os import access, R_OK
from os.path import isfile
from typing import Dict
from renogybt import InverterClient, RoverClient, RoverHistoryClient, BatteryClient, DataLogger, Utils


def is_readable(file):
    return isfile(file) and access(file, R_OK)

def load_user_config():
    try:
        with open('/data/options.json') as f:
            conf = dotdict(json.load(f))
        return conf
    except Exception as e:
        print('error reading /data/options.json, trying options.json', e)
        with open('options.json') as f:
            conf = dotdict(json.load(f))
        return conf

class dotdict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError as e:
            raise AttributeError(e)

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

# Load config
json_config: Dict[str, any] = load_user_config()

# Set up logger
log_level = logging.getLevelName(json_config["data"]["log_level"])
logging.basicConfig(level=log_level)
logger = logging.getLogger()
logger.info(f"Starting renogybtaddon.py - {datetime.now()}")

# Convert json config object (cyrils/renogy-bt built to use configparser)
configparser_config = configparser.ConfigParser()
for section, options in json_config.items():
    configparser_config.add_section(section)
    for key, value in options.items():
        configparser_config.set(section, key, str(value))

# Set up remote logging
data_logger: DataLogger = DataLogger(configparser_config)

# The callback function when data is received
async def on_data_received(client, data):
    filtered_data = Utils.filter_fields(data, configparser_config['data']['fields'])
    logging.info(f"{client.bleManager.device.name} => {filtered_data}")
    if configparser_config['remote_logging'].getboolean('enabled'):
        await data_logger.log_remote(json_data=filtered_data)
    if configparser_config['mqtt'].getboolean('enabled'):
        await data_logger.log_mqtt(json_data=filtered_data)
    if configparser_config['pvoutput'].getboolean('enabled') and configparser_config['device']['type'] == 'RNG_CTRL':
        await data_logger.log_pvoutput(json_data=filtered_data)
    await client.stop()

# Start client
# TODO: Convert to run with multiple devices
async def start_client():
    logger.info(f"Device type: {configparser_config['device']['type']}")
    if configparser_config['device']['type'] == 'RNG_CTRL':
        await RoverClient(configparser_config, on_data_received).start()
    elif configparser_config['device']['type'] == 'RNG_CTRL_HIST':
        await RoverHistoryClient(configparser_config, on_data_received).start()
    elif configparser_config['device']['type'] == 'RNG_BATT':
        await BatteryClient(configparser_config, on_data_received).start()
    elif configparser_config['device']['type'] == 'RNG_INVT':
        await InverterClient(configparser_config, on_data_received).start()
    else:
        logging.error("unknown device type")

async def main():
    while True:
        await start_client()
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
