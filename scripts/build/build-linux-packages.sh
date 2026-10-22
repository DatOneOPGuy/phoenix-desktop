#!/usr/bin/env bash

# Description: Build the Linux app once in a Debian 11 container and package
#   it as both .deb and .rpm. Building on an old glibc (2.31) lets the
#   PyInstaller bundle run on Ubuntu 22.04+, Debian 11+, Fedora and RHEL 9.
#   A build made on the host (NixOS) would only run on NixOS.
# Usage: ./scripts/build/build-linux-packages.sh
# Output: dist/linux/phoenix_<version>_amd64.deb and phoenix-<version>-<rel>.x86_64.rpm
# Needs: docker. Builds from the committed tree (git archive HEAD).

set -euo pipefail

cd "$(dirname "$0")/../.."

IMAGE="python:3.13-bullseye"
OUT="dist/linux"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/phoenix-linux.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

VERSION=$(sed -nE "s/^VERSION\s*=\s*['\"]([^'\"]+)['\"].*/\1/p" packaging/Resistine.spec)
[ -n "$VERSION" ] || {
	echo "No VERSION in packaging/Resistine.spec" >&2
	exit 1
}
# RPM versions can't contain '-': 2026.07.20-rc -> 2026.07.20~rc (sorts before 2026.07.20).
RPM_VERSION="${VERSION//-/\~}"
echo "Building Phoenix ${VERSION} (rpm ${RPM_VERSION}) in ${IMAGE}"

git archive HEAD | tar -x -C "$WORK"
mkdir -p "$OUT"

docker run --rm \
	-v "$WORK:/src" \
	-v "$PWD/$OUT:/out" \
	-e VERSION="$VERSION" -e RPM_VERSION="$RPM_VERSION" \
	-e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
	-w /src "$IMAGE" bash -euo pipefail -c '
apt-get update -qq
apt-get install -y -qq --no-install-recommends rpm binutils >/dev/null

python -m venv /venv
/venv/bin/pip install -q --upgrade pip
/venv/bin/pip install -q -r scripts/requirements/requirements-linux.txt
/venv/bin/pyinstaller --clean -y packaging/Resistine.spec
[ -x dist/Phoenix/Phoenix ]

# One staged root for both formats.
root=/stage/root
mkdir -p $root/opt/phoenix $root/usr/bin $root/usr/share/applications $root/usr/share/pixmaps
cp -a dist/Phoenix/. $root/opt/phoenix/
printf "#!/bin/sh\nexec /opt/phoenix/Phoenix \"\$@\"\n" >$root/usr/bin/phoenix
chmod 755 $root/usr/bin/phoenix
cp packaging/linux/phoenix.desktop $root/usr/share/applications/
cp resources/icons/app_icon.png $root/usr/share/pixmaps/phoenix.png

# .deb
deb=/stage/deb
cp -a $root $deb
mkdir -p $deb/DEBIAN
sed "s/\${VERSION}/$VERSION/g" packaging/linux/control.template >$deb/DEBIAN/control
install -m 755 packaging/linux/postinst packaging/linux/postrm $deb/DEBIAN/
dpkg-deb --root-owner-group --build $deb /out/phoenix_${VERSION}_amd64.deb

# .rpm
sed -e "s/@VERSION@/$RPM_VERSION/" -e "s/@RELEASE@/1/" packaging/linux/phoenix.spec.in >/stage/phoenix.spec
rpmbuild -bb --quiet --define "_topdir /stage/rpm" --define "_phoenix_root $root" /stage/phoenix.spec
cp /stage/rpm/RPMS/x86_64/*.rpm /out/

chown "$HOST_UID:$HOST_GID" /out/*
'

ls -lh "$OUT"
