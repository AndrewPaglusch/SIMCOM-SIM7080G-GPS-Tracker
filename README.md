# GPS Tracker Python Script for SIMCOM SIM7080G Modem

## Introduction

This project is an open-source Python script intended to serve as a straightforward example of interfacing with both GPS and LTE CAT-M components on the SIMCOM SIM7080G modem. The script is designed to perform a simple sequence of operations to obtain GPS coordinates and transmit them via an HTTPS POST.

## Script Workflow

When the script is executed, it goes through the following steps:

1. Turns on the GPS modem.
2. Waits for a stable GPS lock and gathers the coordinates.
3. Powers down the GPS modem to conserve energy.
4. Parses the GPS data into a JSON format with appropriately assigned keys.
5. Activates the cellular connection.
6. Prepares the modem for an HTTPS POST request.
7. Sends the GPS data JSON object to a specified web server.
8. Shuts down the cellular connection to conserve the modem's battery life.

## Current Assumptions

The script operates under a few current assumptions, which may require manual setup:

- The Access Point Name (APN) needs to be preset. There are plans to add functionality to check and set the APN if it's missing. Relevant AT command: `AT+CGDCONT=1,"IP","hologram"`.
- For simplicity, TLS certificate validation and expiration checks (notBefore/notAfter) are not performed in this proof-of-concept phase.

## Usage and Limitations

This script is provided as-is, with no guarantees. It's a basic implementation meant to illustrate the interaction with the SIMCOM SIM7080G modem for GPS tracking purposes. It's not recommended for production use without further development, particularly enhancements in error handling, security features, and robustness.

## Future Work

- Implement automatic APN configuration if not set.
- Enable TLS certificate validation and enforce expiration checks for improved security.

## Contributing

Contributions to this project are welcome. To contribute, please fork the repository, make your changes, and submit a pull request for review.

## License

This script is made available under the MIT License. See the LICENSE file in the repository for the full license text.

## Support the Project

If you find this script useful and feel inclined to support my work, any contributions are welcome but certainly not mandatory. Here are the ways you can offer support:

- PayPal: [https://paypal.me/AndrewPaglusch](https://paypal.me/AndrewPaglusch)
- Bitcoin: `1EYDa33S14ejuQGMhSjtBUmBHTBB8mbTRs`

Your generosity helps fuel further development and is greatly valued!
