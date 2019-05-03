#!/usr/bin/env python3
'''
Fetch a zone using AXFR. 
Go through all RRSIG and verify that none of them are too old or expired

Author: Anders Lowinger, anders@abundo.se
'''

import os
import sys
import time
import datetime
import subprocess

import monitoring_util as m_util


RRSIG_DFORMAT = "%Y%m%d%H%M%S"  # date+time format on RRSIG Resource Record
PACING_SLEEP  = 0.000005        # seconds to sleep between each RRSIG check


class Check_Rrsig_Expiry(m_util.Plugin_Check):
    """
    Format on RRSIG
      example.com. IN RRSIG DS 5 2 3600 20150124203956 20150112001201 44410 se. T3cYDl3hf87bhKq5gxZGMsCf/ox7WH6mzKtPa9zlXDsQZNcI45ezdKqu YF4rRIVCtlimWA9wjuTaRnqDYUqjLBGSDRCK78PxzeS/CzsrNdlqerRJ iOF3W8JVLu2RdJWrHAb4X0XH0HrKsgYlvnbZKJHCFEW5atqRxHQH8uSX Xkg=
    """
    def __init__(self):
        super().__init__(description="Verify age on RRSIG records in a zone")
        self.parser.add_argument("-H", "--host",
                                 help="Host to transfer zone from")
        self.parser.add_argument("--zone",
                                 help="zone to transfer")
        self.parser.add_argument("--tsig", 
                                 help="path to file with tsig")
        
        self.parser.add_argument("-c", "--critical",
                                 type=float,
                                 help="Minimim age in days on RRSIG before critical", default=6.0)
        self.parser.add_argument("-w", "--warning",
                                 type=float,
                                 help="Minimim age in days on RRSIG before warning", default=8.0)
    
        self.parser.add_argument("--zonefile",   
                                 help="read zone from file instead of AXFR")

        self.parse()
    
        # validate parameters
        if self.args.warning <= self.args.critical:
            m_util.response.exit(m_util.UNKNOWN, "Makes no sense with warning %s days <= critical %s days" %
                             (self.args.warning, self.args.critical))
    
        if self.args.zonefile is None:
            if self.args.host is None:
                m_util.response.exit(m_util.UNKNOWN, "No host specified")
            if self.args.zone is None:
                m_util.response.exit(m_util.UNKNOWN, "No zone specified")
            if self.args.tsig != None:
                if not os.path.exists(self.args.tsig):
                    m_util.response.exit(m_util.UNKNOWN, "TSIG file %s does not exist" % self.args.tsig)
    
        if self.args.verbose:
            print("Command arguments:")
            for key,val in vars(self.args).items():
                print("  %-15s = %s" % (key, val))
            print()
    
    def check(self, args):
        oldest_rrsig_expiration = datetime.timedelta(days=999999)
        now = datetime.datetime.now().replace(microsecond=0)
    
        cmd = 'dig'
        cmd += ' +nottlid'                          # Exclude TTL
        if self.args.tsig:
            cmd += " -k %s" % self.args.tsig
        cmd += " @%s" % self.args.host
        cmd += " -q %s" % self.args.zone
        cmd += " -t AXFR"
        if self.args.zonefile:
            cmd = 'zcat %s' % self.args.zonefile
        cmd += ' | grep -i "IN[[:space:]]RRSIG"'    # filter out RRSIG RR
        cmd += ' | tr "\t" " "'                       # replace all tabs->spaces
        cmd += ' | tr -s " "'                       # replace repeated spaces with one
        cmd += ' | m_util. -d " " -f 1,8,9'             # extract name and two date fields
        if self.args.verbose: print("cmd :", cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=65536, shell=True)
        rrsig_count = 0
        for line in p.stdout:
            line = line.decode().lower()
            tmp = line.split()
            if len(tmp) != 3:
                print("Unknown RRSIG format in line:", file=sys.stderr)
                print("  %s" % line, file=sys.stderr)
                continue
            rrsig_count += 1
            try:
                expiration = datetime.datetime.strptime(tmp[1], RRSIG_DFORMAT)
                inception = datetime.datetime.strptime(tmp[2], RRSIG_DFORMAT)
            except ValueError:
                print("Unknown date format in line:", file=sys.stderr)
                print("  %s" % line, file=sys.stderr)
                continue
                
            len_before_expire = expiration - now
            if len_before_expire < oldest_rrsig_expiration:
                oldest_rrsig_expiration = len_before_expire
                # print("%s | %s" % (tmp[0], oldest_rrsig_expiration), file=sys.stderr)
            time.sleep(PACING_SLEEP)
    
        if self.args.verbose: print("Found %i RRSIG records" % rrsig_count)
        if rrsig_count < 1:
            m_util.response.exit(m_util.CRITICAL, "no signatures found")
    
        oldest_rrsig_expiration_sec = oldest_rrsig_expiration.days * 86400 + oldest_rrsig_expiration.seconds
        oldest_rrsig_expiration_days = oldest_rrsig_expiration_sec / 86400
    
        if oldest_rrsig_expiration_days < 0:
            m_util.response.exit(m_util.CRITICAL, "signatures has expired")
    
        if oldest_rrsig_expiration_days <= args.critical:
            m_util.response.exit(m_util.CRITICAL, "some signatures will expire in %0.1f days" % oldest_rrsig_expiration_days) 
           
        if oldest_rrsig_expiration_days < args.warning:
            m_util.response.exit(m_util.WARNING, "some signatures will expire in %.1f days" % oldest_rrsig_expiration_days)
    
        m_util.response.exit(m_util.OK, "minimum signature expire in %.1f days\n" % oldest_rrsig_expiration_days)


if __name__ == "__main__":
    m_util.main(Check_Rrsig_Expiry)
