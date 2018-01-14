# This runs in parallel to maintain up to date ecobee access and refresh tokens

import sys
import requests
import json
from time import sleep

# Read developer key from a file, set scope

a = open("apikey.txt", "r")
APP_KEY = a.read()
SCOPE = 'smartWrite'

while True:

# open token file

    f = open("tokens.txt", "r")

    token_str = str(f.read())

    f.close()

    token_list = token_str.split(",")

    try:

        access_token = token_list[0]
        token_type = token_list[1]
        refresh_token = token_list[2]

    except IndexError:

        sys.exit('Token File Read Error')

    token_url = 'https://api.ecobee.com/token?'
    payload = {'grant_type': 'refresh_token', 'refresh_token': refresh_token, 'client_id': APP_KEY}

    r_refresh = requests.post(token_url, params=payload)

    r_refresh_dict = json.loads(r_refresh.text)

#    print(r_refresh_dict)

    if r_refresh.status_code == requests.codes.ok:

        token_type = r_refresh_dict['token_type']
        access_token = r_refresh_dict['access_token']
        refresh_token = r_refresh_dict['refresh_token']

        auth_log = access_token + "," + token_type + "," + refresh_token

        auth = (token_type) + ' ' + (access_token)

#        print(r_refresh.status_code)

        # write tokens to file

        f = open("tokens.txt", "w+")
        f.truncate()
        f.write(auth_log)

     #   verify tokens are good

        token_str = str(f.read())
        f.close()

        print(token_str)

    else:

        sys.exit('token refresh error')

    sleep(3500)
