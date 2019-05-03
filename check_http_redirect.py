#!/usr/bin/env python3
'''
Check if an URL does a redirect (code 301 or 302), and that the
redirect goes to the correct URL

Author: Anders Lowinger, anders@abundo.se
'''

import sys
import socket
import http.client
import urllib.parse

import monitoring_util as m_util


origGetAddrInfo = socket.getaddrinfo

def getAddrInfoWrapper4(host, port, family=0, socktype=0, proto=0, flags=0):
    return origGetAddrInfo(host, port, socket.AF_INET, socktype, proto, flags)

def getAddrInfoWrapper6(host, port, family=0, socktype=0, proto=0, flags=0):
    return origGetAddrInfo(host, port, socket.AF_INET6, socktype, proto, flags)


class CheckHttpRedirekt(m_util.Plugin_Check):

    def __init__(self):
        super().__init__(description="Check if URL does redirect correctly")

        self.parser.add_argument("-H", "--host",
                                 required=True,
                                 help="Host to check")

        self.parser.add_argument("-4", "--ipv4",
                                 action="store_true",
                                 help="Use IPv4 connection")
        self.parser.add_argument("-6", "--ipv6",
                                 action="store_true",
                                 help="Use IPv6 connection")
        
        self.parser.add_argument("-U", "--url",
                                 required=True,
                                 help="URL to retrieve")
        self.parser.add_argument("-R", "--redir",
                                 required=True,
                                 help="Expected redirect URL")
        
        self.parser.add_argument("-t", "--timeout",
                                 type=int,
                                 default=10,
                                 help="Timeout waiting for a response")

        self.parse()
        
        
    def check(self):
        # replace the original socket.getaddrinfo by our version to force ipv4 or ipv6
        # If neither -4 or -6 is specified, it is up to the OS to choose, which normally
        # prefers IPv6
        if self.args.ipv4:
            socket.getaddrinfo = getAddrInfoWrapper4
        if self.args.ipv6:
            socket.getaddrinfo = getAddrInfoWrapper6
    
        url = urllib.parse.urlparse(self.args.url)
        if not url.scheme in ["http", "https"]:
            m_util.response.exit(m_util.UNKNOWN, "Cannot handle scheme %s" % url.scheme)
        if url.netloc == "":
            m_util.response.exit(m_util.UNKNOWN, "No network location specified")

        if url.scheme == "https":
            conn = http.client.HTTPSConnection(self.args.host, timeout=self.args.timeout)
        else:
            conn = http.client.HTTPConnection(self.args.host, timeout=self.args.timeout)

        try:
            conn.request("HEAD", "/", None, { "Host" : url.netloc })
            res = conn.getresponse()
        except http.client.InvalidURL as e:
            m_util.response.exit(m_util.UNKNOWN, "Invalid URL: %s" % e)
        except http.client.UnknownProtocol as e:
            m_util.response.exit(m_util.UNKNOWN, "Unknown protocol: %s" % e)
        except http.client.CannotSendRequest as e:
            m_util.response.exit(m_util.UNKNOWN, "Cannot send request: %s" % e)
        except (http.client.HTTPException, socket.error) as e:
            m_util.response.exit(m_util.UNKNOWN, "Exception: %s" % e)
    
        if not res.status in [301, 302]:
            m_util.response.exit(m_util.CRITICAL, "No redirect returned, got status %s" % res.status)
    
        location = res.getheader("Location", None)
        if location == None:
            m_util.response.exit(m_util.CRITICAL, "No redirect header")
    
        if location != self.args.redir:
            m_util.response.exit(m_util.CRITICAL, "Redirect to wrong URL: got '%s' expected '%s'" % (location, self.args.redir))
    
        msg = "%s OK: HTTP/%s.%s" % (url.scheme.upper(), res.version // 10, res.version % 10)
        msg += " %s " % res.status
        if res.status == 301:
            msg += "Moved permanently"
        if res.status == 302:
            msg += "Found/Moved temporarily"
    
        m_util.response.exit(m_util.OK, "%s. Redirect to %s" % (msg, location))


if __name__ == "__main__":
    m_util.main(CheckHttpRedirekt)
