"""Network configuration read and write, checked against field captures.

Every payload below was captured from production miners on 2026-08-06 across nine
farms.  The case names carry the farm and firmware the capture came from.
"""

import unittest

from pyasic.data.network import NetworkMode
from pyasic.miners.backends.antminer import AntminerModern, AntminerOld
from pyasic.miners.backends.bitfufu import BitfufuMiner
from pyasic.miners.backends.braiins_os import BOSMiner
from pyasic.miners.backends.btminer import BTMiner
from pyasic.miners.backends.elphapex import ElphapexMiner
from pyasic.miners.backends.hammer import BlackMiner
from pyasic.miners.backends.hashmaster import HashMasterMiner
from pyasic.miners.backends.hiveon import HiveonModern
from pyasic.miners.backends.luxminer import LUXMiner
from pyasic.miners.backends.spideros import SpiderOSMiner
from pyasic.miners.backends.utils import (
    is_bitmain_write_success,
    parse_bitmain_network_info,
)
from pyasic.miners.base import MinerProtocol

# Bitmain CGI captures, keyed by the farm and firmware they came from.
BITMAIN_CAPTURES = {
    "OM01 stock DHCP /24": (
        {
            "nettype": "DHCP",
            "netdevice": "eth0",
            "macaddr": "B0:0E:D5:42:03:5B",
            "ipaddress": "10.4.105.83",
            "netmask": "255.255.255.0",
            "conf_nettype": "DHCP",
            "conf_hostname": "antMiner",
            "conf_ipaddress": "",
            "conf_netmask": "",
            "conf_gateway": "",
            "conf_dnsservers": "",
        },
        {
            "mode": NetworkMode.DHCP,
            "ip": "10.4.105.83",
            "netmask": "255.255.255.0",
            "gateway": None,
            "dns": None,
            "hostname": "antMiner",
        },
    ),
    "LNGA01 stock DHCP /23": (
        {
            "nettype": "DHCP",
            "netdevice": "eth0",
            "macaddr": "42:ED:8E:DC:6D:1B",
            "ipaddress": "172.50.136.47",
            "netmask": "255.255.254.0",
            "conf_nettype": "DHCP",
            "conf_hostname": "antMiner",
            "conf_ipaddress": "",
            "conf_netmask": "",
            "conf_gateway": "",
            "conf_dnsservers": "",
        },
        {
            "mode": NetworkMode.DHCP,
            "ip": "172.50.136.47",
            "netmask": "255.255.254.0",
            "gateway": None,
            "dns": None,
            "hostname": "antMiner",
        },
    ),
    "CF01 stock DHCP /16": (
        {
            "nettype": "DHCP",
            "netdevice": "eth0",
            "macaddr": "02:86:EC:FF:09:9B",
            "ipaddress": "10.95.132.125",
            "netmask": "255.255.0.0",
            "conf_nettype": "DHCP",
            "conf_hostname": "Antminer",
            "conf_ipaddress": "",
            "conf_netmask": "",
            "conf_gateway": "",
            "conf_dnsservers": "",
        },
        {
            "mode": NetworkMode.DHCP,
            "ip": "10.95.132.125",
            "netmask": "255.255.0.0",
            "gateway": None,
            "dns": None,
            "hostname": "Antminer",
        },
    ),
    "OBTX02 hashmaster DHCP": (
        {
            "nettype": "DHCP",
            "netdevice": "eth0",
            "macaddr": "D8:B7:3D:44:53:AD",
            "ipaddress": "192.168.220.148",
            "netmask": "255.255.255.0",
            "conf_nettype": "DHCP",
            "conf_hostname": "Antminer",
            "conf_ipaddress": "",
            "conf_netmask": "",
            "conf_gateway": "",
            "conf_dnsservers": "",
        },
        {
            "mode": NetworkMode.DHCP,
            "ip": "192.168.220.148",
            "netmask": "255.255.255.0",
            "gateway": None,
            "dns": None,
            "hostname": "Antminer",
        },
    ),
    "LNGA01 bitfufuos DHCP": (
        {
            "nettype": "DHCP",
            "netdevice": "eth0",
            "macaddr": "F4:A3:95:47:5A:90",
            "ipaddress": "172.50.56.165",
            "netmask": "255.255.254.0",
            "conf_nettype": "DHCP",
            "conf_hostname": "Antminer",
            "conf_ipaddress": "",
            "conf_netmask": "",
            "conf_gateway": "",
            "conf_dnsservers": "",
        },
        {
            "mode": NetworkMode.DHCP,
            "ip": "172.50.56.165",
            "netmask": "255.255.254.0",
            "gateway": None,
            "dns": None,
            "hostname": "Antminer",
        },
    ),
    "Brest-1 hashmaster static gateway .1": (
        {
            "nettype": "Static",
            "netdevice": "eth0",
            "macaddr": "02:6C:56:D3:66:43",
            "ipaddress": "10.26.12.65",
            "netmask": "255.255.255.0",
            "conf_nettype": "Static",
            "conf_hostname": "Antminer",
            "conf_ipaddress": "10.26.12.65",
            "conf_netmask": "255.255.255.0",
            "conf_gateway": "10.26.12.1",
            "conf_dnsservers": "8.8.8.8",
        },
        {
            "mode": NetworkMode.STATIC,
            "ip": "10.26.12.65",
            "netmask": "255.255.255.0",
            "gateway": "10.26.12.1",
            "dns": "8.8.8.8",
            "hostname": "Antminer",
        },
    ),
    "sabeta hashmaster static gateway .254": (
        {
            "nettype": "Static",
            "netdevice": "eth0",
            "macaddr": "02:78:C5:78:E7:D8",
            "ipaddress": "10.2.11.41",
            "netmask": "255.255.255.0",
            "conf_nettype": "Static",
            "conf_hostname": "Antminer",
            "conf_ipaddress": "10.2.11.41",
            "conf_netmask": "255.255.255.0",
            "conf_gateway": "10.2.11.254",
            "conf_dnsservers": "213.55.96.148",
        },
        {
            "mode": NetworkMode.STATIC,
            "ip": "10.2.11.41",
            "netmask": "255.255.255.0",
            "gateway": "10.2.11.254",
            "dns": "213.55.96.148",
            "hostname": "Antminer",
        },
    ),
    "Minsk static private dns": (
        {
            "nettype": "Static",
            "netdevice": "eth0",
            "macaddr": "06:86:BB:01:32:1F",
            "ipaddress": "192.168.136.23",
            "netmask": "255.255.255.0",
            "conf_nettype": "Static",
            "conf_hostname": "Antminer",
            "conf_ipaddress": "192.168.136.23",
            "conf_netmask": "255.255.255.0",
            "conf_gateway": "192.168.136.1",
            "conf_dnsservers": "194.158.196.245",
        },
        {
            "mode": NetworkMode.STATIC,
            "ip": "192.168.136.23",
            "netmask": "255.255.255.0",
            "gateway": "192.168.136.1",
            "dns": "194.158.196.245",
            "hostname": "Antminer",
        },
    ),
    # Elphapex uses the same field names but lowercases the MAC.
    "sabeta elphapex DHCP": (
        {
            "conf_netmask": "",
            "conf_nettype": "DHCP",
            "ipaddress": "10.4.20.146",
            "netmask": "255.255.255.0",
            "conf_dnsservers": "",
            "conf_gateway": "",
            "nettype": "DHCP",
            "netdevice": "eth0",
            "macaddr": "b8:4c:87:e0:8e:90",
            "conf_ipaddress": "",
            "conf_hostname": "DG1+",
        },
        {
            "mode": NetworkMode.DHCP,
            "ip": "10.4.20.146",
            "netmask": "255.255.255.0",
            "gateway": None,
            "dns": None,
            "hostname": "DG1+",
        },
    ),
}


class TestBitmainNetworkRead(unittest.TestCase):
    def test_field_captures(self):
        for name, (payload, expected) in BITMAIN_CAPTURES.items():
            with self.subTest(capture=name):
                config = parse_bitmain_network_info(payload)
                self.assertIsNotNone(config)
                for field, value in expected.items():
                    self.assertEqual(getattr(config, field), value, msg=field)

    def test_missing_payload_reads_as_unknown(self):
        for payload in (None, {}):
            with self.subTest(payload=payload):
                self.assertIsNone(parse_bitmain_network_info(payload))

    def test_gateway_is_unreadable_in_dhcp_mode(self):
        """``conf_*`` holds the static configuration, which DHCP leaves empty."""
        for name, (payload, _) in BITMAIN_CAPTURES.items():
            if payload["conf_nettype"] != "DHCP":
                continue
            with self.subTest(capture=name):
                config = parse_bitmain_network_info(payload)
                self.assertIsNone(config.gateway)
                self.assertIsNone(config.dns)
                self.assertIsNotNone(config.ip)
                self.assertIsNotNone(config.netmask)

    def test_netmask_is_never_assumed(self):
        """The fleet runs /16, /23 and /24, so the mask is always read."""
        masks = {
            parse_bitmain_network_info(payload).netmask
            for payload, _ in BITMAIN_CAPTURES.values()
        }
        self.assertEqual(masks, {"255.255.255.0", "255.255.254.0", "255.255.0.0"})

    def test_gateway_cannot_be_derived_from_the_subnet(self):
        """Two different last octets are in use across the captures."""
        gateways = {
            parse_bitmain_network_info(payload).gateway
            for payload, _ in BITMAIN_CAPTURES.values()
            if parse_bitmain_network_info(payload).gateway is not None
        }
        last_octets = {gateway.rsplit(".", 1)[1] for gateway in gateways}
        self.assertEqual(last_octets, {"1", "254"})


class TestRpcNetworkRead(unittest.IsolatedAsyncioTestCase):
    async def test_whatsminer_reports_gateway_while_on_dhcp(self):
        """Kuching, M63S."""
        payload = {
            "STATUS": "S",
            "Code": 131,
            "Msg": {
                "ntp": ["0.cn.pool.ntp.org"],
                "ip": "10.100.0.247",
                "proto": "dhcp",
                "netmask": "255.255.0.0",
                "gateway": "10.100.0.1",
                "dns": "10.100.0.1",
                "hostname": "WhatsMiner",
                "mac": "CE:59:05:00:03:77",
                "ledstat": "auto",
            },
        }
        config = await BTMiner("10.100.0.247")._get_network(payload)
        self.assertEqual(config.mode, NetworkMode.DHCP)
        self.assertEqual(config.ip, "10.100.0.247")
        self.assertEqual(config.netmask, "255.255.0.0")
        self.assertEqual(config.gateway, "10.100.0.1")
        self.assertEqual(config.dns, "10.100.0.1")
        self.assertEqual(config.hostname, "WhatsMiner")

    async def test_luxos_reports_gateway_but_not_dns_while_on_dhcp(self):
        """OBTX01, S21+ Hydro.  Good enough to borrow a gateway, not a DNS."""
        payload = {
            "CONFIG": [
                {
                    "DHCP": True,
                    "DNS Servers": "",
                    "Gateway": "192.168.216.250",
                    "Hostname": "Antminer",
                    "IPAddr": "192.168.216.106",
                    "Netmask": "255.255.255.0",
                    "MACAddr": "12:fc:3e:b4:92:74",
                }
            ]
        }
        config = await LUXMiner("192.168.216.106")._get_network(payload)
        self.assertEqual(config.mode, NetworkMode.DHCP)
        self.assertEqual(config.gateway, "192.168.216.250")
        self.assertIsNone(config.dns)

    async def test_luxos_reads_static_from_the_same_boolean(self):
        payload = {"CONFIG": [{"DHCP": False, "IPAddr": "10.0.0.5"}]}
        config = await LUXMiner("10.0.0.5")._get_network(payload)
        self.assertEqual(config.mode, NetworkMode.STATIC)

    async def test_unusable_payloads_read_as_unknown(self):
        self.assertIsNone(await BTMiner("1.1.1.1")._get_network({}))
        self.assertIsNone(await LUXMiner("1.1.1.1")._get_network({"CONFIG": []}))


class TestWriteResponse(unittest.TestCase):
    def test_bitmain_success(self):
        """The field is ``stats``, not ``status``, and the code is N000."""
        self.assertTrue(
            is_bitmain_write_success({"stats": "success", "code": "N000", "msg": "OK!"})
        )

    def test_transport_failure_is_not_success(self):
        """pyasic turns HTTP errors into this shape instead of raising."""
        self.assertFalse(
            is_bitmain_write_success({"success": False, "message": "HTTP error"})
        )

    def test_unrecognised_response_is_not_success(self):
        for response in (None, {}, {"status": "ok"}, "success"):
            with self.subTest(response=response):
                self.assertFalse(is_bitmain_write_success(response))


class TestCapabilityConsistency(unittest.TestCase):
    """Every declared capability has a transport method behind it."""

    WRITE_TRANSPORT = {
        AntminerModern: ("web", "set_network_conf"),
        HashMasterMiner: ("web", "set_network_conf"),
        BitfufuMiner: ("web", "set_network_conf"),
        SpiderOSMiner: ("web", "set_network_conf"),
        BlackMiner: ("web", "set_network_conf"),
        BTMiner: ("rpc", "net_config"),
        LUXMiner: ("rpc", "netset"),
    }

    READ_TRANSPORT = {
        AntminerModern: ("web", "get_network_info"),
        HashMasterMiner: ("web", "get_network_info"),
        BitfufuMiner: ("web", "get_network_info"),
        SpiderOSMiner: ("web", "get_network_info"),
        BlackMiner: ("web", "get_network_info"),
        HiveonModern: ("web", "get_network_info"),
        ElphapexMiner: ("web", "get_network_info"),
        BTMiner: ("rpc", "get_miner_info"),
        LUXMiner: ("rpc", "config"),
    }

    def test_write_capability_has_transport(self):
        for cls, (client, method) in self.WRITE_TRANSPORT.items():
            with self.subTest(backend=cls.__name__):
                self.assertTrue(hasattr(cls, "set_static_ip"))
                self.assertTrue(hasattr(cls, "set_dhcp"))
                self.assertTrue(hasattr(getattr(cls("127.0.0.1"), client), method))

    def test_read_capability_has_transport(self):
        for cls, (client, method) in self.READ_TRANSPORT.items():
            with self.subTest(backend=cls.__name__):
                self.assertIsNot(cls._get_network, MinerProtocol._get_network)
                self.assertTrue(hasattr(getattr(cls("127.0.0.1"), client), method))

    def test_backends_without_support_fall_back_to_the_base_stub(self):
        """``_get_data`` calls ``_get_network`` on every backend, so it must exist."""
        for cls in (AntminerOld, BOSMiner):
            with self.subTest(backend=cls.__name__):
                self.assertIs(cls._get_network, MinerProtocol._get_network)


class TestBaseStubIsUsable(unittest.IsolatedAsyncioTestCase):
    async def test_stub_returns_nothing(self):
        for cls in (AntminerOld, BOSMiner):
            with self.subTest(backend=cls.__name__):
                self.assertIsNone(await cls("127.0.0.1")._get_network())
