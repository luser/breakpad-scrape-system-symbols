#!/usr/bin/env python

import datetime
import optparse
import os
import requests
import subprocess
import sys
import urlparse
import zipfile


SYSTEM_DIRS = [
    '/usr/lib',
    '/System/Library/Frameworks'
    ]
SYMBOL_SERVER_URL = 'http://symbols.mozilla.org/'
MISSING_SYMBOLS_URL = 'https://crash-analysis.mozilla.com/crash_analysis/{date}/{date}-missing-symbols.txt'

def should_process(f):
    '''Determine if a file is a Mach-O binary'''
    if f.endswith('.dylib') or os.access(f, os.X_OK):
        return subprocess.check_output(['file', '-Lb', f]).startswith('Mach-O')
    return False

def get_archs(filename):
    '''
    Find the list of architectures present in a Mach-O file.
    '''
    return subprocess.check_output(['lipo', '-info', filename]).split(':')[2].strip().split()

def server_has_file(filename):
    '''
    Send the symbol server a HEAD request to see if it has this symbol file.
    '''
    r = requests.head(urlparse.urljoin(SYMBOL_SERVER_URL, filename))
    return r.status_code == 200


def process_file(path, arch, verbose, missing_symbols):
    try:
        stderr = None if verbose else open(os.devnull, 'wb')
        stdout = subprocess.check_output(['./dump_syms', '-a', arch, path],
                                         stderr=stderr)
    except subprocess.CalledProcessError:
        if verbose:
            print 'Processing %s [%s]...failed.' % (path, arch)
        return None, None
    module = stdout.splitlines()[0]
    bits = module.split(' ', 4)
    if len(bits) != 5:
        return None, None
    _, platform, cpu_arch, debug_id, debug_file = bits
    # see if this symbol is missing
    if (debug_file, debug_id) not in missing_symbols:
        return None, None
    if verbose:
        sys.stdout.write('Processing %s [%s]...' % (path, arch))
    filename = os.path.join(debug_file, debug_id, debug_file + '.sym')
    # see if the server already has this symbol file
    if server_has_file(filename):
        if verbose:
            print 'already on server.'
        return None, None
    # Collect for uploading
    if verbose:
        print 'done.'
    return filename, stdout

def just_mac_symbols(file):
    symbols = set()
    lines = iter(file.splitlines())
    # Skip header
    next(lines)
    for line in lines:
        line = unicode(line.rstrip(), 'utf-8').encode('ascii', 'replace')
        bits = line.split(',')
        if len(bits) < 2:
            continue
        debug_file, debug_id = bits[:2]
        if debug_file.endswith('.dylib'):
            symbols.add((debug_file, debug_id))
    return symbols

def fetch_missing_symbols(verbose):
    now = datetime.datetime.now()
    for n in range(5):
        d = now + datetime.timedelta(days=-n)
        u = MISSING_SYMBOLS_URL.format(date=d.strftime('%Y%m%d'))
        r = requests.get(u)
        if r.status_code == 200:
            if verbose:
                print 'Fetching missing symbols from %s' % u
            return just_mac_symbols(r.content)
    return set()

def main():
    parser = optparse.OptionParser()
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true')
    options, args = parser.parse_args()
    # check for the dump_syms binary
    if not os.path.exists('dump_syms') or not os.access('dump_syms', os.X_OK):
        print >>sys.stderr, 'Error: can\'t find dump_syms binary next to this script!'
        return 1
    # Fetch list of missing symbols
    missing_symbols = fetch_missing_symbols(options.verbose)
    #TODO: io.BytesIO, build in-memory
    file_list = []
    with zipfile.ZipFile('symbols.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        for d in SYSTEM_DIRS:
            for root, dirs, files in os.walk(d):
                for f in files:
                    fullpath = os.path.join(root, f)
                    if should_process(fullpath):
                        for arch in get_archs(fullpath):
                            filename, contents = process_file(fullpath, arch, options.verbose, missing_symbols)
                            if filename and contents:
                                file_list.append(filename)
                                zf.writestr(filename, contents)
        zf.writestr('osxsyms-1.0-Darwin-{date}-symbols.txt'.format(date=datetime.datetime.now().strftime('%Y%m%d')),
                    '\n'.join(file_list))
    if file_list:
        if options.verbose:
            print 'Generated symbols.zip with %d symbols' % len(file_list)
    else:
        os.unlink('symbols.zip')

if __name__ == '__main__':
    main()
