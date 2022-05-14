#!/usr/bin/env python
# Copyright (C) SURJ Bay Area
# Author Steven Sweeting
# Apache License 2.0 (see LICENSE or http://www.apache.org/licenses/LICENSE-2.0)

"""
Syncs exports of Action Network activists with EveryAction contacts

Uses these environment variables which can be set in an .env file in the
same folder. For example,

    EVERYACTION_APP_NAME="TSURJ.99.9999"
    EVERYACTION_API_KEY="d9999f51-8564-5341-145g-g615d99999af"
    ACTIONNETWORK_ACTIVIST_CSV="downloads/export-2022-03-22-csv_report_332566_1648001887.csv"


 * TODO: `Committee` - SURJ Bay Area used in Member Agreements

Ref: https://github.com/partiallyderived/everyaction-client

"""

import argparse
import csv
import logging
import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv
from everyaction import EAClient, EAHTTPException
from everyaction.objects import Person, ActivistCodeData, Code, ActivistCode


class SyncActvists:
    """Sync/import contacts with EveryAction.

    Subclass for contribution imoprt
    """
    DEFAULT_ENV = "env/test.env"
    DEFAULT_LOGFILE = "FILENAME.LOG"
    MAXINDEX = 1000000

    def __init__(self, env_filename):

        parser = self.create_arg_parser()

        self.args = parser.parse_args()

        # take environment settings from dotenv file
        load_dotenv(dotenv_path=self.args.env, verbose=True)

        if self.args.end_row is None:
            if self.args.count is not None:
                self.args.end_row = self.args.start_row + self.args.count - 1
            else:
                self.args.end_row = SyncActvists.MAXINDEX

        self.client = EAClient(mode=1)

        self.filename = self.args.inputFile or os.getenv(env_filename)

        self.logfile = None
        self.init_logfile()

        self.tags_mapping_filename = "tags_mapping.csv"

        self.tag_mapping = self.load_tag_mapping()

        self.address_field_mapping = {
            "can2_user_address": "addressLine1",
            "can2_user_city": "city",
            "can2_state_abbreviated": "stateOrProvince",
            "zip_code": "zipOrPostalCode",
            "country": "countryCode",
            "isPreferred": True,
        }

    def create_arg_parser(self):
        """Command line arguments and defaults
        """
        parser = argparse.ArgumentParser(
            description='Sync activists from a CSV export')

        parser.add_argument('--env', '-g', default=self.DEFAULT_ENV, metavar='dotenv_file',
                            help='Environment File with API Key.')
        parser.add_argument('--start', '-s', default=1, type=int, metavar='N',
                            dest='start_row',
                            help='First row to process (starting at 1)')
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--end', '-e', type=int, metavar='N', dest='end_row',
                           help='Last row to process')
        group.add_argument('--count', '-c', type=int, metavar='N',
                           help='Number of rows to process')
        parser.add_argument('--verbose', '-v',
                            action="store_true", help="Show data")
        parser.add_argument('--update', '-u', action="store_true",
                            help="Update existing contacts (name, address etc.)")
        parser.add_argument('--dryrun', '-d', action="store_true",
                            help="Indicate what would happen but don't send to EveryAction")
        parser.add_argument('--log', '-l', type=str, default=SyncActvists.DEFAULT_LOGFILE,
                            help="Defaults to name of input file with .log extension. "
                            "Use '-' for console.",
                            dest='logfilename')
        parser.add_argument('--resume', action="store_true",
                            help="Resume importing imports (as per existing file)")
        parser.add_argument('--overwrite', action="store_true",
                            help="Overwrite existing log file")

        parser.add_argument(
            'inputFile', help='Importable CSV file', default='def', nargs='?')

        return parser

    def log_actions(self, rowid, status, key, message=''):
        """Log item status

        OK - No further action
        DRYRUN - Reports what would happen
        """
        if self.args.dryrun and status == "OK":
            status = "DRYRUN"

        print(f"[{rowid:0>4}] {status} {key} {message}",
              file=self.logfile, flush=True)

    def sync_file(self):
        "Reads through file to sync user information with Every Action"

        with open(self.args.logfilename, 'a', encoding='utf8') as self.logfile:
            print(f"SyncTime: {datetime.now():%Y-%m-%d %H:%M:%S}",
                  file=self.logfile)

            with open(self.filename, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                if 'email' not in reader.fieldnames:
                    sys.exit(
                        f"Error: '{self.filename}': Expected column 'email'")
                #check_uuid = 'uuid' in reader.fieldnames
                check_email_subscription_status = 'can2_subscription_status' in reader.fieldnames
                check_phones = any((col in reader.fieldnames) for col in [
                                   'Phone', 'Phone Number', 'can2_phone'])
                check_tags = 'can2_user_tags' in reader.fieldnames

                # Remove fields not present
                found_fields = {}
                for old, new in self.address_field_mapping.items():
                    if old in reader.fieldnames:
                        found_fields[old] = new
                self.address_field_mapping = found_fields

                rowid = 0
                for user in reader:
                    user_actions = []
                    rowid += 1

                    if not self.args.start_row <= rowid <= self.args.end_row:
                        continue

                    if rowid in self.skip_item:
                        continue

                    try:
                        person = self.client.people.lookup(
                            email=user['email'], expand="Addresses,ExternalIds,Emails")
                    except AttributeError as ex:
                        person = None
                        self.log_actions(rowid, "ERROR", user['email'],
                                         f"AttributeError: {ex}")
                    if person is None:
                        user_actions.append("create")
                        person = self.update_or_create(user, user_actions)
                    elif self.args.update:
                        user_actions.append("update")
                        person = self.update_or_create(user, user_actions)
                    else:
                        # Person record exists but may not have correect email subscription
                        if person and check_email_subscription_status:
                            self.sync_email_subscription(
                                person, user, user_actions)

                        # Person record exists but may not have email
                        if person and check_phones:
                            self.sync_phones(person, user, user_actions)

                    if person and check_tags:
                        self.sync_tags(person, user, user_actions)

                    self.log_actions(rowid, "OK", user['email'], user_actions)

    def sync_phones(self, person: Person, user: dict, user_actions: list):
        """Sync phones for existing user
        """
        phones = self.get_user_phones(user, user_actions)
        if len(phones) > 0:
            if not self.args.dryrun:
                try:
                    self.client.people.update(person.van_id,
                                              phones=phones)
                except EAHTTPException as ex:
                    user_actions.append(str(ex))
                    print(
                        f"error: {user['email']}: {phones} {ex}", file=sys.stderr)

    def sync_email_subscription(self, person: Person, user: dict, user_actions: list):
        """Check email subscription status - update if needed
        """
        preferred_contact_email = None
        for contact_email in person.emails:
            if contact_email.isPreferred:
                preferred_contact_email = contact_email
                # If subscriptionStatus is "S", "U" or "" for not subscribed
                person_subscription_status = contact_email.subscriptionStatus or "None"
                break
        if user['can2_subscription_status'] == 'unsubscribed':
            if person_subscription_status == 'None':
                user_actions.append(
                    f"Unsubscribed(was {person_subscription_status}]")
                preferred_contact_email.isSubscribed = False
                if not self.args.dryrun:
                    self.client.people.update(
                        person.van_id,
                        emails=[preferred_contact_email])
        else:
            if person_subscription_status == 'None':
                user_actions.append(
                    f"Subscribed[was {person_subscription_status}]")
                preferred_contact_email.isSubscribed = True
                if not self.args.dryrun:
                    self.client.people.update(
                        person.van_id,
                        emails=[preferred_contact_email])

    def update_or_create(self, user: dict, user_actions: list) -> Person | None:
        """Create or update Every Action person based on ActionNetwork columns

        Attempts to find the given match candidate. If a person is found,
        it is updated with the information provided. If a person is not
        found, a new person record is created.
        """

        fields = {
            "emails": [{
                "email": user['email'],
                "type": "P",
                "isPreferred": True,
                "isSubscribed": user.get('can2_subscription_status', '') == 'unsubscribed',
            }],
            "firstName": user['first_name'],
            "lastName": user['last_name']
        }

        #######################################
        # Add address if address fields found
        address = {}
        for old, new in self.address_field_mapping.items():
            if value := user.get(old, None):
                address[new] = value
        if len(address) > 0:
            fields["addresses"] = [address]

        phones = self.get_user_phones(user, user_actions)
        if len(phones) > 0:
            fields["phones"] = phones

        if not self.args.dryrun:
            person = self.client.people.find_or_create(
                **fields)
            return person

        return None

    def get_user_phones(self, user: dict, user_actions: list) -> list:
        """Extract phones from import record

         * `can2_phone` - mobile/cell phone (newer field added by Action Network)
         * `can2_sms_status` - SMS subscription status
         * `Phone` - contact phone (custom field)
         * `Phone Number` - contact phone (custom field)
        """
        #######################################
        phones = []
        phone_digits = {}
        if user_mobile := user.get('can2_phone', ''):
            phone = {
                "phoneNumber": user_mobile,
                "phoneType": "C"
            }
            if user.get('can2_sms_status', 'unknown') == 'subscribed':
                user_actions.append("mobile subscribed")
                phone["phoneOptInStatus"] = 'I'
            else:
                user_actions.append("mobile")

            phone_digits[self.digits(user_mobile)] = True
            phones.append(phone)

        # 'Phone' - other contact phone
        # 'Phone Number' - other contact phone
        for field in ('Phone', 'Phone Number'):
            if user_phone := user.get(field, ''):
                digits = self.digits(user_phone)
                if digits not in phone_digits:
                    phone_digits[digits] = True
                    phone = {
                        "phoneNumber": user_phone
                    }
                    phones.append(phone)
                    user_actions.append(field)

        return phones

    def digits(self, phone):
        """Returns digits only - used to check for duplicates"""
        return re.sub(r'\D', '', phone.lstrip('+1'))

    def sync_tags(self, person: Person, user: dict, user_actions: list):
        """Create Activist Codes based on ActionNetwork tags

         * `user['can2_user_tags']` - e.g. "SURJ_Action_Hour, SURU2021, ShowUpRiseUp 2020"

        Ignores existing Every Action Activist Codes, Source Codes and Tags

        Calls `apply_activist_code` which uses the API
        https://docs.everyaction.com/reference/people-personidtype-personid-canvassresponses
        with canvassContext.omitActivistCodeContactHistory set to true
        """
        code_by_name = {}
        for user_tag in user['can2_user_tags'].split(", "):
            if user_tag:
                if user_code_data := self.tag_mapping.get(user_tag):
                    if isinstance(user_code_data,  ActivistCode):
                        user_code_id = user_code_data.activistCodeId
                    elif isinstance(user_code_data,  Code):
                        user_code_id = user_code_data.codeId
                    else:
                        user_code_id = None
                        print("Internal Mapping Error:" + str(user_code_data))

                    code_by_name[user_code_id] = user_code_data
                    if self.args.verbose:
                        print(
                            f"Mapped tag {user_tag} to {user_code_id} ({user_code_data.name})")

        if len(code_by_name) > 0:
            # existing Activist Codes
            for code in self.client.people.activist_codes(person.van_id):
                try:
                    code_by_name.pop(code.activistCodeId)
                except KeyError:
                    pass
            # existing Tags - don't know what function to call
            # for code in self.client.people.codes(person.van_id):
            #    try:
            #        code_by_name.pop(code.activistCodeId)
            #    except KeyError:
            #        pass
            for new_code_id, new_code_data in code_by_name.items():
                if isinstance(new_code_data,  ActivistCode):
                    user_actions.append(new_code_data.name)
                    if not self.args.dryrun:
                        self.client.people.apply_activist_code(
                            new_code_id, vanId=person.van_id)
                # Error in client lib
                # elif isinstance(new_code_data,  Code):
                #    self.client.people.add_code(van_id=person.van_id, codeId=new_code_id)

    def load_tag_mapping(self):
        """Look up actvist codes
        """
        tags_mapped = {}
        code_by_name = {}

        for code in self.client.activist_codes.list():
            if self.args.verbose:
                print(f"load activist code: {code.name} {code}")
            code_by_name[code.name] = code

        for code in self.client.codes.list():
            if code.codeType == 'Tag':
                if self.args.verbose:
                    print(f"load tag: {code.codeType} {code}'")
                if code.name in code_by_name:
                    print(
                        f"Warning: Ignoring duplicate {code.codeType} '{code.name}'", file=sys.stderr)
                else:
                    code_by_name[code.name] = code

        with open(self.tags_mapping_filename, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for column in ('old', 'new'):
                if column not in reader.fieldnames:
                    sys.exit(
                        f"Error: '{self.tags_mapping_filename}': Expected column '{column}'")

            rowid = 0
            for tag_map in reader:
                rowid += 1
                if new := tag_map['new']:
                    for map_to in new.split(','):
                        map_to = map_to.strip()
                        if map_to in code_by_name:
                            tags_mapped[tag_map['old']] = code_by_name[map_to]
                        else:
                            print(f"Warning: No Activist Code or Tag called '{map_to}'",
                                  file=sys.stderr)

        return tags_mapped

    def init_logfile(self):
        """Creates log file with one item per item processed

            [999] VERB KEY MESSAGE

        Log file can be reread and will skip OK and SKIP entries
        """
        header_row = f"SyncFile: '{self.filename}'"

        self.skip_item = {}
        if not self.args.logfilename or self.args.logfilename == '-':
            self.args.logfilename = "/dev/stdout"
            if self.args.resume:
                print("Option --resume ignored for stdout", file=sys.stderr)
        else:
            if self.args.logfilename == 'og':
                raise Exception("File: og: Do you mean --log")

            if self.args.logfilename == SyncActvists.DEFAULT_LOGFILE:
                self.args.logfilename = self.filename + ".log"

            if not os.path.isfile(self.args.logfilename) or self.args.overwrite:
                print("Log file:", self.args.logfilename, file=sys.stderr)
                if self.args.resume:
                    print("Option --resume ignored. File not found",
                          file=sys.stderr)
                with open(self.args.logfilename, 'w', encoding='utf8') as logfile:
                    print(header_row, file=logfile)
            else:
                if not self.args.resume:
                    raise Exception(
                        self.args.logfilename +
                        ": File exists. Use --resume, --overwrite or remove file.")

                print("Logile (resume):", self.args.logfilename, file=sys.stderr)
                # Remember items to skip
                with open(self.args.logfilename, 'r', encoding='utf8') as existing_logfile:
                    # SyncFile: 'downloads/export-2022-03-22-csv_report_332566_1648001887.csv'
                    log_line = existing_logfile.readline()
                    if log_line != header_row + "\n":
                        raise Warning(f"Logfile {self.args.logfilename} "
                                      f"for '{self.filename}' found '{log_line}")
                    # [999] VERB ABC DEF -> ('[999]', 'VERB', 'ABC DEF")
                    while True:
                        log_line = existing_logfile.readline()
                        if not log_line:
                            break
                        log_line_tokens = log_line.split(None, 2)
                        if len(log_line_tokens) >= 2:
                            verb = log_line_tokens[1]
                            if verb in ('OK', 'SKIP'):
                                itemid = int(log_line_tokens[0][1:-1])
                                self.skip_item[itemid] = verb


def main():
    """Run from command line with logging"""
    if os.getcwd().endswith("/tests"):
        os.chdir("..")

    sync = SyncActvists('ACTIONNETWORK_ACTIVIST_CSV')

    sync.sync_file()

    logging.basicConfig(level=logging.INFO)


if __name__ == '__main__':
    main()
