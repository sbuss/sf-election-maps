#!/bin/bash

mkdir -p precincts
cd precincts && \
    wget https://sfelections.sfgov.org/sites/default/files/Documents/Maps/2017lines.zip && \
    unzip 2017lines.zip

mkdir -p results/2018-06
cd results/2018-06 && \
    wget https://sfelections.org/results/20180605/data/20180627/20180627_masterlookup.txt && \
    wget https://sfelections.org/results/20180605/data/20180627/20180627_ballotimage.txt && \
    gzip 20180627_ballotimage.txt
