import asyncio
import logging
import contextlib
import time
from bleak import BleakClient, BleakScanner, BLEDevice

DISCOVERY_TIMEOUT = 5  # max wait time to complete the bluetooth scanning (seconds)


async def discover(config):
    lock = config["lock"]
    async with lock:
        logging.info("Starting discovery...")
        discovered_devices = await BleakScanner.discover(timeout=5)
        logging.info(f"Devices found: {len(discovered_devices)}")

    for dev in discovered_devices:
        for config_device in config["devices"]:
            if dev.address != None and (
                dev.address.upper() == config_device["mac_addr"]
                or (dev.name and dev.name.strip() == config_device["alias"])
            ):
                logging.info(f"Found matching device {dev.name} => {dev.address}")
                config_device["bleak_device"] = dev


class BLEManager:
    def __init__(
        self,
        bleak_device,
        mac_address,
        alias,
        on_data,
        on_connect_fail,
        notify_uuid,
        write_uuid,
    ):
        self.mac_address = mac_address
        self.device_alias = alias
        self.data_callback = on_data
        self.connect_fail_callback = on_connect_fail
        self.notify_char_uuid = notify_uuid
        self.write_char_uuid = write_uuid
        self.device: BLEDevice = bleak_device
        self.client: BleakClient = None
        self.discovered_devices = []

    async def connect(self, lock):
        try:
            # Trying to establish a connection to two devices at the same time
            # can cause errors, so use a lock to avoid this.
            async with lock:
                if self.device is None:
                    logging.error(f"{self.device_alias} not found")
                    return
                self.client = BleakClient(self.device)
                logging.info(f"Connecting to {self.device_alias}")
                await self.client.connect()
                logging.info(f"Connected to {self.device_alias}")

            for service in self.client.services:
                for characteristic in service.characteristics:
                    if characteristic.uuid == self.notify_char_uuid:
                        await self.client.start_notify(
                            characteristic, self.notification_callback
                        )
                        logging.debug(
                            f"Subscribed to notification {characteristic.uuid}"
                        )
                    if characteristic.uuid == self.write_char_uuid:
                        logging.debug(
                            f"Found write characteristic {characteristic.uuid}"
                        )

        except Exception as e:
            logging.error(f"Error connecting: {e}", exc_info=True)
            self.connect_fail_callback(e)

    async def notification_callback(self, characteristic, data: bytearray):
        logging.debug("notification_callback")
        await self.data_callback(data)

    async def characteristic_write_value(self, data):
        try:
            logging.debug(f"Writing to {self.write_char_uuid} {data}")
            await self.client.write_gatt_char(self.write_char_uuid, bytearray(data))
            logging.debug("Characteristic_write_value succeeded")
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.warning(f"Characteristic_write_value failed {e}")

    async def disconnect(self):
        if self.client and self.client.is_connected:
            logging.info(
                f"Exit: Disconnecting device: {self.device.name} {self.device.address}"
            )
            await self.client.disconnect()
