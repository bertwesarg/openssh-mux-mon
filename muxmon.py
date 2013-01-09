#!/usr/bin/env python

import os
import os.path
import stat
import sys

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
        self._gc_nid = self._gcc.notify_add(GCONF_APP_PATH, self.gconf_notify, None)

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

        self.close_all_item = gtk.MenuItem('Close All')
        menu.append(self.close_all_item)
        self.close_all_item.connect('activate', self.close_all_activate)
        self.close_all_item.show()
        self.close_all_item.set_sensitive(False)

        item = gtk.SeparatorMenuItem()
        menu.append(item)
        item.show()

        item = gtk.MenuItem('Preferences...')
        menu.append(item)
        item.connect('activate', self.preferences_activate)
        item.show()

        item = gtk.MenuItem('Quit')
        menu.append(item)
        item.connect('activate', self.quit_activate)
        item.show()

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

        # there are not the same, clenup previous root, if any
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

        for path in os.listdir(self.root):
            full = os.path.join(self.root, path)
            try:
                sb = os.stat(full)
            except:
                continue

            if not stat.S_ISSOCK(sb.st_mode):
                continue

            mc = SshMuxEntry(full)
            res, exts = mc.connect()
            if res:
                res, name = mc.info('%r@%h:%p')
            if res:
                mc.name = name
                self.known[full] = mc
                #print >>sys.stderr, 'Already existing mux: %s' % (name,)
            self.add_to_menu(mc)

    def add_to_menu(self, mc):
        self.close_all_item.set_sensitive(True)

        menu = self.get_menu()
        mc.item = gtk.MenuItem(mc.name)
        menu.insert(mc.item, len(menu.get_children()) - 5)
        mc.item.connect('activate', self.mux_activate, mc)
        mc.item.show()

        mc.sub = gtk.Menu()

        item = gtk.MenuItem('Forwards:')
        mc.sub.append(item)
        item.set_sensitive(False)
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

        item = gtk.MenuItem('Stop')
        mc.sub.append(item)
        item.connect('activate', self.mux_stop_activate, mc)
        item.show()

        item = gtk.MenuItem('Close')
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

    def mux_activate(self, w, mc):
        # update forwards and sessions
        for i in range(mc.n_fwds):
            mc.sub.remove(mc.sub.get_children()[1])
        for i in range(mc.n_sessions):
            mc.sub.remove(mc.sub.get_children()[3])

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
            if lh == '':
                lh = 'LOCALHOST'
            if ftype == 'local':
                label = '%s:%u -> %s:%u' % (lh, lp, ch, cp,)
            if ftype == 'remote':
                label = '%s:%u <- %s:%u' % (ch, cp, lh, lp,)
            if ftype == 'dynamic':
                label = '%s:%u -> *:*' % (lh, lp,)
            item = gtk.MenuItem(label)
            mc.sub.insert(item, 1 + mc.n_fwds)
            mc.n_fwds += 1
            item.connect('activate', self.mux_close_forward, mc, fwd)
            item.show()

        for s in sessions:
            sid, stype, rid, cid, name, rname = s
            item = gtk.MenuItem('%s' % (rname,))
            mc.sub.insert(item, 3 + mc.n_fwds + mc.n_sessions)
            mc.n_sessions += 1
            item.show()

        mc.item.set_submenu(mc.sub)

    def mux_close_forward(self, w, mc, fwd):
        #print 'closing forward [%s] %s:%u -> %s:%u' % (fwd[1], fwd[2], fwd[3], fwd[4], fwd[5],)
        mc.forward(False, fwd[1], fwd[2], fwd[3], fwd[4], fwd[5])

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
        n.set_timeout(2)
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
            n.set_timeout(1)
            n.show()
            self.add_to_menu(mc)

        return False

    def gconf_notify(self, client, cnxn_id, entry, arg):
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

if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--prefs':
        d = SshMuxPrefsDialog(None)
    else:
        i = SshMuxIndicator()

    try:
        gtk.main()
    except:
        pass
