#!/usr/bin/env python3
"""
Check a domain for errors
Uses zonemaster-cli
The result is feed into the command file, to update a passive check

required library:
    apt-get install python3-yaml
    zonemaster
"""

import sys
import json
import time
import yaml
import subprocess

import monitoring_util as m_util

nagios_command_file="/var/run/icinga2/cmd/icinga2.cmd"

# Nagios return codes
# OK = 0
# WARNING = 1
# CRITICAL = 2
# UNKNOWN = 3

level_map = {}
level_map['NOTICE'] = 0
level_map['WARNING'] = 1
level_map['ERROR'] = 2


class Check_Zonemaster(m_util.Plugin_Check):

    def __init__(self):
        super().__init__(description="")
        self.parser.add_argument("-c", "--config", 
                                 help="path to file with zones to check")

    def check(self):
        conf = yaml.load(open('/etc/monitoring-plugins/zones.yaml','r'))
        for zone in conf['zones']:

            print("Checking zone %s" % zone)
            f = "[{timestamp}] PROCESS_SERVICE_CHECK_RESULT;{hostname};{service_description};{return_code};{output}\n"

            d = {}
            d['timestamp'] = int(time.time())
            d['service_description'] = "Zonemaster"
            d['output'] = ""
            d['hostname'] = '%s - domain' % zone

            tests = []
            tests.append("Address/address01")
            tests.append("Basic")
            tests.append("Connectivity")
            tests.append("Consistency")
            tests.append("DNSSEC")
            tests.append("Delegation")
            tests.append("Nameserver")
            tests.append("Syntax")
            tests.append("Zone")
            cmd = "/usr/local/bin/zonemaster-cli --json "
            for t in tests:
                cmd += "--test %s " % t
            cmd += "%s" % zone
            # print(cmd)

            return_code = 0
            output = []
            subprocess_out = subprocess.check_output(cmd, shell=True)
            subprocess_out = json.loads(subprocess_out.decode())
            for r in subprocess_out:
                if r['level'] in level_map:
                    tmp = level_map[r['level']]
                    if tmp > return_code:
                        return_code = tmp
                else:
                    print('Unknown level', r['level'])

                tmp = 'level %s, module %s, tag %s' % (r['level'], r['module'], r['tag'])
                if len(r['args']):
                    args = []
                    for key,val in r['args'].items():
                        args.append("%s=%s" % (key,val))
                    tmp += " args(%s)" % ", ".join(args)
                output.append(tmp)

            if len(output) > 1:
                output[0] += "  More..."
            d['output'] = "\\n".join(output)
            d['return_code'] = return_code

            # Send test result to nagios
            s = f.format(**d)
            print(s)
            open(nagios_command_file, "w").write(s)


if __name__ == '__main__':
    m_util.main(Check_Zonemaster)
