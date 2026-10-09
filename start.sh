#!/usr/bin/env sh
# Starts the app: creates the virtual environment the first time, installs requirements, opens the UI.
set -e
cd "$(dirname "$0")"

if [ ! -x venv/bin/python ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Checking requirements..."
venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

exec venv/bin/python -m streamlit run ui.py
