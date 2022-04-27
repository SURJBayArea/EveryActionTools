#!/usr/bin/env python
"""Connects to EveryAction
"""

from dotenv import load_dotenv
from everyaction import EAClient

load_dotenv()  # take environment variables from .env.

client = EAClient(mode=1)

data = client.people.find(email='steven@surjbayarea.org')

print(data)

activist_codes = client.activist_codes.list()

print(activist_codes)