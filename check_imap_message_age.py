#!/usr/bin/env python3
'''
Connect to an IMAP server, check the age of the oldest message
Return warning/critical if older than configured value

Can be used to check if a system is polling for email. If it 
stops polling, email piles up on the IMAP server

Author: Anders Lowinger, anders@abundo.se
'''

import sys
import socket
import datetime
import imaplib
import email

import monitoring_util as m_util


class Check_Imap_Message_Age(m_util.Plugin_Check):

    def __init__(self):
        super().__init__(description="Check age on oldest message in a IMAP folder")
        
        self.parser.add_argument("-H", "--host",
                                 required=True,
                                 help="IMAP server")
        self.parser.add_argument("-p", "--port", 
                                 type=int,
                                 help="Port on IMAP server (default port 143)")
        self.parser.add_argument("-S", "--ssl",
                                 action="store_true", 
                                 help="Use IMAPS (default port 993)")
        self.parser.add_argument("-U", "--username",
                                 help="IMAP account username ")
        self.parser.add_argument("-P", "--password",
                                 help="IMAP account password")
        self.parser.add_argument("--credentials",
                                 help=".INI File with username and password")
        self.parser.add_argument("-f", "--folder",
                                 default="INBOX",
                                 help="IMAP folder to check, default 'INBOX'")
        
        self.parser.add_argument("-w", "--warning",
                                 type=int, 
                                 required=True,
                                 help="Return WARNING if oldest message is older than this many seconds")
        self.parser.add_argument("-c", "--critical", 
                                 type=int, 
                                 required=True,
                                 help="Return CRITICAL if oldest message is older than this many seconds")

        self.parser.add_argument("-t", "--timeout", 
                                 type=int,
                                 default=10,
                                 help="Timeout waiting for a response")
    
        self.parse()

        # handle defaults
        p = 143
        if self.args.ssl and self.args.port == None:
            p = 993
        if self.args.port == None:
            self.args.port = p

        if self.args.credentials:
            import configparser
            with open(self.args.credentials) as f:
                credential_contents = "[dummy_section]\n" + f.read()
            config = configparser.RawConfigParser()
            config.read_string(credential_contents)
            self.args.username = config.get("dummy_section", "username")
            self.args.password = config.get("dummy_section", "password")
       
        
    def check(self):
        """
        Connect to the imap server, get the datetime on the oldest message
        """
        
        imap = None
        try:
            if self.args.ssl:
                if self.args.verbose: print("Connecting to %s:%s using IMAPS" % (self.args.host, self.args.port))
                imap = imaplib.IMAP4_SSL(self.args.host)
            else:
                if self.args.verbose: print("Connecting to %s:%s using IMAP" % (self.args.host, self.args.port))
                imap = imaplib.IMAP4(self.args.host)
        except socket.error:
            m_util.response.exit(m_util.UNKNOWN, "Could not connect to IMAP server %s:%s" % (self.args.host, self.args.port))
    
        if self.args.verbose: print("Login with username '%s'" % (self.args.username))
        try:
            password = self.args.password
            if sys.version_info[0:2] == (3,1):
                password = password.encode() # in python 3.1, password needs to be bytes()
            imap.login(self.args.username, password)
        except imaplib.IMAP4.error:
            m_util.response.exit(m_util.UNKNOWN, "Authentication failure with username '%s'" % self.args.username)
    
        if self.args.verbose: print("IMAP select(%s)" % self.args.folder)
        imap.select(self.args.folder, readonly=True)
        
        if self.args.verbose: print("IMAP search(%s)" % self.args.folder)
        result, data = imap.uid('search', None, 'ALL')
        if result != "OK":
            m_util.response.exit(m_util.UNKNOWN, "Could not search for messages")
        uids = data[0].split()
        
        msg = "IMAP Account '%s' folder '%s'" % (self.args.username, self.args.folder)
        m_util.response.perfdata = "'Messages'=0;;"
         
        if not uids:
            m_util.response.exit(m_util.OK, "%s: No messages found" % msg)
        
        msg_count = len(uids)       # Get the total number of messages
        oldest_message_dt = None    # date of the oldest message

        i = 0
        for uid in uids:
            i += 1
         
            if self.args.verbose:
                print('> Reading message %d of %d (%d%%)' % (i, msg_count, (i / msg_count) * 100))
    
            result, data = imap.uid('fetch', uid, '(BODY[HEADER.FIELDS (FROM DATE SUBJECT RECEIVED)])')
            if result == "OK":
                email_message = email.message_from_string(data[0][1].decode())    # raw email text including headers
    
                # We extract the received date, which is set by the MTA
                # The 'Date' header is set by senders email, and we can't trust this to be correct
                #
                # On exchange 2007 the received header looks like this (multiline):
                #
                # Received from Exchange2k7.office.nic.se ([fe80::5cf9:6773:71d5:d006]) by
                # EXCH2K7HUB-BRG.office.nic.se ([fe80::5cfa:6854:d17d:fe06%10]) with mapi; Wed,
                # 17 Dec 2014 11:21:34 +0100
                received = email_message["Received"]
                p = received.rfind(";")
                if p > 0:
                    received = received[p+1:].replace("\n", "").replace("\r", ".").strip()
                    received = received.replace(".", "")      # exchange adds a dot after the month name, remove it
                else:
                    #  Wed, 24 Sep 2014 11:05:07 +0200
                    received = email_message['Date']   # fall back to senders date
                
                # Extract and remove offset at end so we can convert to UTC
                p = received.rfind(" ")
                offset = received[p+1:]
                received = received[:p]
                try:
                    off = datetime.timedelta(hours=int(offset[1:3]),minutes=int(offset[3:5]))
                except ValueError:
                    off = datetime.timedelta()  # Error, fall back to no offset
    
                try:
                    timestamp = datetime.datetime.strptime(received, "%a, %d %b %Y %H:%M:%S")
                except ValueError:
                    # we don't understand the timestamp format, handle as critical
                    oldest_message_dt = datetime.datetime.now().replace(year=1990)
                    continue
                if offset[0] == "+":
                    timestamp = timestamp - off
                else:
                    timestamp = timestamp + off
    
                if self.args.verbose:
                    print('From.................: %s' % email_message['From'])
                    print('  Date...............: %s' % email_message['Date'])
                    print('  Received (UTC).....: %s' % timestamp)
                    print('  Subject............: %s' % email_message['Subject'])
                    print()
                    
                if oldest_message_dt is None:
                    oldest_message_dt = timestamp
                    continue
                if timestamp < oldest_message_dt:
                    oldest_message_dt = timestamp        
        
        if self.args.verbose: print("IMAP close()")
        imap.close()
        
        if self.args.verbose: print("IMAP logout()")
        imap.logout()

        m_util.response.perfdata = "'Messages'=%d;;" % msg_count
        
        msg_count, oldest_dt = m_util.response
        if msg_count < 1:
            m_util.response.exit(m_util.OK, "%s : No messages" % msg)
    
        age = datetime.datetime.utcnow() - oldest_dt
        age = age.seconds + (age.days * 24 * 3600)
    
        msg = "%s : Oldest message is %d seconds" % (msg, age)
        if age > self.args.critical:
            m_util.response.exit(m_util.CRITICAL, 
                    "%s > Critical limit %d seconds" %
                    (msg, self.args.critical, msg_count))
        if age > self.args.warning:
            m_util.response.exit(m_util.WARNING, 
                    "%s > Warning limit %d seconds" %
                    (msg, self.args.warning, msg_count))
                
        m_util.response.exit(m_util.OK, msg)
         

if __name__ == "__main__":
    m_util.main(Check_Imap_Message_Age)
