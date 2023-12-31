#!/usr/bin/env python3

import serial
import time
import logging
import json
import re
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class SIM7080GException(Exception):
    pass


class SIM7080G:
    def __init__(self):
        self.serial_port = serial.Serial("/dev/ttyUSB2",
                                         baudrate=115200,
                                         exclusive=True,
                                         rtscts=True,
                                         dsrdtr=True)
        self.serial_port.reset_input_buffer()
        self.serial_port.reset_output_buffer()

    def _write_serial_data(self, data_str):
        try:
            logger.debug(f"Sending data to serial interface: \"{data_str}\"")
            self.serial_port.write((data_str + "\r\n").encode("utf-8"))
            time.sleep(.5)  # give time for data to be sent
        except serial.SerialTimeoutException:
            raise SIM7080GException("Write timeout occurred while sending data to serial interface.")
        except serial.SerialException as serial_exception:
            raise SIM7080GException(f"Serial exception occurred: {serial_exception}")
        except Exception as general_exception:
            raise SIM7080GException(f"An unexpected error occurred: {general_exception}")

    def _read_serial_data(self):
        logger.debug("Attempting read from serial interface...")

        if not self.serial_port.in_waiting:
            logger.debug("No data waiting on serial port. Returning empty string")
            return ""

        logger.debug(f"Found {self.serial_port.in_waiting} bytes waiting on serial output")
        response_data = self.serial_port.read(self.serial_port.in_waiting).decode()
        self._log_raw_serial_data(message="AT command response data (untouched)",
                                  serial_data=response_data)

        return response_data.replace("\r", "")  # Remove \r characters, keep \n characters

    def _clean_serial_response(self, input_data, line_to_remove):
        return re.sub(f"^{re.escape(line_to_remove)}$", "", input_data, flags=re.MULTILINE)

    def _filter_serial_response_with_regex(self, *, regex, serial_data):
        return "".join(re.findall(regex, serial_data, re.MULTILINE))

    def _log_raw_serial_data(self, *, message, serial_data):
        logger.debug(f"{message}\n---- BEGIN ----\n{serial_data}\n---- END ----")

    def _send_at_command(self, *,
                         command,
                         expected_reply_regex="^OK$",
                         failure_reply_regex="^ERROR.*",
                         regex_return_filter=".*"):

        # How many read and regex attempts should be made against
        # the modem after sending the AT command before giving up
        attempts = 5

        # send AT command to modem
        self._write_serial_data(command)

        for attempt in range(1, attempts + 1):
            logger.debug(f"Parsing response data. Attempt {attempt} of {attempts}...")

            response_data = self._read_serial_data()
            response_data = self._clean_serial_response(response_data, command)

            success_match = re.search(expected_reply_regex, response_data, re.MULTILINE)
            failure_match = re.search(failure_reply_regex, response_data, re.MULTILINE)

            if success_match:
                logger.debug(f"Response matches expected reply regex: \"{expected_reply_regex}\". Returning data filtered with regex: \"{regex_return_filter}\".")

                filtered_response = self._filter_serial_response_with_regex(regex=regex_return_filter, serial_data=response_data)
                self._log_raw_serial_data(message="AT command response data (after regex filter)",
                                          serial_data=filtered_response)

                return filtered_response

            if failure_match:
                logger.debug(f"Response matches failure reply regex: \"{failure_reply_regex}\". Returning data filtered with failure regex.")

                filtered_response = self._filter_serial_response_with_regex(regex=failure_reply_regex, serial_data=response_data)
                self._log_raw_serial_data(message="AT command failure response data (after regex filter)",
                                          serial_data=filtered_response)

                raise SIM7080GException(filtered_response)

            time.sleep(2)

        logger.error(f"Response did not match success or failure regex after {attempts} attempts.")
        raise SIM7080GException("Response data does not match success or failure regex.")

    def gps_power_on(self):
        logger.info("Powering on GPS modem...")
        try:
            self._send_at_command(command="AT+CGNSPWR=1")
            logger.info("GPS power on successful.")
        except SIM7080GException as e:
            logger.info(f"GPS power on failed: {e}")

    def gps_power_off(self):
        logger.info("Powering off GPS modem...")
        try:
            self._send_at_command(command="AT+CGNSPWR=0")
            logger.info("GPS power off success")
        except SIM7080GException as e:
            logger.info(f"GPS power off failed: {e}")

    def get_gps_position(self):
        while True:
            logger.info("Requesting GPS information...")
            try:
                response = self._send_at_command(command="AT+CGNSINF", expected_reply_regex=".*\+CGNSINF:.*", regex_return_filter="^\+CGNSINF.*")
                if ",,,," in response:
                    logger.info("Waiting for GPS lock. Retrying in 10 seconds...")
                else:
                    logger.info("Got a valid GPS location. Parsing...")
                    logger.debug(f"Sending GPS response to parser: {response}")
                    return self._parse_gps_info(response)
            except SIM7080GException as e:
                logger.warning(f"Failed reading from GPS. Retrying in 10 seconds. Error: {e}")

            time.sleep(10)

    def _parse_gps_info(self, gps_data):
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

        gps_json = dict(zip(gnss_key_names_and_expected_types.keys(), values_from_modem))

        for gnss_key_name, item_value in gps_json.items():
            if item_value:
                expected_item_type = gnss_key_names_and_expected_types[gnss_key_name]
                logging.debug(f"Trying to cast {gnss_key_name} field's value of \"{item_value}\" to type {expected_item_type}...")
                gps_json[gnss_key_name] = expected_item_type(item_value)

        return json.dumps(gps_json)

    def _is_network_up(self):
        logger.debug("Checking to see if network is up...")

        success_regex = r'^\+CNACT: 0,1,"(?!0\.0\.0\.0")\d+\.\d+\.\d+\.\d+"$'
        fail_regex = r'^\+CNACT: 0,0,"0\.0\.0\.0"$'
        try:
            self._send_at_command(command='AT+CNACT?',
                                  expected_reply_regex=success_regex,
                                  failure_reply_regex=fail_regex)
            return True
        except SIM7080GException:
            return False

    def activate_network(self):
        logger.info("Activating network...")
        if self._is_network_up():
            logger.info("Network is up")
            return True
        else:
            try:
                self._send_at_command(command='AT+CNACT=0,1', expected_reply_regex=r'^OK$')
                logger.info("Network activation successful.")
                return True
            except SIM7080GException as e:
                logger.error(f"Failed to activate network. Error: {e}")
                return False

    def deactivate_network(self):
        logger.info("Deactivating network...")
        if not self._is_network_up():
            logger.info("Network is down")
        else:
            try:
                self._send_at_command(command='AT+CNACT=0,0', expected_reply_regex=r'^OK$')
                logger.info("Network deactivation successful.")
            except SIM7080GException as e:
                logger.error(f"Failed to deactivate network. Error: {e}")

    def post_json_payload(self, url, json_string):

        logger.info("Preparing modem for JSON POST over HTTPS...")
        ok_regex = '^OK$'
        json_length = len(json_string)
        commands = (
            ('AT+SHDISC', '.*', 'Cleaning up any old (failed) connections. ERRORs ignored'),
            ('AT+CSSLCFG="sslversion",1,3', ok_regex, 'Setting TLS version'),
            ('AT+CSSLCFG="ignorertctime",1,1', ok_regex, 'Disabling TLS cert expiration checking'),
            ('AT+CSSLCFG="sni",1,"paglusch.com"', ok_regex, 'Enabling SNI'),
            ('AT+SHSSL=1,""', ok_regex, 'Relaxing TLS verification'),
            (f'AT+SHCONF="URL","{url}"', ok_regex, f'Setting URL to {url}'),
            ('AT+SHCONF="BODYLEN",1024', ok_regex, 'Setting max body size to 1024'),
            ('AT+SHCONF="HEADERLEN",350', ok_regex, 'Setting max header size to 350'),
            ('AT+SHCONN', ok_regex, 'Creating HTTPS connection'),
            ('AT+SHSTATE?', '^\+SHSTATE: 1$', 'Verifying connection is alive'),
            ('AT+SHCHEAD', ok_regex, 'Clearing existing headers'),
            ('AT+SHAHEAD="Content-Type","application/json"', ok_regex, 'Adding Content-Type header'),
            (f'AT+SHBOD={json_length},10000', "^>", 'Preparing modem for JSON payload input')
        )
        for command, expected_reply_regex, status_msg in commands:
            logger.debug(f"(POST) {status_msg}...")
            try:
                self._send_at_command(command=command,
                                      expected_reply_regex=expected_reply_regex)
            except SIM7080GException as e:
                logger.error(f"Failed during JSON POST on command \"{command}\" ({status_msg}). Error: {e}")
                return

        # POST the data
        try:
            logger.debug("(POST) Sending JSON payload to modem...")
            self._send_at_command(command=json_string + '\n', regex_return_filter='^\+SHREQ.+')

            logger.debug("(POST) POSTing data...")
            post_result = self._send_at_command(command='AT+SHREQ="/post-echo.php",3',
                                                expected_reply_regex='^\+SHREQ: \"POST\",\d{3},\d{1,4}$',
                                                regex_return_filter='^\+SHREQ: \"POST\",\d{3},\d{1,4}$')
            post_resp_size = post_result.split(',')[-1]

            # read http response
            # TODO actually verify the HTTP reply once this POST is going somewhere useful
            logger.debug("(POST) Reading HTTP reply...")
            http_reply = self._send_at_command(command=f'AT+SHREAD=0,{post_resp_size}')

            # cleanup
            logger.debug("(POST) Closing connection...")
            self._send_at_command(command='AT+SHDISC')

            logger.info("POST succeeded!")
        except SIM7080GException as e:
            logger.error(f"Failed POSTing data to modem. Error: {e}")
            return


def main():
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        # level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    sim7080g = SIM7080G()
    try:
        sim7080g.gps_power_on()
        gps_json = sim7080g.get_gps_position()
        sim7080g.gps_power_off()

        if sim7080g.activate_network():
            # URL must NOT end in a '/'
            sim7080g.post_json_payload('https://paglusch.com', gps_json)
            sim7080g.deactivate_network()
    finally:
        sim7080g.serial_port.close()


if __name__ == "__main__":
    main()
