# Cougarnet

Cougarnet creates a virtual network for learning network configuration and
protocols.  It takes as input a [network configuration
file](#network-configuration-file).  Using the configuration as a guide, it
creates [virtual hosts](#virtual-hosts) and [virtual links](#virtual-links)
between them.  It can also add MAC and IP address information to interfaces,
specify bandwidth, (propagation) delay, or loss to links.

Perhaps the most power feature of Cougarnet is the ability to either use the
built-in Linux network stack or capture raw frames only.  The former is useful
for configuring and using a network with built-in tools (e.g., ping,
traceroute), while the latter is useful for implementing the protocol stack in
software.  Additionally, there can be a mixture--some hosts that use native
stack and some that do not.


# Installation

To install Cougarnet, run the following:

```
$ python setup.py build
$ sudo python setup.py install
```

TODO: `sudo`, `wireshark`, `lxde-terminal`


# Getting Started

To get started, create a simple network configuration.  Create a file called
`simple-net.cfg` with the following contents:

```
NODES
h1
h2

LINKS
h1,10.0.0.1/24 h2,10.0.0.2/24
```

This simple configuration results in a network composed of two nodes, named
`h1` and `h2`.  There is a single link between them.  For the link between `h1`
and `h2`, `h1`'s interface will have an IPv4 address of 10.0.0.1, and `h2` will
have an IPv4 address of 10.0.0.2.  The `/24` indicates that the length of the
IPv4 prefix associated with that link is 24 bit associated with that link is 24
bits, i.e., 10.0.0.0/24.

Start Cougarnet with this configuration by running the following command:

```
cougarnet simple-net.cfg
```

When it starts up, it will launch two new terminals.  One will be associated
with the virtual host `h1` and the other with `h2`.  The prompt at each should
indicate which is which.

Each each terminal, run the following to see the network configuration:
```
$ ip addr
```
Note first that each virtual host sees only its own interface. Also note that
each host is configured with the address from the configuration file.

Next, from the `h2` terminal, run the following:

```
h2$ sudo tcpdump -l
```
(Note that in this example and elsewhere in this document `h2$` simply
indicates that it is the prompt corresponding to `h2`.)

The `-l` option to `tcpdump` ensures that line-based buffering is used, so the
output is printed as soon as it is generated.

Now from the `h1` terminal, run the following:

```
h1$ ping h2
```

You should see activity on both terminals.  The `tcpdump` output on `h2` shows
the ICMP packets resulting from the `ping` command issued on `h1`, as well as
the responses being returned by `h2`.  The `ping` output on `h1` shows the
status of the ICMP messages leaving `h1` and the response messages coming from
`h2`.

Now, enter `Ctrl`+`c` on each terminal to stop the two programs.  Finally,
return to the terminal on which you ran the `cougarnet` command, and enter
`Ctrl`+`c`.

Congratulations!  You have just completed a simple Cougarnet excercise!


# Virtual Hosts

Each virtual host is actually just a process that is running in its own Linux
namespace (see the `man` page for `namespaces(7)`).  Specifically, it is a
process spawned with the `unshare` command.  The `--mount`, `--net`, and
`--uts` options are passed to `unshare` command, the result of which is that
(respectively):
 - any filesystem mounts created (i.e., with the `mount` command) are only seen
   by the process, not by the whole system;
 - the network stack, including interfaces, address configuration, firewall,
   and more, are specific to the process and are not seen by the rest of the
   system; and
 - the hostname is specific to the process.

With only these options in use, the virtual hosts all still have access to the
system-wide filesystem and all system processes (Note that the former could be
changed if `unshare` were called with `--root`, and the latter could be changed
if `unshare` were called with `--pid`, but currently that is not an option).


## Configuration

In the Cougarnet configuration file, a host is designated by a hostname on a
single line in the `NODES` section of the file. Consider the `NODES` section of
the [example configuration given previously](#getting-started):

```
NODES
h1
h2
```

This creates two virtual hosts, with hostnames `h1` and `h2`.  When started,
their hostnames are assigned accordingly.  This can be seen in the title of the
terminal as well as the command-line prompt.  You can also retrieve the
hostname by simply running the following from the command line:

```
$ hostname
```

Or it can be retrieved using Python with the following:

```
import socket
hostname = socket.gethostname()
```

Additional options can be specified for any host.  For example, we might like
to provide `h1` with additional configuration, such as the following:

```
NODES
h1 gw4=10.0.0.4,terminal=false
h2
```

In this case, 10.0.0.4 has been designated as the default IPv4 gateway for
`h1`, and no terminal will be started for `h1` as would normally be the case.

In general, the syntax for a host is:

```
<hostname> [name=val[,name=val[...]]
```

That is, if there are additional options, there is a space after the hostname,
and those options come after the space. The options consist a comma-delimited
list of name-value pairs, each name-value connected by `=`.  The defined host
option names are the following, accompanied by the expected value:
 - `gw4`: an IPv4 address representing the gateway or default router.  Example:
   `10.0.0.4`.  Default: no IPv4 gateway.
 - `gw6`: an IPv6 address representing the gateway or default router.  Example:
   `fd00::4`.  Default: no IPv6 gateway.
 - `native_apps`: a boolean (i.e., `true` or `false`) indicating whether or not
   the native network stack should be used.  Default: `true`.
 - `terminal`: a boolean (i.e., `true` or `false`) indicating whether or not a
   terminal should be spawned.  Sometimes neither an interactive interface with
   a virtual host nor console output is necessary, in which case `false` would
   be appropriate.  An example of this is if a script is designated to be run
   automatically with the host using the `prog` attribute.  Default: `true`.
 - `type`: a string representing the type of node.  The supported types are:
   `host`, `switch`, `router`.  Default: `host`.
 - `prog`: a string representing a program and its arguments, which are to be
   run, instead of an interactive shell.  The program path and its arguments
   are delimited by `|`.  For example, `echo|foo|bar` would execute
   `echo foo bar`.  Default: execute an interactive shell.

## Communicating with the Calling Process

Often it is useful for the virtual host to send messages back to the process
that invoked all the virtual hosts (i.e., the `cougarnet` process).  This
enables the logs for all messages to be received and printed in a single
location.  To accomplish this, each virtual process has the
`COUGARNET_COMM_SOCK`  environment variable set, the value of which is a path
corresponding to a UNIX domain socket (i.e., family `AF_UNIX`) of type
`SOCK_DGRAM`.  Once all the virtual machines are started, the `cougarnet`
process will print to standard output all messages received on this socket.

For example, the following command, issued from a virtual host, will result in
a UDP datagram being sent to the UNIX domain socket on which the `cougarnet`
process is listening.

```
echo -n `hostname`,hello world | socat - UNIX-SENDTO:$COUGARNET_COMM_SOCK
```

The equivalent Python code is the following:

```
import os
import socket

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM, 0)
sock.connect(os.environ['COUGARNET_COMM_SOCK'])
hostname = socket.gethostname()
sock.send(f'{hostname},hello world'.encode('utf-8'))
```

The `cougarnet` process will print a single line of output that will look
something like this:

```
13.766   h1  hello world
```

The three components of the output message can be explained as follows:
 - *Relative time* (`13.766`): the relative time, i.e., the number of seconds
   that have elapsed since the virtual hosts were started by the `cougarnet`
   process.
 - *Hostname* (`h1`): the hostname of the virtual host from which the message
   was sent.  Note that the hostname must be sent by the virtual host.  It is
   done by prepending the hostname, separating it from the actual message with
   a comma.  Thus, the following message in the previous example:
   ```
   echo -n `hostname`,hello world
   ```
 - *Message* (`hello world`): the actual message to be logged and/or printed.

The `rawpkt.BaseFrameHandler` has a function `log()` which can be used to issue
messages.  So if you subclass `rawpkt.BaseFrameHandler` and then call `log()`,
it will handle the formatting for you.

TODO: more on this BaseFrameHandler below.  For an example, refer to
BaseFrameHandler documentation.



## Host Types

## Running Programs

When a host runs the 
TODO: environment vars

## Getting all Interfaces


# Virtual Links

Virtual links are created between two virtual interfaces with the `ip link`
command, using type `veth`: such that one virtual interface is associated with
one network namespace and the second is associated with another network
namespace.  Those two namespaces are the two associated with two processes
 that are running in their own namespaces.  These processes, of course, are
[virtual hosts](#virtual-hosts), so these virtual links become the basis for
connections between virtual hosts.


## Configuration

In the Cougarnet configuration file, a link between two hosts is designated in
the `LINKS` section by indicating two hosts on a line, separated by a space.
Consider the `LINKS` section of the [example configuration given
previously](#getting-started):

```
LINKS
h1,10.0.0.1/24 h2,10.0.0.2/24
```

This results in a virtual interface being created for each virtual host.  Each
interface can be configured with zero or more addresses, up to one MAC address
and zero or more IPv4 and/or IPv6 addresses.  The list of addresses is
comma-separated.  For example, we might like to configure the `h1` and  `h2`
virtual interfaces thus:

```
LINKS
h1,00:00:aa:aa:aa:aa,10.0.0.1/24,fd00::1/64 h2,10.0.0.2/24,fd00::2/64
```

In this case, `h1`'s virtual network interface will not only have IPv4 address
10.0.0.1, but also MAC address 00:00:aa:aa:aa:aa and IPv6 address fd00::1/64.
Likewise, `h2`'s virtual network interface will have IPv6 address fd00::2/64,
in addition to IPv4 address 10.0.0.2.

The interface names for each host created dynamically, starting with `eth0`,
then `eth1`, etc.  The interfaces for a host can be viewed by running the
folloing from the command line:

```
$ ip addr
```

Or they can be retrieved from the special "directory" `/sys/class/net`.  For
example, the Python code to retrieve the names of all interfaces except
loopback interfaces (i.e., starting with `lo`) is the following:

```
import os
ints = [i for i in os.listdir('/sys/class/net/') if not i.startswith('lo')]
```
        
Additional options can be specified for any link.  For example, we might like
to provide the (original) link between `h1` and `h2` with additional
configuration, such as the following:

```
LINKS
h1,10.0.0.1/24 h2,10.0.0.2/24 bw=1Mbps,delay=20ms,loss=10%
```

In this case, the bandwidth of the link will be 1Mbps, instead of the default
10Gbps, an artificial delay of 20 ms will be applied to any packet crossing the
link, and an artificial packet loss rate of 10% will be applied to packets
crossing the link.  That is, any packet has a 10% chance of being dropped.

In general, the syntax for a link is:

```
<hostname>[,<addr>[,<addr>...]] <hostname>[,<addr>[,<addr>...]] [name=val[,name=val[...]]
```

That is, if there are additional options, there is a space after the interface
information for the second host, and those options come after the space. The
options consist a comma-delimited list of name-value pairs, each name-value
connected by `=`.  The defined link option names are the following, accompanied
by the expected value:
 - `bw`:  an artificial bandwith to apply to the link.  Example: `1Mbps`.
   Default: 10Gbps.
 - `delay`: an artificial delay to be added to all packets on the link.
   Example: `50ms`.  Default: no delay.
 - `loss`: an average rate of artificial loss that should be applied
   to the link.  Example: `10%`.  Default: no loss.
 - `vlan`: the VLAN id (integer with value 0 through 1023) associated with the
   link.  Example: `20`.  Default: no VLAN id.
 - `trunk`: a boolean (i.e., `true` or `false`) indicating whether this link
   should be a trunk link between two switches, such that 802.1Q frames are
   passed on that link.  Default: `false`.


## Bi-Directionality of Link Attributes

A note about the link-specific attributes.  They are applied in both
directions.  Thus, using the example configuration above, running a `ping`
command between `h1` and `h2` will result in something like this:

```
h2$ ping h1
PING h1 (10.0.0.1) 56(84) bytes of data.
64 bytes from h1 (10.0.0.1): icmp_seq=2 ttl=64 time=41.5 ms
64 bytes from h1 (10.0.0.1): icmp_seq=4 ttl=64 time=41.3 ms
64 bytes from h1 (10.0.0.1): icmp_seq=5 ttl=64 time=41.1 ms
64 bytes from h1 (10.0.0.1): icmp_seq=6 ttl=64 time=40.8 ms
64 bytes from h1 (10.0.0.1): icmp_seq=7 ttl=64 time=40.8 ms
64 bytes from h1 (10.0.0.1): icmp_seq=8 ttl=64 time=41.8 ms
64 bytes from h1 (10.0.0.1): icmp_seq=9 ttl=64 time=41.4 ms
64 bytes from h1 (10.0.0.1): icmp_seq=10 ttl=64 time=41.3 ms

--- h1 ping statistics ---
10 packets transmitted, 8 received, 20% packet loss, time 9061ms
rtt min/avg/max/mdev = 40.811/41.242/41.775/0.306 ms
```

Note that the round-trip time (RTT) was consistently around just over 40 ms
(i.e., 20 ms for the ICMP request and 20 ms for the ICMP response).  Also, any
packet has a 10% chance of being lost.  Because a successful `ping` requires
the successful transmission of both an ICMP request and the corresponding ICMP
response, the chance of success is 81%:

```
P(success)
  = P(neither pkt is lost)
  = (1 - P(loss)) * (1 - P(loss))
  = (1 - 0.10) * (1 - 0.10)
  = 0.81
```

In other words, 1 in 5 ICMP request messages sent will not result in an ICMP
response message received.  In the example above, packets 1 and 3 were lost.


## VLAN Attributes

Currently, the `vlan` and `trunk` attributes are only useful when the host is
not configured for native apps (i.e., when not enabled with the `native_apps`
host option or the `--native-apps` command-line option).

The `vlan` and `trunk` attributes have no effect unless at least one of the
hosts is of type `switch`.  If `vlan` is specified for a switch, then the
virtual switch is made aware of the VLAN assignment via an environment
variable.  Consider the following configuration.

```
NODES
h1
h2 type=switch
h3

LINKS
h1 h2 vlan=25
h2 h3 vlan=32
```

In this case, both `h1` and `h3` are connected to `h2`, a switch.  The link
between `h2` and `h1` uses VLAN 25, and the link between `h2` and `h3` uses
VLAN 32.  In this case, `h2` the process associated with `h2` will have the
following environment variables set:

```
COUGARNET_VLAN_ETH0=25
COUGARNET_VLAN_ETH1=32
```

# `cougarnet` Usage
