#!/usr/bin/env python3

import serial
import time
import logging
import json
import re
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class SIM7080G:
    def __init__(self):
        self.ser = serial.Serial("/dev/ttyUSB2", 9600, rtscts=True, dsrdtr=True)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def send_at_str(self, command, expected_reply="OK", regex_return_filter=".*"):
        logger.info(f"Sending data to serial interface: \"{command}\"")
        self.ser.write((command + "\r\n").encode("utf-8"))
        time.sleep(1)

        # wait until we have data waiting on serial
        while not self.ser.in_waiting:
            logger.info("Waiting for serial data response. Will re-check in 1 second...")
            time.sleep(1)

        logger.info(f"Found {self.ser.in_waiting} bytes waiting on serial input")
        response_data = self.ser.read(self.ser.in_waiting).decode().rstrip('\r')

        logger.debug(f"AT command response data (before regex filter):\n---- BEGIN ----\n{response_data}\n---- END ----")

        # TODO: Instead of checking to see if expected_reply is inside of response_data,
        # accept a regex to validate the response
        if expected_reply in response_data:
            logger.info(f"Response contains the expected reply string of \"{expected_reply}\". Returning data filtered with regex \"{regex_return_filter}\"")

            regex_filtered_response = "".join(re.findall(regex_return_filter, response_data, re.MULTILINE))
            logger.debug(f"AT command response data (after regex filter):\n---- BEGIN ----\n{regex_filtered_response}\n---- END ----")

            # only return data that matches the given regex
            return regex_filtered_response

        return

    def gps_power_on(self):
        logger.info("Powering on GPS modem...")
        if self.send_at_str("AT+CGNSPWR=1"):
            logger.info("GPS power on success")
        else:
            logger.info("GPS power on failed")

    def gps_power_off(self):
        logger.info("Powering off GPS modem...")
        if self.send_at_str("AT+CGNSPWR=0"):
            logger.info("GPS power off success")
        else:
            logger.info("GPS power off failed")

    def get_gps_position(self):
        while True:
            logger.info("Requesting GNSS information...")
            gps_return = self.send_at_str("AT+CGNSINF", expected_reply="+CGNSINF:", regex_return_filter="^\+CGNSINF.*")

            if gps_return and ",,,," not in gps_return:
                logger.info(f"Got a valid GPS location: {gps_return}")
                logger.info("Sending GPS response to parser...")
                self.parse_gps_info(gps_return)
                break
            else:
                logger.info("Invalid or incomplete GPS location received. Retrying in 2 seconds...")
                time.sleep(2)

    def parse_gps_info(self, gps_data):
        """
        The GPS sends us back a bunch of values seperated with ",".
        We got the key names from the docs and the type they're supposed to be.
        This function associates the values with the correct key name and also
        casts the values to the correct type
        """

        # names and types from docs
        gnss_key_names_and_expected_types = {
            "gnss_run_state": int,
            "gps_fix_status": int,
            "utc_date_time": str,
            "latitude": float,
            "longitude": float,
            "msl_altitude": float,
            "speed_over_ground": float,
            "course_over_ground": float,
            "fix_mode": int,
            "reserved1": str,
            "hdop": float,
            "pdop": float,
            "vdop": float,
            "reserved2": str,
            "gps_satellites_in_view": int,
            "reserved3": str,
            "hpa": float,
            "vpa": float
        }

        # strip '\r' from end, then split into list
        values_from_modem = gps_data[0:-1].split(": ")[1].split(',')

        # merge the values from the gps with the key names
        gps_json = dict(zip(gnss_key_names_and_expected_types.keys(), values_from_modem))

        # cast values to correct type
        for gnss_key_name, item_value in gps_json.items():
            if item_value:
                expected_item_type = gnss_key_names_and_expected_types[gnss_key_name]
                logging.debug(f"Trying to cast {gnss_key_name} field's value of \"{item_value}\" to type {expected_item_type}...")
                gps_json[gnss_key_name] = expected_item_type(item_value)

        print(json.dumps(gps_json, indent=3))

    def test_modem(self):
        logging.info("Checking if SIM7080X is ready...")
        while True:
            if self.send_at_str("AT"):
                logger.info("SIM7080X apears to be ready and responsive")
                return
            logger.info("Did not get an \"OK\" back from modem. Testing again...")


def main():
    # logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    modem = SIM7080G()

    modem.test_modem()
    modem.gps_power_on()
    modem.get_gps_position()
    modem.gps_power_off()


if __name__ == "__main__":
    main()
