#!/usr/bin/env python
"""Connects to EveryAction
"""

import argparse
import sys

from dotenv import load_dotenv
from everyaction import EAClient

load_dotenv()  # take environment variables from .env.

def preferred(data):
    if len(data) == 0:
        return None

    for datum in data:
        if datum.isPreferred:
            return datum

    return None

def show_csv(data, args):
    msg = f'{data.firstName} {data.lastName},'
    if data.pronouns:
        msg += f'{data.pronouns.pronounName},'
    else:
        msg += ','

    email = preferred(data.emails)
    phone = preferred(data.phones)
    address = preferred(data.addresses)
    msg += f'{email.email},' if email else ','
    msg += f'{phone.phoneNumber},' if phone else ','
    msg += f'{address.addressLine1} {address.addressLine2},{address.city},{address.stateOrProvince}' if address else ',,'
    print(msg)

def show_text(data, client, args):
    print(f'{data.firstName} {data.lastName} ({data.pronouns.pronounName if data.pronouns else "??"})')
    email = preferred(data.emails)
    if email:
        print(f'Email: {email.email}')

    address = preferred(data.addresses)
    if address:
        print(f'Address: {address.addressLine1} {address.addressLine2}, {address.city} {address.stateOrProvince}')

    phone = preferred(data.phones)
    if phone:
        print(f'Phone: {phone.phoneNumber}')

    if args['show_codes']:
        print('Activist Codes')
        for code in client.people.activist_codes(data.vanId):
            print(f'  {code.activistCodeName}')

def entrypoint():
    parser = argparse.ArgumentParser(usage='show.py <email>',
                                     description='EA People Lookup')
    parser.add_argument('email',
                        help='Email to look People record for, or "-" to read from stdin')
    parser.add_argument('--codes',
                        dest='show_codes',
                        help='Show Activist Codes',
                        default=False,
                        action='store_true')
    parser.add_argument('--output',
                        help='Different output formats (text, csv)',
                        default='text')
    args = vars(parser.parse_args())

    if 'email' not in args:
        raise Exception('must specify email')

    emails = []
    if args['email'] == '-':
        for line in sys.stdin:
            emails.append(line.rstrip())

    else:
        emails = [args['email']]

    client = EAClient(mode=1)

    if args['output'] == 'csv':
        print('name, pronouns, email, phone, address, city, state')

    for email in emails:
        data = client.people.lookup(email=email, expand="Emails, Addresses, Phones")

        if not data:
            if args['output'] == 'text':
                print(f'Nothing found for {email}')
            elif args['output'] == 'csv':
                print(f',,{email},,,,')
            continue

        if args['output'] == 'text':
            show_text(data, client, args)
        elif args['output'] == 'csv':
            if args['show_codes']:
                raise Exception('cannot show codes in csv')

            show_csv(data, args)

if __name__ == '__main__':
    entrypoint()
