#!/bin/sh
set -e

virtualenv venv
venv/bin/python setup.py install
wget https://people.mozilla.org/~tmielczarek/`uname -s`/dump_syms
chmod +x dump_syms
