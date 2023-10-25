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
        self.ser = serial.Serial("/dev/ttyUSB2",
                                 baudrate=115200,
                                 exclusive=True,
                                 rtscts=True,
                                 dsrdtr=True)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def _send_at_str(self,
                     command,
                     expected_reply_regex="^OK$",
                     failure_reply_regex="^ERROR.*",
                     regex_return_filter=".*"):

        # retry reading response to AT command this many times for each send attempt
        read_retry_limit = 3

        logger.debug(f"Sending data to serial interface: \"{command}\"")
        self.ser.write((command + "\r\n").encode("utf-8"))
        time.sleep(3)

        for read_attempt in range(read_retry_limit):
            logger.debug(f"Starting read attempt {read_attempt +1} of {read_retry_limit}...")

            # is there data waiting?
            if not self.ser.in_waiting:
                logger.warning("No response data waiting. Will try reading again in 3 seconds...")
                time.sleep(3)
                continue

            logger.debug(f"Found {self.ser.in_waiting} bytes waiting on serial output")

            # read response as-is
            response_data = self.ser.read(self.ser.in_waiting).decode()

            logger.debug(f"AT command response data (untouched):\n---- BEGIN ----\n{response_data}\n---- END ----")
            
            # remove \r chars from reply, keeping only \n
            response_data = response_data.replace("\r", "")
            
            # remove our command from the response if its there
            response_data = re.sub(f"^{re.escape(command)}$", "", response_data, flags=re.MULTILINE)

            logger.debug(f"AT command response data (after inital cleanup):\n---- BEGIN ----\n{response_data}\n---- END ----")

            # check to see if reply matches success regex
            if re.search(expected_reply_regex, response_data, re.MULTILINE):
                logger.debug(f"Response matches expected reply regex of \"{expected_reply_regex}\". Returning data filtered with regex \"{regex_return_filter}\"")

                regex_filtered_response = "".join(re.findall(regex_return_filter, response_data, re.MULTILINE))
                logger.debug(f"AT command response data (after regex filter):\n---- BEGIN ----\n{regex_filtered_response}\n---- END ----")

                # only return data that matches the given regex
                return True, regex_filtered_response

            # check to see if reply matches failure regex
            if re.search(failure_reply_regex, response_data, re.MULTILINE):
                logger.error(f"Response matches failure reply regex of \"{failure_reply_regex}\". Returning data filtered with fail regex.")

                regex_filtered_response = "".join(re.findall(failure_reply_regex, response_data, re.MULTILINE))
                logger.debug(f"AT command failure response data (after regex filter):\n---- BEGIN ----\n{regex_filtered_response}\n---- END ----")

                # only return data that matches the failure regex
                return False, regex_filtered_response

            # we got data, but it didnt match the success or fail regex
            # sleep a try again
            logger.warning("Response data does not match success or failure regex. Will try reading again in 3 seconds...")
            time.sleep(3)

        return False, f"Failed to get a response that matches success or fail regex after {read_retry_limit} read attempts."

    def gps_power_on(self):
        logger.info("Powering on GPS modem...")
        success, msg = self._send_at_str("AT+CGNSPWR=1")
        if success:
            logger.info("GPS power on success")
        else:
            logger.info(f"GPS power on failed: {msg}")

    def gps_power_off(self):
        logger.info("Powering off GPS modem...")
        success, msg = self._send_at_str("AT+CGNSPWR=1")
        if success:
            logger.info("GPS power off success")
        else:
            logger.info(f"GPS power off failed: {msg}")

    def get_gps_position(self):
        while True:
            logger.info("Requesting GPS information...")
            success, msg = self._send_at_str("AT+CGNSINF", expected_reply_regex=".*\+CGNSINF:.*", regex_return_filter="^\+CGNSINF.*")

            if success:
                if ",,,," in msg:
                    logger.info("Waiting for GPS lock. Retrying in 10 seconds...")
                else:
                    logger.info(f"Got a valid GPS location. Parsing...")
                    logger.debug(f"Sending GPS response to parser: {msg}")
                    self._parse_gps_info(msg)
                    break
            else:
                logger.warning(f"Failed reading from GPS. Retrying in 10 seconds. Error: {msg}")

            time.sleep(10)

    def _parse_gps_info(self, gps_data):
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

        values_from_modem = gps_data.split(": ")[1].split(',')

        # merge the values from the gps with the key names
        gps_json = dict(zip(gnss_key_names_and_expected_types.keys(), values_from_modem))

        # cast values to correct type
        for gnss_key_name, item_value in gps_json.items():
            if item_value:
                expected_item_type = gnss_key_names_and_expected_types[gnss_key_name]
                logging.debug(f"Trying to cast {gnss_key_name} field's value of \"{item_value}\" to type {expected_item_type}...")
                gps_json[gnss_key_name] = expected_item_type(item_value)

        print(json.dumps(gps_json, indent=3))
        print(f"https://www.google.com/maps/search/?api=1&query={gps_json['latitude']},{gps_json['longitude']}")

    def post_json_payload(self, url, json_string):
        # Setup the HTTPS parameters
        self._send_at_str('AT+SHCONF="bodytx",1')
        self._send_at_str('AT+SHCONF="contype","application/json"')

        # Start HTTPS session
        self._send_at_str('AT+SHCONN')

        # Send the POST request
        self._send_at_str(f'AT+SHREQ="{url}",4,{len(json_string)}')
        self._send_at_str(json_string, expected_reply_regex="^>", regex_return_filter=".*")

        # End HTTPS session
        self._send_at_str('AT+SHDISC')

    def test_modem(self):
        logging.info("Checking if SIM7080X is ready...")
        while True:
            if self._send_at_str("AT"):
                logger.info("SIM7080X apears to be ready and responsive")
                return
            logger.info("Did not get an \"OK\" back from modem. Testing again...")


def main():
    logging.basicConfig(
        stream=sys.stderr,
        # level=logging.INFO,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    modem = SIM7080G()

    modem.test_modem()
    modem.gps_power_on()
    modem.get_gps_position()
    modem.gps_power_off()

    # modem.post_json_payload('https://paglusch.com', '{"key": "value"}')


if __name__ == "__main__":
    main()
