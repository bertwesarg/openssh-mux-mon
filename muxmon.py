#!/usr/bin/env python2

import os
import os.path
import stat
import sys
import subprocess

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import gconf
import pynotify
import pyinotify
import appindicator

import SshMuxClient

GCONF_APP = '/apps/sshmuxmon'
GCONF_APP_PATH = os.path.join(GCONF_APP, 'path')
GCONF_APP_HOSTS = os.path.join(GCONF_APP, 'hosts')

class SshMuxEntry(SshMuxClient.SshMuxClient):
    name = ''
    item = None
    sub = None
    n_fwds = 0
    n_sessions = 0

    def __init__(self, path):
        SshMuxClient.SshMuxClient.__init__(self, path)

class SshMuxIndicator(
    appindicator.Indicator,
    pyinotify.Notifier):

    known = {}
    new = {}
    root = None

    def __init__(self):

        self.icon_path = os.path.normpath(os.path.join(
            os.getcwd(),
            os.path.dirname(__file__),
            'icons'))
        self.icon_name = 'file://' + os.path.join(
            self.icon_path, 'openssh-256.png')

        self._gcc = gconf.client_get_default()
        self._gcc.add_dir(GCONF_APP, gconf.CLIENT_PRELOAD_NONE)
        self._gc_nid = self._gcc.notify_add(GCONF_APP, self.gconf_notify, None)

        pynotify.init('SSH-MUX-Monitor')

        self._wm = pyinotify.WatchManager()
        pyinotify.Notifier.__init__(self, self._wm, self.process_inotify_event)
        self._wd = None
        self._w = gobject.io_add_watch(self._wm.get_fd(), gobject.IO_IN, self.process_io_watch)

        appindicator.Indicator.__init__(self,
            'ssh-mux-monitor',
            'openssh',
            appindicator.CATEGORY_COMMUNICATIONS,
            self.icon_path)
        self.set_status(appindicator.STATUS_ACTIVE)

        # create a menu
        menu = gtk.Menu()

        item = gtk.SeparatorMenuItem()
        menu.append(item)
        item.show()

        self.close_all_item = gtk.ImageMenuItem(gtk.STOCK_DISCONNECT)
        self.close_all_item.set_label('Disconnect All')
        menu.append(self.close_all_item)
        self.close_all_item.connect('activate', self.close_all_activate)
        self.close_all_item.show()
        self.close_all_item.set_sensitive(False)

        self.connect_to = gtk.ImageMenuItem(gtk.STOCK_CONNECT)
        self.connect_to.set_label('Connect to')
        menu.append(self.connect_to)
        self.connect_to.connect('activate', self.connect_to_activate)
        self.connect_to.set_submenu(gtk.Menu())
        self.connect_to.show()

        item = gtk.SeparatorMenuItem()
        menu.append(item)
        item.show()

        item = gtk.ImageMenuItem(gtk.STOCK_PREFERENCES)
        item.set_label('Preferences...')
        menu.append(item)
        item.connect('activate', self.preferences_activate)
        item.show()

        item = gtk.SeparatorMenuItem()
        menu.append(item)
        item.show()

        item = gtk.ImageMenuItem(gtk.STOCK_QUIT)
        menu.append(item)
        item.connect('activate', self.quit_activate)
        item.show()

        self.static_menu_entry_len = len(menu.get_children())
        self.set_menu(menu)

        self.reread_path()

    def __del__(self):
        gobject.source_remove(self._w)
        if self._gc_nid:
            self._gcc.notify_remove(self._gc_nid)

    def reread_path(self):
        try:
            s = self._gcc.get_string(GCONF_APP_PATH)
            if self.root and s and os.path.samefile(self.root, s):
               return
        except:
            s = None

        # there are not the same, cleanup previous root, if any
        if self.root:
            # clear previous known mux
            for mc in self.known.itervalues():
                mc.close()
                self.get_menu().remove(mc.item)
            self.close_all_item.set_sensitive(False)
            if self.root in self._wd:
                self._wm.del_watch(self._wd[self.root])
        self.known = {}
        self.root = None
        self._wd = None

        if not s:
            return
        if not os.path.isdir(s):
            return

        self.root = s
        self._wd = self._wm.add_watch(self.root, pyinotify.IN_CREATE | pyinotify.IN_DELETE)

        muxs = []
        for path in os.listdir(self.root):
            full = os.path.join(self.root, path)
            try:
                sb = os.stat(full)

                if not stat.S_ISSOCK(sb.st_mode):
                    continue
                muxs += [(full, sb.st_mtime)]

            except:
                continue

        muxs.sort(key=lambda x: x[1])
        for full, mtime in muxs:
            try:
                mc = SshMuxEntry(full)
                res, exts = mc.connect()
                if not res:
                    continue

                res, name = mc.info('%r@%h:%p')
                if not res:
                    continue

                if name[-3:] == ':22':
                    name = name[:-3]
                mc.name = name
                self.known[full] = mc
                #print >>sys.stderr, 'Already existing mux: %s' % (name,)
                self.add_to_menu(mc)
            except:
                continue

    def add_to_menu(self, mc):
        self.close_all_item.set_sensitive(True)

        menu = self.get_menu()

        mc.item = gtk.ImageMenuItem()
        mc.item.set_label(mc.name)
        image = gtk.image_new_from_icon_name('network-server', gtk.ICON_SIZE_MENU)
        mc.item.set_image(image)
        mc.item.set_always_show_image(True)
        menu.insert(mc.item, len(menu.get_children()) - self.static_menu_entry_len)
        mc.item.connect('activate', self.mux_activate, mc)
        mc.item.show()

        mc.sub = gtk.Menu()

        item = gtk.MenuItem('Forwards (click to close):')
        mc.sub.append(item)
        item.set_sensitive(False)
        item.show()

        item = gtk.ImageMenuItem(gtk.STOCK_ADD)
        item.set_label('New...')
        mc.sub.append(item)
        #item.set_sensitive(False)
        item.connect('activate', self.mux_new_forward, mc)
        item.show()

        item = gtk.SeparatorMenuItem()
        mc.sub.append(item)
        item.show()

        item = gtk.MenuItem('Sessions:')
        mc.sub.append(item)
        item.set_sensitive(False)
        item.show()

        item = gtk.SeparatorMenuItem()
        mc.sub.append(item)
        item.show()

        item = gtk.ImageMenuItem(gtk.STOCK_STOP)
        mc.sub.append(item)
        item.connect('activate', self.mux_stop_activate, mc)
        item.show()

        item = gtk.ImageMenuItem(gtk.STOCK_DISCONNECT)
        mc.sub.append(item)
        item.connect('activate', self.mux_close_activate, mc)
        item.show()
        
        mc.item.set_submenu(mc.sub)

        self.set_menu(menu)

    def quit_activate(self, w):
        #print 'exit indicator'
        gtk.main_quit()

    def preferences_activate(self, w):
        SshMuxPrefsDialog(self._gcc)

    def close_all_activate(self, w):
        for mc in self.known.itervalues():
            mc.exit()

    def connect_to_activate(self, w):
        try:
            hosts = self._gcc.get_list(GCONF_APP_HOSTS, gconf.VALUE_STRING)
        except:
           hosts = []

        submenu = w.get_submenu()
        for child in submenu.get_children():
            submenu.remove(child)

        # populate devices menu
        for host in hosts:
            item = gtk.ImageMenuItem()
            item.set_label(host)
            try:
                image = gtk.image_new_from_icon_name('network-server', gtk.ICON_SIZE_MENU)
                item.set_image(image)
                item.set_always_show_image(True)
            except:
                pass

            submenu.append(item)
            item.connect('activate', self.connect_to_host_activate, host)
            item.show()

        w.set_submenu(submenu)

    def connect_to_host_activate(self, w, host):
        ret = subprocess.call(['ssh', '-NfT', host, '/bin/true'])
        pass

    def mux_activate(self, w, mc):
        # update forwards and sessions
        for i in range(mc.n_fwds):
            mc.sub.remove(mc.sub.get_children()[1])
        for i in range(mc.n_sessions):
            mc.sub.remove(mc.sub.get_children()[4])

        mc.n_fwds = 0
        mc.n_sessions = 0
        res, fwds = mc.forwards()
        if not res:
            return

        res, sessions = mc.sessions()
        if not res:
            return

        for fwd in fwds:
            fid, ftype, lh, lp, ch, cp = fwd
            label = ''
            lh = lh + ':'
            if lh == ':':
                lh = ''
            if ftype == 'local':
                label = '%s%u -> %s:%u' % (lh, lp, ch, cp,)
            if ftype == 'remote':
                label = '%s:%u <- %s%u' % (ch, cp, lh, lp,)
            if ftype == 'dynamic':
                label = '%s%u -> *:*' % (lh, lp,)
            item = gtk.ImageMenuItem(gtk.STOCK_CANCEL)
            item.set_label(label)
            mc.sub.insert(item, 1 + mc.n_fwds)
            mc.n_fwds += 1
            item.connect('activate', self.mux_close_forward, mc, fwd)
            item.show()

        for s in sessions:
            sid, stype, rid, cid, tname, rname = s

            session_name, session_action = rname.split(': ', 2)
            try:
                session_name, session_args = session_name.split('(', 2)
                session_args = session_args[:-1]
            except:
                session_args = None

            item = gtk.ImageMenuItem()
            item.set_label('%s' % (rname,))
            if tname == 'stdio-forward':
                image = gtk.image_new_from_icon_name('preferences-system-network-proxy-symbolic', gtk.ICON_SIZE_MENU)
                item.set_image(image)
            if session_name == 'subsystem-session' and session_action == 'sftp':
                image = gtk.image_new_from_icon_name('folder-remote-ftp', gtk.ICON_SIZE_MENU)
                item.set_image(image)
            if session_name == 'shell-session':
                image = gtk.image_new_from_icon_name('terminal', gtk.ICON_SIZE_MENU)
                item.set_image(image)
            if session_name == 'exec-session':
                image = gtk.image_new_from_stock(gtk.STOCK_EXECUTE, gtk.ICON_SIZE_MENU)
                item.set_image(image)
            mc.sub.insert(item, 4 + mc.n_fwds + mc.n_sessions)
            mc.n_sessions += 1
            item.show()

        mc.item.set_submenu(mc.sub)

    def mux_close_forward(self, w, mc, fwd):
        #print 'closing forward [%s] %s:%u -> %s:%u' % (fwd[1], fwd[2], fwd[3], fwd[4], fwd[5],)
        mc.close_forward(fwd[1], fwd[2], fwd[3], fwd[4], fwd[5])

    def mux_new_forward(self, w, mc):
        SshMuxForwardingDialog(mc)

    def mux_stop_activate(self, w, mc):
        #print 'stoping %s' % (mc.path,)
        mc.stop()

    def mux_close_activate(self, w, mc):
        #print 'closing %s %s:%r' % (mc.path, type(mc), mc,)
        mc.exit()

    def process_io_watch(self, source, cb_condition):
        self.read_events()
        self.process_events()
        return True

    def process_file_create(self, event):
        #print >>sys.stderr, 'file_create %s' % (event.pathname,)

        try:
            sb = os.stat(event.pathname)
        except:
            #print >>sys.stderr, ' could\'t stat %s' % (event.pathname,)
            return

        if not stat.S_ISSOCK(sb.st_mode):
            #print >>sys.stderr, ' not a socket %s' % (event.pathname,)
            return

        if event.pathname in self.known:
            #print >>sys.stderr, ' already known %s' % (event.pathname,)
            return

        # defer notification, the mux listener will rename it to the final path
        # when he is ready
        #print >>sys.stderr, ' starting grace period'
        self.new[event.pathname] = gobject.timeout_add(100,
            self.process_end_of_grace,
            event.pathname)

    def process_file_delete(self, event):
        #print >>sys.stderr, 'file_delete %s' % (event.pathname,)

        if event.pathname in self.new:
            #print >>sys.stderr, 'grace period not survided'
            gobject.source_remove(self.new[event.pathname])
            del self.new[event.pathname]
            return
        
        if event.pathname not in self.known:
            #print >>sys.stderr, ' not known'
            return

        mc = self.known[event.pathname]
        del self.known[event.pathname]
        mc.close()
        self.get_menu().remove(mc.item)
        if len(self.known) == 0:
            self.close_all_item.set_sensitive(False)
        n = pynotify.Notification(mc.name, 'MUX Closed', self.icon_name)
        n.set_urgency(pynotify.URGENCY_CRITICAL)
        n.set_timeout(5000)
        n.show()

    def process_inotify_event(self, event):
        #print >>sys.stderr, ' event %s' % (arg,)
        if event.mask == pyinotify.IN_CREATE:
            return self.process_file_create(event)
        elif event.mask == pyinotify.IN_DELETE:
            return self.process_file_delete(event)

    def process_end_of_grace(self, path):
        del self.new[path]

        # lets try to get an connection to the socket

        #print >>sys.stderr, ' grace period survived %s' % (path,)
        mc = SshMuxEntry(path)
        res, exts = mc.connect()
        if res:
            res, name = mc.info('%r@%h:%p')
        if res:
            #print >>sys.stderr, ' new %r' % (name,)
            mc.name = name
            self.known[path] = mc
            n = pynotify.Notification(name, 'MUX Established', self.icon_name)
            n.set_urgency(pynotify.URGENCY_LOW)
            n.set_timeout(2500)
            n.show()
            self.add_to_menu(mc)

        return False

    def gconf_notify(self, client, cnxn_id, entry, arg):
        if entry.key == GCONF_APP_PATH and entry.value is not None and entry.value.type == gconf.VALUE_STRING:
            self.reread_path()

class SshMuxPrefsDialog(object):
    def __init__(self, gcc):
        self._gcc = gcc
        self.standalone = False
        if not self._gcc:
            self._gcc = gconf.client_get_default()
            self._gcc.add_dir(GCONF_APP, gconf.CLIENT_PRELOAD_NONE)
            self.standalone = True

        self.dialog = gtk.Dialog('SSH MUX Monitor Preferences',
                None, 0, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_APPLY, gtk.RESPONSE_APPLY))
        # response when closing the dialog via the window manager
        self.dialog.set_default_response(gtk.RESPONSE_CANCEL)

        hbox = gtk.HBox(False, 2)

        self.dialog.vbox.pack_start(hbox, False, False, 0)

        label = gtk.Label('Directory to monitor: ')

        filechooser = gtk.FileChooserButton('Choose directory...', None)
        filechooser.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        try:
            s = self._gcc.get_string(GCONF_APP_PATH)
            if s and os.path.isdir(s):
                filechooser.set_filename(s)
        except:
            filechooser.set_filename(os.path.expanduser('~'))

        hbox.pack_start(label, False, False, 0)
        hbox.pack_end(filechooser, True, True, 0)

        self.dialog.connect('response', self.response_cb, filechooser)

        self.dialog.show_all()

    def select_mux_path(self, filechooser):
        path = filechooser.get_filename()
        if filename and os.path.isdir(filename):
                entry.set_text(filename)

    def response_cb(self, widget, event, filechooser):
        if event == gtk.RESPONSE_APPLY:
            path = filechooser.get_filename()
            if path and os.path.isdir(path):
                self._gcc.set_string(GCONF_APP_PATH, path)
        widget.destroy()
        if self.standalone:
            gtk.main_quit()

class SshMuxForwardingDialog(object):

    _to_fwd_type = [
        SshMuxClient.MUX_FWD_LOCAL,
        SshMuxClient.MUX_FWD_REMOTE,
        SshMuxClient.MUX_FWD_DYNAMIC
    ]

    def __init__(self, mc):
        self.mc = mc

        self.dialog = gtk.Dialog('New forwarding for %s' % (self.mc.name,),
                None, 0, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_APPLY, gtk.RESPONSE_APPLY))
        # response when closing the dialog via the window manager
        self.dialog.set_default_response(gtk.RESPONSE_CANCEL)

        tab = gtk.Table(5, 2, False)

        self.dialog.vbox.pack_start(tab, True, True, 0)

        self.fwd_select = gtk.combo_box_new_text()
        self.fwd_select.append_text('Local forwarding')
        self.fwd_select.append_text('Remote forwarding')
        self.fwd_select.append_text('Dynamic forwarding')
        self.fwd_select.connect('changed', self.type_changed_cb)
        tab.attach(self.fwd_select, 0, 2, 0, 1, gtk.EXPAND|gtk.FILL, 0)

        # bind_address
        self.ba_label = gtk.Label('Bind address:')
        right_alignment = gtk.Alignment(0.0, 0.5, 0.0, 0.0)
        right_alignment.add(self.ba_label)
        tab.attach(right_alignment, 0, 1, 1, 2, gtk.FILL, gtk.FILL)
        # listen_port
        self.lp_label = gtk.Label('Listen port:')
        right_alignment = gtk.Alignment(0.0, 0.5, 0.0, 0.0)
        right_alignment.add(self.lp_label)
        tab.attach(right_alignment, 0, 1, 2, 3, gtk.FILL, gtk.FILL)
        # connect_host
        self.ch_label = gtk.Label('Target host:')
        right_alignment = gtk.Alignment(0.0, 0.5, 0.0, 0.0)
        right_alignment.add(self.ch_label)
        tab.attach(right_alignment, 0, 1, 3, 4, gtk.FILL, gtk.FILL)
        # connect_port
        self.cp_label = gtk.Label('Target port:')
        right_alignment = gtk.Alignment(0.0, 0.5, 0.0, 0.0)
        right_alignment.add(self.cp_label)
        tab.attach(right_alignment, 0, 1, 4, 5, gtk.FILL, gtk.FILL)

        hbox2 = gtk.HBox(False, 2)
        self.ba_entry = gtk.Entry()
        hbox2.pack_start(self.ba_entry, True, True, 0)
        self.ba_all_check = gtk.CheckButton('All')
        self.ba_all_check.connect('toggled', self.toggled_cb, self.ba_entry)
        hbox2.pack_end(self.ba_all_check, False, False, 0)
        tab.attach(hbox2, 1, 2, 1, 2, gtk.EXPAND|gtk.FILL, 0)

        hbox2 = gtk.HBox(False, 2)
        port_adj = gtk.Adjustment(1.0, 1.0, 65535, 1.0, 10.0, 0.0)
        self.lp_entry = gtk.SpinButton(port_adj, 0, 0)
        hbox2.pack_start(self.lp_entry, True, True, 0)
        self.lp_auto_check = gtk.CheckButton('Auto')
        self.lp_auto_check.connect('toggled', self.toggled_cb, self.lp_entry)
        hbox2.pack_end(self.lp_auto_check, False, False, 0)
        tab.attach(hbox2, 1, 2, 2, 3, gtk.EXPAND|gtk.FILL, 0)

        self.ch_entry = gtk.Entry()
        tab.attach(self.ch_entry, 1, 2, 3, 4, gtk.EXPAND|gtk.FILL, 0)

        port_adj = gtk.Adjustment(1.0, 1.0, 65535, 1.0, 32.0, 0.0)
        self.cp_entry = gtk.SpinButton(port_adj, 0, 0)
        tab.attach(self.cp_entry, 1, 2, 4, 5, gtk.EXPAND|gtk.FILL, 0)

        self.dialog.connect('response', self.response_cb)

        self.fwd_select.set_active(0)
        self.ba_all_check.set_active(True)

        self.dialog.show_all()

    def type_changed_cb(self, w):
        fwd_type = self._to_fwd_type[w.get_active()]
        self.lp_entry.set_sensitive(True)
        self.lp_auto_check.set_active(False)
        self.lp_auto_check.set_sensitive(False)
        self.ch_label.set_sensitive(True)
        self.ch_entry.set_sensitive(True)
        self.cp_label.set_sensitive(True)
        self.cp_entry.set_sensitive(True)

        if fwd_type == SshMuxClient.MUX_FWD_REMOTE:
            self.lp_auto_check.set_sensitive(True)
        elif fwd_type == SshMuxClient.MUX_FWD_DYNAMIC:
            self.ch_label.set_sensitive(False)
            self.ch_entry.set_sensitive(False)
            self.cp_label.set_sensitive(False)
            self.cp_entry.set_sensitive(False)

    def toggled_cb(self, source, target):
        target.set_sensitive(not source.get_active())

    def apply_forwarding(self):
        fwd_type = self._to_fwd_type[self.fwd_select.get_active()]
        ba = ''
        if not self.ba_all_check.get_active():
            ba = self.ba_entry.get_text()
        lp = self.lp_entry.get_value_as_int()
        if fwd_type == SshMuxClient.MUX_FWD_REMOTE and self.lp_auto_check.get_active():
            lp = 0
        ch = ''
        cp = 0
        if fwd_type != SshMuxClient.MUX_FWD_DYNAMIC:
            ch = self.ch_entry.get_text()
            cp = self.cp_entry.get_value_as_int()

        if fwd_type == SshMuxClient.MUX_FWD_LOCAL:
            fwd_descr = '-L %s:%u:%s:%u' % (ba, lp, ch, cp,)
        elif fwd_type == SshMuxClient.MUX_FWD_REMOTE:
            fwd_descr = '-R %s:%u:%s:%u' % (ba, lp, ch, cp,)
        else:
            fwd_descr = '-D %s:%u' % (ba, lp,)

        res, remote_port = self.mc.open_forward(fwd_type, ba, lp, ch, cp)
        if res and fwd_type == SshMuxClient.MUX_FWD_REMOTE and lp == 0:
            message = gtk.MessageDialog(
                    parent=None,
                    flags=0,
                    type=gtk.MESSAGE_INFO,
                    buttons=gtk.BUTTONS_OK,
                    message_format=None)
            message.set_markup('Allocated port on the remote side: %d' % (remote_port,))
            message.run()

        return res, fwd_descr

    def response_cb(self, widget, event):
        if event == gtk.RESPONSE_APPLY:
            res, pid = self.mc.check()
            reason = ''
            if res:
                res, fwd_desc = self.apply_forwarding()
                fwd_desc = ' ' + fwd_desc
            else:
                reason = 'Connection already closed.'
            if not res:
                message = gtk.MessageDialog(
                        parent=None,
                        flags=0,
                        type=gtk.MESSAGE_ERROR,
                        buttons=gtk.BUTTONS_OK,
                        message_format=None)
                message.set_markup('Couldn\'t opening forwarding%s for %s' % (fwd_desc, self.mc.name,))
                if reason:
                    message.format_secondary_text(reason)
                message.run()

        self.dialog.destroy()

if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--prefs':
        d = SshMuxPrefsDialog(None)
    else:
        i = SshMuxIndicator()

    try:
        gtk.main()
    except:
        pass
