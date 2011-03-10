#!/usr/bin/env python

from __future__ import with_statement
import sys, os, time, tempfile, zipfile, gzip, optparse, subprocess
# import options
from config import local_symbol_path, symbol_user, symbol_host, symbol_path, symbol_privkey
if not local_symbol_path.endswith("/"):
    local_symbol_path += "/"

def main():
    # Handle command-line options
    parser = optparse.OptionParser()
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true")
    options, args = parser.parse_args()
    verbose = options.verbose

    # Load last run time
    current_time = time.time()
    last_run = None
    last_run_file = os.path.join(os.path.dirname(__file__),
                                 "last-run")
    if os.path.exists(last_run_file):
        with open(last_run_file, 'r') as f:
            last_run = float(f.read())
            if verbose:
                print "Last run time: %s" % time.ctime(last_run)

    # Create a temporary zipfile
    tf, zf = None, None
    try:
        tf = tempfile.NamedTemporaryFile()
        zf = zipfile.ZipFile(tf, 'w', zipfile.ZIP_DEFLATED)

        # Find all symbol files created since the last run
        file_index = []
        for root, dirs, files in os.walk(local_symbol_path):
            for f in files:
                fullpath = os.path.join(root, f)
                if last_run is None or os.stat(fullpath).st_mtime > last_run:
                    # Strip down to relative path without .gz
                    zipname = fullpath[len(local_symbol_path):-3]
                    if verbose:
                        print "Adding %s" % zipname
                    info = zipfile.ZipInfo(zipname)
                    info.external_attr = 0664 << 16L
                    zf.writestr(info, gzip.open(fullpath, 'rb').read())
                    file_index.append(zipname)
        # See if any files were added
        if file_index:
            # Add an index file
            buildid = time.strftime("%Y%m%d%H%M%S", time.localtime(current_time))
            index_filename = "osxsyms-1.0-Darwin-%s-symbols.txt" % buildid
            if verbose:
                print "Adding %s" % index_filename
            info = zipfile.ZipInfo(index_filename)
            info.external_attr = 0664 << 16L
            zf.writestr(info, "\n".join(file_index))
            zf.close()

            # Upload to symbol server and unzip there
            if verbose:
                print "Uploading to %s@%s" % (symbol_user, symbol_host)
            stdout = sys.stdout if verbose else open('/dev/null', 'w')
            subprocess.check_call(["scp", "-i", symbol_privkey,
                                   tf.name,
                                   "%s@%s:/tmp" % (symbol_user, symbol_host)],
                                  stdout = stdout)
            if verbose:
                print "Unpacking to %s" % symbol_path
            bn = os.path.basename(tf.name)
            subprocess.check_call(["ssh", "-i", symbol_privkey,
                                   "-l", symbol_user, symbol_host,
                                   "cd %s; umask 002; unzip -n '/tmp/%s'; /usr/local/bin/post-symbol-upload.py '%s'; rm -v '/tmp/%s'" % (symbol_path, bn, index_filename, bn)],
                                  stdout = stdout)
    finally:
        if zf:
            zf.close()
        if tf and not tf.closed:
            tf.close()
    
    if verbose:
        print "Finished"
    # Save time of current run as last run
    with open(last_run_file, 'w') as f:
        f.write(str(current_time))

if __name__ == '__main__':
    main()
