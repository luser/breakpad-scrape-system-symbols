#!/usr/bin/env python

import sys, os, subprocess, optparse, httplib, socket, urllib

SYSTEM_DIRS = [
    '/usr/lib',
    '/System/Library/Frameworks'
    ]
STORE_DIR = os.path.expanduser("~/Library/Application Support/gathersymbols/")
SERVER = "brasstacks.mozilla.com"
SERVER_PATH = "/symbolserver/"

def should_process(f):
    if f.endswith(".dylib") or os.access(f, os.X_OK):
        return subprocess.Popen(["file", "-Lb", f], stdout=subprocess.PIPE).communicate()[0].startswith("Mach-O")
    return False

def get_archs(filename):
    """
    Find the list of architectures present in a Mach-O file.
    """
    return subprocess.Popen(["lipo", "-info", filename], stdout=subprocess.PIPE).communicate()[0].split(':')[2].strip().split()

def server_has_file(filename, debug_id):
    """
    Send the server a HEAD request to see if it has this symbol file.
    """
    try:
        conn = httplib.HTTPConnection(SERVER)
        conn.request("HEAD", urllib.quote("%s%s/%s" % (SERVER_PATH,
                                                       filename, debug_id)))
        res = conn.getresponse()
        return res.status == 200
    except httplib.HTTPException, e:
        sys.stdout.write("HEAD error: %s " % str(e))
        return False
    except socket.error, e:
        sys.stdout.write("HEAD socket error: %s " % str(e))
        return False

def send_file(filename, debug_id, data):
    """
    HTTP PUT the file contents to the server.
    """
    try:
        conn = httplib.HTTPConnection(SERVER)
        conn.request("PUT", urllib.quote("%s%s/%s" % (SERVER_PATH,
                                                      filename, debug_id)),
                     data)
        res = conn.getresponse()
        return res.status == 200
    except httplib.HTTPException, e:
        sys.stdout.write("PUT error: %s " % str(e))
        return False
    except socket.error, e:
        sys.stdout.write("PUT socket error: %s " % str(e))
        return False

def touch(path):
    d = os.path.dirname(path)
    if not os.path.exists(d):
        try:
            os.makedirs(d)
        except:
            pass
    open(path, 'w').close()

def process_file(path, arch, verbose):
    proc = subprocess.Popen(["./dump_syms", "-a", arch, path],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        if verbose:
            print "Processing %s [%s]...failed." % (path, arch)
        return
    module = stdout.splitlines()[0]
    bits = module.split(" ", 4)
    if len(bits) != 5:
        return
    _, platform, cpu_arch, debug_id, filename = bits
    # see if we've already submitted this symbol file
    marker_file = os.path.join(STORE_DIR, filename, debug_id)
    if os.path.exists(marker_file):
        return
    if verbose:
        sys.stdout.write("Processing %s [%s]..." % (path, arch))
    # see if the server already has this symbol file
    if server_has_file(filename, debug_id):
        if verbose:
            print "already on server."
        touch(marker_file)
        return
    # upload to server
    if send_file(filename, debug_id, stdout):
        if verbose:
            print "submitted successfully."
        touch(marker_file)
    else:
        if verbose:
            print "failed to submit."

def main():
    parser = optparse.OptionParser()
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true")
    options, args = parser.parse_args()
    # check for the dump_syms binary
    if not os.path.exists('dump_syms') or not os.access('dump_syms', os.X_OK):
        print >>sys.stderr, "Error: can't find dump_syms binary next to this script!"
        return 1
    if not os.path.exists(STORE_DIR):
        os.makedirs(STORE_DIR)
    for d in SYSTEM_DIRS:
        for root, dirs, files in os.walk(d):
            for f in files:
                fullpath = os.path.join(root, f)
                if should_process(fullpath):
                    for arch in get_archs(fullpath):
                        process_file(fullpath, arch, options.verbose)

if __name__ == '__main__':
    main()
