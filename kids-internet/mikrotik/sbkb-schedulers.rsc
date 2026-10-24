/system scheduler remove [find where name="sbkb-state-poll"]
/system scheduler remove [find where name="sbkb-lease-sync"]
:local now [/system clock get time]
/system scheduler add name="sbkb-state-poll" start-time=$now interval=15s on-event="/system script run sbkb-state-poll" policy=ftp,read,write,test comment="SmartBild KidsBot"
/system scheduler add name="sbkb-lease-sync" start-time=$now interval=1m on-event="/system script run sbkb-lease-sync" policy=ftp,read,write,test comment="SmartBild KidsBot"
