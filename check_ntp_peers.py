#!/usr/bin/env python3
'''
Check status on NTP
- One peer must be selected
- Offset must be less than allowed max offset
- Jitter must be less than allowed max jitter
- All peers must be up

Verify that both LB are active
Verify that lb1 is the active and lb2 is standby

Author: Anders Lowinger, anders@abundo.se
'''

import os
import sys

import monitoring_util as m_util


class Peer:
    """
    Represents one NTP peer

    tally is one of
      + = denotes symmetric active
      - = indicates symmetric passive
      a = the remote server is being polled in client mode
      ^ = indicates that the server is broadcasting to this address,
      ~ = denotes that the remote peer is sending broadcasts
      * = the peer the server is rently synchronizing to.
      
    t is one of
      u: unicast or manycast client
      b: broadcast or multicast client
      l: local (reference clock)
      s: symmetric (peer)
      A: manycast server
      B: broadcast server
      M: multicast server
    
    """
    def __init__(self, remote=None, line=None):
        self.tally = None
        self.remote = remote
        self.refid = None
        self.stratum = None
        self.t = None
        self.when = None
        self.poll = None
        self.reach = None
        self.delay = None
        self.offset = None
        self.jitter = None
        if line != None:
            # Parse the string into the attributes
            self.tally = line[0]
            tmp = line[1:].split()
            self.remote = tmp[0]
            self.refid = tmp[1]
            self.stratum = int(tmp[2])
            self.t = tmp[3]
            self.when = tmp[4]
            self.poll = int(tmp[5])
            self.reach = int(tmp[6], 8) # octal
            self.delay = float(tmp[7])
            self.offset = float(tmp[8])
            self.jitter = float(tmp[9])

    def isUp(self):
        return self.stratum != 16
            
    def __str__(self):
        s = ""
        for attr in ["tally", "remote", "refid", "stratum", "t", "when", "poll", "reach", "delay", "offset", "jitter"]:
            s += "%s '%s', " % (attr, getattr(self, attr))
        return "Peer(%s)" % s[:-2]


class Check_Ntp_Peers(m_util.Plugin_Check):

    def __init__(self):
        super().__init__(description="Check status on NTP peers")
        
        self.parser.add_argument("--max_offset",
                                 default="250:500", 
                                 help="Max offset in milliseconds before warning/critical. Specify as warning:critical")
        self.parser.add_argument("--max_jitter",
                                 default="250:500",
                                 help="Max offset in milliseconds before warning/critical. Specify as warning:critical")
        
        self.peers = []
        
        self.parse()
        
        self.max_offset = m_util.Check_Range(self.args.max_offset)
        self.max_jitter = m_util.Check_Range(self.args.max_jitter)
        

    def check(self):
        extcmd = m_util.External_Command(self.args, ["ntpq", "-p"])
        
        # First, get the names of each device
        skiplines = True
        for line in extcmd:
            if line[0] == "=":
                skiplines = False         # next row is list of peers
                continue
            if skiplines:
                continue
            self.peers.append(Peer(line=line.rstrip()))

        # Check peer status
        m_util.response.status = m_util.OK
        selectedPeer = None
        countUp = 0
        for peer in self.peers:
            if peer.tally == "*":
                selectedPeer = peer
            s = "Peer %s" % peer.remote

            if peer.isUp():
                countUp += 1
                s += ", offset %s ms, jitter %s ms" % (peer.offset, peer.jitter)
                stat = self.max_offset.check_warn_crit(abs(peer.offset))
                if stat != m_util.OK:
                    m_util.response.setStatus(stat)
                    s += ", Offset %s over maximum" % m_util.errstat_to_str[stat]
                else:
                    s += ", Offset OK"
                    
                stat = self.max_jitter.check_warn_crit(peer.jitter)
                if stat != m_util.OK:
                    m_util.response.setStatus(stat)
                    s += ", Jitter %s over maximum" % m_util.errstat_to_str[stat]
                else:
                    s += ", Jitter OK"
            else:
                s += ", peer is DOWN"
                
            m_util.response.addDetail(s)

        if selectedPeer == None:
            m_util.response.exit(m_util.CRITICAL, "No NTP peer is selected")

        if countUp < 1:
            m_util.response.exit(m_util.CRITICAL, "All NTP peers down")

        if countUp < len(self.peers):
            m_util.response.exit(m_util.WARNING, "Of total %s NTP peers is %s down" % ( len(self.peers), (len(self.peers) - countUp) ))

        m_util.response.exit(m_util.OK, msg="Peer '%s' is selected, offset %s ms, jitter %s ms" % 
                         (selectedPeer.remote, selectedPeer.offset, selectedPeer.jitter))


if __name__ == "__main__":
    m_util.main(Check_Ntp_Peers)
