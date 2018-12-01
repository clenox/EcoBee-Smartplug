# Set up libraries

import datetime
from datetime import timedelta
import sys
import xml.etree.ElementTree as et
from time import sleep
import certifi
import requests
import urllib3
import json
from twilio.rest import Client
from pyHS100 import SmartPlug, Discover
from auth import creds

looptime = 180
token_refresh_loops = 180 / looptime


def main():

    sched = True

    # Get authorizations

    auth_dict = creds()

    # Fresh tokens on program start

    ecobee_token_response = ecobee_tokens(True, datetime.datetime.min)

    auth = ecobee_token_response[0]
    last_refresh_time = ecobee_token_response[1]

    #  Set up Ohmconnect call

    http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

    oc = [False]

    # Initial ecobee API call to populate room class
    # TODO - refactor Ecobee API call and error handling (make consistent) as function

    # timestamp for error message

    timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())

    try:

        thermostat_url = 'https://api.ecobee.com/1/thermostat?'
        payload = {'json': '{"selection":{"selectionType":"registered","includeSensors":"true"}}'}
        header = {'Content-Type': 'application/json;charset=UTF-8', 'Authorization': auth}

        response = requests.get(thermostat_url, headers=header, params=payload)

    except TimeoutError:

        err_string = (str(timestamp) + ' Timeout error in ecobee data call') + "\r"

        print(err_string)
        send_twilio_msg(err_string)

        log = open('log.txt', 'a+')
        log.write(err_string)
        log.close()

    data = response.json()

    # Build temperature sensor dictionary

    tempdict = get_sensors(data)
    sensornames = list(tempdict.keys())

#    print(tempdict)

    if len(tempdict) == 0:

        print(data)
        sys.exit("no temperature sensors detected")

    else:

        pass

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

    # Assign ip addresses to controlled plugs.
    # Must match the plug's assigned names (in Kasa app) to the plug object name.

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

    # Initialize schedule and temperature band
    # Temp setpoints in F.
    # temp_high is top of setpoint deadband, temp_low is bottom of deadband
    # Time setpoints in decimal hours, 24 hour time
    # Note:  All time logic here assumes start after noon and end before noon!

    mbed = Room('MBED', tempdict['MBED'], 'OFF', 66.6, 66.4, 20.5, 7.5)
    lbed = Room('LBED', tempdict['LBED'], 'OFF', 66.6, 66.4, 19.75, 7.5)
    obed = Room('OBED', tempdict['OBED'], 'OFF', 66.6, 66.4, 19.75, 7.5)

    # Define setback temperature for Ohmhour DR event.  Must be a negative number.

    setback = -3.0

    # Define rooms and room dictionary

    roomdict = {'MBED': mbed, 'LBED': lbed, 'OBED': obed}

    # Initialize schedule bounds -- the earliest start and latest end of schedule for all rooms
    # Used to determine when in active vs. sleep mode overall

    start_time = mbed.on_from
    end_time = mbed.on_to

    for name in namelist:

        if roomdict[name].on_from < start_time:

            start_time = roomdict[name].on_from

        if roomdict[name].on_to > end_time:

            end_time = roomdict[name].on_to

# Initialize error counter

    sensor_error_count = 0

    # Start main loop

    while True:

        # Token refresh

        ecobee_token_response = ecobee_tokens(False, last_refresh_time)

        last_refresh_time = ecobee_token_response[1]

        # time handling

        timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        dectime = float(timestamp[11:13]) + float(timestamp[14:16]) / 60

        # Portion of loop inside schedule bounds

        while dectime >= start_time or dectime <= end_time:

            # Token refresh

            ecobee_token_response = ecobee_tokens(False, last_refresh_time)

            auth = ecobee_token_response[0]
            last_refresh_time = ecobee_token_response[1]

            # Time handling in loop

            timestamp = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
            dectime = float(timestamp[11:13]) + float(timestamp[14:16]) / 60

            sched = True

            # Call EcoBee API to get data
            # TODO refactor as function

            try:

                thermostat_url = 'https://api.ecobee.com/1/thermostat?'
                payload = {'json': '{"selection":{"selectionType":"registered","includeSensors":"true"}}'}
                header = {'Content-Type': 'application/json;charset=UTF-8', 'Authorization': auth}

                response = requests.get(thermostat_url, headers=header, params=payload)

                data = response.json()

            except:

                err_string = (str(timestamp) + 'Error in ecobee data call') + "\r"

                print(err_string)

                sleep(30)

                continue

            #  Update temperature readings

            tempdict = get_sensors(data)

            if len(tempdict) == 0:

                print(data)
                sensor_error_count = sensor_error_count + 1

                if sensor_error_count == 1:

                    send_twilio_msg("Warning - sensor temps not updating")

                elif sensor_error_count == 11:

                    send_twilio_msg("Temp reading failure.  Program exited.")
                    sys.exit("Temp reading failure.  Program exited.")

                else:

                    pass

                sleep(60)

                continue

            else:

                if sensor_error_count > 0:

                    send_twilio_msg("Sensor issue resolved")

                else:

                    pass

                sensor_error_count = 0

                pass

            #  Get Ohmconnect status

            try:

                oc_url = auth_dict['ohmconnect_url']

                r = http.request('GET', oc_url)

                data = r.data

                root = et.fromstring(data)

                oc_txt = root[1].text

                if oc_txt == 'True':

                    oc_state = True

                else:

                    oc_state = False

            except:

                oc_state = False

            #TODO use dequeue insted

            oc.insert(0,oc_state)
            last_oc = oc.pop()

            if oc_state == last_oc:

                offset = 0

            elif oc_state == True:

                offset = setback

            else:

                offset = -setback

            for name in namelist:

                roomdict[name].temp = tempdict[name]

                # Decision logic and set booleans for switches
                # Plug status is updated separately from state to reduce calls to plug endpoints
                # and allow rotation of heater operation per below
                # Determine Ohmconnect state and setback offset

                roomdict[name].temp_high = roomdict[name].temp_high + offset
                roomdict[name].temp_low = roomdict[name].temp_low + offset

                # Temp issue debug statement

     #           print(name,' ','current temp: ',roomdict[name].temp,' upper: ',roomdict[name].temp_high,' lower: ',roomdict[name].temp_low)

                #  Determine each room's status (On or Off)

                if roomdict[name].temp == 'badvalue':

                    print('Warning:  bad temp reading in ', name)

                    roomdict[name].status = roomdict[name].status

                elif roomdict[name].temp <= roomdict[name].temp_low \
                        and (dectime >= roomdict[name].on_from or dectime <= roomdict[name].on_to):

                    roomdict[name].status = "ON"

                elif roomdict[name].temp > roomdict[name].temp_high or dectime < roomdict[name].on_from \
                        or dectime > roomdict[name].on_to:

                    roomdict[name].status = "OFF"

                else:

                    roomdict[name].status = roomdict[name].status

            # Check & handle loss of communication with plugs

            try:

                mbed_plug.state = mbed.status
            #   mbed_plug_err = False
            #   Not currently used

            except:

                plugip = get_plugs(plugip, plugnames, named_flag)[0]

                try:
                    mbed_plug = SmartPlug(plugip['MBED'])
                    print(mbed_plug)
                #   mbed_plug_err = False
                #   Not currently used

                except:
                    print('mbed plug error')
                #   mbed_plug_err = True
                #   Not currently used

            try:

                obed_plug_chk = obed_plug.state  # variable only used to force API call
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

                lbed_plug_chk = lbed_plug.state  # variable only used to force API call
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

            # For LBED and OBED rooms determine which will operate when both are in ON state.
            # In my house two heaters are on a single circuit breaker.
            # This breaker trips if both are running simultaneously.
            # The section is specific to this situation.

            if obed.temp < lbed.temp:

                lbed_turn = False

            else:

                lbed_turn = True

            # Determine plug states - this logic actually turns the plugs on or off.

            if obed_plug_err is False and lbed_plug_err is False:

                if obed.status == 'ON' and lbed.status == 'ON' and lbed_turn is True:

                    obed_plug.state = 'OFF'
                    sleep(5)
                    lbed_plug.state = 'ON'
                    lbed_turn = False  # Variable is actually used due to looping
                    statusmsg = 'Alternating obed OFF lbed ON'

                elif obed.status == 'ON' and lbed.status == 'ON' and lbed_turn is False:

                    lbed_plug.state = 'OFF'
                    sleep(5)
                    obed_plug.state = 'ON'
                    lbed_turn = True  # Variable is actually used due to looping
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
                        ", OhmConnect Status" + ", " + oc_txt + "\n")

            log = open("log.txt", "a+")
            log.write(log_str)
            log.close()

            # TODO REWORK TO MAKE MORE READABLE

            print('Latest Timestamp: ', log_str + "\r")

            sleep(looptime)

    # If outside of the schedule enter sleep mode.  No logging in sleep mode.

        if sched is True:

            print('Sleep Mode')

            # Turn all plugs off if possible

            for name in namelist:

                if roomdict[name].status == 'ON':

                    try:

                        plugdict[name].state = 'OFF'
                        roomdict[name].status = plugdict[name].state
                        print(roomdict[name], 'turned off')

                    except:

                        overrun_warn_msg = str(
                            'Warning, {0} offline -- could not be turned off automatically'.format(str(roomdict[name])))

                        send_twilio_msg(overrun_warn_msg)
                        print(overrun_warn_msg)

            sched = False

        else:

            pass

        sleep(looptime)


def get_plugs(plugip, plugnames, named_flag):

    try:

        for dev in Discover.discover():
            plugobj = SmartPlug(dev)
            plugip[plugobj.alias] = dev

            if named_flag is False:

                plugnames.append(plugobj.alias)

            else:

                pass

        return [plugip, plugnames]

    except:

        send_twilio_msg('plug discovery failed')
        sys.exit('plug discovery failed')


def get_sensors(data):

    sensornames = []
    sensortemps = []
    temps = []
    tempdict = {}
    sensor_detect = True

    try:

        for i in range(len(data['thermostatList'][0]['remoteSensors'])):
            sensornames.append(data['thermostatList'][0]['remoteSensors'][i]['name'])
            sensortemps.append(data['thermostatList'][0]['remoteSensors'][i]['capability'][0]['value'])

    except:

        sensor_detect = False

    if sensor_detect is True:

        for item in sensortemps:

            try:

                tval = float(item) / 10

            except ValueError:

                tval = 'badvalue'

            temps.append(tval)

        tempdict = dict(zip(sensornames, temps))

    else:

        pass

    return tempdict


def ecobee_tokens(loop_count_reset, last_refresh_time):

    app_key = creds()['ecobee_apikey']

    retry_count = 0

    token_interval_time = timedelta(minutes=30) # If less than looptime, refresh interval will be looptime interval
                                                # Tokens expire after 3600 seconds
    current_time = datetime.datetime.now()

    elapsed_time = current_time - last_refresh_time

    # open token file store & retrieve current tokens

    f = open("tokens.txt", "r")

    token_str = str(f.read())

    f.close()

    token_list = token_str.split(",")

    try:

        auth = token_list[1]+' '+token_list[0]

    except IndexError:

        send_twilio_msg('Heatrun Error -- Bad Ecobee Token File')
        print("bad tokens:", token_str)
        sys.exit('Token File Read Error')

    while retry_count <= 10:

        if elapsed_time >= token_interval_time or loop_count_reset is True:

            try:

                refresh_token = token_list[2]

            except IndexError:

                send_twilio_msg('Heatrun Error -- Bad Ecobee Token File')
                sys.exit('Token File Read Error')

            token_url = 'https://api.ecobee.com/token?'
            payload = {'grant_type': 'refresh_token', 'refresh_token': refresh_token, 'client_id': app_key}

            try:

                r_refresh = requests.post(token_url, params=payload)

                r_refresh_dict = json.loads(r_refresh.text)

                print(r_refresh_dict)

                if r_refresh.status_code == requests.codes.ok:

                    token_type = r_refresh_dict['token_type']
                    access_token = r_refresh_dict['access_token']
                    refresh_token = r_refresh_dict['refresh_token']

                    auth_log = access_token + "," + token_type + "," + refresh_token

                    auth = token_type + ' ' + access_token

                    # Check tokens are received

                    if len(auth_log) == 0:

                        raise ValueError("Empty token refresh")

                    else:

                        pass

                    # write new tokens to file store

                    f = open("tokens.txt", "w+")
                    f.truncate()
                    f.write(auth_log)
                    f.close()

                    retry_count = 0
                    last_refresh_time = datetime.datetime.now()

                    break

                else:

                    raise ValueError(r_refresh.status_code)

            except:

                if retry_count == 0:

                    retry_count = retry_count + 1
                    send_twilio_msg('Warning - Ecobee token issue.  Retrying for 10 minutes.')
                    sleep(60)

                elif retry_count <= 10:

                    retry_count = retry_count + 1
                    sleep(60)

                else:

                    send_twilio_msg('Ecobee token refresh failed - restart manually!')
                    sys.exit('token refresh error')

                continue

        else:

            break

    return (auth, last_refresh_time)


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


if __name__ == "__main__":

    main()
