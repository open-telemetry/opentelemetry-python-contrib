Installation
============

Option 1: pip + requirements.txt
---------------------------------
::

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Option 2: Poetry
----------------
::

    poetry install

Running Tests
=============

After installing dependencies, simply run:

::

    pytest

This will discover and run `tests/test_sdk.py`.
