#!/usr/bin/env python3
'''
Check status file written by a nagios check, typically run by cron
1. Check the age on the status file, if it is too old return WARNING/CRITICAL
2. Inspect the first line, look for the text OK, WARNING, CRITICAL, UNKNOWN
   If not found, status will be UNKNOWN
3. Print the file so Nagios can show the content
4. exit the script with the correct return code according to 2.

Author: Anders Lowinger, anders@abundo.se
'''

import os
import datetime

import monitoring_util as m_util


DEFAULT_AGE_WARNING = 48.0      # hours
DEFAULT_AGE_CRITICAL = 36.0     # hours


class Check_File_Status(m_util.Plugin_Check):

    def __init__(self):
        super().__init__(description="Verify age on RRSIG records in a zone")

        self.parser.add_argument('-f', '--file',
                                 required=True,
                                 help="File to check")
        self.parser.add_argument("--age_warning", 
                                 type=float,
                                 default=DEFAULT_AGE_WARNING,
                                 help="Max age on file in hours, before WARNING")
        self.parser.add_argument("--age_critical", 
                                 type=float,
                                 default=DEFAULT_AGE_CRITICAL,
                                 help="Max age on file in hours, before CRITICAL")
   
        self.parse()
        

    def check(self):
        if not os.path.exists(self.args.file):
            m_util.response.exit(m_util.UNKNOWN, "File '%s' does not exist" % self.args.file)
    
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(self.args.file))
        except OSError:
            m_util.response.exit(m_util.UNKNOWN, "Cannot get modified time for file %s" % self.args.file)
    
        age = datetime.datetime.now() - mtime
        age_hours = (age.days * 24) + (age.seconds / 3600)
        if age_hours > self.args.age_critical:
            m_util.response.exit(m_util.CRITICAL, "File %s last modified %0.2f hours ago, older than limit %0.2f hours" % 
                          (self.args.file, age_hours, self.args.age_critical))
        if age_hours > self.args.age_warning:
            m_util.response.exit(m_util.WARNING, "File %s last modified %0.2f hours ago, older than limit %0.2f hours" % 
                          (self.args.file, age_hours, self.args.age_warning))
            
        try:
            f = open(self.args.file, "r")
        except IOError:
            m_util.response.exit(m_util.UNKNOWN, "Cannot open file %s, is the path correct?" % self.args.file)
        retcode = None
        for line in f.readlines():
            line = line.rstrip()
            if retcode == None:
                tmp = line.lower()
                for key,val in m_util.str_to_errstat.items():
                    if tmp.startswith(key):
                        retcode = val
                if retcode == None:
                    retcode = m_util.UNKNOWN 
        f.close()
        m_util.response.exit(m_util.OK, "File %s last modified %0.2f hours ago" % (self.args.file, age_hours))
        

if __name__ == "__main__":
    m_util.main(Check_File_Status)
