#!/bin/bash
# Build the notch overlay: body/notch/build/notch
set -e
cd "$(dirname "$0")"
mkdir -p build
swiftc -O -parse-as-library Notch.swift -o build/notch
echo "built $(pwd)/build/notch"
