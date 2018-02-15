# Main Program

# Set up libraries

import sys
import requests
import json
from time import sleep
import datetime
from pyHS100 import SmartPlug

# Initialize error handling

to_err = False

# Read developer key from file apikey.txt, set scope

a = open("apikey.txt", "r")
APP_KEY = a.read()
SCOPE = 'smartWrite'

# Read tokens from file tokens.txt --- tokens are kept updated by token_mngr.py

f = open("tokens.txt", "r")

token_str = str(f.read())

f.close()

token_list = token_str.split(",")

try:

    access_token = token_list[0]
    token_type = token_list[1]
    refresh_token = token_list[2]

except IndexError:

# To do -- add token_mngr relaunch here to automate recovery from this error

    sys.exit('Token File Read Error')

auth = (token_type) + ' ' + (access_token)

# time handling for error message

timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
dectime = float(timestamp[11:13]) + float(timestamp[14:16]) / 60

# Initial ecobee API call to populate room class

try:

    thermostat_url = 'https://api.ecobee.com/1/thermostat?'
    payload = {'json': '{"selection":{"selectionType":"registered","includeSensors":"true"}}'}
    header = {'Content-Type': 'application/json;charset=UTF-8', 'Authorization': auth}

    response = requests.get(thermostat_url, headers=header, params=payload)

    to_err = False

except TimeoutError:

    err_string = (str(timestamp) + ' Timeout error in ecobee data call') + "\r"

    print(err_string)

    log = open('log.txt', 'a+')
    log.write(err_string)
    log.close()

    to_err = True

data = response.json()

# Populate lists used to build dicts

namelist = []
templist = []
temps= []

i = 0
while i < len(data['thermostatList'][0]['remoteSensors']):
    namelist.append(data['thermostatList'][0]['remoteSensors'][i]['name'])
    templist.append(data['thermostatList'][0]['remoteSensors'][i]['capability'][0]['value'])
    i = i + 1

for item in templist:

    try:

        tval = float(item) / 10
    
    except ValueError:
    
        tval = 'badvalue'

    temps.append(tval)

# Remove the Home sensor which is not used.  This implementation has 3 named sensors MBED, OBED and LBED

namelist.remove('Home')

tempdict = dict(zip(namelist, temps))

print(tempdict)

#  To do - replace hard coded IP addresses with file read.  Use the pyhs100 utility to find your plug ip addresses.  Replaced here with dummies.

plugip_dict = {'MBED':'XXX.XXX.X.XX','OBED':'XXX.XXX.X.XX','LBED':'XXX.XXX.X.XX'}

# Assign smart plug objects

mbed_plug = SmartPlug(plugip_dict['MBED'])
obed_plug = SmartPlug(plugip_dict['OBED'])
lbed_plug = SmartPlug(plugip_dict['LBED'])

plugdict = {'MBED':mbed_plug,'LBED':lbed_plug,'OBED':obed_plug}

# Define Room class

class Room:
    def __init__(self, name, temp, status, temp_high, temp_low, on_from, on_to):
        self.name = name
        self.temp = temp
        self.status = status
        self.temp_high = temp_high
        self.temp_low = temp_low
        self.on_from = on_from
        self.on_to = on_to


# Set schedule and temperature band
# Temp setpoints in F
# Time setpoints in decimal hours, 24 hour time
# Note:  All time logic here assumes start after noon and end before noon!

mbed = Room('MBED', tempdict['MBED'], 'OFF', 66.8, 66.6, 20.25, 8.0)
lbed = Room('LBED', tempdict['LBED'], 'OFF', 67.0, 66.8, 19.75, 8.0)
obed = Room('OBED', tempdict['OBED'], 'OFF', 67.0, 66.8, 19.75, 8.0)

rooms = [mbed,lbed,obed]

roomdict = {'MBED':mbed,'LBED':lbed,'OBED':obed}

# Initialize schedule bounds -- the earliest start and latest end of schedule for all rooms
#  Used to determine when in active vs. sleep mode overall

start_time = mbed.on_from
end_time = mbed.on_to

for name in namelist:

    if roomdict[name].on_from < start_time:

        start_time = roomdict[name].on_from

    if roomdict[name].on_to > end_time:

        end_time = roomdict[name].on_to


# Define loop time increment ... timeout between hitting APIs, 180 sec minimum per EcoBee

looptime = 180

# Start main loop

while True:

    # Set sleep indicator for one-time print of mode

    sleepind = 0

    # time handling

    timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
    dectime = float(timestamp[11:13]) + float(timestamp[14:16]) / 60

    while dectime >= start_time or dectime <= end_time:

        timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        dectime = float(timestamp[11:13]) + float(timestamp[14:16]) / 60

        sched = True

    # Get updated tokens
    
        f = open("tokens.txt", "r")

        token_str = str(f.read())

        f.close()

        token_list = token_str.split(",")

        try:

            access_token = token_list[0]
            token_type = token_list[1]
            refresh_token = token_list[2]

        except IndexError:

    # To do -- add token_mngr relaunch here to automate recovery from this error

            sys.exit('Token File Read Error')

        auth = (token_type) + ' ' + (access_token)

        # 4)  Call EcoBee API to get data

        try:

            thermostat_url = 'https://api.ecobee.com/1/thermostat?'
            payload = {'json': '{"selection":{"selectionType":"registered","includeSensors":"true"}}'}
            header = {'Content-Type': 'application/json;charset=UTF-8', 'Authorization': auth}

            response = requests.get(thermostat_url, headers=header, params=payload)

            to_err = False

        except:

            err_string = (str(timestamp) + 'Error in ecobee data call') + "\r"

            print(err_string)

            log = open('log.txt', 'a+')
            log.write(err_string)
            log.close()

            sleep(30)

            to_err = True

            continue

        data = response.json()

        templist = []
        temps = []

        i = 0
        while i < len(data['thermostatList'][0]['remoteSensors']):
            templist.append(data['thermostatList'][0]['remoteSensors'][i]['capability'][0]['value'])
            i = i + 1

        for item in templist:

            try:

                tval = float(item) / 10
    
            except ValueError:
    
                tval = 'badvalue'

            temps.append(tval)

        tempdict = dict(zip(namelist, temps))

        # Assign updated temps to rooms

        for name in namelist:

            roomdict[name].temp = tempdict[name]

            # Decision logic and set booleans for switches
            # Plug status is updated separately from state to reduce calls to plug endpoints and allow rotation of heater operation per below

            if roomdict[name].temp == 'badvalue':

                print('Warning:  bad temp reading in ', name)

                roomdict[name].status = roomdict[name].status

            elif roomdict[name].temp <= roomdict[name].temp_low and (dectime >= roomdict[name].on_from or dectime <= roomdict[name].on_to):

                roomdict[name].status = "ON"

            elif roomdict[name].temp > roomdict[name].temp_high or (dectime < roomdict[name].on_from and dectime > roomdict[name].on_to):

                roomdict[name].status = "OFF"

            else:

                roomdict[name].status = roomdict[name].status

        # Write log

        log_str = (str(timestamp) + ", MBED, " + str(roomdict['MBED'].temp) + ", " + str(roomdict['MBED'].status) +
            ", OBED, " + str(roomdict['OBED'].temp) + ", " + str(roomdict['OBED'].status) +
            ", LBED, " + str(roomdict['LBED'].temp) + ", " + str(roomdict['LBED'].status) +
            "\n")

        log = open("log.txt", "a+")
        log.write(log_str)
        log.close()

        print('Latest Timestamp: ', log_str + "\r")

        # For LBED and OBED determine which will operate when both are in ON state.
        # In this implementation these heaters are on a single breaker.
        # This breaker trips if both are running simultaneously.

        if obed.temp < lbed.temp:

            lbed_turn = False

        else:

            lbed_turn = True

        # Handle loss of communication with plugs

        try:

            mbed_plug.state = mbed.status
            mbed_plug_err = False

        except:

            print('mbed plug error')
            mbed_plug_err = True

        try:

            obed_plug_chk = obed_plug.state
            obed_plug_err = False

        except:

            print('obed plug error')
            obed_plug_err = True

        try:

            lbed_plug_chk = lbed_plug.state
            lbed_plug_err = False

        except:

            print('lbed plug error')
            lbed_plug_err = True

        # Determine plug states - this logic actually turns the plugs on or off.

        if obed_plug_err is False and lbed_plug_err is False:

            if obed.status == 'ON' and lbed.status == 'ON' and lbed_turn is True:

                obed_plug.state = 'OFF'
                sleep(5)
                lbed_plug.state = 'ON'
                lbed_turn = False
                print('Alternating obed OFF lbed ON')

            elif obed.status == 'ON' and lbed.status == 'ON' and lbed_turn is False:

                lbed_plug.state = 'OFF'
                sleep(5)
                obed_plug.state = 'ON'
                lbed_turn = True
                print('Alternating obed ON lbed OFF')

            else:

                obed_plug.state = obed.status
                lbed_plug.state = lbed.status
                print('Operating per status')

        elif obed_plug_err is True and lbed_plug_err is False:

            lbed_plug.state = lbed.status
            print('lbed per status, obed offline')

        elif lbed_plug_err is True and obed_plug_err is False:

            obed_plug.state = obed.status
            print('obed per status, lbed offline')

        else:

            print('obed and lbed offline')

        sleep(looptime)

# If outside of the schedule enter sleep mode.  No logging in sleep mode.

    if sleepind == 0:

        print('Sleep Mode')

        sleepind = 1

    else:

        for name in namelist:

            if(roomdict[name].status) == 'ON':

                try:

                    plugdict[name].state = 'OFF'
                    roomdict[name].status = plugdict[name].state
                    print(roomdict[name],'turned off')

                except:

                    print('warning, ',roomdict[name],' offline -- could not be turned off automatically')

    sleep(looptime)
