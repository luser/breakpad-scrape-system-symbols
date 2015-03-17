#!/usr/bin/env python

import argparse
import datetime
import os
import requests
import subprocess
import sys
import urllib
import urlparse
import zipfile


if sys.platform == 'darwin':
    SYSTEM_DIRS = [
        '/usr/lib',
        '/System/Library/Frameworks'
    ]
else:
    SYSTEM_DIRS = [
        '/lib',
        '/usr/lib',
    ]
SYMBOL_SERVER_URL = 'https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/'
MISSING_SYMBOLS_URL = 'https://crash-analysis.mozilla.com/crash_analysis/{date}/{date}-missing-symbols.txt'

def should_process(f):
    '''Determine if a file is a platform binary'''
    if sys.platform == 'darwin':
        if f.endswith('.dylib') or os.access(f, os.X_OK):
            return subprocess.check_output(['file', '-Lb', f]).startswith('Mach-O')
    elif f.find('.so') != -1 or os.access(f, os.X_OK):
            return subprocess.check_output(['file', '-Lb', f]).startswith('ELF')
    return False

def get_archs(filename):
    '''
    Find the list of architectures present in a Mach-O file, or a single-element
    list on non-OS X.
    '''
    if sys.platform == 'darwin':
        return subprocess.check_output(['lipo', '-info', filename]).split(':')[2].strip().split()
    return [None]

def server_has_file(filename):
    '''
    Send the symbol server a HEAD request to see if it has this symbol file.
    '''
    r = requests.head(urlparse.urljoin(SYMBOL_SERVER_URL, urllib.quote(filename)))
    return r.status_code == 200


def process_file(path, arch, verbose, missing_symbols):
    if sys.platform == 'darwin':
        arch_arg = ['-a', arch]
    else:
        arch_arg = []
    try:
        stderr = None if verbose else open(os.devnull, 'wb')
        stdout = subprocess.check_output(['./dump_syms'] + arch_arg + [path],
                                         stderr=stderr)
    except subprocess.CalledProcessError:
        if verbose:
            print 'Processing %s%s...failed.' % (path, ' [%s]' % arch if arch else '')
        return None, None
    module = stdout.splitlines()[0]
    bits = module.split(' ', 4)
    if len(bits) != 5:
        return None, None
    _, platform, cpu_arch, debug_id, debug_file = bits
    # see if this symbol is missing
    if missing_symbols and (debug_file, debug_id) not in missing_symbols:
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

def just_platform_symbols(file):
    extension = '.dylib' if sys.platform == 'darwin' else '.so'
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
        if debug_file.endswith(extension):
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
            return just_platform_symbols(r.content)
    return set()

def get_files(dirs):
    for d in dirs:
        for root, subdirs, files in os.walk(d):
            for f in files:
                fullpath = os.path.join(root, f)
                if should_process(fullpath):
                    yield fullpath

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Produce verbose output')
    parser.add_argument('--all', action='store_true',
                        help='Gather all system symbols, not just missing ones.')
    args = parser.parse_args()
    # check for the dump_syms binary
    if not os.path.exists('dump_syms') or not os.access('dump_syms', os.X_OK):
        print >>sys.stderr, 'Error: can\'t find dump_syms binary next to this script!'
        return 1
    if args.all:
        missing_symbols = None
    else:
        # Fetch list of missing symbols
        missing_symbols = fetch_missing_symbols(args.verbose)
    #TODO: io.BytesIO, build in-memory
    file_list = []
    with zipfile.ZipFile('symbols.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        for fullpath in get_files(SYSTEM_DIRS):
            for arch in get_archs(fullpath):
                filename, contents = process_file(fullpath, arch, args.verbose, missing_symbols)
                if filename and contents:
                    file_list.append(filename)
                    zf.writestr(filename, contents)
        zf.writestr('ossyms-1.0-{platform}-{date}-symbols.txt'.format(platform=sys.platform.title(), date=datetime.datetime.now().strftime('%Y%m%d%H%M%S')),
                    '\n'.join(file_list))
    if file_list:
        if args.verbose:
            print 'Generated symbols.zip with %d symbols' % len(file_list)
    else:
        os.unlink('symbols.zip')

if __name__ == '__main__':
    main()
