import asyncio
import logging
from .BLEManager import BLEManager
from .Utils import bytes_to_int, crc16_modbus, int_to_bytes

# Base class that works with all Renogy family devices
# Should be extended by each client with its own parsers and section definitions
# Section example: {'register': 5000, 'words': 8, 'parser': self.parser_func}

ALIAS_PREFIX = "BT-TH"
NOTIFY_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000ffd1-0000-1000-8000-00805f9b34fb"
READ_TIMEOUT = 15  # (seconds)


class BaseClient:
    def __init__(self, config):
        self.config = config
        self.bleManager = None
        self.device = None
        self.poll_timer = None
        self.read_timeout = None
        self.data = {}
        self.device_id = self.config["device"]["device_id"]
        self.sections = []
        self.section_index = 0
        self.loop = asyncio.get_event_loop()
        logging.info(
            f"Init {self.__class__.__name__}: {self.config['device']['alias']} => {self.config['device']['mac_addr']}"
        )

    async def start(self):
        try:
            await self.connect()
        except Exception as e:
            self.__on_error(e)
        except KeyboardInterrupt:
            self.__on_error("KeyboardInterrupt")

    async def connect(self):
        self.bleManager = BLEManager(
            bleak_device=self.config["device"]["bleak_device"],
            mac_address=self.config["device"]["mac_addr"],
            alias=self.config["device"]["alias"],
            on_data=self.on_data_received,
            on_connect_fail=self.__on_connect_fail,
            notify_uuid=NOTIFY_CHAR_UUID,
            write_uuid=WRITE_CHAR_UUID,
        )

        await self.bleManager.connect(lock=self.config["lock"])
        if not self.bleManager.device:
            logging.error(
                f"Device not found: {self.config['device']['alias']} => {self.config['device']['mac_addr']}, please check the details provided."
            )
            for dev in self.bleManager.discovered_devices:
                if dev.name and dev.name.startswith(ALIAS_PREFIX):
                    logging.info(
                        f"Possible device found! ====> {dev.name} > [{dev.address}]"
                    )
            await self.stop()
        else:
            if self.bleManager.client and self.bleManager.client.is_connected:
                await self.read_section()

    async def disconnect(self):
        await self.bleManager.disconnect()

    async def on_data_received(self, response):
        if self.read_timeout and not self.read_timeout.cancelled():
            self.read_timeout.cancel()
        operation = bytes_to_int(response, 1, 1)

        if operation == 3:  # read operation
            logging.debug(f"on_data_received: response for read operation")
            if (
                self.section_index < len(self.sections)
                and self.sections[self.section_index]["parser"]
                and self.sections[self.section_index]["words"] * 2 + 5 == len(response)
            ):
                # parse and update data
                self.sections[self.section_index]["parser"](response)

            if (
                self.section_index >= len(self.sections) - 1
            ):  # last section, read complete
                self.section_index = 0
                self.on_read_operation_complete()
                self.data = {}
                await self.check_polling()
            else:
                self.section_index += 1
                await asyncio.sleep(0.5)
                await self.read_section()
        else:
            logging.warn("on_data_received: unknown operation={}".format(operation))

    def on_read_operation_complete(self):
        logging.debug("on_read_operation_complete")
        self.data["__device"] = self.config["device"]["alias"]
        self.data["__client"] = self.__class__.__name__
        if self.on_data_callback:
            asyncio.create_task(self.on_data_callback(self, self.data))

    def on_read_timeout(self):
        logging.error("on_read_timeout => Timed out! Please check your device_id!")
        asyncio.create_task(self.stop())

    async def check_polling(self):
        if bool(self.config["data"]["enable_polling"]):
            await asyncio.sleep(self.config["data"]["poll_interval"])
            await self.read_section()

    async def read_section(self):
        index = self.section_index
        if self.device_id is None or not self.sections:
            return logging.error("BaseClient cannot be used directly")

        self.read_timeout = self.loop.call_later(READ_TIMEOUT, self.on_read_timeout)
        request = self.create_generic_read_request(
            self.device_id,
            3,
            self.sections[index]["register"],
            self.sections[index]["words"],
        )
        await self.bleManager.characteristic_write_value(request)

    def create_generic_read_request(self, device_id, function, regAddr, readWrd):
        data = None
        if regAddr is not None and readWrd is not None:
            data = []
            data.append(device_id)
            data.append(function)
            data.append(int_to_bytes(regAddr, 0))
            data.append(int_to_bytes(regAddr, 1))
            data.append(int_to_bytes(readWrd, 0))
            data.append(int_to_bytes(readWrd, 1))

            crc = crc16_modbus(bytes(data))
            data.append(crc[0])
            data.append(crc[1])
            logging.debug("{} {} => {}".format("create_request_payload", regAddr, data))
        return data

    def __on_error(self, error=None):
        logging.error(f"Exception occurred: {error}")
        asyncio.create_task(self.stop())

    def __on_connect_fail(self, error):
        logging.error(f"Connection failed: {error}")
        asyncio.create_task(self.stop())

    async def stop(self):
        if self.read_timeout and not self.read_timeout.cancelled():
            self.read_timeout.cancel()
        await self.disconnect()
