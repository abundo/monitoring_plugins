#!/usr/bin/env python3 
"""
check free addresses in BECS DHCP scopes

Rewrites the icinga configuration and restarts icinga if there are any scopes
added/removed in BECS.

Author: Anders Lowinger, anders@abundo.se
"""

import os
import sys
import pprint
import filecmp
import shutil
import datetime
import yaml

from lib.becs import BECS
import monitoring_util as m_util

# ----- Start of configuration items ----------------------------------------

CONFIG = "/etc/monitoring_plugins/check_becs_dhcp_scopes.yaml"
BECS_CONFIG = "/etc/monitoring_plugins/becs.yaml"

# ----- End of configuration items ------------------------------------------


class Icinga:
    """
    Manage Icinga2
    """

    def __init__(self):
        pass
    
    def service_name(self, result, prefix):
        return "DHCP Scope %s - %s" % (result['name'], prefix)

    def write_config(self, filename, results):
        """
        Generate an icinga2 configuration file, passive DHCP scope checks
        Compare with existing icinga2 config file, if different install new
        file and reload icinga2 config
        """
        f = open(conf.temp_conf_file, "w")
        f.write(conf.template)
        for result in results.values():
            for prefix, values in result["prefixes"].items():
                if prefix == "summary":
                    name = self.service_name(result, prefix)
                    f.write('apply Service "%s" {\n' % name)
                    f.write('  import "dhcp-scope-free-addresses"\n')
                    f.write('  assign where host.name == "becs.net.piteenergi.se"\n')
                    f.write('}\n\n')
        f.close()

        if os.path.exists(filename):
            if filecmp.cmp(conf.temp_conf_file, filename, shallow=False):
                # Files are identical, nothing needs to be done
                return
        
        # copy new file into correct position
        shutil.copyfile(conf.temp_conf_file, filename)

        # reload icinga config
        os.system("systemctl reload icinga2.service")


    def write_result(self, results, args):
        """
        Write number of free DHCP leases to Icinga FIFO
        """
        timestamp = int(datetime.datetime.now().timestamp())
        f = open(conf.pipe, "wb")
        for result in results.values():
            for prefix, values in result["prefixes"].items():
                if prefix == "summary":
                    name = self.service_name(result, prefix)
                    free = values["free"]

                    return_code = m_util.OK
                    if free < args.free_critical:
                        return_code = m_util.CRITICAL
                    elif free < args.free_warning:
                        return_code = m_util.WARNING

                    res = "[%s] PROCESS_SERVICE_CHECK_RESULT;%s;%s;%s;%d free addresses, %d assigned addresses" %\
                        (timestamp, conf.host, name, return_code, values["free"], values["assigned"])
                    print(res)
                    f.write(res.encode())
                    f.write(b"\n")
        f.close()

class Check_becs_dhcp_scopes(m_util.Plugin_Check):

    def __init__(self):
        global conf

        super().__init__(description="Check number of freee DHCP leases in BECS DHCP scopes")

        # Read this script configuration file
        conf = m_util.yaml_load(CONFIG)

        self.parser.add_argument("--free_warning", 
                                 type=int,
                                 default=conf.age_warning,
                                 help="Generate WARNING if number of free addresses is below")
        self.parser.add_argument("--free_critical", 
                                 type=int,
                                 default=conf.age_critical,
                                 help="Generate CRITICAL if number of free addresses is below")
        self.parser.add_argument('--icinga',
                                 default=False,
                                 action="store_true",
                                 help="Write icinga2 config file and send result as passsive check")
        self.parser.add_argument('--icinga_config_file',
                                 default=conf.dhcp_scope_conf_file,
                                 help="Path to icinga2 config file")
        self.parse()

    def check(self):
        global becs_conf

        # Read BECS configuration file        
        becs_conf = m_util.yaml_load(BECS_CONFIG)
 
        becs = BECS(url=becs_conf.eapi, username=becs_conf.username, password=becs_conf.password)
        results = becs.get_dhcp_scope_util(oid=conf.becs.scope_id)
        becs.logout()

        # pp = pprint.PrettyPrinter(indent=4)
        # pp.pprint(results)

        if self.args.icinga:
            icinga = Icinga()
            icinga.write_config(conf.dhcp_scope_conf_file, results)
            icinga.write_result(results, self.args)


if __name__ == "__main__":
    m_util.main(Check_becs_dhcp_scopes)
