import bisect
import fcntl
import os
import select
import signal
import socket
import struct
import time

import pcapy

# From: /usr/include/asm-generic/socket.h:
SO_BINDTODEVICE = 25

class EndRun(Exception):
    pass

class Event(object):
    '''
    An Event to be scheduled.  An Event has an action, as well as positional
    and keyword arguments.
    '''

    def __init__(self, action, args, kwargs):
        self.action = action
        self.args = args
        self.kwargs = kwargs

    def __repr__(self):
        return str(self)

    def __str__(self):
        return '<Event: %s>' % (repr(self.action))

    def __lt__(self, other):
        return id(self) < id (other)

    def run(self):
        return self.action(*(self.args), **(self.kwargs))

class NetworkEventLoop(object):
    '''
    An event loop for monitoring network interfaces for incoming frames, and
    other related events.
    '''

    def __init__(self, handle_frame):
        self._handle_frame = handle_frame
        self.wake_fh_read, self.wake_fh_write = None, None
        self.epoll = select.epoll()
        self.sock_to_int = {}
        self.int_to_sock4 = {}
        self.int_to_sock6 = {}
        self.sock_to_pc = {}
        self.events = []
        self._setup_receive_sockets()
        self._register_wake_pipe()
        self._ref_time = None

    def _set_wakeup_fd(self, fd):
        def _send_sig(sig, stack_frame):
            sig_bytes = struct.pack('!B', sig)
            os.write(fd, sig_bytes)
        signal.signal(signal.SIGALRM, _send_sig)

    def _end_run(self):
        raise EndRun()

    def _register_wake_pipe(self):
        fdr, fdw = os.pipe()
        self.wake_fh_read, self.wake_fh_write = os.fdopen(fdr, 'rb'), os.fdopen(fdw, 'wb')
        fcntl.fcntl(self.wake_fh_read.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(self.wake_fh_write.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)

        self._set_wakeup_fd(self.wake_fh_write.fileno())
        self.epoll.register(self.wake_fh_read.fileno(), select.EPOLLIN)

    def _setup_receive_sockets(self):
        ints = os.listdir('/sys/class/net/')
        for intf in ints:

            if intf.startswith('lo'):
                continue

            # For receiving...
            pc = pcapy.open_live(intf, 0, 0, 1)
            pc.setnonblock(1)
            self.epoll.register(pc.getfd(), select.EPOLLIN)
            self.sock_to_int[pc.getfd()] = intf
            self.sock_to_pc[pc.getfd()] = pc

    def _handle_wake_event(self):
        while True:
            try:
                b = self.wake_fh_read.read(1024)
            except IOError:
                break
            if not b:
                break

    def _consume_epoll_events(self):
        events = self.epoll.poll(0)
        for fd, event in events:
            if fd == self.wake_fh_read.fileno():
                continue
            pc = self.sock_to_pc[fd]
            pc.next()

    def _handle_epoll_events(self):
        try:
            events = self.epoll.poll()
        except IOError:
            # interrupted
            return
        for fd, event in events:
            if fd == self.wake_fh_read.fileno():
                self._handle_wake_event()
                continue
            intf = self.sock_to_int[fd]
            pc = self.sock_to_pc[fd]
            hdr, frame = pc.next()
            ts = self.time()
            self._handle_frame(ts, intf, frame)

    def _handle_scheduled_events(self):
        handled = False
        while self.events:
            ts, event = self.events[0]
            if time.time() >= ts:
                self.events.pop(0)
                event.run()
                handled = True
            else:
                break
        if handled and self.events:
            signal.setitimer(signal.ITIMER_REAL, max(ts - time.time(), 0))

    def reset_events(self):
        self.events = []
        self._ref_time = None

    def _reset_ref_time(self):
        self._ref_time = time.time()

    def _relativize_time(self, ts):
        return ts - self._ref_time

    def time(self):
        return self._relativize_time(time.time())

    def _relativize_event_times(self):
        new_events = []
        now = time.time()
        for ts, event in self.events:
            ts = now + ts
            new_events.append((ts, event))
        self.events = new_events
        if self.events:
            ts = self.events[0][0]
            signal.setitimer(signal.ITIMER_REAL, max(ts - time.time(), 0))

    def schedule_event(self, seconds, action, args=None, kwargs=None):
        '''
        Schedule an action to happen in the future, based on a time relative to
        the current time.  Return the Event() instance corresponding to the
        scheduled action.

        seconds: a float, the amount of time in the future that the action
                should happen.
        action: the function or method that should be called.
        args: a tuple of one or more arguments that should be passed to the
                function or method when it is called.
        kwargs: a dictionary of one or more keyword argument pairs that should
                be passed to the function or method when it is called.
        '''

        if seconds < 0:
            raise ValueError('Relative time cannot be negative: %d' % seconds)
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        if self._ref_time is None:
            ts = seconds
        else:
            ts = time.time() + seconds
        return self.schedule_event_abs(ts, action, args, kwargs, force=True)

    def schedule_event_abs(self, ts, action, args, kwargs, force=False):
        '''
        Schedule an action to happen at a specific time in the future.  Return
        the Event() instance corresponding to the scheduled action.

        seconds: a float representing the time in the future that the action
                should happen.
        action: the function or method that should be called.
        args: a tuple of one or more arguments that should be passed to the
                function or method when it is called.
        kwargs: a dictionary of one or more keyword argument pairs that should
                be passed to the function or method when it is called.
        '''

        if ts < time.time() and not force:
            raise ValueError('Event is scheduled in the past: %f' % ts)

        event = Event(action, args, kwargs)
        event_tuple = (ts, event)
        i = bisect.bisect(self.events, event_tuple)
        self.events.insert(i, event_tuple)
        if i == 0:
            signal.setitimer(signal.ITIMER_REAL, max(ts - time.time(), 0))
        return event

    def cancel_event(self, event):
        '''
        Remove a given event from the queue of scheduled events.

        event: the Event instance that is to be removed/canceled.
        '''

        found = False
        for i, (ts, ev) in enumerate(self.events):
            if ev == event:
                found = True
                break
        if found:
            self.events.remove((ts, event))
            if i == 0 and self.events:
                ts = self.events[0][0]
                signal.setitimer(signal.ITIMER_REAL, max(ts - time.time(), 0))

    def run(self):
        '''
        Carry out scheduled events and also handle epoll events, e.g., from raw
        packet processes.
        '''

        self._consume_epoll_events()
        self._relativize_event_times()
        self._reset_ref_time()
        while True:
            try:
                self._handle_scheduled_events()
                self._handle_epoll_events()
            except EndRun as e:
                break