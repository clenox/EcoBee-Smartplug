# EcoBee---TPLink-SmartPlug-Control
Control TPLink smart plugs with EcoBee sensor data

heatrun.py is used to control multiple electric space heaters on TPLink smartplugs based on temperature data from EcoBee remote sensors.

The program will autodetect smart plugs with matching names - check code and update as needed to match your naming convention (please do not merge such changes into master).  This only works if run locally (inside LAN).

Supports text message push for issues / events -- must have Twilio account.

Integrates with Ohmconnect to respond to Ohmconnect events -- must have Ohmconnect account.

auth.py needs to be updated with keys -- ecobee developer api key, twilio keys & phone numbers, and ohmconnect URL
