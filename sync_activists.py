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

Looks for these special columns. Only `email` is required:
 * `email` (Required)
 * `uuid` - If present warns if it does not match ExternalId of type ActionNetworkId if one is found
 * `can2_subscription_status` - If present will update subscription status in EveryAction
 * TODO: `can2_user_tags` - Tag names separated by ", "
 * TODO: `first_name`
 * TODO: `last_name`
 * TODO: `zip_code`
 * TODO: `can2_phone`
 * TODO: `Committee`

Ref: https://github.com/partiallyderived/everyaction-client


"""

import argparse
import csv
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from everyaction import EAClient


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

    def create_arg_parser(self):
        """Command line arguments override env variables

        CONFIG_ENV = self.args.env
        CONFIG_IMPORTFILE = self.args.inputFile
        CONFIG_VERBOSE = args.verbose
        CONFIG_FORCE_SUBSCRIBED = args.force
        CONFIG_START_INDEX = args.start
        CONFIG_INCLUDE_UNSUBSCRIBED = args.unsubscribed
        CONFIG_DRY_RUN = args.dryrun
        CONFIG_RESUME = args.resume
        CONFIG_LOGFILE = args.logfile

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
        # parser.add_argument('--unsubscribed', '-u', action="store_true",
        #                    help="Include unsubscribed users")
        # parser.add_argument('--force', '-f', action="store_true",
        #                    help="Force subscribe of existing users")
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
        "Reads through file"

        with open(self.args.logfilename, 'a', encoding='utf8') as self.logfile:
            print(
                f"SyncTime: {datetime.now():%Y-%m-%d %H:%M:%S}", file=self.logfile)

            with open(self.filename, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                if 'email' not in reader.fieldnames:
                    sys.exit(
                        f"Error: '{self.filename}': Expected column 'email'")
                check_uuid = 'uuid' in reader.fieldnames
                check_subscription_status = 'can2_subscription_status' in reader.fieldnames
                check_tags = 'can2_user_tags' in reader.fieldnames

                rowid = 0
                for row in reader:
                    row_actions = []
                    rowid += 1

                    if not self.args.start_row <= rowid <= self.args.end_row:
                        continue

                    if rowid in self.skip_item:
                        continue

                    row_email = row['email']
                    try:
                        contact = self.client.people.lookup(
                            email=row_email, expand="Addresses,ExternalIds,Emails")
                    except AttributeError as ex:
                        self.log_actions(rowid, "ERROR", row_email,
                                         f"AttributeError: {ex}")
                        continue

                    if contact is None:
                        self.log_actions(rowid, "NOT_FOUND",
                                         row_email, "Record not found")
                        continue

                    if check_uuid:
                        for identifier in contact.identifiers:
                            if identifier.type == 'ActionNetworkID' and \
                                    identifier.externalId != row['uuid']:
                                self.log_actions(rowid, "MISMATCH_ID", row_email,
                                                 f"Found ActionNetworkId {identifier.externalId}: "
                                                 f"Does not match data {row['uuid']}")
                                continue

                    if check_subscription_status:
                        preferred_contact_email = None
                        for contact_email in contact.emails:
                            if contact_email.isPreferred:
                                preferred_contact_email = contact_email
                                # If subscriptionStatus is None then same as "S"
                                contact_subscription_status = contact_email.subscriptionStatus or "S"
                                break
                        if row['can2_subscription_status'] == 'unsubscribed' and \
                                contact_subscription_status != 'U':
                            row_actions.append("Unsubscribed")
                            preferred_contact_email.isSubscribed = False
                            if not self.args.dryrun:
                                self.client.people.update(
                                    contact.van_id,
                                    emails=[preferred_contact_email])

                    self.log_actions(rowid, "OK", row_email, row_actions)

    def get_activist_codes(self):
        """Look up actvist codes
        """
        return self.client.activist_codes.list()

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
                        f"{self.args.logfilename}: File exists. Use --resume, --overwrite or remove file.")

                print("Logile (resume):", self.args.logfilename, file=sys.stderr)
                # Remember items to skip
                with open(self.args.logfilename, 'r', encoding='utf8') as existing_logfile:
                    # SyncFile: 'downloads/export-2022-03-22-csv_report_332566_1648001887.csv'
                    log_line = existing_logfile.readline()
                    if log_line != header_row + "\n":
                        raise Warning(f"Logfile {self.args.logfilename} "
                                      "for '{self.filename}' found '{log_line}")
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
