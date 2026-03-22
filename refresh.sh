#!/bin/bash

docker build -t vpn_bot .

docker compose up -d --build --force-recreate
