#!/bin/bash

mkdir -p precincts
cd precincts && \
    wget https://sfelections.sfgov.org/sites/default/files/Documents/Maps/2017lines.zip && \
    unzip 2017lines.zip
