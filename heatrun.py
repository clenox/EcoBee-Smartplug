# Set up libraries

import datetime
import sys
import xml.etree.ElementTree as ET
from time import sleep
import certifi
import requests
import urllib3
import json
from twilio.rest import Client
from pyHS100 import SmartPlug, Discover
from auth import creds

#TODO - check unused variables

def main():

    sched = True

    # Get authorizations

    auth_dict = creds()

    auth = ecobee_tokens(0)

    if auth == 'NA':

        sys.exit('Bad token file')

    else:

        pass


    # time handling for error message

    timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())

    #  Set up Ohmconnect call

    http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

    OH = False

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
        send_twilio_msg(err_string)

        log = open('log.txt', 'a+')
        log.write(err_string)
        log.close()

        to_err = True

    data = response.json()

    # Populate lists used to build dicts.

    sensornames = []
    sensortemps = []
    temps = []

    for i in range(len(data['thermostatList'][0]['remoteSensors'])):
        sensornames.append(data['thermostatList'][0]['remoteSensors'][i]['name'])
        sensortemps.append(data['thermostatList'][0]['remoteSensors'][i]['capability'][0]['value'])

    for item in sensortemps:

        try:

            tval = float(item) / 10

        except ValueError:

            tval = 'badvalue'

        temps.append(tval)

    tempdict = dict(zip(sensornames, temps))

    #  Discover smart plug names and IP addresses.  Names of rooms, sensors, and plugs must match.

    plugip = {}
    plugnames = []

    mbed_plug = SmartPlug('0.0.0.0')
    obed_plug = SmartPlug('0.0.0.0')
    lbed_plug = SmartPlug('0.0.0.0')

    plugdict = {'MBED': mbed_plug, 'OBED': obed_plug, 'LBED': lbed_plug}

    # Discover all plugs

    named_flag = False

    discover = get_plugs(plugip, plugnames, named_flag)

    plugip = discover[0]

    plugnames = discover[1]

    named_flag = True

    # Assign ip addresses to controlled plugs.  Match the plug's assigned names (in Kasa app) to the plug object name.

    try:
        mbed_plug = SmartPlug(plugip['MBED'])
    except:
        pass
    try:
        obed_plug = SmartPlug(plugip['OBED'])
    except:
        pass
    try:
        lbed_plug = SmartPlug(plugip['LBED'])
    except:
        pass

    # Create list of valid rooms with both active sensors and plugs

    namelist = set(sensornames).intersection(plugnames)

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
    # Temp setpoints in F.
    # temp_high is top of setpoint deadband, temp_low is bottom of deadband
    # Time setpoints in decimal hours, 24 hour time
    # Note:  All time logic here assumes start after noon and end before noon!

    mbed = Room('MBED', tempdict['MBED'], 'OFF', 66.4, 66.4, 20.5, 7.5)
    lbed = Room('LBED', tempdict['LBED'], 'OFF', 66.4, 66.4, 19.75, 7.5)
    obed = Room('OBED', tempdict['OBED'], 'OFF', 66.4, 66.4, 19.75, 7.5)

    # Define setback for Ohmhour DR event.  Must be a negative number.

    setback = -3.0

    # Define rooms and room dictionary

    roomdict = {'MBED': mbed,'LBED': lbed,'OBED': obed}

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

    token_refresh_loops = 3600 / looptime
    token_refresh_count = 0
    retry = 0

    # Start main loop

    while True:

        # Token refresh

        if token_refresh_count < token_refresh_loops:

            token_refresh_count = token_refresh_count + 1

        else:

            auth_temp = ecobee_tokens(retry)

            if auth_temp == 'NA':

                retry = retry + 1
                print('debug - auth NA')

            else:

                auth = auth_temp
                retry = 0
                token_refresh_count = 0

        # time handling

        timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        dectime = float(timestamp[11:13]) + float(timestamp[14:16]) / 60

        while dectime >= start_time or dectime <= end_time:

            timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
            dectime = float(timestamp[11:13]) + float(timestamp[14:16]) / 60

            sched = True

            # Call EcoBee API to get data

            try:

                thermostat_url = 'https://api.ecobee.com/1/thermostat?'
                payload = {'json': '{"selection":{"selectionType":"registered","includeSensors":"true"}}'}
                header = {'Content-Type': 'application/json;charset=UTF-8', 'Authorization': auth}

                response = requests.get(thermostat_url, headers=header, params=payload)

                # Add requests

                to_err = False

                data = response.json()

            except:

                err_string = (str(timestamp) + 'Error in ecobee data call') + "\r"

                print(err_string)

                statusmsg = 'Ecobee data call error'

                sleep(30)

                to_err = True

                continue

            #  Update temperature readings

            sensornames = []
            sensortemps = []
            temps = []

            for i in range(len(data['thermostatList'][0]['remoteSensors'])):
                sensornames.append(data['thermostatList'][0]['remoteSensors'][i]['name'])
                sensortemps.append(data['thermostatList'][0]['remoteSensors'][i]['capability'][0]['value'])

            for item in sensortemps:

                try:

                    tval = float(item) / 10

                except ValueError:

                    tval = 'badvalue'

                temps.append(tval)

            tempdict = dict(zip(sensornames, temps))

            dt = datetime.datetime.now()

            hr = datetime.timedelta(hours=dt.hour, minutes=0, seconds=0)

            timediff = dt - hr

            OC_state = 'False'

            #  Get Ohm connect status

            try:

                oc_url = auth_dict['ohmconnect_url']

                r = http.request('GET', oc_url)

                data = r.data

                root = ET.fromstring(data)

                OC_state = root[1].text

            except:

                OC_state = 'False'

            for name in namelist:

                roomdict[name].temp = tempdict[name]

                # Decision logic and set booleans for switches
                # Plug status is updated separately from state to reduce calls to plug endpoints
                # and allow rotation of heater operation per below
                # Determine Ohmconnect state and setback

                #  Set back temperature thresholds when Ohnhour detected

                if OC_state == 'True':

                    roomdict[name].temp_high = roomdict[name].temp_high + setback
                    roomdict[name].temp_low = roomdict[name].temp_low + setback
                    OH = True

                elif OH == True:

                    roomdict[name].temp_high = roomdict[name].temp_high - setback
                    roomdict[name].temp_low = roomdict[name].temp_low - setback
                    OH = False

                else:

                    pass

                #  End setback logic

                if roomdict[name].temp == 'badvalue':

                    print('Warning:  bad temp reading in ', name)

                    roomdict[name].status = roomdict[name].status

                elif roomdict[name].temp <= roomdict[name].temp_low and (dectime >= roomdict[name].on_from or dectime <= roomdict[name].on_to):

                    roomdict[name].status = "ON"

                elif roomdict[name].temp > roomdict[name].temp_high or (dectime < roomdict[name].on_from and dectime > roomdict[name].on_to):

                    roomdict[name].status = "OFF"

                else:

                    roomdict[name].status = roomdict[name].status

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

                plugip = get_plugs(plugip, plugnames, named_flag)[0]

                try:
                    mbed_plug = SmartPlug(plugip['MBED'])
                    print(mbed_plug)
                    mbed_plug_err = False

                except:
                    print('mbed plug error')
                    mbed_plug_err = True

            try:

                obed_plug_chk = obed_plug.state
                obed_plug_err = False

            except:

                plugip = get_plugs(plugip, plugnames, named_flag)[0]

                try:
                    obed_plug = SmartPlug(plugip['OBED'])
                    obed_plug_err = False
                    print(obed_plug)

                except:
                    print('obed plug error')
                    obed_plug_err = True

            try:

                lbed_plug_chk = lbed_plug.state
                lbed_plug_err = False

            except:

                plugip = get_plugs(plugip, plugnames, named_flag)[0]

                try:
                    lbed_plug = SmartPlug(plugip['LBED'])
                    lbed_plug_err = False
                    print(lbed_plug)

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
                    statusmsg = 'Alternating obed OFF lbed ON'

                elif obed.status == 'ON' and lbed.status == 'ON' and lbed_turn is False:

                    lbed_plug.state = 'OFF'
                    sleep(5)
                    obed_plug.state = 'ON'
                    lbed_turn = True
                    statusmsg = 'Alternating obed ON lbed OFF'

                else:

                    obed_plug.state = obed.status
                    lbed_plug.state = lbed.status
                    statusmsg = 'Normal'

            elif obed_plug_err is True and lbed_plug_err is False:

                lbed_plug.state = lbed.status
                statusmsg = 'lbed per status, obed offline'

            elif lbed_plug_err is True and obed_plug_err is False:

                obed_plug.state = obed.status
                statusmsg = 'obed per status, lbed offline'

            else:

                statusmsg = 'obed and lbed offline'

            # Write log -- TODO UPDATE ASSUMING HEADERS

            log_str = (str(timestamp) + ", MBED, " + str(roomdict['MBED'].temp) + ", " + str(roomdict['MBED'].status) +
                        ", OBED, " + str(roomdict['OBED'].temp) + ", " + str(roomdict['OBED'].status) +
                        ", LBED, " + str(roomdict['LBED'].temp) + ", " + str(roomdict['LBED'].status) +
                        ", Status" + ", " + statusmsg +
                        ", OhmConnect Status" + ", " + OC_state + "\n")

            log = open("log.txt", "a+")
            log.write(log_str)
            log.close()

            # TODO REWORK TO MAKE MORE FRIENDLY

            print('Latest Timestamp: ', log_str + "\r")

            sleep(looptime)

    # If outside of the schedule enter sleep mode.  No logging in sleep mode.

        if sched is True:

            print('Sleep Mode')

            for name in namelist:

                if roomdict[name].status == 'ON':

                    try:

                        plugdict[name].state = 'OFF'
                        roomdict[name].status = plugdict[name].state
                        print(roomdict[name], 'turned off')

                    except:

                        print('warning, ', roomdict[name], ' offline -- could not be turned off automatically')

            sched = False

        else:

            pass

        sleep(looptime)


def get_plugs(plugip, plugnames, named_flag):

    try:

        for dev in Discover.discover():
            plugobj = SmartPlug(dev)
            plugip[plugobj.alias] = dev

            if named_flag == False:

                plugnames.append(plugobj.alias)

            else:

                pass

        return [plugip, plugnames]


    except:

        print('plug discovery failed')


def ecobee_tokens(retry):

    app_key = creds()['ecobee_apikey']

    # open token file store & retrieve refresh token

    f = open("tokens.txt", "r")

    token_str = str(f.read())

    f.close()

    token_list = token_str.split(",")

    try:

        refresh_token = token_list[2]

    except IndexError:

        send_twilio_msg('Heatrun Error -- Bad Ecobee Token File')
        sys.exit('Token File Read Error')

    token_url = 'https://api.ecobee.com/token?'
    payload = {'grant_type': 'refresh_token', 'refresh_token': refresh_token, 'client_id': app_key}

    try:

        r_refresh = requests.post(token_url, params=payload)

        # print(r_refresh.text)

        r_refresh_dict = json.loads(r_refresh.text)

        #    print(r_refresh_dict)

        if r_refresh.status_code == requests.codes.ok:

            token_type = r_refresh_dict['token_type']
            access_token = r_refresh_dict['access_token']
            refresh_token = r_refresh_dict['refresh_token']

            auth_log = access_token + "," + token_type + "," + refresh_token

            auth = (token_type) + ' ' + (access_token)

            #        print(r_refresh.status_code)

            # write new tokens to file store

            f = open("tokens.txt", "w+")
            f.truncate()
            f.write(auth_log)

            #   verify stored tokens are good

            #token_str = str(f.read())
            #f.close()

         #   print(token_str)

            return auth

        else:

            raise ValueError(r_refresh.status_code)

    except:

        if retry <= 20:

            auth = 'NA'

            if retry == 0:

                send_twilio_msg('Warning - Ecobee token issue.  Retrying ...')

            else:

                pass

            return auth

        else:

            send_twilio_msg('Ecobee token refresh failed - restart manually!')
            sys.exit('token refresh error')

def send_twilio_msg(alert_msg):

    twilio_sid = creds()['twilio_sid']
    twilio_token = creds()['twilio_token']
    twilio_from = creds()['twilio_from']
    twilio_to = creds()['twilio_to']

    client = Client(twilio_sid, twilio_token)

    message = client.messages.create(
        from_=twilio_from,
        body=alert_msg,
        to=twilio_to
    )

    print(message.sid)

    return True

if __name__== "__main__":

    main()