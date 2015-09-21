#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import argparse
import concurrent.futures
import datetime
import os
import requests
import subprocess
import sys
import urllib
import urlparse
import zipfile


if sys.platform == 'darwin':
    is_linux = False
    SYSTEM_DIRS = [
        '/usr/lib',
        '/System/Library/Frameworks'
    ]
else:
    is_linux = True
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
    try:
        r = requests.head(urlparse.urljoin(SYMBOL_SERVER_URL, urllib.quote(filename)))
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def process_file(dump_syms, path, arch, verbose, missing_symbols):
    if sys.platform == 'darwin':
        arch_arg = ['-a', arch]
    else:
        arch_arg = []
    try:
        stderr = None if verbose else open(os.devnull, 'wb')
        stdout = subprocess.check_output([dump_syms] + arch_arg + [path],
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

def get_files(paths):
    '''
    For each entry passed in paths if the path is a file that can
    be processed, yield it, otherwise if it is a directory yield files
    under it that can be processed.
    '''
    for path in paths:
        if os.path.isdir(path):
            for root, subdirs, files in os.walk(d):
                for f in files:
                    fullpath = os.path.join(root, f)
                    if should_process(fullpath):
                        yield fullpath
        elif should_process(path):
            yield path

def process_paths(paths, executor, dump_syms, verbose, missing_symbols):
    jobs = set()
    for fullpath in get_files(paths):
        while os.path.islink(fullpath):
            fullpath = os.path.join(os.path.dirname(fullpath),
                                    os.readlink(fullpath))
        if is_linux:
            # See if there's a -dbg package installed and dump that instead.
            dbgpath = '/usr/lib/debug' + fullpath
            if os.path.isfile(dbgpath):
                fullpath = dbgpath
        for arch in get_archs(fullpath):
            jobs.add(executor.submit(process_file, dump_syms, fullpath, arch, verbose, missing_symbols))
    for job in concurrent.futures.as_completed(jobs):
        try:
            yield job.result()
        except Exception as e:
            print >>sys.stderr, 'Error: %s' % str(e)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Produce verbose output')
    parser.add_argument('--all', action='store_true',
                        help='Gather all system symbols, not just missing ones.')
    parser.add_argument('dump_syms', help='Path to dump_syms binary')
    parser.add_argument('files', nargs='*',
                        help='Specific files from which to gather symbols.')
    args = parser.parse_args()
    # check for the dump_syms binary
    if not os.path.exists(args.dump_syms) or not os.access(args.dump_syms, os.X_OK):
        print >>sys.stderr, 'Error: can\'t find dump_syms binary at %s!' % args.dump_syms
        return 1
    if args.all or args.files:
        missing_symbols = None
    else:
        # Fetch list of missing symbols
        missing_symbols = fetch_missing_symbols(args.verbose)
    file_list = []
    executor = concurrent.futures.ProcessPoolExecutor()
    with zipfile.ZipFile('symbols.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, contents in process_paths(args.files if args.files else SYSTEM_DIRS, executor, args.dump_syms, args.verbose, missing_symbols):
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
