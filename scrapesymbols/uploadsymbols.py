#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import requests
import sys

url = 'https://crash-stats.mozilla.com/symbols/upload'

def main():
    if len(sys.argv) != 3:
        print 'Usage: uploadsymbols.py <zip file> <auth token>'
        return 1
    r = requests.post(
        url,
        files={'symbols.zip': open(sys.argv[1], 'rb')},
        headers={'Auth-Token': sys.argv[2]},
        allow_redirects=False
    )
    if r.status_code >= 200 and r.status_code < 300:
        print 'Uploaded successfully!'
    elif r.status_code < 400:
        print 'Error: bad auth token? (%d)' % r.status_code
    else:
        print 'Error: %d' % r.status_code
        print r.text
    return 0

if __name__ == '__main__':
    sys.exit(main())

