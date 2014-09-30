from __future__ import absolute_import, print_function
import json
import tornado.ioloop
import tornado.httpserver
from .. import controller, flow
from . import app


class Stop(Exception):
    pass


class WebFlowView(flow.FlowView):
    def __init__(self, connection, *args, **kwargs):
        self.connection = connection
        super(WebFlowView, self).__init__(*args, **kwargs)
        self.emit("all_flows", [f.get_state(short=True) for f in self.flows])

    def add(self, f):
        index = super(WebFlowView, self).add(f)
        if index is not None:
            self.emit("add_flow", f.get_state(short=True))

    def update(self, f):
        if super(WebFlowView, self).update(f):
            self.emit("update_flow", f.get_state(short=True))

    def remove(self, f):
        if super(WebFlowView, self).remove(f):
            self.emit("delete_flow", f.get_state(short=True))

    def emit(self, type, data):
        self.connection.write_message(
            json.dumps(
                {
                    "type": type,
                    "data": data
                }
            )
        )


class WebState(flow.StateBase):
    def __init__(self):
        super(WebState, self).__init__()

    def open_view(self, connection, filt):
        view = WebFlowView(connection, self._flow_list, filt)
        self._views.append(view)
        return view

    def close_view(self, view):
        self._views.remove(view)


class Options(object):
    attributes = [
        "app",
        "app_domain",
        "app_ip",
        "anticache",
        "anticomp",
        "client_replay",
        "eventlog",
        "keepserving",
        "kill",
        "intercept",
        "no_server",
        "refresh_server_playback",
        "rfile",
        "scripts",
        "showhost",
        "replacements",
        "rheaders",
        "setheaders",
        "server_replay",
        "stickycookie",
        "stickyauth",
        "stream_large_bodies",
        "verbosity",
        "wfile",
        "nopop",

        "wdebug",
        "wport",
        "wiface",
    ]

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for i in self.attributes:
            if not hasattr(self, i):
                setattr(self, i, None)


class WebMaster(flow.FlowMaster):
    def __init__(self, server, options):
        self.options = options
        super(WebMaster, self).__init__(server, WebState())
        self.app = app.Application(self.state, self.options.wdebug)


        self.last_log_id = 0

    def tick(self):
        flow.FlowMaster.tick(self, self.masterq, timeout=0)

    def run(self):  # pragma: no cover
        self.server.start_slave(
            controller.Slave,
            controller.Channel(self.masterq, self.should_exit)
        )
        iol = tornado.ioloop.IOLoop.instance()

        http_server = tornado.httpserver.HTTPServer(self.app)
        http_server.listen(self.options.wport)

        tornado.ioloop.PeriodicCallback(self.tick, 5).start()
        try:
            iol.start()
        except (Stop, KeyboardInterrupt):
            self.shutdown()

    def handle_request(self, f):
        flow.FlowMaster.handle_request(self, f)
        if f:
            f.reply()
        return f

    def handle_response(self, f):
        flow.FlowMaster.handle_response(self, f)
        if f:
            f.reply()
        return f

    def handle_error(self, f):
        flow.FlowMaster.handle_error(self, f)
        return f

    def handle_log(self, l):
        self.last_log_id += 1
        app.ClientConnection.broadcast(
            "add_event", {
                "id": self.last_log_id,
                "message": l.msg,
                "level": l.level
            }
        )
        self.add_event(l.msg, l.level)
        l.reply()
