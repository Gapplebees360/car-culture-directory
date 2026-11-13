"""Notify the authenticated member backend after the static event feed is published.

Only a fixed, public feed is imported by the server. No privileged key is used here.
"""
import json
import urllib.error
import urllib.request

URL='https://lswnpxeiagureogrlopy.supabase.co/functions/v1/community/sync'
KEY='sb_publishable_hv4k-gXpG5Zh0tNzbcCRaA_Q7J0Bmvd'

if __name__=='__main__':
    request=urllib.request.Request(URL,data=b'{}',headers={'Content-Type':'application/json','apikey':KEY})
    try:
        with urllib.request.urlopen(request,timeout=60) as response:
            print('Member catalog refresh:',json.load(response))
    except urllib.error.HTTPError as error:
        if error.code in (404,503):
            print('::warning::Community backend is not active yet; static events remain published.')
        else:
            raise
