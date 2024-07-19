import logging
import json
import configparser
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

# Set up logger 
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Load config
json_config: Dict[str, any] = load_user_config()

# Test logging
logger.info(f"Starting renogybtaddon.py - {datetime.now()}")

# Set logger level 
data_logger: DataLogger = DataLogger(json_config)

# Hard code certain values to config
json_config["data"]["enable_polling"] = False

# Convert json config object (cyrils/renogy-bt built to use configparser)
configparser_config = configparser.ConfigParser()
for section, options in json_config.items():
    configparser_config.add_section(section)
    for key, value in options.items():
        configparser_config.set(section, key, str(value))

# The callback function when data is received
def on_data_received(client, data):
    filtered_data = Utils.filter_fields(data, configparser_config['data']['fields'])
    logging.info(f"{client.bleManager.device.name} => {filtered_data}")
    if configparser_config['remote_logging'].getboolean('enabled'):
        data_logger.log_remote(json_data=filtered_data)
    if configparser_config['mqtt'].getboolean('enabled'):
        data_logger.log_mqtt(json_data=filtered_data)
    if configparser_config['pvoutput'].getboolean('enabled') and configparser_config['device']['type'] == 'RNG_CTRL':
        data_logger.log_pvoutput(json_data=filtered_data)
    if not configparser_config['data'].getboolean('enable_polling'):
        client.stop()

# Start client
# TODO: Convert to run with multiple devices
# logger.info(f"Device type: {configparser_config["device"]["type"]}")
if configparser_config['device']['type'] == 'RNG_CTRL':
    RoverClient(configparser_config, on_data_received).start()
elif configparser_config['device']['type'] == 'RNG_CTRL_HIST':
    RoverHistoryClient(configparser_config, on_data_received).start()
elif configparser_config['device']['type'] == 'RNG_BATT':
    BatteryClient(configparser_config, on_data_received).start()
elif configparser_config['device']['type'] == 'RNG_INVT':
    InverterClient(configparser_config, on_data_received).start()
else:
    logging.error("unknown device type")
