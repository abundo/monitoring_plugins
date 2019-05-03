#!/usr/bin/env python3
'''
Common monitor plugins functions

Author: Anders Lowinger, anders@abundo.se
'''

import os
import sys
import time
import argparse
import subprocess

# nagios return codes
OK       = 0
WARNING  = 1
CRITICAL = 2
UNKNOWN  = 3

str_to_errstat = { 
    'ok'       : OK, 
    'warning'  : WARNING, 
    'critical' : CRITICAL,
    'unknown'  : UNKNOWN 
}

errstat_to_str = {
    OK       : 'OK',
    WARNING  : 'WARNING',
    CRITICAL : 'CRITICAL',
    UNKNOWN  : 'UNKNOWN'
}


class Response:
    
    def __init__(self):
        self.status = UNKNOWN
        self.perfdata = None
        self.details = None

    def set_status(self, status):
        if status > self.status:
            self.status = status
    
    def exit(self, status, msg=None):
        if status != None:
            self.status = status
        s = '%s' % errstat_to_str[self.status]
        if msg != None:
            s += ' ' + msg
        if self.perfdata != None:
            s += '|' + self.perfdata
        if self.details:
            for detail in self.details:
                s += '\n' + detail
        print(s)
        sys.exit(self.status)
    
    def add_detail(self, msg):
        if self.details == None:
            self.details = []
        self.details.append(msg)

response = Response()


class Check_Range:
    """
    Decode a nagios range specification
      start < end
      start and : is not required if start = 0
      if range is of format "start:" and end is not specified, assume end is infinity
      to specify negative infinity, use "~"
      alert is raised if metric is outside start and end range (inclusive of endpoints)
      todo: if range starts with "@", then alert if inside this range (inclusive of endpoints)
    """
    
    def __init__(self, range_):
        self.range = range_
        
        self.inside = False
        if self.range.startswith('@'):
            self.inside = True
            self.range = self.range[1:]

        tmp = self.range.split(':')
        if len(tmp) > 2:
            raise ValueError('Invalid range')
        if len(tmp) == 2:
            # we have a range
            if tmp[0] != '':
                self.start = float(tmp[0])
            else:
                self.start = 0
            if tmp[1] != '':
                self.end = float(tmp[1])
            else:
                self.end = sys.maxsize
        else:
            # only end is specified
            self.start = 0
            self.end = float(range)
        
        if self.start > self.end:
            raise ValueError('Start must be lower than end')

    def check(self, value):
        return value < self.start or value > self.end

    def check_warn_crit(self, value):
        '''
        Compare a value, handle start as warning and end as critical
        '''
        if value > self.end:
            return CRITICAL
        if value > self.start:
            return WARNING
        return OK
         

class ArgumentParser(argparse.ArgumentParser):
    '''
    We subclass this so we always can return UNKNOWN(3) if there are errors in the parser
    '''
    def __init__(self, **kwargs):
        super(ArgumentParser, self).__init__(formatter_class=argparse.ArgumentDefaultsHelpFormatter, **kwargs)

    def error(self, message):
        self.print_help(sys.stderr)
        self.exit(3, '%s: error: %s\n' % (self.prog, message))


class External_Command:
    '''
    Run an external command, return the output
    '''
    def __init__(self, args, cmd):
        self.args = args
        self.cmd = cmd
        self.lines = ''
        if self.args.verbose: print('cmd :', ' '.join(cmd))
        self.lines = subprocess.check_output(' '.join(cmd), 
            stderr=subprocess.STDOUT, bufsize=4096, shell=True, universal_newlines=True)

    def __iter__(self):
        for line in self.lines.split('\n'):
            line = line.rstrip()
            if line != '':
                yield line


class Plugin_Check:
    '''
    Base class, an nagios check should create a superclass and override check(), main()
    '''
    def __init__(self, description=""):
        self.parser = ArgumentParser(description=description)
        self.parser.add_argument('--unknown_as', 
                                 choices=str_to_errstat,
                                 default='unknown', 
                                 help='How to return UNKNOWN')
        self.parser.add_argument('--warning_as',
                                 choices=str_to_errstat,
                                 default='warning', 
                                 help='How to return WARNING')
        self.parser.add_argument('--critical_as',
                                 choices=str_to_errstat,
                                 default='critical', 
                                 help='How to return CRITICAL')
    
        self.parser.add_argument('-v', '--verbose',
                                 action="store_true",
                                 help="Show details ")
        self.parser.add_argument('--debug',
                                 action='store_true',
                                 help='Print debug output, mostly for development')
        
        self.status = UNKNOWN
        self.perfdata = None
        self.details = None

        path = os.path.basename( os.path.abspath(sys.argv[0]))
        if path.endswith('.py'):
            path = path[:-3]
        path = '/tmp/%s' % path
        if os.path.exists(path):
            if time.time() - os.path.getmtime(path) < 3600:
                import syslog
                syslog.syslog('%s' % sys.argv)


    def parse(self):
        global UNKNOWN, WARNING, CRITICAL
        
        self.args = self.parser.parse_args()

        # optionally override return codes
        if self.args.unknown_as != None:
            UNKNOWN = str_to_errstat[self.args.unknown_as]
        if self.args.warning_as != None:
            WARNING = str_to_errstat[self.args.warning_as]
        if self.args.critical_as != None:
            CRITICAL = str_to_errstat[self.args.critical_as]
            
        if self.args.verbose:
            print("Command arguments:")
            for key,val in vars(self.args).items():
                print('  %-15s = %s' % (key, val))
            print()

    def check(self):
        pass

    def main(self):
        pass


def main(cls):
    obj = cls()
    obj.check()

if __name__ == '__main__':
    sys.exit(1)
