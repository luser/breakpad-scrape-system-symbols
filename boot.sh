#!/bin/bash
# Run this script with `curl -L https://github.com/luser/breakpad-scrape-system-symbols/raw/master/boot.sh | bash` to scrape symbols from an Ubuntu install.

set -v -e

#XXX: having the version hardcoded here sucks
wget https://archive.mozilla.org/pub/firefox/nightly/latest-mozilla-central/firefox-50.0a1.en-US.linux-x86_64.tar.bz2
tar xjf firefox-50.0a1.en-US.linux-x86_64.tar.bz2

xvfb-run ./firefox/firefox &
sleep 5

pid=$(pidof firefox)
if test -z $pid; then
  echo "Firefox not running"
  exit 1
fi
dir=`pwd`/firefox

# Get necessary scripts and tools.
cd
git clone https://github.com/luser/breakpad-scrape-system-symbols.git
cd breakpad-scrape-system-symbols
./setup.sh
set +v
. ./venv/bin/activate
set -v

# Get the list of libraries loaded in the Firefox process.
grep r-x /proc/$pid/maps | awk '{ print $6 }' | sort -u | grep ^/ | grep -v "^${dir}" > /tmp/libs.list

kill $pid

find-packages() {
    while read i; do
        if ! dpkg -S "$i" 2>/dev/null; then
            [ -L "$i" ] && dpkg -S `readlink "$i"`;
        fi
    done
}

find-debug() {
    while read i; do
        echo $i `dpkg-query -s $i | grep Version | cut -f2 -d' '` >> /tmp/packages.list
        for ext in dbgsym dbg; do
            i=$(echo "$i"|cut -f 1 -d:) #remove the architecture suffix
            apt-cache search "^$i-$ext\$"
        done | head -1 | sed -e 's/ - .*$//'
    done
}

# Add ddeb sources.
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 5FDFF622
tee -a /etc/apt/sources.list.d/ddebs.list <<EOF
deb http://ddebs.ubuntu.com $(lsb_release -cs) main restricted universe multiverse
deb http://ddebs.ubuntu.com $(lsb_release -cs)-updates main restricted universe multiverse
deb http://ddebs.ubuntu.com $(lsb_release -cs)-proposed main restricted universe multiverse
EOF
apt-get update

# Find the debug packages matching these libraries.
find-packages < /tmp/libs.list | sed -e 's/^\(.*\): .*$/\1/' | sort -u | find-debug > /tmp/debug-packages.list
xargs apt-get install -y < /tmp/debug-packages.list

# Now scrape the symbols.
xargs gathersymbols -v ./dump_syms < /tmp/libs.list
