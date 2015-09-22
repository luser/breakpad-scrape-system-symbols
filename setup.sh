#!/bin/sh
set -e

virtualenv venv
venv/bin/pip install -r requirements.txt
wget https://people.mozilla.org/~tmielczarek/`uname -s`/dump_syms
chmod +x dump_syms
