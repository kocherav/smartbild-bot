/ip firewall filter remove [find where comment~"SmartBild KidsBot "]
/ip firewall filter add chain=sbkb-out src-address-list=kids_extension action=return disabled=yes comment="SmartBild KidsBot 10 extension outbound return"
/ip firewall filter add chain=sbkb-out time=07:00:00-22:59:59,mon,tue,wed,thu action=return disabled=yes comment="SmartBild KidsBot 20 Mon-Thu outbound return"
/ip firewall filter add chain=sbkb-out time=07:00:00-23:59:59,fri,sat action=return disabled=yes comment="SmartBild KidsBot 30 Fri-Sat outbound return"
/ip firewall filter add chain=sbkb-out time=07:00:00-22:59:59,sun action=return disabled=yes comment="SmartBild KidsBot 40 Sun outbound return"
/ip firewall filter add chain=sbkb-out action=drop disabled=yes comment="SmartBild KidsBot 90 internet outbound block"
/ip firewall filter add chain=sbkb-in dst-address-list=kids_extension connection-state=established,related action=return disabled=yes comment="SmartBild KidsBot 11 extension inbound return"
/ip firewall filter add chain=sbkb-in connection-state=established,related time=07:00:00-22:59:59,mon,tue,wed,thu action=return disabled=yes comment="SmartBild KidsBot 21 Mon-Thu inbound return"
/ip firewall filter add chain=sbkb-in connection-state=established,related time=07:00:00-23:59:59,fri,sat action=return disabled=yes comment="SmartBild KidsBot 31 Fri-Sat inbound return"
/ip firewall filter add chain=sbkb-in connection-state=established,related time=07:00:00-22:59:59,sun action=return disabled=yes comment="SmartBild KidsBot 41 Sun inbound return"
/ip firewall filter add chain=sbkb-in action=drop disabled=yes comment="SmartBild KidsBot 91 internet inbound block"
:local firstForward [/ip firewall filter find where chain=forward]
:if ([:len $firstForward] > 0) do={
    :local firstRule [:pick $firstForward 0]
    /ip firewall filter add chain=forward src-address-list=kids_devices out-interface-list=WAN action=jump jump-target=sbkb-out place-before=$firstRule disabled=yes comment="SmartBild KidsBot 01 outbound jump"
    /ip firewall filter add chain=forward dst-address-list=kids_devices in-interface-list=WAN action=jump jump-target=sbkb-in place-before=$firstRule disabled=yes comment="SmartBild KidsBot 02 inbound jump"
} else={
    /ip firewall filter add chain=forward src-address-list=kids_devices out-interface-list=WAN action=jump jump-target=sbkb-out disabled=yes comment="SmartBild KidsBot 01 outbound jump"
    /ip firewall filter add chain=forward dst-address-list=kids_devices in-interface-list=WAN action=jump jump-target=sbkb-in disabled=yes comment="SmartBild KidsBot 02 inbound jump"
}
